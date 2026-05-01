import pytest
import asyncio
from datetime import datetime, timezone
from app.models.workflow import (
    WorkflowTemplate,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowStepExecution,
    StepStatus
)
from app.models.metrics import StepMetrics
from app.models.models import User, Session, WorkflowCategory
from app.services.workflow_orchestrator import WorkflowOrchestrator


@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_workflow_execution(db_session):
    """
    Integration test: Create template, run workflow, verify metrics.

    Tests the complete flow from template creation through execution
    to metrics collection.
    """
    # 1. Create user and session
    user = User(email="test@example.com", name="Test User", password_hash="hashed_password")
    db_session.add(user)
    db_session.commit()

    session = Session(user_id=user.id)
    db_session.add(session)
    db_session.commit()

    # 2. Create workflow template
    template = WorkflowTemplate(
        name="integration_test_workflow",
        description="Integration test workflow",
        version="1.0.0",
        workflow_category=WorkflowCategory.WORKFLOW,
        definition={
            "entry_point": "init",
            "steps": [
                {
                    "id": "init",
                    "name": "Initialize Database",
                    "type": "tool_call",
                    "config": {"tool": "mock_init"},
                    "next": ["configure"]
                },
                {
                    "id": "configure",
                    "name": "Configure Settings",
                    "type": "tool_call",
                    "config": {"tool": "mock_configure"},
                    "next": []
                }
            ]
        }
    )
    db_session.add(template)
    db_session.commit()

    # 3. Create workflow orchestrator
    orchestrator = WorkflowOrchestrator(db_session)

    # 4. Create workflow run
    workflow_run = orchestrator.create_workflow_run(
        template_name="integration_test_workflow",
        session_id=session.id,
        input_data={"club_name": "Integration Test Club"}
    )

    assert workflow_run.status == WorkflowRunStatus.PENDING

    # 5. Execute workflow
    result = await orchestrator.execute_workflow(workflow_run.id)

    # 6. Verify workflow run completed
    db_session.refresh(workflow_run)
    assert workflow_run.status == WorkflowRunStatus.COMPLETED
    assert workflow_run.completed_at is not None

    # 7. Verify step executions created
    steps = db_session.query(WorkflowStepExecution).filter_by(
        workflow_run_id=workflow_run.id
    ).order_by(WorkflowStepExecution.id).all()

    assert len(steps) == 2
    assert steps[0].step_id == "init"
    assert steps[0].status == StepStatus.COMPLETED
    assert steps[1].step_id == "configure"
    assert steps[1].status == StepStatus.COMPLETED

    # 8. Verify metrics collected for all steps
    metrics = db_session.query(StepMetrics).filter_by(
        workflow_run_id=workflow_run.id
    ).all()

    assert len(metrics) == 2
    for metric in metrics:
        assert metric.status == StepStatus.COMPLETED
        assert metric.started_at is not None
        assert metric.completed_at is not None
        # Calculate duration from timestamps
        duration_ms = (metric.completed_at - metric.started_at).total_seconds() * 1000
        assert duration_ms > 0

    # 9. Verify final state
    assert "step_results" in result
    step_results = result["step_results"]
    assert "init_status" in step_results
    assert step_results["init_status"] == "completed"
    assert "configure_status" in step_results
    assert step_results["configure_status"] == "completed"
