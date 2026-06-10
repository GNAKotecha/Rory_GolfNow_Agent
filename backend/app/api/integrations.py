"""API endpoints for tenant MCP integrations management."""
import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, validator
from datetime import datetime

from app.db.session import get_db
from app.models.models import TenantMCPIntegration, User
from app.models.external_credential import ExternalCredential, CredentialType
from app.api.auth_deps import get_approved_user, get_current_user_tenant_id
from app.services.oauth_service import OAuthService
from app.services.credential_service import CredentialService
from gateway_mcp.core.credentials import CredentialEncryption


def get_tenant_mcp_manager():
    """Dependency to get the global tenant MCP connection manager."""
    from app.main import get_global_tenant_mcp_manager
    manager = get_global_tenant_mcp_manager()
    if manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tenant MCP manager not initialized"
        )
    return manager

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
async def create_integration(
    integration_data: TenantMCPIntegrationCreate,
    current_user: User = Depends(get_approved_user),
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
    manager = Depends(get_tenant_mcp_manager),
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

    # Auto-connect if enabled and has credentials
    if integration.is_enabled:
        # Check if credentials exist
        credential = db.query(ExternalCredential).filter(
            ExternalCredential.integration_id == integration.id
        ).first()

        if credential:
            try:
                await manager.connect_integration(integration.id)
            except Exception as e:
                # Log error but don't fail the request
                import logging
                logging.error(f"Failed to auto-connect integration {integration.id}: {e}")

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
async def delete_integration(
    integration_id: int,
    current_user: User = Depends(get_approved_user),
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
    manager = Depends(get_tenant_mcp_manager),
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

    # Disconnect before deleting
    try:
        await manager.disconnect_integration(integration_id)
    except Exception as e:
        import logging
        logging.error(f"Failed to disconnect integration {integration_id} before delete: {e}")

    db.delete(integration)
    db.commit()


@router.post("/{integration_id}/enable", response_model=TenantMCPIntegrationResponse)
async def enable_integration(
    integration_id: int,
    current_user: User = Depends(get_approved_user),
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
    manager = Depends(get_tenant_mcp_manager),
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

    # Connect the integration
    try:
        await manager.connect_integration(integration_id)
    except Exception as e:
        import logging
        logging.error(f"Failed to connect integration {integration_id} after enable: {e}")
        # Don't fail the request - integration is enabled in DB even if connection failed

    return integration


@router.post("/{integration_id}/disable", response_model=TenantMCPIntegrationResponse)
async def disable_integration(
    integration_id: int,
    current_user: User = Depends(get_approved_user),
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
    manager = Depends(get_tenant_mcp_manager),
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

    # Disconnect the integration
    try:
        await manager.disconnect_integration(integration_id)
    except Exception as e:
        import logging
        logging.error(f"Failed to disconnect integration {integration_id} after disable: {e}")

    return integration


@router.post("/{integration_id}/health")
async def health_check(
    integration_id: int,
    current_user: User = Depends(get_approved_user),
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
    manager = Depends(get_tenant_mcp_manager),
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

    # Get connection status from manager
    connection_status = await manager.get_connection_status(integration_id)

    return {
        "status": "healthy" if (integration.is_enabled and connection_status.get("healthy")) else "degraded",
        "integration_id": integration.id,
        "integration_name": integration.integration_name,
        "is_enabled": integration.is_enabled,
        "connected": connection_status.get("connected", False),
        "healthy": connection_status.get("healthy", False),
        "error": connection_status.get("error"),
        "checked_at": datetime.utcnow().isoformat()
    }


# OAuth Response Schemas
class OAuthInitiateResponse(BaseModel):
    """Response for OAuth initiate endpoint."""
    authorization_url: str
    state: str


class OAuthCallbackResponse(BaseModel):
    """Response for OAuth callback endpoint."""
    success: bool
    message: str
    credential_id: Optional[int] = None


# OAuth Endpoints
@router.post("/{integration_id}/oauth/initiate", response_model=OAuthInitiateResponse)
def oauth_initiate(
    integration_id: int,
    current_user: User = Depends(get_approved_user),
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
):
    """Start OAuth authorization flow for an integration.

    Args:
        integration_id: ID of the integration to authorize
        current_user: Authenticated user
        tenant_id: Current user's tenant ID
        db: Database session

    Returns:
        OAuth authorization URL and state token

    Raises:
        404: Integration not found or doesn't belong to tenant
    """
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

    # Generate state token
    state = OAuthService.generate_state_token()

    # Store state with metadata
    state_store = OAuthService.get_state_store()
    state_store.store(
        state=state,
        data={
            "integration_id": integration_id,
            "tenant_id": tenant_id,
            "user_id": current_user.id,
            "integration_name": integration.integration_name
        },
        tenant_id=tenant_id
    )

    # Build authorization URL
    base_url = os.environ.get("BACKEND_URL", "http://localhost:8000")
    callback_url = f"{base_url}/api/integrations/{integration_id}/oauth/callback"

    authorization_url = OAuthService.build_authorize_url(
        integration_name=integration.integration_name,
        config=integration.config,
        state=state,
        base_url=callback_url
    )

    return OAuthInitiateResponse(
        authorization_url=authorization_url,
        state=state
    )


@router.get("/{integration_id}/oauth/callback", response_model=OAuthCallbackResponse)
def oauth_callback(
    integration_id: int,
    code: str = Query(..., description="Authorization code from OAuth provider"),
    state: str = Query(..., description="State token for CSRF protection"),
    current_user: User = Depends(get_approved_user),
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
):
    """Handle OAuth callback and store credentials.

    Args:
        integration_id: ID of the integration
        code: Authorization code from OAuth provider
        state: State token for validation
        current_user: Authenticated user
        tenant_id: Current user's tenant ID
        db: Database session

    Returns:
        Success message and credential ID

    Raises:
        400: Invalid state token or token exchange failed
        403: State token belongs to different tenant
        404: Integration not found
    """
    # Validate state token
    state_store = OAuthService.get_state_store()
    state_data = state_store.retrieve(state, tenant_id=tenant_id)

    if not state_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state token or token expired"
        )

    # Verify tenant ownership
    if state_data.get("tenant_id") != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="State token belongs to different tenant"
        )

    # Verify integration ID matches
    if state_data.get("integration_id") != integration_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Integration ID mismatch"
        )

    # Fetch integration
    integration = db.query(TenantMCPIntegration).filter(
        TenantMCPIntegration.id == integration_id,
        TenantMCPIntegration.tenant_id == tenant_id
    ).first()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found"
        )

    # Exchange code for token
    try:
        token_data = OAuthService.exchange_code_for_token(
            integration_name=integration.integration_name,
            config=integration.config,
            code=code
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Token exchange failed: {str(e)}"
        )

    # Encrypt access token
    encryption_key = os.environ.get("GATEWAY_CREDENTIAL_ENCRYPTION_KEY")
    if not encryption_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Credential encryption not configured"
        )

    encryption = CredentialEncryption(encryption_key)
    encrypted_token = encryption.encrypt(token_data["access_token"])

    # Store credential
    credential = ExternalCredential(
        tenant_id=tenant_id,
        user_id=current_user.id,
        integration_id=integration_id,
        provider=integration.integration_name,
        credential_type=CredentialType.OAUTH,
        secret_enc=encrypted_token,
        scope=token_data.get("scope", ""),
    )

    db.add(credential)
    db.commit()
    db.refresh(credential)

    return OAuthCallbackResponse(
        success=True,
        message=f"OAuth credential stored successfully for {integration.integration_name}",
        credential_id=credential.id
    )


# API-key and PAT Credential Schemas
class StoreAPIKeyRequest(BaseModel):
    """Request schema for storing an API key."""
    api_key: str
    metadata: Optional[dict] = {}


class StorePATRequest(BaseModel):
    """Request schema for storing a PAT."""
    pat: str
    metadata: Optional[dict] = {}


class CredentialResponse(BaseModel):
    """Response schema for credential storage."""
    id: int
    integration_id: int
    credential_type: str
    stored_at: str
    verified: bool


class TestConnectionResponse(BaseModel):
    """Response schema for connection test."""
    status: str
    provider: str
    authenticated_user: Optional[str] = None
    error: Optional[str] = None


@router.post("/{integration_id}/credentials/api-key", status_code=status.HTTP_201_CREATED)
def store_api_key(
    integration_id: int,
    request: StoreAPIKeyRequest,
    current_user: User = Depends(get_approved_user),
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Store an API key credential for an integration.

    Validates the API key before storing by making a test request to the provider.
    Returns 400 if validation fails.
    """
    # Verify integration exists and belongs to tenant
    integration = db.query(TenantMCPIntegration).filter(
        TenantMCPIntegration.id == integration_id,
        TenantMCPIntegration.tenant_id == tenant_id
    ).first()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found"
        )

    # Get base_url from integration config
    base_url = integration.config.get("base_url", "")
    if not base_url and integration.integration_name not in ["github"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Integration config missing base_url"
        )

    # Initialize credential service
    credential_service = CredentialService(db)

    # Validate API key before storing
    is_valid = credential_service.validate_api_key(
        provider=integration.integration_name,
        api_key=request.api_key,
        base_url=base_url
    )

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"API key validation failed for {integration.integration_name}. "
                   "Please check that the key is valid and has appropriate permissions."
        )

    # Store the validated credential
    credential = credential_service.store_api_key_credential(
        user_id=current_user.id,
        tenant_id=tenant_id,
        integration_id=integration_id,
        provider=integration.integration_name,
        api_key=request.api_key,
        metadata=request.metadata
    )

    return CredentialResponse(
        id=credential.id,
        integration_id=credential.integration_id,
        credential_type=credential.credential_type.value,
        stored_at=credential.created_at.isoformat(),
        verified=True
    )


@router.post("/{integration_id}/credentials/pat", status_code=status.HTTP_201_CREATED)
def store_pat(
    integration_id: int,
    request: StorePATRequest,
    current_user: User = Depends(get_approved_user),
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Store a Personal Access Token (PAT) credential for an integration.

    Validates the PAT before storing by making a test request to the provider.
    Returns 400 if validation fails.
    """
    # Verify integration exists and belongs to tenant
    integration = db.query(TenantMCPIntegration).filter(
        TenantMCPIntegration.id == integration_id,
        TenantMCPIntegration.tenant_id == tenant_id
    ).first()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found"
        )

    # Get base_url from integration config
    base_url = integration.config.get("base_url", "")
    if not base_url and integration.integration_name not in ["github"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Integration config missing base_url"
        )

    # Initialize credential service
    credential_service = CredentialService(db)

    # Validate PAT before storing
    is_valid = credential_service.validate_pat(
        provider=integration.integration_name,
        pat=request.pat,
        base_url=base_url
    )

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"PAT validation failed for {integration.integration_name}. "
                   "Please check that the token is valid and has appropriate permissions."
        )

    # Store the validated credential
    credential = credential_service.store_pat_credential(
        user_id=current_user.id,
        tenant_id=tenant_id,
        integration_id=integration_id,
        provider=integration.integration_name,
        pat=request.pat,
        metadata=request.metadata
    )

    return CredentialResponse(
        id=credential.id,
        integration_id=credential.integration_id,
        credential_type=credential.credential_type.value,
        stored_at=credential.created_at.isoformat(),
        verified=True
    )


@router.post("/{integration_id}/test")
def test_connection(
    integration_id: int,
    current_user: User = Depends(get_approved_user),
    tenant_id: int = Depends(get_current_user_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Test connection using stored credentials for an integration.

    Uses the stored OAuth token, API key, or PAT to verify the connection
    is working.
    """
    # Verify integration exists and belongs to tenant
    integration = db.query(TenantMCPIntegration).filter(
        TenantMCPIntegration.id == integration_id,
        TenantMCPIntegration.tenant_id == tenant_id
    ).first()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found"
        )

    # Initialize credential service
    credential_service = CredentialService(db)

    # Get credential for this integration
    credential = credential_service.get_credential(
        user_id=current_user.id,
        tenant_id=tenant_id,
        integration_id=integration_id
    )

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No credential found for this integration. Please configure authentication first."
        )

    # Get base_url from integration config
    base_url = integration.config.get("base_url", "")
    if not base_url and integration.integration_name not in ["github"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Integration config missing base_url"
        )

    # Test the credential
    is_valid = credential_service.test_credential(credential, base_url)

    if is_valid:
        return TestConnectionResponse(
            status="ok",
            provider=integration.integration_name,
            authenticated_user=credential.provider_metadata.get("username") if credential.provider_metadata else None
        )
    else:
        return TestConnectionResponse(
            status="error",
            provider=integration.integration_name,
            error="Authentication failed. The credential may be invalid or expired."
        )
