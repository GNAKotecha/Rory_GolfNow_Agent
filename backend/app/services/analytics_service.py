"""Analytics service for workflow and prompt metrics."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.prompt_template import PromptTemplateVersion
from app.models.workflow import (
    StepStatus,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowStepExecution,
)


class AnalyticsService:
    """Service for workflow and prompt analytics.

    Queries workflow execution data and prompt template metrics
    for the analytics dashboard.

    Usage:
        service = AnalyticsService(db_session)

        success_rate = service.get_workflow_success_rate(template_id)
        avg_duration = service.get_average_workflow_duration(template_id)
        failures = service.get_step_failure_analysis(template_id)
        comparison = service.get_prompt_version_comparison(prompt_template_id)
        summary = service.get_dashboard_summary(template_id)
    """

    def __init__(self, db: Session):
        self.db = db

    def get_workflow_success_rate(
        self,
        template_id: int,
        tenant_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> float:
        """Calculate success rate over completed/failed runs in range.

        Args:
            template_id: Workflow template ID
            tenant_id: Tenant ID for isolation (from JWT)
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Success rate (0.0 when no terminal runs exist)
        """
        query = self.db.query(WorkflowRun).filter(
            WorkflowRun.template_id == template_id,
            WorkflowRun.tenant_id == tenant_id,
            WorkflowRun.status.in_(
                [WorkflowRunStatus.COMPLETED, WorkflowRunStatus.FAILED]
            ),
        )

        if start_date:
            query = query.filter(WorkflowRun.created_at >= start_date)
        if end_date:
            query = query.filter(WorkflowRun.created_at <= end_date)

        total_count = query.count()
        if total_count == 0:
            return 0.0

        success_count = query.filter(
            WorkflowRun.status == WorkflowRunStatus.COMPLETED
        ).count()

        return success_count / total_count

    def get_average_workflow_duration(
        self,
        template_id: int,
        tenant_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Optional[float]:
        """Average duration (seconds) for completed workflows in range.

        Args:
            template_id: Workflow template ID
            tenant_id: Tenant ID for isolation (from JWT)
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Average duration in seconds (None when no completed workflows exist)
        """
        query = self.db.query(WorkflowRun).filter(
            WorkflowRun.template_id == template_id,
            WorkflowRun.tenant_id == tenant_id,
            WorkflowRun.status == WorkflowRunStatus.COMPLETED,
            WorkflowRun.started_at.isnot(None),
            WorkflowRun.completed_at.isnot(None),
        )

        if start_date:
            query = query.filter(WorkflowRun.created_at >= start_date)
        if end_date:
            query = query.filter(WorkflowRun.created_at <= end_date)

        workflows = query.all()
        if not workflows:
            return None

        durations = [
            (w.completed_at - w.started_at).total_seconds() for w in workflows
        ]
        return sum(durations) / len(durations)

    def get_step_failure_analysis(
        self,
        template_id: int,
        tenant_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Per-step failure analysis across runs of a template.

        Args:
            template_id: Workflow template ID
            tenant_id: Tenant ID for isolation (from JWT)
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dict mapping step_name to {total_executions, failed_executions, failure_rate}
        """
        query = self.db.query(WorkflowStepExecution).join(
            WorkflowRun, WorkflowStepExecution.workflow_run_id == WorkflowRun.id
        ).filter(
            WorkflowRun.template_id == template_id,
            WorkflowRun.tenant_id == tenant_id
        )

        if start_date:
            query = query.filter(WorkflowRun.created_at >= start_date)
        if end_date:
            query = query.filter(WorkflowRun.created_at <= end_date)

        executions = query.all()

        step_stats: Dict[str, Dict[str, int]] = {}
        for execution in executions:
            step_name = execution.step_name
            if step_name not in step_stats:
                step_stats[step_name] = {"total": 0, "failed": 0}
            step_stats[step_name]["total"] += 1
            if execution.status == StepStatus.FAILED:
                step_stats[step_name]["failed"] += 1

        analysis: Dict[str, Dict[str, Any]] = {}
        for step_name, stats in step_stats.items():
            total = stats["total"]
            failed = stats["failed"]
            analysis[step_name] = {
                "total_executions": total,
                "failed_executions": failed,
                "failure_rate": failed / total if total > 0 else 0.0,
            }

        return analysis

    def get_prompt_version_comparison(
        self,
        template_id: int,
        tenant_id: int
    ) -> List[Dict[str, Any]]:
        """Compare metrics across all versions of a prompt template.

        Args:
            template_id: Workflow template ID
            tenant_id: Tenant ID for isolation (from JWT)

        Returns a list sorted by version_number.
        """
        versions = (
            self.db.query(PromptTemplateVersion)
            .filter(
                PromptTemplateVersion.template_id == template_id,
                PromptTemplateVersion.tenant_id == tenant_id
            )
            .order_by(PromptTemplateVersion.version_number)
            .all()
        )

        comparison = []
        for version in versions:
            success_rate = version.calculate_success_rate()
            comparison.append(
                {
                    "version_number": version.version_number,
                    "usage_count": version.usage_count,
                    "success_count": version.success_count,
                    "success_rate": success_rate if success_rate is not None else 0.0,
                    "avg_latency_ms": version.avg_latency_ms,
                    "is_active": version.is_active,
                    "created_at": version.created_at.isoformat(),
                }
            )

        return comparison

    def get_dashboard_summary(self, template_id: int, tenant_id: int) -> Dict[str, Any]:
        """Aggregate summary metrics for a workflow template.

        Args:
            template_id: Workflow template ID
            tenant_id: Tenant ID for isolation (from JWT)

        Returns:
            Dictionary with success_rate, avg_duration_seconds, step_failures, total_runs
        """
        total_runs = (
            self.db.query(WorkflowRun)
            .filter(
                WorkflowRun.template_id == template_id,
                WorkflowRun.tenant_id == tenant_id
            )
            .count()
        )
        return {
            "success_rate": self.get_workflow_success_rate(template_id, tenant_id),
            "avg_duration_seconds": self.get_average_workflow_duration(template_id, tenant_id),
            "step_failures": self.get_step_failure_analysis(template_id, tenant_id),
            "total_runs": total_runs,
        }
