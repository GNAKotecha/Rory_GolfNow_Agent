"""Unit tests for hardened error handling.

Tests for:
- TOOL_FAILURE exhausted/no fallback => terminal action (ABORT)
- 401/403 classified as non-retryable (AUTH_FAILURE)
- Skipped/failed actions are recorded and affect dedupe checks
- Error classification from HTTP status codes and messages
"""
import pytest
from datetime import datetime, timezone

from app.services.error_handler import (
    ErrorType,
    ErrorContext,
    ErrorRecoveryStrategy,
    ErrorRecoveryAction,
    AgentErrorHandler,
    ToolCallTelemetry,
    is_error_retryable,
    classify_error_from_http_status,
    classify_error_from_message,
    NON_RETRYABLE_ERRORS,
)
from app.services.agent_state import (
    AgentState,
    ActionOutcome,
    ActionRecord,
    LOOP_DETECTION_OUTCOMES,
)


class TestErrorClassification:
    """Tests for error classification from HTTP status codes and messages."""
    
    def test_401_classified_as_auth_failure(self):
        """401 Unauthorized should be classified as AUTH_FAILURE."""
        error_type = classify_error_from_http_status(401)
        assert error_type == ErrorType.AUTH_FAILURE
    
    def test_403_classified_as_auth_failure(self):
        """403 Forbidden should be classified as AUTH_FAILURE."""
        error_type = classify_error_from_http_status(403)
        assert error_type == ErrorType.AUTH_FAILURE
    
    def test_400_classified_as_validation_error(self):
        """400 Bad Request should be classified as VALIDATION_ERROR."""
        error_type = classify_error_from_http_status(400)
        assert error_type == ErrorType.VALIDATION_ERROR
    
    def test_422_classified_as_validation_error(self):
        """422 Unprocessable Entity should be classified as VALIDATION_ERROR."""
        error_type = classify_error_from_http_status(422)
        assert error_type == ErrorType.VALIDATION_ERROR
    
    def test_404_classified_as_tool_not_found(self):
        """404 Not Found should be classified as TOOL_NOT_FOUND."""
        error_type = classify_error_from_http_status(404)
        assert error_type == ErrorType.TOOL_NOT_FOUND
    
    def test_429_classified_as_rate_limit(self):
        """429 Too Many Requests should be classified as RATE_LIMIT."""
        error_type = classify_error_from_http_status(429)
        assert error_type == ErrorType.RATE_LIMIT
    
    def test_500_classified_as_tool_failure(self):
        """500 Internal Server Error should be classified as TOOL_FAILURE (retryable)."""
        error_type = classify_error_from_http_status(500)
        assert error_type == ErrorType.TOOL_FAILURE
    
    def test_504_classified_as_timeout(self):
        """504 Gateway Timeout should be classified as TIMEOUT."""
        error_type = classify_error_from_http_status(504)
        assert error_type == ErrorType.TIMEOUT
    
    def test_unknown_status_classified_as_tool_failure(self):
        """Unknown status codes should default to TOOL_FAILURE."""
        error_type = classify_error_from_http_status(599)
        assert error_type == ErrorType.TOOL_FAILURE
    
    def test_message_with_unauthorized_classified_as_auth_failure(self):
        """Error message containing 'unauthorized' should be AUTH_FAILURE."""
        error_type = classify_error_from_message("Unauthorized access to resource")
        assert error_type == ErrorType.AUTH_FAILURE
    
    def test_message_with_validation_classified_as_validation_error(self):
        """Error message containing 'validation' should be VALIDATION_ERROR."""
        error_type = classify_error_from_message("Validation failed: missing required field")
        assert error_type == ErrorType.VALIDATION_ERROR
    
    def test_message_with_not_found_classified_as_tool_not_found(self):
        """Error message containing 'not found' should be TOOL_NOT_FOUND."""
        error_type = classify_error_from_message("Tool 'foo' not found")
        assert error_type == ErrorType.TOOL_NOT_FOUND
    
    def test_http_status_takes_precedence_over_message(self):
        """HTTP status should take precedence over error message for classification."""
        # Message says "unauthorized" but status is 500
        error_type = classify_error_from_message("unauthorized error", http_status=500)
        assert error_type == ErrorType.TOOL_FAILURE  # 500 wins


class TestErrorRetryability:
    """Tests for error retryability classification."""
    
    def test_auth_failure_not_retryable(self):
        """AUTH_FAILURE should not be retryable."""
        assert not is_error_retryable(ErrorType.AUTH_FAILURE)
    
    def test_validation_error_not_retryable(self):
        """VALIDATION_ERROR should not be retryable."""
        assert not is_error_retryable(ErrorType.VALIDATION_ERROR)
    
    def test_tool_not_found_not_retryable(self):
        """TOOL_NOT_FOUND should not be retryable."""
        assert not is_error_retryable(ErrorType.TOOL_NOT_FOUND)
    
    def test_contract_error_not_retryable(self):
        """CONTRACT_ERROR should not be retryable."""
        assert not is_error_retryable(ErrorType.CONTRACT_ERROR)
    
    def test_loop_detected_not_retryable(self):
        """LOOP_DETECTED should not be retryable."""
        assert not is_error_retryable(ErrorType.LOOP_DETECTED)
    
    def test_tool_failure_is_retryable(self):
        """TOOL_FAILURE should be retryable."""
        assert is_error_retryable(ErrorType.TOOL_FAILURE)
    
    def test_timeout_is_retryable(self):
        """TIMEOUT should be retryable (implicit, as it's not in non-retryable set)."""
        # Note: TIMEOUT leads to ABORT in decide_recovery, but the error type itself is retryable
        assert is_error_retryable(ErrorType.TIMEOUT)
    
    def test_rate_limit_is_retryable(self):
        """RATE_LIMIT should be retryable."""
        assert is_error_retryable(ErrorType.RATE_LIMIT)


class TestErrorRecoveryDecisions:
    """Tests for error recovery decision making."""
    
    def test_exhausted_retries_no_fallback_aborts_in_strict_mode(self):
        """TOOL_FAILURE with exhausted retries and no fallback should ABORT in strict mode."""
        handler = AgentErrorHandler(max_retries=3, strict_terminal=True)
        
        context = ErrorContext(
            error_type=ErrorType.TOOL_FAILURE,
            step_number=1,
            tool_name="test_tool",
            error_message="Connection failed",
            retry_count=3,  # Max retries reached
            metadata={},
            attempt_budget=3,
        )
        
        action = handler.decide_recovery(context)
        
        assert action.strategy == ErrorRecoveryStrategy.ABORT
        assert action.terminal is True
        assert "failed after" in action.reason.lower() or "no fallback" in action.reason.lower()
    
    def test_exhausted_retries_no_fallback_asks_user_in_non_strict_mode(self):
        """TOOL_FAILURE with exhausted retries should ASK_USER in non-strict mode."""
        handler = AgentErrorHandler(max_retries=3, strict_terminal=False)
        
        context = ErrorContext(
            error_type=ErrorType.TOOL_FAILURE,
            step_number=1,
            tool_name="test_tool",
            error_message="Connection failed",
            retry_count=3,
            metadata={},
            attempt_budget=3,
        )
        
        action = handler.decide_recovery(context)
        
        assert action.strategy == ErrorRecoveryStrategy.ASK_USER
        assert action.remediation_prompt is not None
    
    def test_auth_failure_asks_user_immediately(self):
        """AUTH_FAILURE should immediately ASK_USER without retrying."""
        handler = AgentErrorHandler(max_retries=3)
        
        context = ErrorContext(
            error_type=ErrorType.AUTH_FAILURE,
            step_number=1,
            tool_name="test_tool",
            error_message="401 Unauthorized",
            retry_count=0,  # First attempt
            metadata={},
            http_status=401,
        )
        
        action = handler.decide_recovery(context)
        
        assert action.strategy == ErrorRecoveryStrategy.ASK_USER
        assert action.terminal is True
        assert action.remediation_prompt is not None
        assert "credential" in action.remediation_prompt.lower() or "auth" in action.remediation_prompt.lower()
    
    def test_validation_error_asks_user_immediately(self):
        """VALIDATION_ERROR should ASK_USER immediately without retrying."""
        handler = AgentErrorHandler(max_retries=3)
        
        context = ErrorContext(
            error_type=ErrorType.VALIDATION_ERROR,
            step_number=1,
            tool_name="test_tool",
            error_message="Invalid parameter: foo must be an integer",
            retry_count=0,
            metadata={},
            http_status=400,
        )
        
        action = handler.decide_recovery(context)
        
        assert action.strategy == ErrorRecoveryStrategy.ASK_USER
        assert action.terminal is True
        assert action.remediation_prompt is not None
    
    def test_tool_not_found_aborts_immediately(self):
        """TOOL_NOT_FOUND should ABORT immediately."""
        handler = AgentErrorHandler(max_retries=3)
        
        context = ErrorContext(
            error_type=ErrorType.TOOL_NOT_FOUND,
            step_number=1,
            tool_name="nonexistent_tool",
            error_message="Tool not found",
            retry_count=0,
            metadata={},
            http_status=404,
        )
        
        action = handler.decide_recovery(context)
        
        assert action.strategy == ErrorRecoveryStrategy.ABORT
        assert action.terminal is True

    def test_validation_prompt_includes_field_hint_when_present(self):
        """Validation remediation should include field-level hint when parsable."""
        handler = AgentErrorHandler(max_retries=3)

        context = ErrorContext(
            error_type=ErrorType.VALIDATION_ERROR,
            step_number=1,
            tool_name="create_club",
            error_message="Error: Invalid input at 'name': String should have at least 1 character",
            retry_count=0,
            metadata={"tool_args": {"name": "", "country": "GB"}},
            http_status=400,
        )

        action = handler.decide_recovery(context)

        assert action.strategy == ErrorRecoveryStrategy.ASK_USER
        assert action.remediation_prompt is not None
        assert "name" in action.remediation_prompt.lower()
        assert "create_club" in action.remediation_prompt
    
    def test_tool_failure_retries_with_budget(self):
        """TOOL_FAILURE should RETRY when retry budget remains."""
        handler = AgentErrorHandler(max_retries=3)
        
        context = ErrorContext(
            error_type=ErrorType.TOOL_FAILURE,
            step_number=1,
            tool_name="test_tool",
            error_message="Connection timeout",
            retry_count=1,  # Still have retries left
            metadata={},
            attempt_budget=3,
        )
        
        action = handler.decide_recovery(context)
        
        assert action.strategy == ErrorRecoveryStrategy.RETRY
        assert action.retry_delay_seconds is not None
        assert action.retry_delay_seconds > 0
    
    def test_skip_strategy_not_used_for_tool_failure(self):
        """SKIP strategy should never be returned for TOOL_FAILURE."""
        handler = AgentErrorHandler(max_retries=3, strict_terminal=True)
        
        # Test various retry counts
        for retry_count in range(0, 5):
            context = ErrorContext(
                error_type=ErrorType.TOOL_FAILURE,
                step_number=1,
                tool_name="test_tool",
                error_message="Some error",
                retry_count=retry_count,
                metadata={},
                attempt_budget=3,
            )
            
            action = handler.decide_recovery(context)
            
            # Should be RETRY, FALLBACK, ABORT, or ASK_USER - never SKIP
            assert action.strategy != ErrorRecoveryStrategy.SKIP, \
                f"SKIP returned for retry_count={retry_count}"


class TestAgentState:
    """Tests for agent state tracking."""
    
    def test_failed_actions_recorded_in_state(self):
        """Failed actions should be recorded in state history."""
        state = AgentState(session_id=1, current_step=0)
        
        state.record_action(
            action_type="tool_call",
            action_data={"name": "test_tool", "args": {}},
            result="Error message",
            success=False,
            outcome=ActionOutcome.RETRYABLE_FAILURE,
            error_type="tool_failure",
        )
        
        assert len(state.completed_actions) == 1
        assert state.completed_actions[0].outcome == ActionOutcome.RETRYABLE_FAILURE
        assert state.completed_actions[0].error_type == "tool_failure"
    
    def test_skipped_actions_recorded_in_state(self):
        """Skipped actions should be recorded in state history."""
        state = AgentState(session_id=1, current_step=0)
        
        state.record_action(
            action_type="tool_call",
            action_data={"name": "test_tool", "args": {}},
            result="Circuit breaker open",
            success=False,
            outcome=ActionOutcome.SKIPPED,
            error_type="circuit_breaker",
        )
        
        assert len(state.completed_actions) == 1
        assert state.completed_actions[0].outcome == ActionOutcome.SKIPPED
    
    def test_terminal_failure_detected(self):
        """Terminal failures should be detectable for future calls."""
        state = AgentState(session_id=1, current_step=0)
        action_data = {"name": "test_tool", "args": {"x": 1}}
        
        # Record a non-retryable failure
        state.record_action(
            action_type="tool_call",
            action_data=action_data,
            result="401 Unauthorized",
            success=False,
            outcome=ActionOutcome.NON_RETRYABLE_FAILURE,
            error_type="auth_failure",
            http_status=401,
        )
        
        # Should detect that this action failed terminally
        assert state.has_action_failed_terminally("tool_call", action_data)
    
    def test_successful_completion_detected(self):
        """Successfully completed actions should be detectable."""
        state = AgentState(session_id=1, current_step=0)
        action_data = {"name": "test_tool", "args": {"x": 1}}
        
        state.record_action(
            action_type="tool_call",
            action_data=action_data,
            result={"success": True},
            success=True,
            outcome=ActionOutcome.SUCCESS,
        )
        
        assert state.has_action_been_completed("tool_call", action_data)
    
    def test_retryable_failure_not_completed(self):
        """Retryable failures should not count as completed."""
        state = AgentState(session_id=1, current_step=0)
        action_data = {"name": "test_tool", "args": {"x": 1}}
        
        state.record_action(
            action_type="tool_call",
            action_data=action_data,
            result="Connection timeout",
            success=False,
            outcome=ActionOutcome.RETRYABLE_FAILURE,
        )
        
        # Should not be considered "completed" (allow retry)
        assert not state.has_action_been_completed("tool_call", action_data)
    
    def test_loop_detection_includes_failures(self):
        """Loop detection should consider failed actions."""
        state = AgentState(session_id=1, current_step=0)
        
        # Create a pattern of failed actions that repeats
        for _ in range(2):
            for i in range(3):
                state.record_action(
                    action_type="tool_call",
                    action_data={"name": f"tool_{i}", "args": {}},
                    result="Error",
                    success=False,
                    outcome=ActionOutcome.RETRYABLE_FAILURE,
                )
        
        # Should detect the loop
        assert state.detect_loop(window_size=3)
    
    def test_tool_failure_loop_detection(self):
        """Consecutive failures of same tool should be detected."""
        state = AgentState(session_id=1, current_step=0)
        
        # Record 3 consecutive failures for same tool
        for _ in range(3):
            state.record_action(
                action_type="tool_call",
                action_data={"name": "failing_tool", "args": {}},
                result="Error",
                success=False,
                outcome=ActionOutcome.RETRYABLE_FAILURE,
            )
        
        assert state.detect_tool_failure_loop("failing_tool", threshold=3)
        assert not state.detect_tool_failure_loop("other_tool", threshold=3)
    
    def test_attempt_count_tracking(self):
        """Attempt count should be tracked per action."""
        state = AgentState(session_id=1, current_step=0)
        action_data = {"name": "test_tool", "args": {}}
        
        # Record 3 attempts
        for i in range(3):
            state.record_action(
                action_type="tool_call",
                action_data=action_data,
                result="Error",
                success=False,
                outcome=ActionOutcome.RETRYABLE_FAILURE,
            )
        
        assert state.get_attempt_count("tool_call", action_data) == 3
    
    def test_global_budget_exhaustion(self):
        """Global attempt budget should be tracked."""
        state = AgentState(session_id=1, current_step=0)
        state._max_total_attempts = 5  # Set low for testing
        
        for i in range(5):
            state.record_action(
                action_type="tool_call",
                action_data={"name": f"tool_{i}", "args": {}},
                result="Result",
                success=True,
                outcome=ActionOutcome.SUCCESS,
            )
        
        assert state.is_budget_exhausted()
    
    def test_action_history_summary(self):
        """Action history summary should include all outcome types."""
        state = AgentState(session_id=1, current_step=0)
        
        state.record_action("tool_call", {"name": "t1"}, "ok", True, ActionOutcome.SUCCESS)
        state.record_action("tool_call", {"name": "t2"}, "err", False, ActionOutcome.RETRYABLE_FAILURE)
        state.record_action("tool_call", {"name": "t3"}, "err", False, ActionOutcome.NON_RETRYABLE_FAILURE)
        
        summary = state.get_action_history_summary()
        
        assert summary["total_actions"] == 3
        assert summary["outcomes"]["success"] == 1
        assert summary["outcomes"]["retryable_failure"] == 1
        assert summary["outcomes"]["non_retryable_failure"] == 1


class TestToolCallTelemetry:
    """Tests for telemetry data structure."""
    
    def test_telemetry_to_dict(self):
        """Telemetry should serialize to dict correctly."""
        telemetry = ToolCallTelemetry(
            tool_name="test_tool",
            error_type="auth_failure",
            http_status=401,
            retryable=False,
            attempt_index=0,
            attempt_budget=3,
            recovery_strategy="ask_user",
            terminal=True,
            duration_ms=150,
        )
        
        data = telemetry.to_dict()
        
        assert data["tool_name"] == "test_tool"
        assert data["error_type"] == "auth_failure"
        assert data["http_status"] == 401
        assert data["retryable"] is False
        assert data["attempt_index"] == 0
        assert data["attempt_budget"] == 3
        assert data["recovery_strategy"] == "ask_user"
        assert data["terminal"] is True
        assert data["duration_ms"] == 150
