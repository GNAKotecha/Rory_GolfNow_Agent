"""Analytics API endpoints for workflow and prompt metrics."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.auth_deps import get_approved_user
from app.db.session import get_db
from app.models.models import User
from app.models.workflow import WorkflowRun, WorkflowTemplate
from app.schemas.analytics import (
    DashboardSummaryResponse,
    PromptVersionMetrics,
    StepFailureAnalysis,
    WorkflowAnalyticsResponse,
)
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _get_workflow_template_or_404(db: Session, template_id: int, tenant_id: int) -> WorkflowTemplate:
    """Fetch workflow template or raise 404. Enforces tenant isolation."""
    template = db.query(WorkflowTemplate).filter(
        WorkflowTemplate.id == template_id,
        WorkflowTemplate.tenant_id == tenant_id,
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail=f"Workflow template {template_id} not found")
    return template


@router.get(
    "/workflows/{template_id}/success-rate",
    response_model=WorkflowAnalyticsResponse,
)
async def get_workflow_success_rate(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_approved_user),
):
    """Get workflow success rate and basic metrics for a template."""
    tenant_id = current_user.tenant_id
    _get_workflow_template_or_404(db, template_id, tenant_id)
    service = AnalyticsService(db)
    total_runs = (
        db.query(WorkflowRun)
        .filter(
            WorkflowRun.template_id == template_id,
            WorkflowRun.tenant_id == tenant_id,
        )
        .count()
    )
    return WorkflowAnalyticsResponse(
        success_rate=service.get_workflow_success_rate(template_id, tenant_id),
        avg_duration_seconds=service.get_average_workflow_duration(template_id, tenant_id),
        total_runs=total_runs,
    )


@router.get(
    "/workflows/{template_id}/step-failures",
    response_model=List[StepFailureAnalysis],
)
async def get_step_failure_analysis(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_approved_user),
):
    """Get step-by-step failure analysis for a workflow template."""
    tenant_id = current_user.tenant_id
    _get_workflow_template_or_404(db, template_id, tenant_id)
    service = AnalyticsService(db)
    analysis = service.get_step_failure_analysis(template_id, tenant_id)
    return [
        StepFailureAnalysis(step_name=step_name, **stats)
        for step_name, stats in analysis.items()
    ]


@router.get(
    "/prompts/{template_id}/version-comparison",
    response_model=List[PromptVersionMetrics],
)
async def get_prompt_version_comparison(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_approved_user),
):
    """Compare performance across all versions of a prompt template."""
    tenant_id = current_user.tenant_id
    service = AnalyticsService(db)
    return service.get_prompt_version_comparison(template_id, tenant_id)


@router.get(
    "/dashboard/{template_id}",
    response_model=DashboardSummaryResponse,
)
async def get_dashboard_summary(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_approved_user),
):
    """Get dashboard summary statistics for a workflow template."""
    tenant_id = current_user.tenant_id
    _get_workflow_template_or_404(db, template_id, tenant_id)
    service = AnalyticsService(db)
    return service.get_dashboard_summary(template_id, tenant_id)
