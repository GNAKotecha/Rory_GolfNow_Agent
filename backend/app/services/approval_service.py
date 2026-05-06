"""Approval service for human-in-the-loop workflow gates.

Manages approval requests on WorkflowRun rows: pausing a run to WAITING_APPROVAL,
processing approve/reject decisions, and listing pending approvals or history.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.workflow import WorkflowRun, WorkflowRunStatus


class ApprovalStatus:
    """Constants describing approval outcomes on a workflow run."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalService:
    """Service for managing human approval gates on workflow runs."""

    def __init__(self, db: Session):
        self.db = db

    def request_approval(
        self,
        workflow_run_id: int,
        approval_data: dict,
        approval_prompt: str,
    ) -> WorkflowRun:
        """Pause a workflow run and mark it as WAITING_APPROVAL.

        Stores the approval payload (data to be reviewed) and a human-readable
        prompt describing what is being approved.
        """
        workflow_run = (
            self.db.query(WorkflowRun)
            .filter(WorkflowRun.id == workflow_run_id)
            .first()
        )
        if workflow_run is None:
            raise ValueError(f"WorkflowRun {workflow_run_id} not found")

        workflow_run.status = WorkflowRunStatus.WAITING_APPROVAL
        workflow_run.approval_data = approval_data
        workflow_run.approval_prompt = approval_prompt
        workflow_run.updated_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(workflow_run)
        return workflow_run

    def process_approval(
        self,
        workflow_run_id: int,
        approved: bool,
        user_id: int,
        notes: Optional[str] = None,
    ) -> WorkflowRun:
        """Process an approve/reject decision on a waiting workflow run.

        - If approved: status -> RUNNING (workflow resumes).
        - If rejected: status -> FAILED (workflow terminates).
        Records who approved, when, and any optional notes.
        """
        workflow_run = (
            self.db.query(WorkflowRun)
            .filter(WorkflowRun.id == workflow_run_id)
            .first()
        )
        if workflow_run is None:
            raise ValueError(f"WorkflowRun {workflow_run_id} not found")

        if workflow_run.status != WorkflowRunStatus.WAITING_APPROVAL:
            raise ValueError(
                f"Workflow run {workflow_run_id} is not waiting for approval "
                f"(current status: {workflow_run.status})"
            )

        if approved:
            workflow_run.status = WorkflowRunStatus.RUNNING
        else:
            workflow_run.status = WorkflowRunStatus.FAILED
            workflow_run.error_message = f"Rejected by user {user_id}: {notes}"

        workflow_run.approved_by = user_id
        workflow_run.approved_at = datetime.now(timezone.utc)
        workflow_run.approval_notes = notes
        workflow_run.updated_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(workflow_run)
        return workflow_run

    def get_pending_approvals(
        self,
        user_id: Optional[int] = None,
    ) -> List[WorkflowRun]:
        """Return all workflow runs currently waiting for approval.

        If user_id is provided, results may be filtered in future iterations
        (e.g. by ownership of the session). For now we return all waiting runs;
        user_id is accepted for API stability.
        """
        query = self.db.query(WorkflowRun).filter(
            WorkflowRun.status == WorkflowRunStatus.WAITING_APPROVAL
        )
        return query.order_by(WorkflowRun.created_at).all()

    def get_approval_history(self, workflow_run_id: int) -> Dict[str, Any]:
        """Return the approval metadata for a workflow run as a dict."""
        workflow_run = (
            self.db.query(WorkflowRun)
            .filter(WorkflowRun.id == workflow_run_id)
            .first()
        )

        if not workflow_run:
            raise ValueError(f"Workflow run not found: {workflow_run_id}")

        return {
            "workflow_run_id": workflow_run.id,
            "approval_data": workflow_run.approval_data,
            "approval_prompt": workflow_run.approval_prompt,
            "approved_by": workflow_run.approved_by,
            "approved_at": workflow_run.approved_at.isoformat() if workflow_run.approved_at else None,
            "approval_notes": workflow_run.approval_notes,
            "status": workflow_run.status.value,
        }
