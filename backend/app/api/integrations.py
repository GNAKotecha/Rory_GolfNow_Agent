"""API endpoints for tenant MCP integrations management."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, validator
from datetime import datetime

from app.db.session import get_db
from app.models.models import TenantMCPIntegration, User
from app.api.auth_deps import get_approved_user, get_current_user_tenant_id

router = APIRouter(prefix="/integrations", tags=["integrations"])

# Valid auth types
VALID_AUTH_TYPES = {"oauth", "api_key", "pat"}


# Pydantic Schemas
class TenantMCPIntegrationCreate(BaseModel):
    """Schema for creating a new MCP integration."""
    integration_name: str
    auth_type: str
    config: dict = {}

    @validator("auth_type")
    def validate_auth_type(cls, v):
        """Validate that auth_type is one of the allowed values."""
        if v not in VALID_AUTH_TYPES:
            raise ValueError(f"auth_type must be one of: {', '.join(VALID_AUTH_TYPES)}")
        return v


class TenantMCPIntegrationUpdate(BaseModel):
    """Schema for updating an existing MCP integration."""
    integration_name: Optional[str] = None
    config: Optional[dict] = None
    is_enabled: Optional[bool] = None


class TenantMCPIntegrationResponse(BaseModel):
    """Schema for MCP integration response."""
    id: int
    tenant_id: int
    integration_name: str
    auth_type: str
    config: dict
    is_enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# REST Endpoints
@router.post("", response_model=TenantMCPIntegrationResponse, status_code=status.HTTP_201_CREATED)
def create_integration(
    integration_data: TenantMCPIntegrationCreate,
    current_user: User = Depends(get_approved_user),
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
):
    """Create a new MCP integration for the authenticated tenant."""
    # Validate auth_type
    if integration_data.auth_type not in VALID_AUTH_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid auth_type. Must be one of: {', '.join(VALID_AUTH_TYPES)}"
        )

    # Check for duplicate integration_name in same tenant
    existing = db.query(TenantMCPIntegration).filter(
        TenantMCPIntegration.tenant_id == tenant_id,
        TenantMCPIntegration.integration_name == integration_data.integration_name
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Integration '{integration_data.integration_name}' already exists for this tenant"
        )

    # Create integration
    integration = TenantMCPIntegration(
        tenant_id=tenant_id,
        integration_name=integration_data.integration_name,
        auth_type=integration_data.auth_type,
        config=integration_data.config,
    )

    try:
        db.add(integration)
        db.commit()
        db.refresh(integration)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Integration '{integration_data.integration_name}' already exists for this tenant"
        )

    return integration


@router.get("", response_model=List[TenantMCPIntegrationResponse])
def list_integrations(
    current_user: User = Depends(get_approved_user),
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
):
    """List all MCP integrations for the authenticated tenant."""
    integrations = db.query(TenantMCPIntegration).filter(
        TenantMCPIntegration.tenant_id == tenant_id
    ).order_by(TenantMCPIntegration.created_at.desc()).all()

    return integrations


@router.get("/{integration_id}", response_model=TenantMCPIntegrationResponse)
def get_integration(
    integration_id: int,
    current_user: User = Depends(get_approved_user),
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
):
    """Get details of a specific MCP integration (must belong to tenant)."""
    integration = db.query(TenantMCPIntegration).filter(
        TenantMCPIntegration.id == integration_id,
        TenantMCPIntegration.tenant_id == tenant_id
    ).first()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found"
        )

    return integration


@router.patch("/{integration_id}", response_model=TenantMCPIntegrationResponse)
def update_integration(
    integration_id: int,
    update_data: TenantMCPIntegrationUpdate,
    current_user: User = Depends(get_approved_user),
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
):
    """Update an MCP integration (must belong to tenant)."""
    # Fetch integration with tenant isolation
    integration = db.query(TenantMCPIntegration).filter(
        TenantMCPIntegration.id == integration_id,
        TenantMCPIntegration.tenant_id == tenant_id
    ).first()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found"
        )

    # Update fields
    if update_data.integration_name is not None:
        integration.integration_name = update_data.integration_name
    if update_data.config is not None:
        integration.config = update_data.config
    if update_data.is_enabled is not None:
        integration.is_enabled = update_data.is_enabled

    try:
        db.commit()
        db.refresh(integration)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Integration '{update_data.integration_name}' already exists for this tenant"
        )

    return integration


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_integration(
    integration_id: int,
    current_user: User = Depends(get_approved_user),
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
):
    """Remove an MCP integration (must belong to tenant)."""
    integration = db.query(TenantMCPIntegration).filter(
        TenantMCPIntegration.id == integration_id,
        TenantMCPIntegration.tenant_id == tenant_id
    ).first()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found"
        )

    db.delete(integration)
    db.commit()


@router.post("/{integration_id}/enable", response_model=TenantMCPIntegrationResponse)
def enable_integration(
    integration_id: int,
    current_user: User = Depends(get_approved_user),
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
):
    """Enable an MCP integration (must belong to tenant)."""
    integration = db.query(TenantMCPIntegration).filter(
        TenantMCPIntegration.id == integration_id,
        TenantMCPIntegration.tenant_id == tenant_id
    ).first()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found"
        )

    integration.is_enabled = True
    db.commit()
    db.refresh(integration)

    return integration


@router.post("/{integration_id}/disable", response_model=TenantMCPIntegrationResponse)
def disable_integration(
    integration_id: int,
    current_user: User = Depends(get_approved_user),
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
):
    """Disable an MCP integration (must belong to tenant)."""
    integration = db.query(TenantMCPIntegration).filter(
        TenantMCPIntegration.id == integration_id,
        TenantMCPIntegration.tenant_id == tenant_id
    ).first()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found"
        )

    integration.is_enabled = False
    db.commit()
    db.refresh(integration)

    return integration


@router.post("/{integration_id}/health")
def health_check(
    integration_id: int,
    current_user: User = Depends(get_approved_user),
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
):
    """Perform health check on an MCP integration (must belong to tenant)."""
    integration = db.query(TenantMCPIntegration).filter(
        TenantMCPIntegration.id == integration_id,
        TenantMCPIntegration.tenant_id == tenant_id
    ).first()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found"
        )

    # Basic health check: verify integration exists and is configured
    return {
        "status": "healthy" if integration.is_enabled else "disabled",
        "integration_id": integration.id,
        "integration_name": integration.integration_name,
        "is_enabled": integration.is_enabled,
        "checked_at": datetime.utcnow().isoformat()
    }
