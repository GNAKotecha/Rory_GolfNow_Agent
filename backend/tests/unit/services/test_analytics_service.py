"""Unit tests for AnalyticsService."""
from datetime import datetime, timezone, timedelta

import pytest

from app.models.prompt_template import PromptTemplate, PromptTemplateVersion
from app.models.workflow import StepStatus, WorkflowRun, WorkflowRunStatus
from app.services.analytics_service import AnalyticsService


def test_get_workflow_success_rate(db_session, workflow_template_fixture, session):
    """Should calculate success rate across all workflow runs."""
    # Create workflow runs with different statuses: 7 completed, 3 failed
    for i in range(10):
        status = WorkflowRunStatus.COMPLETED if i < 7 else WorkflowRunStatus.FAILED
        run = WorkflowRun(
            template_id=workflow_template_fixture.id,
            session_id=session.id,
            status=status,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
    db_session.commit()

    service = AnalyticsService(db_session)
    success_rate = service.get_workflow_success_rate(workflow_template_fixture.id)

    assert success_rate == 0.7


def test_get_average_workflow_duration(db_session, workflow_template_fixture, session):
    """Should calculate average duration for completed workflows."""
    now = datetime.now(timezone.utc)
    # Create 5 completed workflows with durations 60, 120, 180, 240, 300 seconds
    for i in range(5):
        started = now - timedelta(seconds=300)
        completed = now - timedelta(seconds=300 - ((i + 1) * 60))
        run = WorkflowRun(
            template_id=workflow_template_fixture.id,
            session_id=session.id,
            status=WorkflowRunStatus.COMPLETED,
            created_at=now - timedelta(seconds=300),
            started_at=started,
            completed_at=completed,
        )
        db_session.add(run)
    db_session.commit()

    service = AnalyticsService(db_session)
    avg_duration = service.get_average_workflow_duration(workflow_template_fixture.id)

    # (60 + 120 + 180 + 240 + 300) / 5 = 180
    assert avg_duration == 180.0


def test_get_step_failure_analysis(
    db_session, workflow_run_factory, workflow_step_execution_factory
):
    """Should identify which steps fail most frequently."""
    workflow_run = workflow_run_factory()

    # init_database: 10 successes
    # config_setup: 7 successes, 3 failures (30% failure rate)
    for i in range(10):
        workflow_step_execution_factory(
            workflow_run_id=workflow_run.id,
            step_name="init_database",
            status=StepStatus.COMPLETED,
        )
        workflow_step_execution_factory(
            workflow_run_id=workflow_run.id,
            step_name="config_setup",
            status=StepStatus.FAILED if i < 3 else StepStatus.COMPLETED,
        )

    service = AnalyticsService(db_session)
    failures = service.get_step_failure_analysis(workflow_run.template_id)

    assert len(failures) == 2
    assert failures["config_setup"]["failure_rate"] == 0.3
    assert failures["init_database"]["failure_rate"] == 0.0
    assert failures["config_setup"]["total_executions"] == 10
    assert failures["config_setup"]["failed_executions"] == 3


def test_get_prompt_version_comparison(db_session):
    """Should compare performance metrics across prompt versions."""
    template = PromptTemplate(
        name="test_prompt_analytics",
        description="Test prompt for analytics",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(template)
    db_session.commit()

    v1 = PromptTemplateVersion(
        template_id=template.id,
        version_number=1,
        prompt_text="V1",
        variables={},
        is_active=False,
        usage_count=100,
        success_count=70,
        avg_latency_ms=200.0,
        created_at=datetime.now(timezone.utc),
    )
    v2 = PromptTemplateVersion(
        template_id=template.id,
        version_number=2,
        prompt_text="V2",
        variables={},
        is_active=True,
        usage_count=100,
        success_count=85,
        avg_latency_ms=180.0,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add_all([v1, v2])
    db_session.commit()

    service = AnalyticsService(db_session)
    comparison = service.get_prompt_version_comparison(template.id)

    assert len(comparison) == 2
    assert comparison[0]["version_number"] == 1
    assert comparison[0]["success_rate"] == 0.7
    assert comparison[1]["version_number"] == 2
    assert comparison[1]["success_rate"] == 0.85
    assert comparison[1]["is_active"] is True
