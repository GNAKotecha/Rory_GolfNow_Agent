"""Tests for MetricsCollector service."""
from datetime import datetime, timezone

import pytest

from app.models.metrics import StepMetrics, LLMDecisionMetrics
from app.models.workflow import StepStatus
from app.services.metrics_collector import MetricsCollector


def test_record_step_start(db_session, workflow_run_fixture):
    """Test recording step start creates StepMetrics."""
    collector = MetricsCollector(db_session)

    metrics = collector.record_step_start(
        workflow_run_id=workflow_run_fixture.id,
        step_execution_id=1,
        attempt_number=1
    )

    assert metrics.id is not None
    assert metrics.workflow_run_id == workflow_run_fixture.id
    assert metrics.step_execution_id == 1
    assert metrics.attempt_number == 1
    assert metrics.started_at is not None
    assert metrics.status == StepStatus.RUNNING
    assert metrics.completed_at is None


def test_record_step_completion_success(db_session, workflow_run_fixture):
    """Test recording successful step completion updates StepMetrics."""
    collector = MetricsCollector(db_session)

    # Start step
    metrics = collector.record_step_start(
        workflow_run_id=workflow_run_fixture.id,
        step_execution_id=1,
        attempt_number=1
    )

    # Complete step
    updated_metrics = collector.record_step_completion(
        metrics_id=metrics.id,
        success=True,
        error_type=None,
        error_message=None,
        output_data={"result": "success"},
        tokens_used=150,
        tool_latency_ms=250
    )

    assert updated_metrics.status == StepStatus.COMPLETED
    assert updated_metrics.completed_at is not None
    assert updated_metrics.tokens_used == 150
    assert updated_metrics.tool_latency_ms == 250
    assert updated_metrics.output_data == {"result": "success"}
    assert updated_metrics.error_type is None
    assert updated_metrics.error_message is None


def test_record_step_completion_failure(db_session, workflow_run_fixture):
    """Test recording failed step completion updates StepMetrics."""
    collector = MetricsCollector(db_session)

    # Start step
    metrics = collector.record_step_start(
        workflow_run_id=workflow_run_fixture.id,
        step_execution_id=1,
        attempt_number=1
    )

    # Fail step
    updated_metrics = collector.record_step_completion(
        metrics_id=metrics.id,
        success=False,
        error_type="validation_error",
        error_message="Invalid input",
        output_data=None,
        tokens_used=50,
        tool_latency_ms=100
    )

    assert updated_metrics.status == StepStatus.FAILED
    assert updated_metrics.completed_at is not None
    assert updated_metrics.error_type == "validation_error"
    assert updated_metrics.error_message == "Invalid input"
    assert updated_metrics.tokens_used == 50
    assert updated_metrics.tool_latency_ms == 100


def test_record_llm_decision(db_session, workflow_run_fixture):
    """Test recording LLM decision creates LLMDecisionMetrics."""
    collector = MetricsCollector(db_session)

    decision = collector.record_llm_decision(
        workflow_run_id=workflow_run_fixture.id,
        step_execution_id=1,
        decision_point="tool_selection",
        prompt_template_id="template_001",
        prompt_text="Select the appropriate tool for: test query",
        model_used="qwen2.5:32b",
        response='{"tool": "search", "query": "test"}',
        decision_parsed='{"tool": "search"}',
        tokens_used=150,
        latency_ms=250,
        temperature=0.7
    )

    assert decision.id is not None
    assert decision.workflow_run_id == workflow_run_fixture.id
    assert decision.step_execution_id == 1
    assert decision.decision_point == "tool_selection"
    assert decision.prompt_template_id == "template_001"
    assert decision.prompt_text == "Select the appropriate tool for: test query"
    assert decision.model_used == "qwen2.5:32b"
    assert decision.response == '{"tool": "search", "query": "test"}'
    assert decision.decision_parsed == '{"tool": "search"}'
    assert decision.tokens_used == 150
    assert decision.latency_ms == 250
    assert decision.temperature == 0.7
    assert decision.created_at is not None


def test_record_step_completion_invalid_id(db_session):
    """Test recording step completion with invalid metrics_id raises ValueError."""
    collector = MetricsCollector(db_session)

    with pytest.raises(ValueError) as exc_info:
        collector.record_step_completion(
            metrics_id=99999,
            success=True,
            output_data={"result": "success"}
        )

    assert "StepMetrics with id 99999 not found" in str(exc_info.value)


def test_record_step_start_rollback_on_commit_failure(db_session, workflow_run_fixture, monkeypatch):
    """Test that record_step_start rolls back transaction on commit failure."""
    collector = MetricsCollector(db_session)

    # Mock db.commit to raise an exception
    def mock_commit():
        raise Exception("Database commit failed")

    monkeypatch.setattr(db_session, "commit", mock_commit)

    # Verify rollback is called on failure
    with pytest.raises(Exception) as exc_info:
        collector.record_step_start(
            workflow_run_id=workflow_run_fixture.id,
            step_execution_id=1,
            attempt_number=1
        )

    assert "Database commit failed" in str(exc_info.value)

    # Verify no StepMetrics were persisted
    metrics_count = db_session.query(StepMetrics).count()
    assert metrics_count == 0
