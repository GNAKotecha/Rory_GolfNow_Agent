"""Pydantic schemas for analytics API responses."""
from typing import Dict, Optional

from pydantic import BaseModel


class WorkflowAnalyticsResponse(BaseModel):
    """Response schema for workflow analytics."""

    success_rate: float
    avg_duration_seconds: Optional[float]
    total_runs: int


class StepFailureAnalysis(BaseModel):
    """Step failure analysis."""

    step_name: str
    total_executions: int
    failed_executions: int
    failure_rate: float


class PromptVersionMetrics(BaseModel):
    """Metrics for a prompt template version."""

    version_number: int
    usage_count: int
    success_count: int
    success_rate: float
    avg_latency_ms: Optional[float]
    is_active: bool
    created_at: str


class StepFailureBreakdown(BaseModel):
    """Per-step failure counts and rate for a single step.

    Nested value type used in DashboardSummaryResponse.step_failures.
    """

    total_executions: int
    failed_executions: int
    failure_rate: float


class DashboardSummaryResponse(BaseModel):
    """Dashboard summary response."""

    success_rate: float
    avg_duration_seconds: Optional[float]
    step_failures: Dict[str, StepFailureBreakdown]
    total_runs: int
