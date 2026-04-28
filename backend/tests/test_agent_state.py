"""Tests for agent state management."""
import pytest
from datetime import datetime, timezone
from app.services.agent_state import AgentState, ActionRecord


# ==============================================================================
# ActionRecord Tests
# ==============================================================================

def test_action_record_creation():
    """Test creating an action record."""
    timestamp = datetime.now(timezone.utc)
    record = ActionRecord(
        action_type="tool_call",
        action_key="abc123",
        timestamp=timestamp,
        result={"status": "success"},
        success=True,
    )

    assert record.action_type == "tool_call"
    assert record.action_key == "abc123"
    assert record.timestamp == timestamp
    assert record.result == {"status": "success"}
    assert record.success is True


# ==============================================================================
# AgentState Initialization Tests
# ==============================================================================

def test_agent_state_initialization():
    """Test agent state initialization."""
    state = AgentState(session_id=1, current_step=0)

    assert state.session_id == 1
    assert state.current_step == 0
    assert len(state.completed_actions) == 0
    assert len(state.action_keys_seen) == 0
    assert len(state.plan_steps) == 0
    assert len(state.plan_completed) == 0


def test_agent_state_with_initial_step():
    """Test agent state with non-zero initial step."""
    state = AgentState(session_id=5, current_step=3)

    assert state.session_id == 5
    assert state.current_step == 3


# ==============================================================================
# Action Deduplication Tests
# ==============================================================================

def test_has_action_been_completed_false():
    """Test action deduplication returns false for new action."""
    state = AgentState(session_id=1, current_step=0)

    has_completed = state.has_action_been_completed(
        action_type="tool_call",
        action_data={"tool": "search", "query": "test"}
    )

    assert has_completed is False


def test_has_action_been_completed_true():
    """Test action deduplication returns true for completed action."""
    state = AgentState(session_id=1, current_step=0)

    # Record an action
    state.record_action(
        action_type="tool_call",
        action_data={"tool": "search", "query": "test"},
        result="found 5 items",
        success=True,
    )

    # Check if same action is completed
    has_completed = state.has_action_been_completed(
        action_type="tool_call",
        action_data={"tool": "search", "query": "test"}
    )

    assert has_completed is True


def test_action_key_order_independence():
    """Test action keys are same regardless of dict key order."""
    state = AgentState(session_id=1, current_step=0)

    # Record action with keys in one order
    state.record_action(
        action_type="tool_call",
        action_data={"a": 1, "b": 2, "c": 3},
        result="result",
        success=True,
    )

    # Check with keys in different order
    has_completed = state.has_action_been_completed(
        action_type="tool_call",
        action_data={"c": 3, "a": 1, "b": 2}
    )

    assert has_completed is True


def test_different_actions_not_duplicates():
    """Test different actions are not considered duplicates."""
    state = AgentState(session_id=1, current_step=0)

    # Record first action
    state.record_action(
        action_type="tool_call",
        action_data={"tool": "search", "query": "test1"},
        result="result1",
        success=True,
    )

    # Check different action
    has_completed = state.has_action_been_completed(
        action_type="tool_call",
        action_data={"tool": "search", "query": "test2"}
    )

    assert has_completed is False


# ==============================================================================
# Action Recording Tests
# ==============================================================================

def test_record_action():
    """Test recording an action."""
    state = AgentState(session_id=1, current_step=0)

    state.record_action(
        action_type="tool_call",
        action_data={"tool": "analyze", "data": [1, 2, 3]},
        result={"summary": "analysis complete"},
        success=True,
    )

    assert len(state.completed_actions) == 1
    assert len(state.action_keys_seen) == 1

    record = state.completed_actions[0]
    assert record.action_type == "tool_call"
    assert record.result == {"summary": "analysis complete"}
    assert record.success is True


def test_record_multiple_actions():
    """Test recording multiple different actions."""
    state = AgentState(session_id=1, current_step=0)

    state.record_action("tool_call", {"tool": "search"}, "result1", True)
    state.record_action("tool_call", {"tool": "analyze"}, "result2", True)
    state.record_action("plan_step", {"step": 1}, "result3", True)

    assert len(state.completed_actions) == 3
    assert len(state.action_keys_seen) == 3


def test_record_failed_action():
    """Test recording a failed action."""
    state = AgentState(session_id=1, current_step=0)

    state.record_action(
        action_type="tool_call",
        action_data={"tool": "broken_tool"},
        result="error message",
        success=False,
    )

    assert len(state.completed_actions) == 1
    record = state.completed_actions[0]
    assert record.success is False
    assert record.result == "error message"


# ==============================================================================
# Loop Detection Tests
# ==============================================================================

def test_detect_loop_insufficient_actions():
    """Test loop detection returns false with insufficient actions."""
    state = AgentState(session_id=1, current_step=0)

    state.record_action("tool_call", {"tool": "search"}, "result", True)
    state.record_action("tool_call", {"tool": "search"}, "result", True)

    # Only 2 actions, need at least 6 for window_size=3
    is_loop = state.detect_loop(window_size=3)
    assert is_loop is False


def test_detect_loop_no_repetition():
    """Test loop detection returns false when actions vary."""
    state = AgentState(session_id=1, current_step=0)

    # 6 different actions
    for i in range(6):
        state.record_action("tool_call", {"tool": f"tool_{i}"}, f"result_{i}", True)

    is_loop = state.detect_loop(window_size=3)
    assert is_loop is False


def test_detect_loop_exact_repetition():
    """Test loop detection returns true when pattern repeats."""
    state = AgentState(session_id=1, current_step=0)

    # Record pattern ABC twice
    pattern = [
        {"tool": "search", "query": "A"},
        {"tool": "analyze", "data": "B"},
        {"tool": "retry", "attempt": "C"},
    ]

    # First occurrence
    for action_data in pattern:
        state.record_action("tool_call", action_data, "result", True)

    # Second occurrence (repeat)
    for action_data in pattern:
        state.record_action("tool_call", action_data, "result", True)

    is_loop = state.detect_loop(window_size=3)
    assert is_loop is True


def test_detect_loop_broken_pattern():
    """Test loop detection returns false when pattern is broken."""
    state = AgentState(session_id=1, current_step=0)

    # Record pattern ABC
    state.record_action("tool_call", {"tool": "A"}, "result", True)
    state.record_action("tool_call", {"tool": "B"}, "result", True)
    state.record_action("tool_call", {"tool": "C"}, "result", True)

    # Start to repeat but break pattern
    state.record_action("tool_call", {"tool": "A"}, "result", True)
    state.record_action("tool_call", {"tool": "B"}, "result", True)
    state.record_action("tool_call", {"tool": "X"}, "result", True)  # Different!

    is_loop = state.detect_loop(window_size=3)
    assert is_loop is False


def test_detect_loop_with_window_size_2():
    """Test loop detection with smaller window size."""
    state = AgentState(session_id=1, current_step=0)

    # Record pattern AB twice
    state.record_action("tool_call", {"tool": "A"}, "result", True)
    state.record_action("tool_call", {"tool": "B"}, "result", True)
    state.record_action("tool_call", {"tool": "A"}, "result", True)
    state.record_action("tool_call", {"tool": "B"}, "result", True)

    is_loop = state.detect_loop(window_size=2)
    assert is_loop is True


def test_detect_loop_after_recovery():
    """Test loop detection after initial work."""
    state = AgentState(session_id=1, current_step=0)

    # Some initial varied work
    state.record_action("tool_call", {"tool": "search"}, "result", True)
    state.record_action("tool_call", {"tool": "analyze"}, "result", True)

    # Then a repeating pattern
    for _ in range(2):
        state.record_action("tool_call", {"tool": "retry"}, "result", True)
        state.record_action("tool_call", {"tool": "check"}, "result", True)

    is_loop = state.detect_loop(window_size=2)
    assert is_loop is True


# ==============================================================================
# Generate Action Key Tests
# ==============================================================================

def test_generate_action_key_consistency():
    """Test action key generation is consistent."""
    state = AgentState(session_id=1, current_step=0)

    key1 = state._generate_action_key("tool_call", {"a": 1, "b": 2})
    key2 = state._generate_action_key("tool_call", {"a": 1, "b": 2})

    assert key1 == key2


def test_generate_action_key_different_data():
    """Test different action data produces different keys."""
    state = AgentState(session_id=1, current_step=0)

    key1 = state._generate_action_key("tool_call", {"query": "test1"})
    key2 = state._generate_action_key("tool_call", {"query": "test2"})

    assert key1 != key2


def test_generate_action_key_different_type():
    """Test different action types produce different keys."""
    state = AgentState(session_id=1, current_step=0)

    key1 = state._generate_action_key("tool_call", {"data": "same"})
    key2 = state._generate_action_key("plan_step", {"data": "same"})

    assert key1 != key2
