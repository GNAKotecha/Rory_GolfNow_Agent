"""Integration tests for harness with mocked agent execution.

Tests realistic multi-step agent scenarios with canned tool traces.
"""
from typing import List, Dict, Any, Optional
from app.services.harness import (
    HarnessConfig,
    HarnessState,
    StopReason,
    should_continue,
    record_action,
    record_progress,
    increment_step,
    extract_action_signature,
    get_audit_summary,
)


# ==============================================================================
# Mock Agent Execution
# ==============================================================================

class MockAgentStep:
    """Represents one agent execution step."""

    def __init__(self, tool_call: Dict[str, Any], result: str, progress_marker: str):
        self.tool_call = tool_call
        self.result = result
        self.progress_marker = progress_marker


def execute_mock_agent(
    state: HarnessState,
    steps: List[MockAgentStep],
) -> tuple[bool, Optional[StopReason], List[str]]:
    """
    Execute mock agent with canned steps.

    Returns:
        (completed, stop_reason, execution_log)
    """
    execution_log = []

    for i, step in enumerate(steps):
        # Check if we should continue
        should_cont, stop_reason = should_continue(state)

        if not should_cont:
            execution_log.append(f"Step {i}: Stopped - {stop_reason.value}")
            return False, stop_reason, execution_log

        # Execute step
        increment_step(state)
        action_sig = extract_action_signature(step.tool_call)
        record_action(state, action_sig)
        record_progress(state, step.progress_marker)

        execution_log.append(
            f"Step {i+1}: {step.tool_call['name']} -> {step.progress_marker}"
        )

    # All steps completed
    return True, None, execution_log


# ==============================================================================
# Test Scenarios
# ==============================================================================

def test_scenario_normal_completion():
    """Test normal agent execution that completes successfully."""
    config = HarnessConfig(max_steps=10, max_repeat_action=3)
    state = HarnessState(config)

    # Normal workflow: search -> analyze -> respond
    steps = [
        MockAgentStep(
            tool_call={"name": "search", "arguments": {"query": "test"}},
            result="Found 5 results",
            progress_marker="search_complete",
        ),
        MockAgentStep(
            tool_call={"name": "analyze", "arguments": {"data": "results"}},
            result="Analysis complete",
            progress_marker="analysis_complete",
        ),
        MockAgentStep(
            tool_call={"name": "respond", "arguments": {"message": "Done"}},
            result="Response sent",
            progress_marker="task_complete",
        ),
    ]

    completed, stop_reason, log = execute_mock_agent(state, steps)

    assert completed is True
    assert stop_reason is None
    assert state.step_count == 3
    assert len(log) == 3
    assert "task_complete" in log[-1]


def test_scenario_max_steps_exceeded():
    """Test agent execution hitting max steps."""
    config = HarnessConfig(max_steps=5, max_repeat_action=3)
    state = HarnessState(config)

    # Long workflow that exceeds max steps
    steps = [
        MockAgentStep(
            tool_call={"name": "step", "arguments": {"n": i}},
            result=f"Step {i} done",
            progress_marker=f"state_{i}",
        )
        for i in range(10)  # Try 10 steps but limit is 5
    ]

    completed, stop_reason, log = execute_mock_agent(state, steps)

    assert completed is False
    assert stop_reason == StopReason.MAX_STEPS
    assert state.step_count == 5
    assert len(log) == 6  # 5 successful + 1 stop message
    assert "Stopped - max_steps" in log[-1]


def test_scenario_loop_detection():
    """Test agent getting stuck in a loop."""
    config = HarnessConfig(max_steps=20, max_repeat_action=3)
    state = HarnessState(config)

    # Agent repeats same search 3 times
    steps = [
        MockAgentStep(
            tool_call={"name": "search", "arguments": {"query": "test"}},
            result="Found nothing",
            progress_marker="searching",
        ),
        MockAgentStep(
            tool_call={"name": "search", "arguments": {"query": "test"}},
            result="Found nothing",
            progress_marker="searching",
        ),
        MockAgentStep(
            tool_call={"name": "search", "arguments": {"query": "test"}},
            result="Found nothing",
            progress_marker="searching",
        ),
        # This 4th identical step should not execute
        MockAgentStep(
            tool_call={"name": "search", "arguments": {"query": "test"}},
            result="Should not reach",
            progress_marker="searching",
        ),
    ]

    completed, stop_reason, log = execute_mock_agent(state, steps)

    assert completed is False
    assert stop_reason == StopReason.LOOP_DETECTED
    assert state.step_count == 3
    assert len(log) == 4  # 3 successful + 1 stop message
    assert "Stopped - loop_detected" in log[-1]


def test_scenario_no_progress():
    """Test agent making no progress."""
    config = HarnessConfig(max_steps=20, max_repeat_action=5, no_progress_window=4)
    state = HarnessState(config)

    # Agent tries different actions but makes no progress
    steps = [
        MockAgentStep(
            tool_call={"name": "search", "arguments": {"query": "A"}},
            result="Nothing",
            progress_marker="stuck_state",
        ),
        MockAgentStep(
            tool_call={"name": "search", "arguments": {"query": "B"}},
            result="Nothing",
            progress_marker="stuck_state",
        ),
        MockAgentStep(
            tool_call={"name": "analyze", "arguments": {"data": "none"}},
            result="Nothing",
            progress_marker="stuck_state",
        ),
        MockAgentStep(
            tool_call={"name": "retry", "arguments": {}},
            result="Nothing",
            progress_marker="stuck_state",
        ),
        # This should not execute
        MockAgentStep(
            tool_call={"name": "give_up", "arguments": {}},
            result="Should not reach",
            progress_marker="stuck_state",
        ),
    ]

    completed, stop_reason, log = execute_mock_agent(state, steps)

    assert completed is False
    assert stop_reason == StopReason.NO_PROGRESS
    assert state.step_count == 4
    assert "Stopped - no_progress" in log[-1]


def test_scenario_loop_recovery():
    """Test agent recovering from near-loop."""
    config = HarnessConfig(max_steps=20, max_repeat_action=3)
    state = HarnessState(config)

    # Agent repeats twice, then changes approach
    steps = [
        MockAgentStep(
            tool_call={"name": "search", "arguments": {"query": "test"}},
            result="Nothing",
            progress_marker="searching",
        ),
        MockAgentStep(
            tool_call={"name": "search", "arguments": {"query": "test"}},
            result="Nothing",
            progress_marker="searching",
        ),
        MockAgentStep(
            tool_call={"name": "analyze", "arguments": {"different": True}},
            result="New approach",
            progress_marker="analyzing",
        ),
        MockAgentStep(
            tool_call={"name": "respond", "arguments": {"message": "Done"}},
            result="Success",
            progress_marker="complete",
        ),
    ]

    completed, stop_reason, log = execute_mock_agent(state, steps)

    assert completed is True
    assert stop_reason is None
    assert state.step_count == 4
    assert "complete" in log[-1]


def test_scenario_complex_workflow():
    """Test realistic complex workflow with multiple phases."""
    config = HarnessConfig(max_steps=50, max_repeat_action=3, no_progress_window=5)
    state = HarnessState(config)

    # Multi-phase workflow: search -> analyze -> refine -> respond
    steps = [
        # Phase 1: Initial search
        MockAgentStep(
            tool_call={"name": "search", "arguments": {"query": "user request"}},
            result="Found 10 results",
            progress_marker="search_phase",
        ),
        # Phase 2: Analysis
        MockAgentStep(
            tool_call={"name": "analyze", "arguments": {"data": "results"}},
            result="Need more context",
            progress_marker="analysis_phase",
        ),
        # Phase 3: Refined search
        MockAgentStep(
            tool_call={"name": "search", "arguments": {"query": "refined query"}},
            result="Found 3 relevant",
            progress_marker="refine_phase",
        ),
        # Phase 4: Deep analysis
        MockAgentStep(
            tool_call={"name": "deep_analyze", "arguments": {"items": [1, 2, 3]}},
            result="Found answer",
            progress_marker="deep_analysis_phase",
        ),
        # Phase 5: Response
        MockAgentStep(
            tool_call={"name": "respond", "arguments": {"answer": "result"}},
            result="Complete",
            progress_marker="response_phase",
        ),
    ]

    completed, stop_reason, log = execute_mock_agent(state, steps)

    assert completed is True
    assert stop_reason is None
    assert state.step_count == 5

    # Verify progress markers show distinct phases
    markers = state.progress_markers
    assert "search_phase" in markers
    assert "analysis_phase" in markers
    assert "refine_phase" in markers
    assert "deep_analysis_phase" in markers
    assert "response_phase" in markers


def test_scenario_audit_trail():
    """Test audit trail captures execution details."""
    config = HarnessConfig(max_steps=10, max_repeat_action=3)
    state = HarnessState(config)

    steps = [
        MockAgentStep(
            tool_call={"name": "search", "arguments": {"query": "test"}},
            result="Done",
            progress_marker="state_1",
        ),
        MockAgentStep(
            tool_call={"name": "analyze", "arguments": {"data": "x"}},
            result="Done",
            progress_marker="state_2",
        ),
    ]

    execute_mock_agent(state, steps)

    # Check audit log
    assert len(state.audit_log) > 0

    # Get summary
    summary = get_audit_summary(state)
    assert summary["total_steps"] == 2
    assert summary["total_actions"] == 2
    assert "search" in str(summary["action_sequence"])
    assert "analyze" in str(summary["action_sequence"])


def test_scenario_different_args_no_loop():
    """Test that different arguments prevent loop detection."""
    config = HarnessConfig(max_steps=20, max_repeat_action=3)
    state = HarnessState(config)

    # Same tool, different arguments each time
    steps = [
        MockAgentStep(
            tool_call={"name": "search", "arguments": {"query": "A"}},
            result="Result A",
            progress_marker="state_1",
        ),
        MockAgentStep(
            tool_call={"name": "search", "arguments": {"query": "B"}},
            result="Result B",
            progress_marker="state_2",
        ),
        MockAgentStep(
            tool_call={"name": "search", "arguments": {"query": "C"}},
            result="Result C",
            progress_marker="state_3",
        ),
        MockAgentStep(
            tool_call={"name": "respond", "arguments": {"message": "Done"}},
            result="Complete",
            progress_marker="complete",
        ),
    ]

    completed, stop_reason, log = execute_mock_agent(state, steps)

    # Should complete (different args = different actions)
    assert completed is True
    assert stop_reason is None
    assert state.step_count == 4
