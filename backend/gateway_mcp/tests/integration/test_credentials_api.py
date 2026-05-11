"""
Integration tests for Credential API endpoints.

Tests the full flow through FastAPI API router with mocked external services.
Uses a standalone FastAPI app to avoid database dependencies from main app.
"""
import os
import pytest
from unittest.mock import patch, Mock, MagicMock
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.external_credential import CredentialType
from gateway_mcp.core.credentials import (
    Credential,
    OAuthFlow,
    OAuthStateStore,
    PATFlow,
    PROVIDER_PRESETS,
    generate_encryption_key,
)
from gateway_mcp.core.credentials.providers.base import (
    AuthorizationResult,
    TokenExchangeResult,
    PATValidationResult,
)


@pytest.fixture
def mock_oauth_flow():
    """Create mock OAuth flow."""
    flow = Mock(spec=OAuthFlow)
    flow._state_store = OAuthStateStore()
    flow.list_providers.return_value = ["atlassian"]
    return flow


@pytest.fixture
def mock_pat_flow():
    """Create mock PAT flow."""
    flow = Mock(spec=PATFlow)
    flow.list_providers.return_value = ["github"]
    return flow


@pytest.fixture
def mock_credential_store():
    """Create mock credential store."""
    return Mock()


@pytest.fixture
def test_app(mock_oauth_flow, mock_pat_flow, mock_credential_store):
    """Create test FastAPI app with mocked dependencies."""
    from fastapi import APIRouter, Depends, HTTPException, Query, status
    from fastapi.responses import RedirectResponse
    from pydantic import BaseModel, Field
    from typing import Optional

    app = FastAPI()
    router = APIRouter(prefix="/api/credentials", tags=["credentials"])

    # Wire up module-level references via patching
    oauth_flow = mock_oauth_flow
    pat_flow = mock_pat_flow
    credential_store = mock_credential_store

    @router.get("/providers")
    def list_providers():
        """List available credential providers."""
        providers = {}
        for name, preset in PROVIDER_PRESETS.items():
            providers[name] = {
                "type": preset["type"],
                "display_name": preset.get("display_name", name.title()),
            }
        return providers

    @router.get("/{provider}/authorize")
    def authorize(
        provider: str,
        scopes: Optional[str] = Query(None),
    ):
        """Start OAuth authorization flow."""
        try:
            scope_list = scopes.split(",") if scopes else None
            result = oauth_flow.start_authorization(
                provider=provider,
                user_id=1,  # Mock user
                scopes=scope_list,
            )
            return RedirectResponse(
                url=result.authorization_url,
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/{provider}/callback")
    def callback(
        provider: str,
        code: Optional[str] = None,
        state: Optional[str] = None,
        error: Optional[str] = None,
        error_description: Optional[str] = None,
    ):
        """Handle OAuth callback."""
        if error:
            raise HTTPException(status_code=400, detail=error_description or error)

        try:
            token_result, metadata, state_data = oauth_flow.handle_callback(
                code=code,
                state=state,
            )
            credential_store.store_oauth_credential(
                user_id=state_data["user_id"],
                provider=provider,
                access_token=token_result.access_token,
                refresh_token=token_result.refresh_token,
                expires_in=token_result.expires_in,
                scope=token_result.scope,
                metadata=metadata,
            )
            return {"success": True, "provider": provider}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    class PATRequest(BaseModel):
        pat: str = Field(..., min_length=1)

    @router.post("/{provider}/pat")
    def store_pat(provider: str, request: PATRequest):
        """Store a PAT after validation."""
        result = pat_flow.validate_and_prepare(provider=provider, pat=request.pat)
        if not result.success:
            raise HTTPException(
                status_code=400,
                detail=f"{result.error.code}: {result.error.message}",
            )
        credential_store.store_pat_credential(
            user_id=1,
            provider=provider,
            pat=request.pat,
            scopes=result.scopes,
            metadata=result.metadata,
        )
        return {
            "success": True,
            "user_login": result.user_login,
            "scopes": result.scopes,
        }

    @router.delete("/{provider}")
    def revoke(provider: str):
        """Revoke a credential."""
        success = credential_store.revoke_credential(user_id=1, provider=provider)
        if not success:
            raise HTTPException(status_code=404, detail="Credential not found")
        return {"success": True}

    @router.get("")
    def list_credentials():
        """List user credentials."""
        creds = credential_store.list_credentials(user_id=1)
        return [
            {
                "provider": c.provider,
                "credential_type": c.credential_type.value,
                "scopes": c.scopes,
            }
            for c in creds
        ]

    @router.get("/{provider}/token-url")
    def get_token_url(provider: str, scopes: Optional[str] = Query(None)):
        """Get token creation URL."""
        scope_list = scopes.split(",") if scopes else None
        url = pat_flow.get_token_creation_url(provider, scope_list)
        if not url:
            raise HTTPException(status_code=400, detail="Unknown provider")
        return {"url": url}

    app.include_router(router)
    return app


@pytest.fixture
def client(test_app):
    """Create test client."""
    return TestClient(test_app)


class TestCredentialAPIProviders:
    """Test /api/credentials/providers endpoint."""
    
    def test_list_providers(self, client):
        """Test listing available credential providers."""
        response = client.get("/api/credentials/providers")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have provider entries
        assert isinstance(data, dict)
        # Check for known preset providers
        assert "atlassian" in data
        assert "github" in data
        
        # Check Atlassian entry structure
        atlassian = data["atlassian"]
        assert atlassian["type"] == "oauth"
        assert "Atlassian" in atlassian["display_name"]
        
        # Check GitHub entry structure
        github = data["github"]
        assert github["type"] == "pat"
        assert "GitHub" in github["display_name"]


class TestOAuthAuthorizeEndpoint:
    """Test /api/credentials/{provider}/authorize endpoint."""
    
    def test_authorize_redirects(self, mock_oauth_flow, test_app):
        """Test authorize endpoint returns redirect URL."""
        mock_oauth_flow.start_authorization.return_value = AuthorizationResult(
            authorization_url="https://auth.atlassian.com/authorize?client_id=xyz&...",
            state="state123",
            code_verifier="verifier456",
        )
        
        client = TestClient(test_app)
        response = client.get(
            "/api/credentials/atlassian/authorize",
            params={"scopes": "read:jira-work,write:jira-work"},
            follow_redirects=False,
        )
        
        # Should redirect to authorization URL
        assert response.status_code == 307
        assert "auth.atlassian.com" in response.headers["location"]
    
    def test_authorize_unknown_provider(self, mock_oauth_flow, test_app):
        """Test authorize with unknown provider raises error."""
        mock_oauth_flow.start_authorization.side_effect = ValueError("Unknown provider: unknown")
        
        client = TestClient(test_app)
        response = client.get("/api/credentials/unknown/authorize")
        
        assert response.status_code == 400
        assert "Unknown" in response.json()["detail"]
    
    def test_authorize_with_custom_scopes(self, mock_oauth_flow, test_app):
        """Test authorize with custom scope list."""
        mock_oauth_flow.start_authorization.return_value = AuthorizationResult(
            authorization_url="https://auth.test.com?scope=custom",
            state="state123",
        )
        
        client = TestClient(test_app)
        response = client.get(
            "/api/credentials/atlassian/authorize",
            params={"scopes": "custom:scope,another:scope"},
            follow_redirects=False,
        )
        
        assert response.status_code == 307
        mock_oauth_flow.start_authorization.assert_called_once()
        call_args = mock_oauth_flow.start_authorization.call_args
        assert ["custom:scope", "another:scope"] == call_args.kwargs.get("scopes")


class TestOAuthCallbackEndpoint:
    """Test /api/credentials/{provider}/callback endpoint."""
    
    def test_callback_success(self, mock_oauth_flow, mock_credential_store, test_app):
        """Test successful OAuth callback stores credentials."""
        mock_oauth_flow.handle_callback.return_value = (
            TokenExchangeResult(
                access_token="access_xyz",
                refresh_token="refresh_abc",
                expires_in=3600,
                scope="read:jira-work write:jira-work",
            ),
            {"cloud_id": "test-cloud-123"},
            {"user_id": 1, "provider": "atlassian"},
        )
        
        client = TestClient(test_app)
        response = client.get(
            "/api/credentials/atlassian/callback",
            params={"code": "auth_code_123", "state": "valid_state"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["provider"] == "atlassian"
        
        # Verify credential was stored
        mock_credential_store.store_oauth_credential.assert_called_once()
    
    def test_callback_invalid_state(self, mock_oauth_flow, test_app):
        """Test callback with invalid state returns error."""
        mock_oauth_flow.handle_callback.side_effect = ValueError("Invalid or expired state")
        
        client = TestClient(test_app)
        response = client.get(
            "/api/credentials/atlassian/callback",
            params={"code": "code", "state": "bad_state"},
        )
        
        assert response.status_code == 400
        assert "Invalid" in response.json()["detail"]
    
    def test_callback_error_from_provider(self, test_app):
        """Test callback when provider returns error."""
        client = TestClient(test_app)
        response = client.get(
            "/api/credentials/atlassian/callback",
            params={"error": "access_denied", "error_description": "User denied access"},
        )
        
        assert response.status_code == 400
        assert "User denied access" in response.json()["detail"]


class TestPATEndpoint:
    """Test /api/credentials/{provider}/pat endpoint."""
    
    def test_store_pat_success(self, mock_pat_flow, mock_credential_store, test_app):
        """Test storing a valid PAT."""
        mock_pat_flow.validate_and_prepare.return_value = Mock(
            success=True,
            user_login="testuser",
            user_id="123",
            scopes=["repo", "read:org"],
            metadata={"name": "Test User"},
            error=None,
        )
        
        client = TestClient(test_app)
        response = client.post(
            "/api/credentials/github/pat",
            json={"pat": "ghp_test_token_12345"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["user_login"] == "testuser"
        
        mock_credential_store.store_pat_credential.assert_called_once()
    
    def test_store_pat_invalid_token(self, mock_pat_flow, test_app):
        """Test storing invalid PAT returns error."""
        mock_pat_flow.validate_and_prepare.return_value = Mock(
            success=False,
            error=Mock(code="invalid_token", message="Token is invalid or expired"),
        )
        
        client = TestClient(test_app)
        response = client.post(
            "/api/credentials/github/pat",
            json={"pat": "invalid_token"},
        )
        
        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()
    
    def test_store_pat_insufficient_scopes(self, mock_pat_flow, test_app):
        """Test storing PAT with insufficient scopes."""
        mock_pat_flow.validate_and_prepare.return_value = Mock(
            success=False,
            error=Mock(
                code="insufficient_scopes",
                message="Missing required scopes",
                missing_scopes=["repo"],
            ),
        )
        
        client = TestClient(test_app)
        response = client.post(
            "/api/credentials/github/pat",
            json={"pat": "ghp_limited_token"},
        )
        
        assert response.status_code == 400
        assert "scopes" in response.json()["detail"].lower()


class TestTokenURLEndpoint:
    """Test /api/credentials/{provider}/token-url endpoint."""
    
    def test_get_token_creation_url(self, mock_pat_flow, test_app):
        """Test getting token creation URL."""
        mock_pat_flow.get_token_creation_url.return_value = "https://github.com/settings/tokens/new?scopes=repo,read:org"
        
        client = TestClient(test_app)
        response = client.get(
            "/api/credentials/github/token-url",
            params={"scopes": "repo,read:org"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "url" in data
        assert "github.com" in data["url"]
    
    def test_get_token_url_unknown_provider(self, mock_pat_flow, test_app):
        """Test token URL for unknown provider."""
        mock_pat_flow.get_token_creation_url.return_value = None
        
        client = TestClient(test_app)
        response = client.get("/api/credentials/unknown/token-url")
        
        assert response.status_code == 400


class TestRevokeCredentialEndpoint:
    """Test DELETE /api/credentials/{provider} endpoint."""
    
    def test_revoke_credential_success(self, mock_credential_store, test_app):
        """Test revoking a credential."""
        mock_credential_store.revoke_credential.return_value = True
        
        client = TestClient(test_app)
        response = client.delete("/api/credentials/github")
        
        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_credential_store.revoke_credential.assert_called_once()
    
    def test_revoke_credential_not_found(self, mock_credential_store, test_app):
        """Test revoking non-existent credential."""
        mock_credential_store.revoke_credential.return_value = False
        
        client = TestClient(test_app)
        response = client.delete("/api/credentials/github")
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestListCredentialsEndpoint:
    """Test GET /api/credentials endpoint."""
    
    def test_list_credentials_empty(self, mock_credential_store, test_app):
        """Test listing credentials when none exist."""
        mock_credential_store.list_credentials.return_value = []
        
        client = TestClient(test_app)
        response = client.get("/api/credentials")
        
        assert response.status_code == 200
        assert response.json() == []
    
    def test_list_credentials_with_entries(self, mock_credential_store, test_app):
        """Test listing credentials with stored entries."""
        mock_credential_store.list_credentials.return_value = [
            Credential(
                user_id=1,
                provider="github",
                credential_type=CredentialType.PAT,
                access_token="[REDACTED]",
                scopes=["repo", "read:org"],
            ),
            Credential(
                user_id=1,
                provider="atlassian",
                credential_type=CredentialType.OAUTH,
                access_token="[REDACTED]",
                scopes=["read:jira-work"],
                expires_at=datetime.utcnow() + timedelta(hours=1),
            ),
        ]
        
        client = TestClient(test_app)
        response = client.get("/api/credentials")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        
        # Check GitHub entry
        github = next(c for c in data if c["provider"] == "github")
        assert github["credential_type"] == "pat"
        assert github["scopes"] == ["repo", "read:org"]
        
        # Check Atlassian entry
        atlassian = next(c for c in data if c["provider"] == "atlassian")
        assert atlassian["credential_type"] == "oauth"


class TestOAuthFlowIntegration:
    """Integration tests for full OAuth flow simulation."""
    
    def test_full_oauth_flow_simulation(self, mock_oauth_flow, mock_credential_store, test_app):
        """Test simulated end-to-end OAuth flow."""
        # Step 1: Configure mock for authorization
        mock_oauth_flow.start_authorization.return_value = AuthorizationResult(
            authorization_url="https://auth.atlassian.com/authorize?state=test_state_123&client_id=xyz",
            state="test_state_123",
            code_verifier="verifier456",
        )
        
        client = TestClient(test_app)
        
        # Start authorization (would redirect user)
        response = client.get(
            "/api/credentials/atlassian/authorize",
            follow_redirects=False,
        )
        
        assert response.status_code == 307
        redirect_url = response.headers["location"]
        assert "state=test_state_123" in redirect_url
        
        # Step 2: Configure mock for callback
        mock_oauth_flow.handle_callback.return_value = (
            TokenExchangeResult(
                access_token="access_token_123",
                refresh_token="refresh_token_456",
                expires_in=3600,
                scope="read:jira-work write:jira-work",
            ),
            {"cloud_id": "cloud-abc"},
            {"user_id": 1, "provider": "atlassian"},
        )
        
        # Simulate callback from Atlassian
        response = client.get(
            "/api/credentials/atlassian/callback",
            params={"code": "auth_code_from_provider", "state": "test_state_123"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["provider"] == "atlassian"
        
        # Verify credential store was called
        mock_credential_store.store_oauth_credential.assert_called_once()

