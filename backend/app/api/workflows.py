"""Workflows API endpoints for tenant-scoped workflows management."""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime

from app.db.session import get_db
from app.api.auth_deps import get_current_user_tenant_id, get_current_user
from app.services.skill_workflow_service import SkillWorkflowService
from app.models.models import User


router = APIRouter(prefix="/workflows", tags=["workflows"])


# Pydantic Schemas
class TenantWorkflowCreate(BaseModel):
    """Schema for creating a new workflow."""
    workflow_name: str
    description: Optional[str] = None
    workflow_definition: Dict[str, Any]


class TenantWorkflowUpdate(BaseModel):
    """Schema for updating a workflow."""
    description: Optional[str] = None
    workflow_definition: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    active_version: Optional[int] = None


class TenantWorkflowResponse(BaseModel):
    """Schema for workflow responses."""
    id: int
    tenant_id: int
    workflow_name: str
    description: Optional[str]
    workflow_definition: Dict[str, Any]
    version: int
    is_active: bool
    active_version: Optional[int]
    created_at: datetime
    updated_at: datetime
    created_by: Optional[int]

    class Config:
        from_attributes = True


# API Endpoints

@router.get("", response_model=Dict[str, List[TenantWorkflowResponse]])
def list_workflows(
    active_only: bool = Query(False, description="Filter to only active workflows"),
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
):
    """
    List all workflows for the authenticated user's tenant.

    Query Parameters:
    - active_only: If true, only return active workflows
    """
    workflows = SkillWorkflowService.list_workflows(
        db=db,
        tenant_id=tenant_id,
        active_only=active_only
    )
    return {"workflows": workflows}


@router.post("", response_model=TenantWorkflowResponse, status_code=status.HTTP_201_CREATED)
def create_workflow(
    workflow_create: TenantWorkflowCreate,
    tenant_id: int = Depends(get_current_user_tenant_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a new workflow for the tenant.

    The workflow will be created with version=1, is_active=False, and active_version=None.

    Raises:
    - 409 Conflict: If a workflow with the same name already exists
    - 422 Unprocessable Entity: If validation fails
    """
    workflow = SkillWorkflowService.create_workflow(
        db=db,
        tenant_id=tenant_id,
        workflow_name=workflow_create.workflow_name,
        workflow_definition=workflow_create.workflow_definition,
        description=workflow_create.description,
        created_by=current_user.id
    )
    return workflow


@router.get("/{workflow_id}", response_model=TenantWorkflowResponse)
def get_workflow(
    workflow_id: int,
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Get a specific workflow by ID.

    Raises:
    - 404 Not Found: If workflow doesn't exist or belongs to another tenant
    """
    workflow = SkillWorkflowService.get_workflow(
        db=db,
        workflow_id=workflow_id,
        tenant_id=tenant_id
    )
    return workflow


@router.patch("/{workflow_id}", response_model=TenantWorkflowResponse)
def update_workflow(
    workflow_id: int,
    workflow_update: TenantWorkflowUpdate,
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Update a workflow.

    Only provided fields will be updated.

    Raises:
    - 404 Not Found: If workflow doesn't exist or belongs to another tenant
    """
    workflow = SkillWorkflowService.update_workflow(
        db=db,
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        description=workflow_update.description,
        workflow_definition=workflow_update.workflow_definition,
        is_active=workflow_update.is_active,
        active_version=workflow_update.active_version
    )
    return workflow


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(
    workflow_id: int,
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Delete all versions of a workflow.

    This will delete all versions of the workflow with the same workflow_name.

    Raises:
    - 404 Not Found: If workflow doesn't exist or belongs to another tenant
    """
    SkillWorkflowService.delete_workflow(
        db=db,
        workflow_id=workflow_id,
        tenant_id=tenant_id
    )
    return None


@router.post("/{workflow_id}/activate", response_model=TenantWorkflowResponse)
def activate_workflow(
    workflow_id: int,
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Activate a specific workflow version.

    This sets is_active=True for the target version, is_active=False for all
    other versions, and sets active_version to the target workflow ID for all versions.

    Raises:
    - 404 Not Found: If workflow doesn't exist or belongs to another tenant
    """
    workflow = SkillWorkflowService.activate_workflow_version(
        db=db,
        workflow_id=workflow_id,
        tenant_id=tenant_id
    )
    return workflow
