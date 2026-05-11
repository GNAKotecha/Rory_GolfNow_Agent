"""
Unit tests for Credential Subsystem

Tests encryption, generic providers, OAuth flow, and PAT flow.
"""
import os
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, Mock

from cryptography.fernet import Fernet

from gateway_mcp.core.credentials import (
    Credential,
    CredentialEncryption,
    CredentialStore,
    ExtendedOAuthConfig,
    ExtendedPATConfig,
    GenericOAuthProvider,
    GenericPATProvider,
    OAuthFlow,
    OAuthStateStore,
    PATFlow,
    PROVIDER_PRESETS,
    create_oauth_provider,
    create_pat_provider,
    generate_encryption_key,
)
from gateway_mcp.core.credentials.providers.base import (
    AuthorizationResult,
    PATValidationResult,
    ProviderType,
    TokenExchangeResult,
)
from app.models.external_credential import CredentialType


class TestCredentialEncryption:
    """Tests for CredentialEncryption class."""
    
    def test_encrypt_decrypt_roundtrip(self):
        """Test encryption and decryption produces original value."""
        key = generate_encryption_key()
        encryption = CredentialEncryption(key)
        
        plaintext = "my_secret_token_12345"
        ciphertext = encryption.encrypt(plaintext)
        
        assert ciphertext != plaintext.encode()
        assert encryption.decrypt(ciphertext) == plaintext
    
    def test_different_keys_produce_different_ciphertext(self):
        """Test different keys produce different ciphertext."""
        key1 = generate_encryption_key()
        key2 = generate_encryption_key()
        
        enc1 = CredentialEncryption(key1)
        enc2 = CredentialEncryption(key2)
        
        plaintext = "secret"
        cipher1 = enc1.encrypt(plaintext)
        cipher2 = enc2.encrypt(plaintext)
        
        assert cipher1 != cipher2
    
    def test_encryption_from_env_var(self):
        """Test encryption key can be loaded from env var."""
        key = generate_encryption_key()
        with patch.dict(os.environ, {"GATEWAY_CREDENTIAL_ENCRYPTION_KEY": key}):
            encryption = CredentialEncryption()
            plaintext = "test_secret"
            assert encryption.decrypt(encryption.encrypt(plaintext)) == plaintext
    
    def test_missing_key_raises_error(self):
        """Test missing encryption key raises ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove the key if it exists
            os.environ.pop("GATEWAY_CREDENTIAL_ENCRYPTION_KEY", None)
            with pytest.raises(ValueError, match="required"):
                CredentialEncryption()
    
    def test_invalid_key_raises_error(self):
        """Test invalid encryption key raises ValueError."""
        with pytest.raises(ValueError, match="Invalid"):
            CredentialEncryption("not-a-valid-fernet-key")


class TestGenerateEncryptionKey:
    """Tests for key generation."""
    
    def test_generates_valid_fernet_key(self):
        """Test generated key is valid for Fernet."""
        key = generate_encryption_key()
        # Should not raise
        Fernet(key.encode())
    
    def test_generates_different_keys(self):
        """Test multiple calls generate different keys."""
        keys = {generate_encryption_key() for _ in range(10)}
        assert len(keys) == 10


class TestCredential:
    """Tests for Credential dataclass."""
    
    def test_as_bearer(self):
        """Test as_bearer returns formatted header."""
        cred = Credential(
            user_id=1,
            provider="github",
            credential_type=CredentialType.PAT,
            access_token="ghp_xxxx",
        )
        assert cred.as_bearer() == "Bearer ghp_xxxx"
    
    def test_is_expired_no_expiry(self):
        """Test is_expired returns False when no expiry."""
        cred = Credential(
            user_id=1,
            provider="github",
            credential_type=CredentialType.PAT,
            access_token="token",
        )
        assert not cred.is_expired
    
    def test_is_expired_future(self):
        """Test is_expired returns False for future expiry."""
        cred = Credential(
            user_id=1,
            provider="atlassian",
            credential_type=CredentialType.OAUTH,
            access_token="token",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        assert not cred.is_expired
    
    def test_is_expired_past(self):
        """Test is_expired returns True for past expiry."""
        cred = Credential(
            user_id=1,
            provider="atlassian",
            credential_type=CredentialType.OAUTH,
            access_token="token",
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        assert cred.is_expired
    
    def test_is_expired_within_window(self):
        """Test is_expired returns True within 60s window."""
        cred = Credential(
            user_id=1,
            provider="atlassian",
            credential_type=CredentialType.OAUTH,
            access_token="token",
            expires_at=datetime.utcnow() + timedelta(seconds=30),
        )
        assert cred.is_expired  # Within 60s window
    
    def test_has_scope(self):
        """Test has_scope checks scope list."""
        cred = Credential(
            user_id=1,
            provider="atlassian",
            credential_type=CredentialType.OAUTH,
            access_token="token",
            scopes=["read:jira-work", "write:jira-work"],
        )
        assert cred.has_scope("read:jira-work")
        assert not cred.has_scope("admin")
    
    def test_has_all_scopes(self):
        """Test has_all_scopes checks multiple scopes."""
        cred = Credential(
            user_id=1,
            provider="atlassian",
            credential_type=CredentialType.OAUTH,
            access_token="token",
            scopes=["read:jira-work", "write:jira-work"],
        )
        assert cred.has_all_scopes(["read:jira-work", "write:jira-work"])
        assert not cred.has_all_scopes(["read:jira-work", "admin"])


class TestProviderPresets:
    """Tests for provider preset configurations."""
    
    def test_atlassian_preset_exists(self):
        """Test Atlassian preset is configured."""
        assert "atlassian" in PROVIDER_PRESETS
        preset = PROVIDER_PRESETS["atlassian"]
        assert preset["type"] == "oauth"
        assert "authz_url" in preset
        assert "token_url" in preset
    
    def test_github_preset_exists(self):
        """Test GitHub preset is configured."""
        assert "github" in PROVIDER_PRESETS
        preset = PROVIDER_PRESETS["github"]
        assert preset["type"] == "pat"
        assert "validate_url" in preset
        assert "token_creation_hint_url" in preset


class TestGenericOAuthProvider:
    """Tests for GenericOAuthProvider."""
    
    @pytest.fixture
    def oauth_config(self):
        """Create test OAuth config."""
        from gateway_mcp.core.credentials.providers.generic import ExtendedOAuthConfig
        return ExtendedOAuthConfig(
            name="test_oauth",
            type=ProviderType.OAUTH,
            display_name="Test OAuth",
            default_scopes=["read", "write"],
            authz_url="https://auth.example.com/authorize",
            token_url="https://auth.example.com/token",
            client_id_env="TEST_CLIENT_ID",
            client_secret_env="TEST_CLIENT_SECRET",
            redirect_uri="http://localhost/callback",
            use_pkce=True,
        )
    
    def test_get_authorization_url_with_pkce(self, oauth_config):
        """Test authorization URL generation with PKCE."""
        with patch.dict(os.environ, {"TEST_CLIENT_ID": "test_id", "TEST_CLIENT_SECRET": "test_secret"}):
            provider = GenericOAuthProvider(oauth_config)
            result = provider.get_authorization_url()
            
            assert result.authorization_url.startswith("https://auth.example.com/authorize")
            assert "client_id=test_id" in result.authorization_url
            assert "code_challenge=" in result.authorization_url
            assert result.code_verifier is not None
            assert result.state is not None
    
    def test_get_authorization_url_custom_scopes(self, oauth_config):
        """Test authorization URL with custom scopes."""
        with patch.dict(os.environ, {"TEST_CLIENT_ID": "test_id", "TEST_CLIENT_SECRET": "test_secret"}):
            provider = GenericOAuthProvider(oauth_config)
            result = provider.get_authorization_url(scopes=["custom_scope"])
            
            assert "scope=custom_scope" in result.authorization_url
    
    def test_create_oauth_provider_from_preset(self):
        """Test creating OAuth provider from preset."""
        provider = create_oauth_provider("atlassian", {
            "redirect_uri": "http://localhost/callback",
        })
        
        assert provider.config.name == "atlassian"
        assert provider.config.authz_url == "https://auth.atlassian.com/authorize"


class TestGenericPATProvider:
    """Tests for GenericPATProvider."""
    
    @pytest.fixture
    def pat_config(self):
        """Create test PAT config."""
        from gateway_mcp.core.credentials.providers.generic import ExtendedPATConfig
        return ExtendedPATConfig(
            name="test_pat",
            type=ProviderType.PAT,
            display_name="Test PAT",
            validate_url="https://api.example.com/user",
            token_creation_hint_url="https://example.com/settings/tokens/new",
            required_scopes=["read", "write"],
            scope_parse_mode="header",
            scope_field="x-oauth-scopes",
            user_id_path="id",
            user_login_path="login",
        )
    
    @patch("httpx.Client.request")
    def test_validate_token_success(self, mock_request, pat_config):
        """Test successful token validation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 123, "login": "testuser"}
        mock_response.headers = {"x-oauth-scopes": "read, write"}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response
        
        provider = GenericPATProvider(pat_config)
        result = provider.validate_token("test_token")
        
        assert result.valid
        assert result.user_id == "123"
        assert result.user_login == "testuser"
        assert result.scopes == ["read", "write"]
    
    @patch("httpx.Client.request")
    def test_validate_token_unauthorized(self, mock_request, pat_config):
        """Test token validation with 401 response."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_request.return_value = mock_response
        
        provider = GenericPATProvider(pat_config)
        result = provider.validate_token("invalid_token")
        
        assert not result.valid
        assert "Invalid" in result.error
    
    def test_check_scopes_with_parent_scope(self, pat_config):
        """Test scope checking with parent scope matching."""
        provider = GenericPATProvider(pat_config)
        
        # Mock validate_token to return scopes
        with patch.object(provider, "validate_token") as mock_validate:
            mock_validate.return_value = PATValidationResult(
                valid=True,
                scopes=["repo"],  # Parent scope
            )
            
            has_all, missing = provider.check_scopes("token", ["repo:status"])
            assert has_all  # repo covers repo:status
    
    def test_get_token_creation_url(self, pat_config):
        """Test token creation URL generation."""
        provider = GenericPATProvider(pat_config)
        url = provider.get_token_creation_url(scopes=["read", "write"])
        
        assert "https://example.com/settings/tokens/new" in url
        assert "scopes=" in url
    
    def test_create_pat_provider_from_preset(self):
        """Test creating PAT provider from preset."""
        provider = create_pat_provider("github")
        
        assert provider.config.name == "github"
        assert "api.github.com" in provider.config.validate_url


class TestOAuthStateStore:
    """Tests for OAuth state storage."""
    
    def test_store_and_get(self):
        """Test storing and retrieving state."""
        store = OAuthStateStore()
        
        store.store(
            state="test_state",
            code_verifier="verifier123",
            provider="atlassian",
            user_id=1,
        )
        
        data = store.get("test_state")
        
        assert data is not None
        assert data["code_verifier"] == "verifier123"
        assert data["provider"] == "atlassian"
        assert data["user_id"] == 1
    
    def test_get_consumes_state(self):
        """Test that getting state removes it."""
        store = OAuthStateStore()
        store.store(state="test_state", provider="test")
        
        assert store.get("test_state") is not None
        assert store.get("test_state") is None  # Second call returns None
    
    def test_get_nonexistent_state(self):
        """Test getting nonexistent state returns None."""
        store = OAuthStateStore()
        assert store.get("nonexistent") is None


class TestOAuthFlow:
    """Tests for OAuth flow orchestration."""
    
    @pytest.fixture
    def mock_provider(self):
        """Create mock OAuth provider."""
        provider = Mock()
        provider.get_authorization_url.return_value = AuthorizationResult(
            authorization_url="https://auth.example.com/auth?...",
            state="generated_state",
            code_verifier="verifier123",
        )
        provider.exchange_code.return_value = TokenExchangeResult(
            access_token="access_123",
            refresh_token="refresh_456",
            expires_in=3600,
            scope="read write",
        )
        provider.get_resource_metadata.return_value = {"cloud_id": "abc123"}
        return provider
    
    def test_start_authorization(self, mock_provider):
        """Test starting authorization flow."""
        flow = OAuthFlow(providers={"test": mock_provider})
        
        result = flow.start_authorization(
            provider="test",
            user_id=1,
            redirect_after="/dashboard",
        )
        
        assert result.authorization_url.startswith("https://")
        assert result.state == "generated_state"
    
    def test_start_authorization_unknown_provider(self, mock_provider):
        """Test starting authorization with unknown provider raises."""
        flow = OAuthFlow(providers={"test": mock_provider})
        
        with pytest.raises(ValueError, match="Unknown"):
            flow.start_authorization(provider="unknown", user_id=1)
    
    def test_handle_callback_invalid_state(self, mock_provider):
        """Test handling callback with invalid state raises."""
        flow = OAuthFlow(providers={"test": mock_provider})
        
        with pytest.raises(ValueError, match="Invalid"):
            flow.handle_callback(code="auth_code", state="bad_state")
    
    def test_handle_callback_success(self, mock_provider):
        """Test successful callback handling."""
        flow = OAuthFlow(providers={"test": mock_provider})
        
        # First, start authorization to store state
        flow.start_authorization(provider="test", user_id=1)
        
        # Get the state that was stored
        stored_state = list(flow._state_store._states.keys())[0]
        
        token_result, metadata, state_data = flow.handle_callback(
            code="auth_code",
            state=stored_state,
        )
        
        assert token_result.access_token == "access_123"
        assert metadata.get("cloud_id") == "abc123"
        assert state_data["user_id"] == 1
    
    def test_refresh_token(self, mock_provider):
        """Test token refresh."""
        mock_provider.refresh_token.return_value = TokenExchangeResult(
            access_token="new_access",
            refresh_token="new_refresh",
            expires_in=3600,
        )
        
        flow = OAuthFlow(providers={"test": mock_provider})
        result = flow.refresh_token("test", "old_refresh")
        
        assert result["access_token"] == "new_access"
    
    def test_list_providers(self, mock_provider):
        """Test listing available providers."""
        flow = OAuthFlow(providers={"test": mock_provider, "other": mock_provider})
        assert set(flow.list_providers()) == {"test", "other"}


class TestPATFlow:
    """Tests for PAT flow orchestration."""
    
    @pytest.fixture
    def mock_provider(self):
        """Create mock PAT provider."""
        provider = Mock()
        provider.config = Mock()
        provider.config.token_creation_hint_url = "https://example.com/tokens/new"
        provider.config.required_scopes = ["read", "write"]
        provider.validate_token.return_value = PATValidationResult(
            valid=True,
            user_id="123",
            user_login="testuser",
            scopes=["read", "write"],
            metadata={"email": "test@example.com"},
        )
        provider.check_scopes.return_value = (True, [])
        provider.get_token_creation_url.return_value = "https://example.com/tokens/new?scopes=read,write"
        return provider
    
    def test_validate_and_prepare_success(self, mock_provider):
        """Test successful PAT validation."""
        flow = PATFlow(providers={"test": mock_provider})
        
        result = flow.validate_and_prepare(provider="test", pat="test_token")
        
        assert result.success
        assert result.user_login == "testuser"
        assert result.scopes == ["read", "write"]
    
    def test_validate_and_prepare_unknown_provider(self, mock_provider):
        """Test validation with unknown provider."""
        flow = PATFlow(providers={"test": mock_provider})
        
        result = flow.validate_and_prepare(provider="unknown", pat="token")
        
        assert not result.success
        assert result.error.code == "unknown_provider"
    
    def test_validate_and_prepare_invalid_token(self, mock_provider):
        """Test validation with invalid token."""
        mock_provider.validate_token.return_value = PATValidationResult(
            valid=False,
            error="Token expired",
        )
        
        flow = PATFlow(providers={"test": mock_provider})
        result = flow.validate_and_prepare(provider="test", pat="bad_token")
        
        assert not result.success
        assert result.error.code == "invalid_token"
    
    def test_validate_and_prepare_insufficient_scopes(self, mock_provider):
        """Test validation with insufficient scopes."""
        mock_provider.check_scopes.return_value = (False, ["admin"])
        
        flow = PATFlow(providers={"test": mock_provider})
        result = flow.validate_and_prepare(provider="test", pat="token")
        
        assert not result.success
        assert result.error.code == "insufficient_scopes"
        assert "admin" in result.error.missing_scopes
    
    def test_get_token_creation_url(self, mock_provider):
        """Test getting token creation URL."""
        flow = PATFlow(providers={"test": mock_provider})
        
        url = flow.get_token_creation_url("test", ["custom"])
        
        assert url is not None
        assert "https://example.com" in url
    
    def test_list_providers(self, mock_provider):
        """Test listing available providers."""
        flow = PATFlow(providers={"github": mock_provider, "gitlab": mock_provider})
        assert set(flow.list_providers()) == {"github", "gitlab"}
