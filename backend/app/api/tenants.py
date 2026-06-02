"""Tenant management API endpoints (admin-only)."""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, validator
import re

from app.api.auth_deps import get_admin_user, get_db
from app.models.models import Tenant, User

router = APIRouter()


# Pydantic Schemas
class TenantCreate(BaseModel):
    """Schema for creating a new tenant."""
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255)

    @validator('slug')
    def validate_slug(cls, v):
        """Validate slug format: lowercase, alphanumeric, hyphens only."""
        if not re.match(r'^[a-z0-9-]+$', v):
            raise ValueError('Slug must be lowercase alphanumeric with hyphens only (no spaces)')
        return v


class TenantUpdate(BaseModel):
    """Schema for updating a tenant."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(None, min_length=1, max_length=255)

    @validator('slug')
    def validate_slug(cls, v):
        """Validate slug format if provided."""
        if v is not None and not re.match(r'^[a-z0-9-]+$', v):
            raise ValueError('Slug must be lowercase alphanumeric with hyphens only (no spaces)')
        return v


class TenantResponse(BaseModel):
    """Schema for tenant response."""
    id: int
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Endpoints
@router.post("/tenants", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    tenant_data: TenantCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    """
    Create a new tenant (admin-only).

    Validates:
    - Slug format (lowercase, alphanumeric, hyphens only)
    - Name uniqueness
    - Slug uniqueness
    """
    # Check for duplicate name
    existing_name = db.query(Tenant).filter(Tenant.name == tenant_data.name).first()
    if existing_name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant with name '{tenant_data.name}' already exists",
        )

    # Check for duplicate slug
    existing_slug = db.query(Tenant).filter(Tenant.slug == tenant_data.slug).first()
    if existing_slug:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant with slug '{tenant_data.slug}' already exists",
        )

    # Create tenant
    new_tenant = Tenant(
        name=tenant_data.name,
        slug=tenant_data.slug,
    )
    db.add(new_tenant)
    db.commit()
    db.refresh(new_tenant)

    return new_tenant


@router.get("/tenants", response_model=List[TenantResponse])
async def list_tenants(
    db: Session = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    """
    List all tenants (admin-only).

    Returns all tenants without filtering by current user's tenant.
    """
    tenants = db.query(Tenant).order_by(Tenant.created_at.desc()).all()
    return tenants


@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    """
    Get specific tenant by ID (admin-only).
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant with ID {tenant_id} not found",
        )
    return tenant


@router.patch("/tenants/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: int,
    tenant_data: TenantUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    """
    Update tenant name and/or slug (admin-only).

    Validates:
    - Slug format if provided
    - Name uniqueness if changed
    - Slug uniqueness if changed
    """
    # Get existing tenant
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant with ID {tenant_id} not found",
        )

    # Check for duplicate name if changing
    if tenant_data.name and tenant_data.name != tenant.name:
        existing_name = db.query(Tenant).filter(Tenant.name == tenant_data.name).first()
        if existing_name:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Tenant with name '{tenant_data.name}' already exists",
            )
        tenant.name = tenant_data.name

    # Check for duplicate slug if changing
    if tenant_data.slug and tenant_data.slug != tenant.slug:
        existing_slug = db.query(Tenant).filter(Tenant.slug == tenant_data.slug).first()
        if existing_slug:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Tenant with slug '{tenant_data.slug}' already exists",
            )
        tenant.slug = tenant_data.slug

    # Update timestamp (SQLAlchemy onupdate should handle this, but explicit is safer)
    tenant.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(tenant)

    return tenant
