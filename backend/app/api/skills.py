"""Skills API endpoints for tenant-scoped skills management."""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime

from app.db.session import get_db
from app.api.auth_deps import get_current_user_tenant_id, get_current_user, get_approved_user
from app.services.skill_workflow_service import SkillWorkflowService
from app.services.skill_discovery import SkillDiscoveryService
from app.dependencies import get_skill_discovery_service
from app.models.models import User
from app.utils.skill_invoker import invoke_skill


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


class InvokeSkillRequest(BaseModel):
    """Request schema for skill invocation."""
    skill_name: str
    context: Dict[str, Any] = {}


class InvokeSkillResponse(BaseModel):
    """Response schema for skill invocation."""
    success: bool
    skill_name: str
    message: str
    context: Dict[str, Any]


class MatchSkillRequest(BaseModel):
    """Request schema for intent-based skill matching."""
    user_message: str


class MatchSkillResponse(BaseModel):
    """Response schema for skill matching."""
    matched: bool
    skill: Optional[TenantSkillResponse] = None


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


# Skill Invocation Endpoints

@router.post("/invoke", response_model=InvokeSkillResponse)
def invoke_skill_endpoint(
    request: InvokeSkillRequest,
    current_user: User = Depends(get_approved_user),
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
    skill_service: SkillDiscoveryService = Depends(get_skill_discovery_service),
):
    """
    Invoke a skill by name with the provided context.

    Validates that the skill exists and belongs to the current tenant
    before invoking it. Currently returns mock responses as actual
    skill execution is not yet implemented.

    Args:
        request: Skill invocation request with skill_name and context
        current_user: Authenticated user (injected)
        tenant_id: Current user's tenant ID (injected)
        db: Database session (injected)
        skill_service: Skill discovery service (injected)

    Returns:
        Skill execution result with success status and message

    Raises:
        401: If user is not authenticated
        404: If skill not found or doesn't belong to tenant
        500: If skill execution fails
    """
    # Get all skills for tenant and check if requested skill exists
    skills = skill_service.get_skills(tenant_id)
    skill_names = {skill.skill_name for skill in skills}

    if request.skill_name not in skill_names:
        raise HTTPException(
            status_code=404,
            detail=f"Skill '{request.skill_name}' not found for this tenant"
        )

    try:
        # Invoke the skill
        result = invoke_skill(
            skill_name=request.skill_name,
            context=request.context,
            tenant_id=tenant_id
        )
        return InvokeSkillResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Skill execution failed: {str(e)}"
        )


@router.post("/match", response_model=MatchSkillResponse)
def match_skill_endpoint(
    request: MatchSkillRequest,
    current_user: User = Depends(get_approved_user),
    tenant_id: int = Depends(get_current_user_tenant_id),
    skill_service: SkillDiscoveryService = Depends(get_skill_discovery_service),
):
    """
    Match a user message to a skill using intent pattern matching.

    Searches through active skills for the current tenant and attempts
    to match the user message against configured intent patterns using
    regex pattern matching.

    Args:
        request: Match request with user_message
        current_user: Authenticated user (injected)
        tenant_id: Current user's tenant ID (injected)
        skill_service: Skill discovery service (injected)

    Returns:
        Match result with matched flag and skill details if found

    Raises:
        401: If user is not authenticated
    """
    matched_skill = skill_service.match_skill_by_intent(
        user_message=request.user_message,
        tenant_id=tenant_id
    )

    if matched_skill:
        # Convert to dict and add required fields for TenantSkillResponse
        skill_dict = {
            "id": matched_skill.id,
            "tenant_id": matched_skill.tenant_id,
            "skill_name": matched_skill.skill_name,
            "description": matched_skill.description,
            "skill_data": matched_skill.skill_data or {},
            "version": matched_skill.version,
            "is_active": matched_skill.is_active,
            "created_at": matched_skill.created_at,
            "updated_at": matched_skill.updated_at,
            "created_by": matched_skill.created_by
        }
        return MatchSkillResponse(
            matched=True,
            skill=TenantSkillResponse(**skill_dict)
        )
    else:
        return MatchSkillResponse(matched=False, skill=None)
