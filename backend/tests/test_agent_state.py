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


# ==============================================================================
# Run-Scoped Fingerprint Retry Budget Tests (Task A1)
# ==============================================================================

def test_fingerprint_generation_consistency():
    """Test fingerprint generation is consistent for same tool+args."""
    state = AgentState(session_id=1, current_step=0)
    
    fp1 = state._generate_fingerprint("create_club", {"name": "Test Club", "email": "test@test.com"})
    fp2 = state._generate_fingerprint("create_club", {"name": "Test Club", "email": "test@test.com"})
    
    assert fp1 == fp2


def test_fingerprint_generation_order_independence():
    """Test fingerprint is same regardless of argument order."""
    state = AgentState(session_id=1, current_step=0)
    
    fp1 = state._generate_fingerprint("create_club", {"name": "Test", "email": "a@b.com", "type": "golf"})
    fp2 = state._generate_fingerprint("create_club", {"type": "golf", "name": "Test", "email": "a@b.com"})
    
    assert fp1 == fp2


def test_fingerprint_different_args_different_fingerprint():
    """Test different args produce different fingerprints."""
    state = AgentState(session_id=1, current_step=0)
    
    fp1 = state._generate_fingerprint("create_club", {"name": "Club A"})
    fp2 = state._generate_fingerprint("create_club", {"name": "Club B"})
    
    assert fp1 != fp2


def test_fingerprint_different_tools_different_fingerprint():
    """Test different tools produce different fingerprints even with same args."""
    state = AgentState(session_id=1, current_step=0)
    
    fp1 = state._generate_fingerprint("create_club", {"name": "Test"})
    fp2 = state._generate_fingerprint("update_club", {"name": "Test"})
    
    assert fp1 != fp2


def test_get_fingerprint_retry_count_initial():
    """Test initial retry count is zero."""
    state = AgentState(session_id=1, current_step=0)
    
    count = state.get_fingerprint_retry_count("create_club", {"name": "Test"})
    
    assert count == 0


def test_increment_fingerprint_retry():
    """Test incrementing fingerprint retry count."""
    state = AgentState(session_id=1, current_step=0)
    
    new_count = state.increment_fingerprint_retry("create_club", {"name": "Test"})
    assert new_count == 1
    
    new_count = state.increment_fingerprint_retry("create_club", {"name": "Test"})
    assert new_count == 2
    
    # Verify via get
    count = state.get_fingerprint_retry_count("create_club", {"name": "Test"})
    assert count == 2


def test_fingerprint_retry_count_survives_step_increment():
    """Test retry count persists when step number changes (run-scoped)."""
    state = AgentState(session_id=1, current_step=1)
    
    # Increment retry in step 1
    state.increment_fingerprint_retry("create_club", {"name": "Test"})
    
    # Simulate moving to step 2
    state.current_step = 2
    
    # Count should persist
    count = state.get_fingerprint_retry_count("create_club", {"name": "Test"})
    assert count == 1
    
    # Increment again in step 2
    state.increment_fingerprint_retry("create_club", {"name": "Test"})
    
    # Count should be cumulative
    count = state.get_fingerprint_retry_count("create_club", {"name": "Test"})
    assert count == 2


def test_can_retry_fingerprint_within_budget():
    """Test can_retry returns True when within budget."""
    state = AgentState(session_id=1, current_step=0)
    
    assert state.can_retry_fingerprint("create_club", {"name": "Test"}, budget=3) is True
    
    state.increment_fingerprint_retry("create_club", {"name": "Test"})
    assert state.can_retry_fingerprint("create_club", {"name": "Test"}, budget=3) is True
    
    state.increment_fingerprint_retry("create_club", {"name": "Test"})
    assert state.can_retry_fingerprint("create_club", {"name": "Test"}, budget=3) is True


def test_can_retry_fingerprint_budget_exhausted():
    """Test can_retry returns False when budget exhausted."""
    state = AgentState(session_id=1, current_step=0)
    
    # Exhaust budget of 3
    state.increment_fingerprint_retry("create_club", {"name": "Test"})
    state.increment_fingerprint_retry("create_club", {"name": "Test"})
    state.increment_fingerprint_retry("create_club", {"name": "Test"})
    
    assert state.can_retry_fingerprint("create_club", {"name": "Test"}, budget=3) is False


def test_fingerprint_retry_isolation():
    """Test retry counts are isolated per fingerprint."""
    state = AgentState(session_id=1, current_step=0)
    
    # Exhaust budget for one fingerprint
    state.increment_fingerprint_retry("create_club", {"name": "Club A"})
    state.increment_fingerprint_retry("create_club", {"name": "Club A"})
    state.increment_fingerprint_retry("create_club", {"name": "Club A"})
    
    # Different args should have fresh budget
    assert state.can_retry_fingerprint("create_club", {"name": "Club B"}, budget=3) is True
    assert state.get_fingerprint_retry_count("create_club", {"name": "Club B"}) == 0


def test_get_fingerprint_retry_summary():
    """Test fingerprint retry summary for telemetry."""
    state = AgentState(session_id=1, current_step=0)
    
    state.increment_fingerprint_retry("create_club", {"name": "Test"})
    state.increment_fingerprint_retry("create_club", {"name": "Test"})
    state.increment_fingerprint_retry("update_club", {"id": 1})
    
    summary = state.get_fingerprint_retry_summary()
    
    assert len(summary) == 2
    # Keys are truncated fingerprints
    assert all("..." in key for key in summary.keys())
    # Values should be the counts
    assert 2 in summary.values()
    assert 1 in summary.values()


# ==============================================================================
# Task A3: Reflection Turn Tracking Tests
# ==============================================================================

def test_get_reflection_attempts_initial():
    """Test initial reflection attempts is zero."""
    state = AgentState(session_id=1, current_step=0)
    
    count = state.get_reflection_attempts("test_tool", {"param": "value"})
    
    assert count == 0


def test_increment_reflection_attempt():
    """Test incrementing reflection attempts."""
    state = AgentState(session_id=1, current_step=0)
    
    new_count = state.increment_reflection_attempt("test_tool", {"param": "value"})
    assert new_count == 1
    
    new_count = state.increment_reflection_attempt("test_tool", {"param": "value"})
    assert new_count == 2


def test_can_reflect_within_limit():
    """Test can_reflect returns True when within limit."""
    state = AgentState(session_id=1, current_step=0)
    
    # Should be able to reflect initially
    assert state.can_reflect("test_tool", {"param": "value"}) is True
    
    # After one reflection, should not be able to reflect again (default max is 1)
    state.increment_reflection_attempt("test_tool", {"param": "value"})
    assert state.can_reflect("test_tool", {"param": "value"}) is False


def test_can_reflect_custom_limit():
    """Test can_reflect with custom max_reflections."""
    state = AgentState(session_id=1, current_step=0)
    
    # With max_reflections=2, should allow 2 reflections
    assert state.can_reflect("test_tool", {"param": "value"}, max_reflections=2) is True
    
    state.increment_reflection_attempt("test_tool", {"param": "value"})
    assert state.can_reflect("test_tool", {"param": "value"}, max_reflections=2) is True
    
    state.increment_reflection_attempt("test_tool", {"param": "value"})
    assert state.can_reflect("test_tool", {"param": "value"}, max_reflections=2) is False


def test_reflection_attempts_isolated_per_fingerprint():
    """Test reflection attempts are isolated per fingerprint."""
    state = AgentState(session_id=1, current_step=0)
    
    # Exhaust reflection for one fingerprint
    state.increment_reflection_attempt("test_tool", {"param": "A"})
    assert state.can_reflect("test_tool", {"param": "A"}) is False
    
    # Different fingerprint should have fresh budget
    assert state.can_reflect("test_tool", {"param": "B"}) is True
