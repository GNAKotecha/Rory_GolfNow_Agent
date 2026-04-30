"""Tests for metrics database models."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.metrics import LLMDecisionMetrics, StepMetrics


def test_step_metrics_creation(db_session):
    """Test creating a StepMetrics record."""
    started_at = datetime.now(timezone.utc)
    completed_at = started_at + timedelta(seconds=5)

    metrics = StepMetrics(
        workflow_run_id=1,
        step_name="research_step",
        started_at=started_at,
        completed_at=completed_at,
        status="completed",
        tokens_used=1500,
        cost_usd=0.015,
        input_tokens=1000,
        output_tokens=500,
    )

    db_session.add(metrics)
    db_session.commit()

    assert metrics.id is not None
    assert metrics.workflow_run_id == 1
    assert metrics.step_name == "research_step"
    assert metrics.status == "completed"
    assert metrics.tokens_used == 1500
    assert metrics.cost_usd == 0.015
    assert metrics.input_tokens == 1000
    assert metrics.output_tokens == 500


def test_step_metrics_calculate_duration(db_session):
    """Test duration calculation for StepMetrics."""
    started_at = datetime.now(timezone.utc)
    completed_at = started_at + timedelta(seconds=10)

    metrics = StepMetrics(
        workflow_run_id=1,
        step_name="analysis_step",
        started_at=started_at,
        completed_at=completed_at,
        status="completed",
    )

    db_session.add(metrics)
    db_session.commit()

    # Duration should be 10 seconds
    duration = (metrics.completed_at - metrics.started_at).total_seconds()
    assert duration == 10.0


def test_llm_decision_metrics_creation(db_session):
    """Test creating an LLMDecisionMetrics record."""
    metrics = LLMDecisionMetrics(
        workflow_run_id=1,
        step_name="decision_step",
        decision_type="route_selection",
        llm_reasoning="Selected path A based on data quality",
        human_feedback="correct",
        outcome_quality=0.95,
    )

    db_session.add(metrics)
    db_session.commit()

    assert metrics.id is not None
    assert metrics.workflow_run_id == 1
    assert metrics.step_name == "decision_step"
    assert metrics.decision_type == "route_selection"
    assert metrics.llm_reasoning == "Selected path A based on data quality"
    assert metrics.human_feedback == "correct"
    assert metrics.outcome_quality == 0.95
    assert metrics.created_at is not None


def test_step_metrics_required_fields(db_session):
    """Test that required fields are enforced."""
    metrics = StepMetrics(
        step_name="test_step",
        started_at=datetime.now(timezone.utc),
    )

    db_session.add(metrics)

    # Should fail because workflow_run_id is required
    with pytest.raises(IntegrityError):
        db_session.commit()
