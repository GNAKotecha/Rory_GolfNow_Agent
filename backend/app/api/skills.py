"""Skills API endpoints for tenant-scoped skills management."""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime

from app.db.session import get_db
from app.api.auth_deps import get_current_user_tenant_id, get_current_user
from app.services.skill_workflow_service import SkillWorkflowService
from app.models.models import User


router = APIRouter(prefix="/skills", tags=["skills"])


# Pydantic Schemas
class TenantSkillCreate(BaseModel):
    """Schema for creating a new skill."""
    skill_name: str
    description: Optional[str] = None
    skill_data: Dict[str, Any]


class TenantSkillUpdate(BaseModel):
    """Schema for updating a skill."""
    description: Optional[str] = None
    skill_data: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class TenantSkillResponse(BaseModel):
    """Schema for skill responses."""
    id: int
    tenant_id: int
    skill_name: str
    description: Optional[str]
    skill_data: Dict[str, Any]
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: Optional[int]

    class Config:
        from_attributes = True


# API Endpoints

@router.get("", response_model=Dict[str, List[TenantSkillResponse]])
def list_skills(
    active_only: bool = Query(False, description="Filter to only active skills"),
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
):
    """
    List all skills for the authenticated user's tenant.

    Query Parameters:
    - active_only: If true, only return active skills
    """
    skills = SkillWorkflowService.list_skills(
        db=db,
        tenant_id=tenant_id,
        active_only=active_only
    )
    return {"skills": skills}


@router.post("", response_model=TenantSkillResponse, status_code=status.HTTP_201_CREATED)
def create_skill(
    skill_create: TenantSkillCreate,
    tenant_id: int = Depends(get_current_user_tenant_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a new skill for the tenant.

    The skill will be created with version=1 and is_active=False.

    Raises:
    - 409 Conflict: If a skill with the same name already exists
    - 422 Unprocessable Entity: If validation fails
    """
    skill = SkillWorkflowService.create_skill(
        db=db,
        tenant_id=tenant_id,
        skill_name=skill_create.skill_name,
        skill_data=skill_create.skill_data,
        description=skill_create.description,
        created_by=current_user.id
    )
    return skill


@router.get("/{skill_id}", response_model=TenantSkillResponse)
def get_skill(
    skill_id: int,
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Get a specific skill by ID.

    Raises:
    - 404 Not Found: If skill doesn't exist or belongs to another tenant
    """
    skill = SkillWorkflowService.get_skill(
        db=db,
        skill_id=skill_id,
        tenant_id=tenant_id
    )
    return skill


@router.patch("/{skill_id}", response_model=TenantSkillResponse)
def update_skill(
    skill_id: int,
    skill_update: TenantSkillUpdate,
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Update a skill.

    Only provided fields will be updated.

    Raises:
    - 404 Not Found: If skill doesn't exist or belongs to another tenant
    """
    skill = SkillWorkflowService.update_skill(
        db=db,
        skill_id=skill_id,
        tenant_id=tenant_id,
        description=skill_update.description,
        skill_data=skill_update.skill_data,
        is_active=skill_update.is_active
    )
    return skill


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_skill(
    skill_id: int,
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Delete all versions of a skill.

    This will delete all versions of the skill with the same skill_name.

    Raises:
    - 404 Not Found: If skill doesn't exist or belongs to another tenant
    """
    SkillWorkflowService.delete_skill(
        db=db,
        skill_id=skill_id,
        tenant_id=tenant_id
    )
    return None


@router.post("/{skill_id}/activate", response_model=TenantSkillResponse)
def activate_skill(
    skill_id: int,
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Activate a specific skill version.

    This sets is_active=True for the target version and is_active=False
    for all other versions of the same skill_name.

    Raises:
    - 404 Not Found: If skill doesn't exist or belongs to another tenant
    """
    skill = SkillWorkflowService.activate_skill_version(
        db=db,
        skill_id=skill_id,
        tenant_id=tenant_id
    )
    return skill
