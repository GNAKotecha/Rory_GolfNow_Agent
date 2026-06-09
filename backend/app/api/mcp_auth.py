"""API endpoints for per-user MCP credential management."""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.api.auth_deps import get_approved_user
from app.db.session import get_db
from app.models.models import User
from app.models.user_mcp_credential import UserMCPCredential

router = APIRouter(prefix="/integrations/mcp/auth", tags=["mcp-auth"])

VALID_AUTH_METHODS = {"oauth2", "api_key", "basic"}

# Tools associated with each provider — used to populate authenticated_tools in responses
TOOL_PROVIDER_MAP = {
    "get_club_by_name": "BRS",
    "verify_club_setup": "BRS",
    "get_club_config": "BRS",
    "call_api": "BRS",
    "create_jira_issue": "Jira",
    "get_jira_issue": "Jira",
}


def _get_authenticated_tools(provider: str) -> List[str]:
    return [tool for tool, p in TOOL_PROVIDER_MAP.items() if p == provider]


def _expires_in_seconds(expires_at: Optional[datetime]) -> Optional[int]:
    if expires_at is None:
        return None
    now = datetime.now(timezone.utc)
    # Normalise to UTC-aware if naive
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    remaining = (expires_at - now).total_seconds()
    return max(0, int(remaining))


def _credential_to_status(cred: UserMCPCredential) -> dict:
    return {
        "provider": cred.provider,
        "auth_method": cred.auth_method,
        "is_authenticated": not cred.is_expired,
        "expires_at": cred.expires_at.isoformat() if cred.expires_at else None,
        "scopes": cred.scopes_list,
        "authenticated_tools": _get_authenticated_tools(cred.provider),
    }


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class StoreCredentialRequest(BaseModel):
    provider: str
    auth_method: str
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: Optional[datetime] = None
    scopes: Optional[List[str]] = None
    token_type: Optional[str] = "Bearer"
    provider_metadata: Optional[dict] = None

    @field_validator("auth_method")
    @classmethod
    def validate_auth_method(cls, v: str) -> str:
        if v not in VALID_AUTH_METHODS:
            raise ValueError(f"auth_method must be one of: {', '.join(sorted(VALID_AUTH_METHODS))}")
        return v


class StoreCredentialResponse(BaseModel):
    status: str
    provider: str
    expires_in: Optional[int]
    authenticated_tools: List[str]


class CredentialStatusResponse(BaseModel):
    provider: str
    auth_method: str
    is_authenticated: bool
    expires_at: Optional[str]
    scopes: List[str]
    authenticated_tools: List[str]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", response_model=StoreCredentialResponse, status_code=status.HTTP_200_OK)
def store_credential(
    body: StoreCredentialRequest,
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """Store or update MCP credentials for a provider."""
    cred = UserMCPCredential.get_by_user_and_provider(db, current_user.id, body.provider)

    if cred:
        # Upsert: update existing record
        cred.auth_method = body.auth_method
        cred.access_token = body.access_token
        cred.refresh_token = body.refresh_token
        cred.token_type = body.token_type or "Bearer"
        cred.expires_at = body.expires_at
        cred.scopes = body.scopes
        cred.provider_metadata = body.provider_metadata
        cred.updated_at = datetime.utcnow()
    else:
        cred = UserMCPCredential(
            user_id=current_user.id,
            provider=body.provider,
            auth_method=body.auth_method,
            access_token=body.access_token,
            refresh_token=body.refresh_token,
            token_type=body.token_type or "Bearer",
            expires_at=body.expires_at,
            scopes=body.scopes,
            provider_metadata=body.provider_metadata,
        )
        db.add(cred)

    db.commit()
    db.refresh(cred)

    return StoreCredentialResponse(
        status="authenticated",
        provider=cred.provider,
        expires_in=_expires_in_seconds(cred.expires_at),
        authenticated_tools=_get_authenticated_tools(cred.provider),
    )


@router.get("", response_model=List[CredentialStatusResponse])
def list_credentials(
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """List all MCP credential statuses for current user (no tokens returned)."""
    creds = UserMCPCredential.get_all_by_user(db, current_user.id)
    return [CredentialStatusResponse(**_credential_to_status(c)) for c in creds]


@router.get("/{provider}", response_model=CredentialStatusResponse)
def get_credential(
    provider: str,
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """Get MCP credential status for a specific provider."""
    cred = UserMCPCredential.get_by_user_and_provider(db, current_user.id, provider)
    if not cred:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No credentials found for provider: {provider}",
        )
    return CredentialStatusResponse(**_credential_to_status(cred))


@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
def delete_credential(
    provider: str,
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """Delete MCP credentials for a specific provider."""
    cred = UserMCPCredential.get_by_user_and_provider(db, current_user.id, provider)
    if not cred:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No credentials found for provider: {provider}",
        )
    db.delete(cred)
    db.commit()


@router.post("/{provider}/refresh", response_model=StoreCredentialResponse)
def refresh_credential(
    provider: str,
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """Manually trigger token refresh for a provider credential.

    Currently a stub — automatic refresh via MCP client on tool calls
    is the primary refresh path. Returns current state for oauth2,
    501 for non-refreshable credential types.
    """
    cred = UserMCPCredential.get_by_user_and_provider(db, current_user.id, provider)
    if not cred:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No credentials found for provider: {provider}",
        )
    if cred.auth_method != "oauth2":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Token refresh is only supported for oauth2 credentials (current: {cred.auth_method})",
        )
    if not cred.refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No refresh token available. Please re-authenticate.",
        )

    # Stub: automatic refresh is handled by the MCP client during tool execution.
    # A full implementation would call the provider's token endpoint here.
    return StoreCredentialResponse(
        status="refreshed",
        provider=cred.provider,
        expires_in=_expires_in_seconds(cred.expires_at),
        authenticated_tools=_get_authenticated_tools(cred.provider),
    )
