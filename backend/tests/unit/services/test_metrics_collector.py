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
        step_name="research"
    )

    assert metrics.id is not None
    assert metrics.workflow_run_id == workflow_run_fixture.id
    assert metrics.step_execution_id == 1
    assert metrics.step_name == "research"
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
        step_name="research"
    )

    # Complete step
    updated_metrics = collector.record_step_completion(
        metrics_id=metrics.id,
        success=True,
        error_message=None,
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.002
    )

    assert updated_metrics.status == StepStatus.COMPLETED
    assert updated_metrics.completed_at is not None
    assert updated_metrics.input_tokens == 100
    assert updated_metrics.output_tokens == 50
    assert updated_metrics.tokens_used == 150
    assert updated_metrics.cost_usd == 0.002
    assert updated_metrics.error_message is None


def test_record_step_completion_failure(db_session, workflow_run_fixture):
    """Test recording failed step completion updates StepMetrics."""
    collector = MetricsCollector(db_session)

    # Start step
    metrics = collector.record_step_start(
        workflow_run_id=workflow_run_fixture.id,
        step_execution_id=1,
        step_name="research"
    )

    # Fail step
    updated_metrics = collector.record_step_completion(
        metrics_id=metrics.id,
        success=False,
        error_message="Invalid input",
        input_tokens=30,
        output_tokens=20,
        cost_usd=0.001
    )

    assert updated_metrics.status == StepStatus.FAILED
    assert updated_metrics.completed_at is not None
    assert updated_metrics.error_message == "Invalid input"
    assert updated_metrics.input_tokens == 30
    assert updated_metrics.output_tokens == 20
    assert updated_metrics.tokens_used == 50


def test_record_llm_decision(db_session, workflow_run_fixture):
    """Test recording LLM decision creates LLMDecisionMetrics."""
    collector = MetricsCollector(db_session)

    decision = collector.record_llm_decision(
        workflow_run_id=workflow_run_fixture.id,
        step_execution_id=1,
        step_name="research",
        decision_point="tool_selection",
        tokens_used=150,
        latency_ms=250,
        model_used="qwen2.5:32b",
        temperature=0.7,
        response_raw='{"tool": "search", "query": "test"}',
        decision_parsed='{"tool": "search"}',
        llm_reasoning="User requested search"
    )

    assert decision.id is not None
    assert decision.workflow_run_id == workflow_run_fixture.id
    assert decision.step_execution_id == 1
    assert decision.step_name == "research"
    assert decision.decision_point == "tool_selection"
    assert decision.tokens_used == 150
    assert decision.latency_ms == 250
    assert decision.model_used == "qwen2.5:32b"
    assert decision.temperature == 0.7
    assert decision.response_raw == '{"tool": "search", "query": "test"}'
    assert decision.decision_parsed == '{"tool": "search"}'
    assert decision.llm_reasoning == "User requested search"
    assert decision.created_at is not None
