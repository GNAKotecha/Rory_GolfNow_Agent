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
        tenant_id: int,
        approval_data: dict,
        approval_prompt: str,
    ) -> WorkflowRun:
        """Pause a workflow run and mark it as WAITING_APPROVAL.

        Stores the approval payload (data to be reviewed) and a human-readable
        prompt describing what is being approved.

        Args:
            workflow_run_id: ID of the workflow run
            tenant_id: Tenant ID for isolation (from JWT)
            approval_data: Data to be reviewed
            approval_prompt: Human-readable description
        """
        workflow_run = (
            self.db.query(WorkflowRun)
            .filter(
                WorkflowRun.id == workflow_run_id,
                WorkflowRun.tenant_id == tenant_id
            )
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
        tenant_id: int,
        approved: bool,
        user_id: int,
        notes: Optional[str] = None,
    ) -> WorkflowRun:
        """Process an approve/reject decision on a waiting workflow run.

        - If approved: status -> RUNNING (workflow resumes).
        - If rejected: status -> FAILED (workflow terminates).
        Records who approved, when, and any optional notes.

        Args:
            workflow_run_id: ID of the workflow run
            tenant_id: Tenant ID for isolation (from JWT)
            approved: True to approve, False to reject
            user_id: ID of user making the decision
            notes: Optional approval notes
        """
        workflow_run = (
            self.db.query(WorkflowRun)
            .filter(
                WorkflowRun.id == workflow_run_id,
                WorkflowRun.tenant_id == tenant_id
            )
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
            workflow_run.error_message = (
                f"Rejected by user {user_id}: {notes}" if notes
                else f"Rejected by user {user_id}"
            )

        workflow_run.approved_by = user_id
        workflow_run.approved_at = datetime.now(timezone.utc)
        workflow_run.approval_notes = notes
        workflow_run.updated_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(workflow_run)
        return workflow_run

    def get_pending_approvals(
        self,
        tenant_id: int,
        user_id: Optional[int] = None,
    ) -> List[WorkflowRun]:
        """Return all workflow runs currently waiting for approval within tenant.

        Args:
            tenant_id: Tenant ID for isolation (from JWT)
            user_id: Optional user ID filter (for future use)

        Returns:
            List of pending workflow runs for the tenant
        """
        query = self.db.query(WorkflowRun).filter(
            WorkflowRun.tenant_id == tenant_id,
            WorkflowRun.status == WorkflowRunStatus.WAITING_APPROVAL
        )
        return query.order_by(WorkflowRun.created_at).all()

    def get_approval_history(self, workflow_run_id: int, tenant_id: int) -> Dict[str, Any]:
        """Return the approval metadata for a workflow run as a dict.

        Args:
            workflow_run_id: ID of the workflow run
            tenant_id: Tenant ID for isolation (from JWT)
        """
        workflow_run = (
            self.db.query(WorkflowRun)
            .filter(
                WorkflowRun.id == workflow_run_id,
                WorkflowRun.tenant_id == tenant_id
            )
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
