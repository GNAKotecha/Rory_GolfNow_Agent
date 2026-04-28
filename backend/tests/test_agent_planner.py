"""Tests for agent planning and verification."""
import pytest
from unittest.mock import AsyncMock, Mock
from app.services.agent_planner import (
    AgentPlanner,
    TaskPlan,
    PlanStep,
    PlanStepStatus,
)


@pytest.mark.asyncio
async def test_create_plan_success():
    """Test successful plan creation."""
    # Mock Ollama client
    ollama = Mock()
    ollama.generate_chat_completion = AsyncMock(
        return_value='{"steps": [{"step_number": 1, "description": "Read database", "dependencies": [], "verification_criteria": "Data retrieved"}, {"step_number": 2, "description": "Process data", "dependencies": [1], "verification_criteria": "Data transformed"}]}'
    )

    planner = AgentPlanner()
    plan = await planner.create_plan(
        task_description="Analyze database records",
        ollama_client=ollama,
        available_tools=["db_query", "process_data"],
    )

    assert isinstance(plan, TaskPlan)
    assert plan.task_description == "Analyze database records"
    assert len(plan.steps) == 2
    assert plan.steps[0].description == "Read database"
    assert plan.steps[0].status == PlanStepStatus.PENDING
    assert plan.steps[1].dependencies == [1]


@pytest.mark.asyncio
async def test_create_plan_fallback_on_error():
    """Test plan creation falls back to single step on error."""
    # Mock Ollama client that returns invalid JSON
    ollama = Mock()
    ollama.generate_chat_completion = AsyncMock(return_value="Invalid JSON")

    planner = AgentPlanner()
    plan = await planner.create_plan(
        task_description="Do something",
        ollama_client=ollama,
        available_tools=["tool1"],
    )

    # Should create single-step plan
    assert len(plan.steps) == 1
    assert plan.steps[0].description == "Do something"
    assert plan.steps[0].status == PlanStepStatus.PENDING


@pytest.mark.asyncio
async def test_verify_step_success():
    """Test step verification passes."""
    # Mock Ollama client
    ollama = Mock()
    ollama.generate_chat_completion = AsyncMock(return_value="YES, the step completed successfully because data was retrieved.")

    planner = AgentPlanner()
    step = PlanStep(
        step_number=1,
        description="Read database",
        status=PlanStepStatus.PENDING,
        verification_criteria="Data must be retrieved",
    )

    verified = await planner.verify_step(
        step=step,
        execution_result={"rows": 10},
        ollama_client=ollama,
    )

    assert verified is True


@pytest.mark.asyncio
async def test_verify_step_failure():
    """Test step verification fails."""
    # Mock Ollama client
    ollama = Mock()
    ollama.generate_chat_completion = AsyncMock(return_value="NO, the step failed because no data was retrieved.")

    planner = AgentPlanner()
    step = PlanStep(
        step_number=1,
        description="Read database",
        status=PlanStepStatus.PENDING,
        verification_criteria="Data must be retrieved",
    )

    verified = await planner.verify_step(
        step=step,
        execution_result=None,
        ollama_client=ollama,
    )

    assert verified is False


@pytest.mark.asyncio
async def test_verify_step_no_criteria():
    """Test step verification without criteria assumes success."""
    planner = AgentPlanner()
    step = PlanStep(
        step_number=1,
        description="Do something",
        status=PlanStepStatus.PENDING,
        verification_criteria=None,
    )

    # Should pass if result exists
    verified = await planner.verify_step(
        step=step,
        execution_result={"success": True},
        ollama_client=Mock(),
    )

    assert verified is True

    # Should fail if result is None
    verified = await planner.verify_step(
        step=step,
        execution_result=None,
        ollama_client=Mock(),
    )

    assert verified is False


def test_task_plan_get_next_step():
    """Test getting next available step."""
    plan = TaskPlan(
        task_description="Test",
        steps=[
            PlanStep(1, "Step 1", PlanStepStatus.COMPLETED, []),
            PlanStep(2, "Step 2", PlanStepStatus.PENDING, [1]),
            PlanStep(3, "Step 3", PlanStepStatus.PENDING, [2]),
        ],
    )

    # Step 2 should be next (depends on 1, which is completed)
    next_step = plan.get_next_step()
    assert next_step is not None
    assert next_step.step_number == 2


def test_task_plan_get_next_step_blocked():
    """Test that blocked steps are not returned."""
    plan = TaskPlan(
        task_description="Test",
        steps=[
            PlanStep(1, "Step 1", PlanStepStatus.PENDING, []),
            PlanStep(2, "Step 2", PlanStepStatus.PENDING, [1]),
        ],
    )

    # Only step 1 should be available (step 2 depends on 1)
    next_step = plan.get_next_step()
    assert next_step is not None
    assert next_step.step_number == 1


def test_task_plan_mark_step_completed():
    """Test marking step as completed."""
    plan = TaskPlan(
        task_description="Test",
        steps=[PlanStep(1, "Step 1", PlanStepStatus.PENDING, [])],
    )

    plan.mark_step_completed(1, {"result": "success"})

    assert plan.steps[0].status == PlanStepStatus.COMPLETED
    assert plan.steps[0].result == {"result": "success"}


def test_task_plan_mark_step_failed():
    """Test marking step as failed."""
    plan = TaskPlan(
        task_description="Test",
        steps=[PlanStep(1, "Step 1", PlanStepStatus.PENDING, [])],
    )

    plan.mark_step_failed(1, "Error occurred")

    assert plan.steps[0].status == PlanStepStatus.FAILED
    assert plan.steps[0].result == "Error occurred"


def test_task_plan_is_complete():
    """Test plan completion check."""
    plan = TaskPlan(
        task_description="Test",
        steps=[
            PlanStep(1, "Step 1", PlanStepStatus.COMPLETED, []),
            PlanStep(2, "Step 2", PlanStepStatus.COMPLETED, []),
        ],
    )

    assert plan.is_complete() is True

    # Not complete if any step is pending
    plan.steps[1].status = PlanStepStatus.PENDING
    assert plan.is_complete() is False


def test_task_plan_get_progress():
    """Test progress calculation."""
    plan = TaskPlan(
        task_description="Test",
        steps=[
            PlanStep(1, "Step 1", PlanStepStatus.COMPLETED, []),
            PlanStep(2, "Step 2", PlanStepStatus.PENDING, []),
            PlanStep(3, "Step 3", PlanStepStatus.PENDING, []),
        ],
    )

    # 1 out of 3 completed = 33%
    assert plan.get_progress() == pytest.approx(0.333, rel=0.01)

    # Mark second step completed
    plan.mark_step_completed(2, {})
    assert plan.get_progress() == pytest.approx(0.666, rel=0.01)

    # All completed
    plan.mark_step_completed(3, {})
    assert plan.get_progress() == 1.0


def test_extract_json_direct():
    """Test extracting direct JSON."""
    planner = AgentPlanner()

    result = planner._extract_json('{"key": "value"}')
    assert result == {"key": "value"}


def test_extract_json_with_code_blocks():
    """Test extracting JSON from code blocks."""
    planner = AgentPlanner()

    text = """Here's the plan:
```json
{"steps": [{"step_number": 1}]}
```
"""
    result = planner._extract_json(text)
    assert result == {"steps": [{"step_number": 1}]}


def test_extract_json_with_surrounding_text():
    """Test extracting JSON from text with surrounding content."""
    planner = AgentPlanner()

    text = """Here is the plan: {"steps": []} and that's it."""
    result = planner._extract_json(text)
    assert result == {"steps": []}


def test_extract_json_invalid():
    """Test extracting invalid JSON returns None."""
    planner = AgentPlanner()

    result = planner._extract_json("This is not JSON")
    assert result is None
