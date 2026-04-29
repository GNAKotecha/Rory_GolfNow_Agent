"""Tests for agent error handling and recovery."""
import pytest
from app.services.error_handler import (
    AgentErrorHandler,
    ErrorType,
    ErrorContext,
    ErrorRecoveryStrategy,
    ErrorRecoveryAction,
)


# ==============================================================================
# Error Handler Initialization Tests
# ==============================================================================

def test_error_handler_default_retries():
    """Test error handler initializes with default retries."""
    handler = AgentErrorHandler()
    assert handler.max_retries == 3


def test_error_handler_custom_retries():
    """Test error handler with custom max retries."""
    handler = AgentErrorHandler(max_retries=5)
    assert handler.max_retries == 5


# ==============================================================================
# Tool Failure Recovery Tests
# ==============================================================================

def test_tool_failure_first_retry():
    """Test tool failure triggers retry on first attempt."""
    handler = AgentErrorHandler(max_retries=3)

    context = ErrorContext(
        error_type=ErrorType.TOOL_FAILURE,
        step_number=1,
        tool_name="search",
        error_message="Connection timeout",
        retry_count=0,
        metadata={},
    )

    action = handler.decide_recovery(context)

    assert action.strategy == ErrorRecoveryStrategy.RETRY
    assert action.retry_delay_seconds == 1.0  # 2^0
    assert "retry" in action.reason.lower()


def test_tool_failure_exponential_backoff():
    """Test exponential backoff for tool failure retries."""
    handler = AgentErrorHandler(max_retries=3)

    # Test backoff progression
    for retry_count, expected_delay in [(0, 1.0), (1, 2.0), (2, 4.0)]:
        context = ErrorContext(
            error_type=ErrorType.TOOL_FAILURE,
            step_number=1,
            tool_name="search",
            error_message="Error",
            retry_count=retry_count,
            metadata={},
        )

        action = handler.decide_recovery(context)
        assert action.strategy == ErrorRecoveryStrategy.RETRY
        assert action.retry_delay_seconds == expected_delay


def test_tool_failure_max_retries_no_fallback():
    """Test tool failure after max retries without fallback."""
    handler = AgentErrorHandler(max_retries=3)

    context = ErrorContext(
        error_type=ErrorType.TOOL_FAILURE,
        step_number=1,
        tool_name="unknown_tool",  # No fallback defined
        error_message="Still failing",
        retry_count=3,  # At max
        metadata={},
    )

    action = handler.decide_recovery(context)

    assert action.strategy == ErrorRecoveryStrategy.SKIP
    assert "no fallback" in action.reason.lower()


# ==============================================================================
# Malformed Output Recovery Tests
# ==============================================================================

def test_malformed_output_first_retry():
    """Test malformed output triggers retry."""
    handler = AgentErrorHandler()

    context = ErrorContext(
        error_type=ErrorType.MALFORMED_OUTPUT,
        step_number=2,
        tool_name=None,
        error_message="Invalid JSON",
        retry_count=0,
        metadata={},
    )

    action = handler.decide_recovery(context)

    assert action.strategy == ErrorRecoveryStrategy.RETRY
    assert "malformed" in action.reason.lower()


def test_malformed_output_second_retry():
    """Test malformed output allows second retry."""
    handler = AgentErrorHandler()

    context = ErrorContext(
        error_type=ErrorType.MALFORMED_OUTPUT,
        step_number=2,
        tool_name=None,
        error_message="Still invalid",
        retry_count=1,
        metadata={},
    )

    action = handler.decide_recovery(context)

    assert action.strategy == ErrorRecoveryStrategy.RETRY


def test_malformed_output_abort_after_retries():
    """Test malformed output aborts after retries."""
    handler = AgentErrorHandler()

    context = ErrorContext(
        error_type=ErrorType.MALFORMED_OUTPUT,
        step_number=2,
        tool_name=None,
        error_message="Persistent format error",
        retry_count=2,  # Third attempt
        metadata={},
    )

    action = handler.decide_recovery(context)

    assert action.strategy == ErrorRecoveryStrategy.ABORT
    assert "persistent" in action.reason.lower()


# ==============================================================================
# Loop Detection Recovery Tests
# ==============================================================================

def test_loop_detected_abort():
    """Test loop detection triggers immediate abort."""
    handler = AgentErrorHandler()

    context = ErrorContext(
        error_type=ErrorType.LOOP_DETECTED,
        step_number=5,
        tool_name="search",
        error_message="Repeating same action",
        retry_count=0,
        metadata={},
    )

    action = handler.decide_recovery(context)

    assert action.strategy == ErrorRecoveryStrategy.ABORT
    assert "loop" in action.reason.lower()


# ==============================================================================
# Low Confidence Recovery Tests
# ==============================================================================

def test_low_confidence_ask_user():
    """Test low confidence triggers user guidance request."""
    handler = AgentErrorHandler()

    context = ErrorContext(
        error_type=ErrorType.LOW_CONFIDENCE,
        step_number=3,
        tool_name=None,
        error_message="Unsure about next action",
        retry_count=0,
        metadata={"confidence": 0.3},
    )

    action = handler.decide_recovery(context)

    assert action.strategy == ErrorRecoveryStrategy.ASK_USER
    assert "low confidence" in action.reason.lower()


# ==============================================================================
# Timeout Recovery Tests
# ==============================================================================

def test_timeout_abort():
    """Test timeout triggers abort."""
    handler = AgentErrorHandler()

    context = ErrorContext(
        error_type=ErrorType.TIMEOUT,
        step_number=10,
        tool_name=None,
        error_message="Execution timeout exceeded",
        retry_count=0,
        metadata={},
    )

    action = handler.decide_recovery(context)

    assert action.strategy == ErrorRecoveryStrategy.ABORT
    assert "timeout" in action.reason.lower()


# ==============================================================================
# Rate Limit Recovery Tests
# ==============================================================================

def test_rate_limit_retry_with_delay():
    """Test rate limit triggers retry with long delay."""
    handler = AgentErrorHandler()

    context = ErrorContext(
        error_type=ErrorType.RATE_LIMIT,
        step_number=2,
        tool_name="api_call",
        error_message="Rate limit exceeded",
        retry_count=0,
        metadata={},
    )

    action = handler.decide_recovery(context)

    assert action.strategy == ErrorRecoveryStrategy.RETRY
    assert action.retry_delay_seconds == 60.0
    assert "rate limit" in action.reason.lower()


# ==============================================================================
# Unknown Error Type Tests
# ==============================================================================

def test_unknown_error_type_abort():
    """Test unknown error type triggers abort."""
    handler = AgentErrorHandler()

    # Use RESOURCE_EXHAUSTED which should trigger default case
    context = ErrorContext(
        error_type=ErrorType.RESOURCE_EXHAUSTED,
        step_number=1,
        tool_name=None,
        error_message="Unknown error",
        retry_count=0,
        metadata={},
    )

    action = handler.decide_recovery(context)

    assert action.strategy == ErrorRecoveryStrategy.ABORT
    assert "unhandled" in action.reason.lower()


# ==============================================================================
# Confidence Parsing Tests
# ==============================================================================

def test_parse_confidence_certain():
    """Test parsing high confidence keyword."""
    handler = AgentErrorHandler()

    response = "I am certain that this is the correct approach."
    confidence = handler.parse_confidence(response)

    assert confidence == 0.9


def test_parse_confidence_confident():
    """Test parsing confident keyword."""
    handler = AgentErrorHandler()

    response = "I'm confident this will work."
    confidence = handler.parse_confidence(response)

    assert confidence == 0.8


def test_parse_confidence_likely():
    """Test parsing likely keyword."""
    handler = AgentErrorHandler()

    response = "This is likely the right solution."
    confidence = handler.parse_confidence(response)

    assert confidence == 0.7


def test_parse_confidence_probably():
    """Test parsing probably keyword."""
    handler = AgentErrorHandler()

    response = "This will probably work."
    confidence = handler.parse_confidence(response)

    assert confidence == 0.6


def test_parse_confidence_maybe():
    """Test parsing maybe keyword."""
    handler = AgentErrorHandler()

    response = "Maybe this is correct."
    confidence = handler.parse_confidence(response)

    assert confidence == 0.5


def test_parse_confidence_unsure():
    """Test parsing unsure keyword."""
    handler = AgentErrorHandler()

    response = "I'm unsure about this approach."
    confidence = handler.parse_confidence(response)

    assert confidence == 0.4


def test_parse_confidence_uncertain():
    """Test parsing uncertain keyword."""
    handler = AgentErrorHandler()

    # "uncertain" contains "certain" as substring
    # After fix: keywords are ordered to check "uncertain" before "certain"
    response = "I'm uncertain, not certain, about this."
    confidence = handler.parse_confidence(response)

    # Should now consistently match "uncertain" (0.3)
    assert confidence == 0.3


def test_parse_confidence_guess():
    """Test parsing guess keyword."""
    handler = AgentErrorHandler()

    response = "I would guess this might work."
    confidence = handler.parse_confidence(response)

    assert confidence == 0.2


def test_parse_confidence_default():
    """Test default confidence when no keywords found."""
    handler = AgentErrorHandler()

    response = "Here is the result without any confidence indicator."
    confidence = handler.parse_confidence(response)

    assert confidence == 0.7  # Default medium confidence


def test_parse_confidence_case_insensitive():
    """Test confidence parsing is case insensitive."""
    handler = AgentErrorHandler()

    response = "I am CERTAIN this works."
    confidence = handler.parse_confidence(response)

    assert confidence == 0.9


def test_parse_confidence_first_match():
    """Test confidence parsing returns first matching keyword."""
    handler = AgentErrorHandler()

    # "certain" appears first and has highest confidence
    response = "I am certain, though maybe there are edge cases."
    confidence = handler.parse_confidence(response)

    assert confidence == 0.9  # "certain" matched first


# ==============================================================================
# Fallback Tool Tests
# ==============================================================================

def test_find_fallback_tool_no_mapping():
    """Test fallback tool returns None when no mapping exists."""
    handler = AgentErrorHandler()

    fallback = handler._find_fallback_tool("unknown_tool")

    assert fallback is None


def test_find_fallback_tool_none_input():
    """Test fallback tool handles None input."""
    handler = AgentErrorHandler()

    fallback = handler._find_fallback_tool(None)

    assert fallback is None
