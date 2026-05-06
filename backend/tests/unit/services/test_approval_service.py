"""Unit tests for ApprovalService."""
import pytest
from datetime import datetime, timezone

from app.services.approval_service import ApprovalService, ApprovalStatus
from app.models.workflow import WorkflowRun, WorkflowRunStatus


def test_request_approval_updates_workflow_run(db_session, workflow_run_factory):
    """Should update workflow run to WAITING_APPROVAL status."""
    workflow_run = workflow_run_factory(status=WorkflowRunStatus.RUNNING)
    service = ApprovalService(db_session)

    approval_data = {"config": {"club_name": "Test Club"}}

    service.request_approval(
        workflow_run_id=workflow_run.id,
        approval_data=approval_data,
        approval_prompt="Please review the generated configuration",
    )

    db_session.refresh(workflow_run)
    assert workflow_run.status == WorkflowRunStatus.WAITING_APPROVAL
    assert workflow_run.approval_data == approval_data
    assert "review" in workflow_run.approval_prompt.lower()


def test_approve_workflow_run_updates_status(db_session, workflow_run_factory):
    """Should approve workflow and update status to RUNNING."""
    workflow_run = workflow_run_factory(status=WorkflowRunStatus.WAITING_APPROVAL)
    service = ApprovalService(db_session)

    service.process_approval(
        workflow_run_id=workflow_run.id,
        approved=True,
        user_id=1,
        notes="Looks good",
    )

    db_session.refresh(workflow_run)
    assert workflow_run.status == WorkflowRunStatus.RUNNING
    assert workflow_run.approved_by == 1
    assert workflow_run.approved_at is not None
    assert workflow_run.approval_notes == "Looks good"


def test_reject_workflow_run_updates_status(db_session, workflow_run_factory):
    """Should reject workflow and update status to FAILED."""
    workflow_run = workflow_run_factory(status=WorkflowRunStatus.WAITING_APPROVAL)
    service = ApprovalService(db_session)

    service.process_approval(
        workflow_run_id=workflow_run.id,
        approved=False,
        user_id=1,
        notes="Config is incorrect",
    )

    db_session.refresh(workflow_run)
    assert workflow_run.status == WorkflowRunStatus.FAILED
    assert workflow_run.approved_by == 1
    assert workflow_run.approved_at is not None
    assert workflow_run.approval_notes == "Config is incorrect"


def test_get_pending_approvals_returns_waiting_workflows(db_session, workflow_run_factory):
    """Should return all workflows waiting for approval."""
    waiting1 = workflow_run_factory(status=WorkflowRunStatus.WAITING_APPROVAL)
    waiting2 = workflow_run_factory(status=WorkflowRunStatus.WAITING_APPROVAL)
    running = workflow_run_factory(status=WorkflowRunStatus.RUNNING)
    completed = workflow_run_factory(status=WorkflowRunStatus.COMPLETED)

    service = ApprovalService(db_session)
    pending = service.get_pending_approvals()

    pending_ids = [w.id for w in pending]
    assert waiting1.id in pending_ids
    assert waiting2.id in pending_ids
    assert running.id not in pending_ids
    assert completed.id not in pending_ids
