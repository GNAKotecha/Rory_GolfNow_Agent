"""Tests for OAuth service (state management and OAuth flow)."""
import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from app.services.oauth_service import OAuthService, StateTokenStore


class TestStateTokenGeneration:
    """Test state token generation."""

    def test_generate_state_token_format(self):
        """State tokens should be URL-safe strings."""
        token = OAuthService.generate_state_token()

        assert isinstance(token, str)
        assert len(token) > 20  # Should be reasonably long
        # URL-safe characters only
        assert all(c.isalnum() or c in '-_' for c in token)

    def test_generate_state_token_uniqueness(self):
        """Each state token should be unique."""
        tokens = [OAuthService.generate_state_token() for _ in range(100)]

        assert len(set(tokens)) == 100  # All unique


class TestStateTokenStore:
    """Test state token storage and retrieval."""

    def test_store_and_retrieve_state(self):
        """State token should be stored and retrievable."""
        store = StateTokenStore()
        state = "test_state_123"
        data = {"integration_id": 1, "tenant_id": 1, "user_id": 10}

        store.store(state, data, tenant_id=1)
        retrieved = store.retrieve(state, tenant_id=1)

        assert retrieved == data

    def test_retrieve_nonexistent_state(self):
        """Retrieving non-existent state should return None."""
        store = StateTokenStore()

        result = store.retrieve("nonexistent", tenant_id=1)

        assert result is None

    def test_tenant_isolation(self):
        """State tokens should be tenant-scoped."""
        store = StateTokenStore()
        state = "test_state_456"
        data = {"integration_id": 1, "tenant_id": 1, "user_id": 10}

        store.store(state, data, tenant_id=1)

        # Attempt retrieval with wrong tenant
        result = store.retrieve(state, tenant_id=2)

        assert result is None

    def test_state_expiry(self):
        """State tokens should expire after 10 minutes."""
        store = StateTokenStore(expiry_seconds=1)  # 1 second for testing
        state = "test_state_789"
        data = {"integration_id": 1, "tenant_id": 1, "user_id": 10}

        store.store(state, data, tenant_id=1)
        time.sleep(1.1)  # Wait for expiry

        result = store.retrieve(state, tenant_id=1)

        assert result is None

    def test_cleanup_expired_tokens(self):
        """Cleanup should remove expired tokens."""
        store = StateTokenStore(expiry_seconds=1)
        state1 = "state1"
        state2 = "state2"
        data = {"integration_id": 1, "tenant_id": 1, "user_id": 10}

        store.store(state1, data, tenant_id=1)
        time.sleep(1.1)  # Expire state1
        store.store(state2, data, tenant_id=1)  # state2 still valid

        store.cleanup()

        assert store.retrieve(state1, tenant_id=1) is None
        assert store.retrieve(state2, tenant_id=1) == data


class TestOAuthServiceBuildAuthorizeURL:
    """Test OAuth authorization URL building."""

    def test_build_github_authorize_url(self):
        """GitHub authorization URL should be correctly formatted."""
        config = {
            "client_id": "github_client_123",
            "scopes": ["repo", "read:user"]
        }
        state = "test_state_abc"
        base_url = "http://localhost:8000"

        url = OAuthService.build_authorize_url(
            integration_name="github",
            config=config,
            state=state,
            base_url=base_url
        )

        assert url.startswith("https://github.com/login/oauth/authorize")
        assert f"client_id={config['client_id']}" in url
        assert f"state={state}" in url
        assert "scope=repo+read%3Auser" in url or "scope=repo%20read%3Auser" in url
        assert "redirect_uri=http%3A%2F%2Flocalhost%3A8000" in url  # URL-encoded

    def test_build_authorize_url_invalid_provider(self):
        """Invalid provider should raise ValueError."""
        config = {"client_id": "test_123"}
        state = "test_state"
        base_url = "http://localhost:8000"

        with pytest.raises(ValueError, match="Unsupported integration"):
            OAuthService.build_authorize_url(
                integration_name="unsupported_provider",
                config=config,
                state=state,
                base_url=base_url
            )


class TestOAuthServiceExchangeToken:
    """Test OAuth token exchange."""

    @patch('requests.post')
    def test_exchange_code_for_token_github_success(self, mock_post):
        """Successful token exchange should return access token."""
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {
                "access_token": "gho_test_token_123",
                "token_type": "bearer",
                "scope": "repo,read:user"
            }
        )

        config = {
            "client_id": "github_client_123",
            "client_secret": "github_secret_456"
        }
        code = "auth_code_789"

        result = OAuthService.exchange_code_for_token(
            integration_name="github",
            config=config,
            code=code
        )

        assert result["access_token"] == "gho_test_token_123"
        assert result["token_type"] == "bearer"
        assert "repo" in result.get("scope", "")

    @patch('requests.post')
    def test_exchange_code_for_token_github_failure(self, mock_post):
        """Failed token exchange should raise ValueError."""
        mock_post.return_value = Mock(
            status_code=400,
            json=lambda: {"error": "bad_verification_code"}
        )

        config = {
            "client_id": "github_client_123",
            "client_secret": "github_secret_456"
        }
        code = "invalid_code"

        with pytest.raises(ValueError, match="Token exchange failed"):
            OAuthService.exchange_code_for_token(
                integration_name="github",
                config=config,
                code=code
            )

    @patch('requests.post')
    def test_exchange_code_for_token_network_error(self, mock_post):
        """Network error during token exchange should raise ValueError."""
        mock_post.side_effect = Exception("Network timeout")

        config = {
            "client_id": "github_client_123",
            "client_secret": "github_secret_456"
        }
        code = "auth_code_789"

        with pytest.raises(ValueError, match="Token exchange failed"):
            OAuthService.exchange_code_for_token(
                integration_name="github",
                config=config,
                code=code
            )


class TestOAuthServiceValidateState:
    """Test state token validation."""

    def test_validate_state_token_match(self):
        """Matching state tokens should validate successfully."""
        stored = "state_token_123"
        received = "state_token_123"

        result = OAuthService.validate_state_token(stored, received)

        assert result is True

    def test_validate_state_token_mismatch(self):
        """Mismatched state tokens should fail validation."""
        stored = "state_token_123"
        received = "state_token_456"

        result = OAuthService.validate_state_token(stored, received)

        assert result is False

    def test_validate_state_token_none(self):
        """None state tokens should fail validation."""
        assert OAuthService.validate_state_token(None, "test") is False
        assert OAuthService.validate_state_token("test", None) is False
        assert OAuthService.validate_state_token(None, None) is False
