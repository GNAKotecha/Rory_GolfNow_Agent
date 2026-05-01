"""Tests for metrics database models."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.metrics import LLMDecisionMetrics, StepMetrics
from app.models.workflow import WorkflowStepExecution, StepStatus


def test_step_metrics_creation(db_session, workflow_run_fixture):
    """Test creating a StepMetrics record."""
    # Create parent WorkflowStepExecution
    step_execution = WorkflowStepExecution(
        workflow_run_id=workflow_run_fixture.id,
        step_id="research_step_1",
        step_name="research_step",
        step_type="tool_call",
        status=StepStatus.COMPLETED,
    )
    db_session.add(step_execution)
    db_session.commit()
    db_session.refresh(step_execution)

    started_at = datetime.now(timezone.utc)
    completed_at = started_at + timedelta(seconds=5)

    metrics = StepMetrics(
        workflow_run_id=workflow_run_fixture.id,
        step_execution_id=step_execution.id,
        started_at=started_at,
        completed_at=completed_at,
        status=StepStatus.COMPLETED,
        tokens_used=1500,
        output_data={"result": "research complete"},
    )

    db_session.add(metrics)
    db_session.commit()

    assert metrics.id is not None
    assert metrics.workflow_run_id == workflow_run_fixture.id
    assert metrics.step_execution_id == step_execution.id
    assert metrics.status == StepStatus.COMPLETED
    assert metrics.tokens_used == 1500
    assert metrics.output_data == {"result": "research complete"}


def test_step_metrics_calculate_duration(db_session, workflow_run_fixture):
    """Test duration calculation for StepMetrics."""
    # Create parent WorkflowStepExecution
    step_execution = WorkflowStepExecution(
        workflow_run_id=workflow_run_fixture.id,
        step_id="analysis_step_1",
        step_name="analysis_step",
        step_type="llm_call",
        status=StepStatus.COMPLETED,
    )
    db_session.add(step_execution)
    db_session.commit()
    db_session.refresh(step_execution)

    started_at = datetime.now(timezone.utc)
    completed_at = started_at + timedelta(seconds=10)

    metrics = StepMetrics(
        workflow_run_id=workflow_run_fixture.id,
        step_execution_id=step_execution.id,
        started_at=started_at,
        completed_at=completed_at,
        status=StepStatus.COMPLETED,
    )

    db_session.add(metrics)
    db_session.commit()

    # Duration should be 10 seconds
    duration = (metrics.completed_at - metrics.started_at).total_seconds()
    assert duration == 10.0


def test_llm_decision_metrics_creation(db_session, workflow_run_fixture):
    """Test creating an LLMDecisionMetrics record."""
    # Create parent WorkflowStepExecution
    step_execution = WorkflowStepExecution(
        workflow_run_id=workflow_run_fixture.id,
        step_id="decision_step_1",
        step_name="decision_step",
        step_type="decision",
        status=StepStatus.COMPLETED,
    )
    db_session.add(step_execution)
    db_session.commit()
    db_session.refresh(step_execution)

    metrics = LLMDecisionMetrics(
        workflow_run_id=workflow_run_fixture.id,
        step_execution_id=step_execution.id,
        decision_point="route_selection",
        prompt_text="Which route should we take based on the data?",
        model_used="qwen2.5:14b",
        response="I recommend path A based on data quality analysis",
        decision_parsed="path_a",
        human_feedback="correct",
        outcome_quality=0.95,
    )

    db_session.add(metrics)
    db_session.commit()

    assert metrics.id is not None
    assert metrics.workflow_run_id == workflow_run_fixture.id
    assert metrics.step_execution_id == step_execution.id
    assert metrics.decision_point == "route_selection"
    assert metrics.model_used == "qwen2.5:14b"
    assert metrics.prompt_text == "Which route should we take based on the data?"
    assert metrics.response == "I recommend path A based on data quality analysis"
    assert metrics.decision_parsed == "path_a"
    assert metrics.human_feedback == "correct"
    assert metrics.outcome_quality == 0.95
    assert metrics.created_at is not None


def test_step_metrics_required_fields(db_session):
    """Test that required fields are enforced."""
    metrics = StepMetrics(
        started_at=datetime.now(timezone.utc),
        status=StepStatus.RUNNING,
    )

    db_session.add(metrics)

    # Should fail because workflow_run_id and step_execution_id are required
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_step_metrics_cascade_delete(db_session, workflow_run_fixture):
    """Test that StepMetrics are deleted when parent WorkflowStepExecution is deleted."""
    # Create parent WorkflowStepExecution
    step_execution = WorkflowStepExecution(
        workflow_run_id=workflow_run_fixture.id,
        step_id="cascade_test_step",
        step_name="cascade_step",
        step_type="tool_call",
        status=StepStatus.COMPLETED,
    )
    db_session.add(step_execution)
    db_session.commit()
    db_session.refresh(step_execution)

    # Create StepMetrics
    metrics = StepMetrics(
        workflow_run_id=workflow_run_fixture.id,
        step_execution_id=step_execution.id,
        started_at=datetime.now(timezone.utc),
        status=StepStatus.COMPLETED,
    )
    db_session.add(metrics)
    db_session.commit()
    db_session.refresh(metrics)

    metrics_id = metrics.id

    # Delete parent
    db_session.delete(step_execution)
    db_session.commit()

    # Verify metrics are deleted
    deleted_metrics = db_session.query(StepMetrics).filter_by(id=metrics_id).first()
    assert deleted_metrics is None
