"""Analytics API endpoints for workflow and prompt metrics."""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth_deps import get_approved_user
from app.db.session import get_db
from app.models.models import User
from app.models.workflow import WorkflowRun
from app.schemas.analytics import (
    DashboardSummaryResponse,
    PromptVersionMetrics,
    StepFailureAnalysis,
    WorkflowAnalyticsResponse,
)
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


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
    service = AnalyticsService(db)
    total_runs = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.template_id == template_id)
        .count()
    )
    return WorkflowAnalyticsResponse(
        success_rate=service.get_workflow_success_rate(template_id),
        avg_duration_seconds=service.get_average_workflow_duration(template_id),
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
    service = AnalyticsService(db)
    analysis = service.get_step_failure_analysis(template_id)
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
    service = AnalyticsService(db)
    return service.get_prompt_version_comparison(template_id)


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
    service = AnalyticsService(db)
    return service.get_dashboard_summary(template_id)
