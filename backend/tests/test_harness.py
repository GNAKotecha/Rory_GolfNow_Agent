"""Tests for runtime harness control system."""
import time
from datetime import datetime, timedelta, timezone

import pytest

from app.services.harness import (
    HarnessConfig,
    HarnessState,
    StopReason,
    check_max_steps,
    check_loop_detected,
    check_no_progress,
    check_timeout,
    should_continue,
    record_action,
    record_progress,
    increment_step,
    get_audit_summary,
    ExecutionContext,
    normalize_tool_call,
    extract_action_signature,
)


# ==============================================================================
# Configuration Tests
# ==============================================================================

def test_harness_config_defaults():
    """Test default harness configuration."""
    config = HarnessConfig()

    assert config.max_steps == 50
    assert config.max_repeat_action == 3
    assert config.no_progress_window == 5
    assert config.timeout_seconds == 300


def test_harness_config_custom():
    """Test custom harness configuration."""
    config = HarnessConfig(
        max_steps=10,
        max_repeat_action=2,
        no_progress_window=3,
        timeout_seconds=60,
    )

    assert config.max_steps == 10
    assert config.max_repeat_action == 2
    assert config.no_progress_window == 3
    assert config.timeout_seconds == 60


# ==============================================================================
# Step Counter Tests
# ==============================================================================

def test_step_increment():
    """Test step counter increments correctly."""
    config = HarnessConfig(max_steps=5)
    state = HarnessState(config)

    assert state.step_count == 0

    for i in range(5):
        increment_step(state)
        assert state.step_count == i + 1


def test_max_steps_detection():
    """Test max steps detection."""
    config = HarnessConfig(max_steps=3)
    state = HarnessState(config)

    # Should not trigger before limit
    assert check_max_steps(state) is None

    # Increment to limit
    state.step_count = 3

    # Should trigger at limit
    reason = check_max_steps(state)
    assert reason == StopReason.MAX_STEPS


# ==============================================================================
# Loop Detection Tests
# ==============================================================================

def test_loop_detection_no_repeat():
    """Test loop detection with varied actions."""
    config = HarnessConfig(max_repeat_action=3)
    state = HarnessState(config)

    record_action(state, "search")
    record_action(state, "analyze")
    record_action(state, "search")

    # Should not detect loop (actions vary)
    reason = check_loop_detected(state)
    assert reason is None


def test_loop_detection_exact_threshold():
    """Test loop detection at exact threshold."""
    config = HarnessConfig(max_repeat_action=3)
    state = HarnessState(config)

    record_action(state, "search")
    record_action(state, "search")
    record_action(state, "search")

    # Should detect loop (3 identical actions)
    reason = check_loop_detected(state)
    assert reason == StopReason.LOOP_DETECTED


def test_loop_detection_broken_sequence():
    """Test loop detection with broken sequence."""
    config = HarnessConfig(max_repeat_action=3)
    state = HarnessState(config)

    record_action(state, "search")
    record_action(state, "search")
    record_action(state, "analyze")  # Different action
    record_action(state, "search")

    # Should not detect loop (sequence broken)
    reason = check_loop_detected(state)
    assert reason is None


def test_loop_detection_after_break():
    """Test loop detection after initial break."""
    config = HarnessConfig(max_repeat_action=3)
    state = HarnessState(config)

    # First sequence
    record_action(state, "search")
    record_action(state, "analyze")

    # New repeating sequence
    record_action(state, "tool_X")
    record_action(state, "tool_X")
    record_action(state, "tool_X")

    # Should detect loop in recent actions
    reason = check_loop_detected(state)
    assert reason == StopReason.LOOP_DETECTED


# ==============================================================================
# No Progress Detection Tests
# ==============================================================================

def test_no_progress_detection_with_progress():
    """Test no-progress detection with actual progress."""
    config = HarnessConfig(no_progress_window=5)
    state = HarnessState(config)

    for i in range(5):
        record_progress(state, f"state_{i}")

    # Should not trigger (progress is changing)
    reason = check_no_progress(state)
    assert reason is None


def test_no_progress_detection_stuck():
    """Test no-progress detection when stuck."""
    config = HarnessConfig(no_progress_window=5)
    state = HarnessState(config)

    for i in range(5):
        record_progress(state, "stuck_state")

    # Should trigger (no progress)
    reason = check_no_progress(state)
    assert reason == StopReason.NO_PROGRESS


def test_no_progress_detection_recovery():
    """Test no-progress detection after recovery."""
    config = HarnessConfig(no_progress_window=3)
    state = HarnessState(config)

    # Stuck for a while
    record_progress(state, "stuck")
    record_progress(state, "stuck")

    # Then progress
    record_progress(state, "progress_1")
    record_progress(state, "progress_2")
    record_progress(state, "progress_3")

    # Should not trigger (recent window shows progress)
    reason = check_no_progress(state)
    assert reason is None


# ==============================================================================
# Timeout Detection Tests
# ==============================================================================

def test_timeout_detection_not_exceeded():
    """Test timeout detection before limit."""
    config = HarnessConfig(timeout_seconds=10)
    state = HarnessState(config)

    # Should not trigger immediately
    reason = check_timeout(state)
    assert reason is None


def test_timeout_detection_exceeded():
    """Test timeout detection after limit."""
    config = HarnessConfig(timeout_seconds=1)
    state = HarnessState(config)

    # Simulate time passing
    state.start_time = datetime.now(timezone.utc) - timedelta(seconds=2)

    # Should trigger
    reason = check_timeout(state)
    assert reason == StopReason.TIMEOUT


# ==============================================================================
# Combined Control Tests
# ==============================================================================

def test_should_continue_all_clear():
    """Test should_continue with all checks passing."""
    config = HarnessConfig(
        max_steps=10,
        max_repeat_action=3,
        no_progress_window=5,
        timeout_seconds=60,
    )
    state = HarnessState(config)

    state.step_count = 5
    record_action(state, "action_1")
    record_action(state, "action_2")
    record_progress(state, "progress_1")

    should_cont, reason = should_continue(state)

    assert should_cont is True
    assert reason is None


def test_should_continue_max_steps():
    """Test should_continue stops at max steps."""
    config = HarnessConfig(max_steps=3)
    state = HarnessState(config)
    state.step_count = 3

    should_cont, reason = should_continue(state)

    assert should_cont is False
    assert reason == StopReason.MAX_STEPS


def test_should_continue_loop_detected():
    """Test should_continue stops on loop."""
    config = HarnessConfig(max_repeat_action=3)
    state = HarnessState(config)

    record_action(state, "repeat")
    record_action(state, "repeat")
    record_action(state, "repeat")

    should_cont, reason = should_continue(state)

    assert should_cont is False
    assert reason == StopReason.LOOP_DETECTED


def test_should_continue_no_progress():
    """Test should_continue stops on no progress."""
    config = HarnessConfig(no_progress_window=3)
    state = HarnessState(config)

    record_progress(state, "stuck")
    record_progress(state, "stuck")
    record_progress(state, "stuck")

    should_cont, reason = should_continue(state)

    assert should_cont is False
    assert reason == StopReason.NO_PROGRESS


# ==============================================================================
# Audit Logging Tests
# ==============================================================================

def test_audit_log_records_events():
    """Test audit log records events."""
    config = HarnessConfig()
    state = HarnessState(config)

    increment_step(state)
    record_action(state, "test_action")
    record_progress(state, "test_marker")

    assert len(state.audit_log) == 3
    assert state.audit_log[0]["event"] == "step_incremented"
    assert state.audit_log[1]["event"] == "action_recorded"
    assert state.audit_log[2]["event"] == "progress_recorded"


def test_audit_summary():
    """Test audit summary generation."""
    config = HarnessConfig()
    state = HarnessState(config)

    increment_step(state)
    increment_step(state)
    record_action(state, "action_1")
    record_action(state, "action_2")
    record_progress(state, "progress_1")

    summary = get_audit_summary(state)

    assert summary["total_steps"] == 2
    assert summary["total_actions"] == 2
    assert summary["audit_events"] == 5
    assert "action_1" in summary["action_sequence"]
    assert "progress_1" in summary["progress_sequence"]


# ==============================================================================
# Execution Context Tests
# ==============================================================================

def test_execution_context():
    """Test execution context manager."""
    config = HarnessConfig(max_steps=5)

    with ExecutionContext(config) as state:
        assert state.step_count == 0
        assert len(state.audit_log) > 0
        assert state.audit_log[0]["event"] == "execution_started"

        increment_step(state)
        assert state.step_count == 1

    # Context should log execution_ended
    assert state.audit_log[-1]["event"] == "execution_ended"


# ==============================================================================
# Tool Call Normalization Tests
# ==============================================================================

def test_normalize_tool_call():
    """Test tool call normalization."""
    sig = normalize_tool_call("search", {"query": "test", "limit": 10})

    assert "search" in sig
    assert "query=test" in sig
    assert "limit=10" in sig


def test_normalize_tool_call_ordering():
    """Test tool call normalization is order-independent."""
    sig1 = normalize_tool_call("tool", {"a": 1, "b": 2})
    sig2 = normalize_tool_call("tool", {"b": 2, "a": 1})

    assert sig1 == sig2


def test_extract_action_signature():
    """Test action signature extraction."""
    tool_call = {
        "name": "search",
        "arguments": {
            "query": "test",
            "limit": 10,
            "timestamp": "2024-01-01",  # Should be filtered
        }
    }

    sig = extract_action_signature(tool_call)

    assert "search" in sig
    assert "query=test" in sig
    assert "limit=10" in sig
    assert "timestamp" not in sig  # Filtered out


def test_extract_action_signature_filters_noise():
    """Test action signature filters non-deterministic fields."""
    tool_call = {
        "name": "api_call",
        "arguments": {
            "endpoint": "/users",
            "request_id": "abc123",  # Should be filtered
            "session_id": "xyz789",  # Should be filtered
        }
    }

    sig = extract_action_signature(tool_call)

    assert "api_call" in sig
    assert "endpoint=/users" in sig
    assert "request_id" not in sig
    assert "session_id" not in sig
