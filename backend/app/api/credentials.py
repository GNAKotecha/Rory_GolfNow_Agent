"""
Credential Management API

Endpoints for managing OAuth and PAT credentials for external services.
Routes are mounted at /api/credentials.

Endpoints:
- GET /api/credentials - List user's connected providers
- GET /api/credentials/{provider}/authorize - Start OAuth flow (for OAuth providers)
- GET /api/credentials/{provider}/callback - Handle OAuth callback
- POST /api/credentials/{provider}/pat - Store PAT (for PAT providers)
- DELETE /api/credentials/{provider} - Disconnect a provider
"""
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_user, get_current_user_tenant_id
from app.db.session import get_db
from app.models.models import User
from gateway_mcp.core.credentials import (
    CredentialEncryption,
    CredentialStore,
    OAuthFlow,
    OAuthStateStore,
    PATFlow,
    PROVIDER_PRESETS,
    create_oauth_flow,
    create_pat_flow,
)

router = APIRouter(prefix="/credentials", tags=["credentials"])

# Module-level state store (should be Redis-backed in production)
_oauth_state_store = OAuthStateStore()


def get_credentials_config() -> dict:
    """
    Load credentials configuration.
    
    Merges environment-specific settings with provider presets.
    Add new providers by extending this configuration.
    """
    return {
        "providers": {
            "atlassian": {
                "type": "oauth",
                "client_id_env": "ATLASSIAN_CLIENT_ID",
                "client_secret_env": "ATLASSIAN_CLIENT_SECRET",
                "redirect_uri": os.environ.get(
                    "ATLASSIAN_REDIRECT_URI",
                    "http://localhost:8000/api/credentials/atlassian/callback",
                ),
                "default_scopes": ["read:jira-work", "write:jira-work"],
            },
            "github": {
                "type": "pat",
                "required_scopes": ["repo", "read:user"],
            },
            # Add more providers here - they'll automatically work
            # if their preset exists in PROVIDER_PRESETS
        },
    }


def get_credential_store(db: Session = Depends(get_db)) -> CredentialStore:
    """Get credential store with database session."""
    encryption_key = os.environ.get("GATEWAY_CREDENTIAL_ENCRYPTION_KEY")
    if not encryption_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Credential encryption not configured",
        )
    
    encryption = CredentialEncryption(encryption_key)
    return CredentialStore(
        db_session=db,
        encryption=encryption,
        oauth_base_url="/api/credentials",
    )


def get_oauth_flow() -> OAuthFlow:
    """Get OAuth flow handler with all configured OAuth providers."""
    config = get_credentials_config()
    flow = create_oauth_flow(config)
    # Inject shared state store
    flow._state_store = _oauth_state_store
    return flow


def get_pat_flow() -> PATFlow:
    """Get PAT flow handler with all configured PAT providers."""
    config = get_credentials_config()
    return create_pat_flow(config)


# --- Response Models ---

class CredentialInfo(BaseModel):
    """Credential information (without secrets)."""
    provider: str
    credential_type: str
    scopes: list[str] = Field(default_factory=list)
    expires_at: Optional[str] = None
    is_expired: bool = False
    is_revoked: bool = False
    metadata: dict = Field(default_factory=dict)
    created_at: str
    updated_at: str


class CredentialsListResponse(BaseModel):
    """Response for listing credentials."""
    credentials: list[CredentialInfo]


class AuthorizationResponse(BaseModel):
    """Response for starting OAuth flow."""
    authorization_url: str
    state: str


class PATRequest(BaseModel):
    """Request for storing a PAT."""
    pat: str = Field(..., min_length=1, description="Personal Access Token")


class PATResponse(BaseModel):
    """Response for PAT storage."""
    success: bool
    provider: str
    user_login: Optional[str] = None
    scopes: list[str] = Field(default_factory=list)
    message: Optional[str] = None


class DisconnectResponse(BaseModel):
    """Response for disconnecting a provider."""
    success: bool
    provider: str
    message: str


class ErrorResponse(BaseModel):
    """Error response."""
    detail: str
    code: Optional[str] = None
    reconnect_url: Optional[str] = None


# --- Endpoints ---

@router.get("", response_model=CredentialsListResponse)
def list_credentials(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_user_tenant_id),
):
    """
    List user's connected external credentials within their tenant.

    Returns credential metadata without secrets.
    """
    store = get_credential_store(db)
    credentials = store.list_credentials(
        user_id=current_user.id,
        tenant_id=tenant_id
    )
    
    return CredentialsListResponse(
        credentials=[CredentialInfo(**c) for c in credentials]
    )


@router.get("/providers")
def list_available_providers():
    """
    List available credential providers and their types.
    
    Returns provider configurations for UI rendering.
    """
    config = get_credentials_config()
    providers = []
    
    for name, provider_config in config["providers"].items():
        preset = PROVIDER_PRESETS.get(name, {})
        providers.append({
            "name": name,
            "type": provider_config.get("type"),
            "display_name": preset.get("display_name", name.title()),
            "icon_url": preset.get("icon_url"),
        })
    
    return {"providers": providers}


@router.get("/{provider}/authorize")
def oauth_authorize(
    provider: str,
    current_user: User = Depends(get_current_user),
    scopes: Optional[str] = Query(None, description="Comma-separated scopes"),
    redirect_after: Optional[str] = Query(None, description="URL to redirect after OAuth"),
):
    """
    Start OAuth authorization flow for a provider.
    
    Redirects user to provider for authorization.
    """
    oauth_flow = get_oauth_flow()
    
    if provider not in oauth_flow.list_providers():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider '{provider}' is not an OAuth provider or not configured",
        )
    
    # Parse scopes if provided
    scope_list = scopes.split(",") if scopes else None
    
    try:
        result = oauth_flow.start_authorization(
            provider=provider,
            user_id=current_user.id,
            scopes=scope_list,
            redirect_after=redirect_after,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    # Redirect to authorization URL
    return RedirectResponse(
        url=result.authorization_url,
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/{provider}/callback")
def oauth_callback(
    provider: str,
    code: str = Query(..., description="Authorization code"),
    state: str = Query(..., description="OAuth state"),
    error: Optional[str] = Query(None, description="OAuth error"),
    error_description: Optional[str] = Query(None, description="Error description"),
    db: Session = Depends(get_db),
):
    """
    Handle OAuth callback for a provider.
    
    Exchanges authorization code for tokens and stores credential.
    """
    frontend_base = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    
    # Handle OAuth errors
    if error:
        error_msg = error_description or error
        return RedirectResponse(
            url=f"{frontend_base}/settings/credentials?error={error_msg}",
            status_code=status.HTTP_302_FOUND,
        )
    
    oauth_flow = get_oauth_flow()
    
    try:
        token_result, metadata, state_data = oauth_flow.handle_callback(
            code=code,
            state=state,
        )
    except ValueError as e:
        return RedirectResponse(
            url=f"{frontend_base}/settings/credentials?error={str(e)}",
            status_code=status.HTTP_302_FOUND,
        )
    except Exception:
        return RedirectResponse(
            url=f"{frontend_base}/settings/credentials?error=OAuth+exchange+failed",
            status_code=status.HTTP_302_FOUND,
        )
    
    # Get provider from state (it was stored when authorization started)
    provider_name = state_data.get("provider", provider)
    user_id = state_data.get("user_id")

    if not user_id:
        return RedirectResponse(
            url=f"{frontend_base}/settings/credentials?error=Invalid+state",
            status_code=status.HTTP_302_FOUND,
        )

    # Fetch user to get tenant_id
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse(
            url=f"{frontend_base}/settings/credentials?error=User+not+found",
            status_code=status.HTTP_302_FOUND,
        )

    store = get_credential_store(db)

    try:
        store.store_oauth_credential(
            user_id=user_id,
            tenant_id=user.tenant_id,
            provider=provider_name,
            access_token=token_result.access_token,
            refresh_token=token_result.refresh_token,
            scope=token_result.scope,
            expires_in=token_result.expires_in,
            metadata=metadata,
        )
    except Exception:
        return RedirectResponse(
            url=f"{frontend_base}/settings/credentials?error=Storage+failed",
            status_code=status.HTTP_302_FOUND,
        )
    
    # Redirect to success URL
    redirect_after = state_data.get("redirect_after") or f"{frontend_base}/settings/credentials"
    return RedirectResponse(
        url=f"{redirect_after}?provider={provider_name}&success=true",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/{provider}/pat", response_model=PATResponse)
def store_pat(
    provider: str,
    request: PATRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_user_tenant_id),
):
    """
    Store a Personal Access Token for a provider within tenant.

    Validates the PAT and stores it encrypted.
    """
    pat_flow = get_pat_flow()

    if provider not in pat_flow.list_providers():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider '{provider}' is not a PAT provider or not configured",
        )

    # Validate the PAT
    result = pat_flow.validate_and_prepare(
        provider=provider,
        pat=request.pat,
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error.message if result.error else "Validation failed",
        )

    # Store the credential
    store = get_credential_store(db)

    try:
        store.store_pat_credential(
            user_id=current_user.id,
            tenant_id=tenant_id,
            provider=provider,
            pat=request.pat,
            metadata=result.metadata,
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store credential",
        )
    
    return PATResponse(
        success=True,
        provider=provider,
        user_login=result.user_login,
        scopes=result.scopes,
        message=f"{provider.title()} PAT stored successfully",
    )


@router.delete("/{provider}", response_model=DisconnectResponse)
def disconnect_provider(
    provider: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_user_tenant_id),
):
    """
    Disconnect an external provider within tenant.

    Revokes the stored credential (soft delete).
    """
    config = get_credentials_config()

    if provider not in config["providers"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider: {provider}",
        )

    store = get_credential_store(db)

    revoked = store.revoke_credential(
        user_id=current_user.id,
        tenant_id=tenant_id,
        provider=provider,
    )
    
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active credential found for {provider}",
        )
    
    return DisconnectResponse(
        success=True,
        provider=provider,
        message=f"Disconnected from {provider}",
    )


@router.get("/{provider}/token-url")
def get_pat_token_url(
    provider: str,
    scopes: Optional[str] = Query(None, description="Comma-separated scopes"),
    current_user: User = Depends(get_current_user),
):
    """
    Get URL for creating a new PAT for a provider.
    
    Returns a URL with pre-selected scopes.
    """
    pat_flow = get_pat_flow()
    
    if provider not in pat_flow.list_providers():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider '{provider}' is not a PAT provider or not configured",
        )
    
    scope_list = scopes.split(",") if scopes else None
    url = pat_flow.get_token_creation_url(provider, scope_list)
    
    if not url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Token creation URL not configured for {provider}",
        )
    
    return {"url": url, "provider": provider}
