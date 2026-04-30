"""Workflow-related Pydantic schemas for API requests and responses."""
from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from app.models.models import WorkflowCategory
from app.models.workflow import WorkflowRunStatus, StepStatus


class WorkflowTemplateCreate(BaseModel):
    """Schema for creating workflow template."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    version: str = Field(..., pattern=r'^\d+\.\d+\.\d+$')
    workflow_category: WorkflowCategory
    definition: Dict[str, Any] = Field(..., description="Workflow definition as JSON")


class WorkflowTemplateResponse(BaseModel):
    """Schema for workflow template response."""
    id: int
    name: str
    description: Optional[str]
    version: str
    workflow_category: WorkflowCategory
    definition: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkflowRunCreate(BaseModel):
    """Schema for creating workflow run."""
    template_name: str = Field(..., min_length=1)
    session_id: int = Field(..., gt=0)
    input_data: Dict[str, Any] = Field(default_factory=dict)


class WorkflowRunResponse(BaseModel):
    """Schema for workflow run response."""
    id: int
    template_id: int
    session_id: int
    status: WorkflowRunStatus
    workflow_category: WorkflowCategory
    input_data: Dict[str, Any]
    state: Dict[str, Any]
    output_data: Optional[Dict[str, Any]]
    started_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class WorkflowStepExecutionResponse(BaseModel):
    """Schema for step execution response."""
    id: int
    workflow_run_id: int
    step_id: str
    step_name: str
    step_type: str
    status: StepStatus
    inputs: Optional[Dict[str, Any]]
    outputs: Optional[Dict[str, Any]]
    error: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True
