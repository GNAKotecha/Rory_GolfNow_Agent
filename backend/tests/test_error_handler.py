"""Tests for agent error handling and recovery."""
import pytest
from app.services.error_handler import (
    AgentErrorHandler,
    ErrorType,
    ErrorContext,
    ErrorRecoveryStrategy,
    ErrorRecoveryAction,
    classify_error_from_message,
)


# ==============================================================================
# Error Classification Tests
# ==============================================================================

def test_container_error_classified_as_resource_exhausted():
    """Test 'no such container' is classified as RESOURCE_EXHAUSTED, not TOOL_NOT_FOUND."""
    error_type = classify_error_from_message("No such container: php")
    assert error_type == ErrorType.RESOURCE_EXHAUSTED


def test_docker_daemon_error_classified_as_resource_exhausted():
    """Test Docker daemon errors are classified as RESOURCE_EXHAUSTED."""
    error_type = classify_error_from_message("Cannot connect to Docker daemon at unix:///var/run/docker.sock")
    assert error_type == ErrorType.RESOURCE_EXHAUSTED


def test_container_not_running_classified_as_resource_exhausted():
    """Test 'container not running' errors are classified correctly."""
    error_type = classify_error_from_message("Container brs-teesheet is not running")
    assert error_type == ErrorType.RESOURCE_EXHAUSTED


def test_tool_not_found_on_mcp_server():
    """Test actual tool lookup failures are classified as TOOL_NOT_FOUND."""
    error_type = classify_error_from_message("Tool 'create_club' not found on any MCP server")
    assert error_type == ErrorType.TOOL_NOT_FOUND


def test_http_404_without_container_is_tool_not_found():
    """Test HTTP 404 without container context is TOOL_NOT_FOUND."""
    error_type = classify_error_from_message("HTTP 404: Tool endpoint not found")
    assert error_type == ErrorType.TOOL_NOT_FOUND


def test_connection_refused_is_resource_exhausted():
    """Test connection refused is classified as RESOURCE_EXHAUSTED."""
    error_type = classify_error_from_message("Connection refused to localhost:8056")
    assert error_type == ErrorType.RESOURCE_EXHAUSTED


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

    # Changed from SKIP to ABORT - exhausted retries with no fallback should abort
    assert action.strategy == ErrorRecoveryStrategy.ABORT
    assert action.terminal is True
    assert "failed" in action.reason.lower() or "no fallback" in action.reason.lower()


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

def test_resource_exhausted_asks_user():
    """Test RESOURCE_EXHAUSTED (container/infra failures) triggers ASK_USER with remediation."""
    handler = AgentErrorHandler()

    # Use RESOURCE_EXHAUSTED which should trigger infra remediation
    context = ErrorContext(
        error_type=ErrorType.RESOURCE_EXHAUSTED,
        step_number=1,
        tool_name="create_club",
        error_message="No such container: php",
        retry_count=0,
        metadata={},
    )

    action = handler.decide_recovery(context)

    assert action.strategy == ErrorRecoveryStrategy.ASK_USER
    assert action.terminal is True
    assert "infrastructure" in action.reason.lower()
    assert action.remediation_prompt is not None
    # Should mention container issue in remediation
    assert "container" in action.remediation_prompt.lower()


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
