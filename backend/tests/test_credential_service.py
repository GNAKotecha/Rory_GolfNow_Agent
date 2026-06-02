"""
Unit tests for CredentialService.

Tests API-key and PAT validation, storage, encryption, and tenant isolation.
"""
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import requests

from app.db.session import Base
from app.models.models import Tenant, User
from app.models.external_credential import ExternalCredential, CredentialType
from app.services.credential_service import CredentialService
from gateway_mcp.core.credentials.store import CredentialEncryption


# Test database setup
@pytest.fixture
def db():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Seed test data
    tenant1 = Tenant(id=1, name="Test Tenant 1", slug="test-tenant-1")
    tenant2 = Tenant(id=2, name="Test Tenant 2", slug="test-tenant-2")
    session.add_all([tenant1, tenant2])

    user1 = User(id=1, name="User 1", email="user1@test.com", password_hash="hash1", tenant_id=1)
    user2 = User(id=2, name="User 2", email="user2@test.com", password_hash="hash2", tenant_id=2)
    session.add_all([user1, user2])

    session.commit()

    yield session

    session.close()


@pytest.fixture
def encryption_key():
    """Generate test encryption key."""
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


@pytest.fixture
def credential_service(db, encryption_key):
    """Create CredentialService instance with test encryption key."""
    return CredentialService(db, encryption_key)


# Test API Key Validation
class TestAPIKeyValidation:
    """Test API key validation logic."""

    @patch('requests.get')
    def test_validate_github_api_key_success(self, mock_get, credential_service):
        """Test successful GitHub API key validation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        result = credential_service.validate_api_key(
            provider="github",
            api_key="ghp_test123",
            base_url="https://api.github.com"
        )

        assert result is True
        mock_get.assert_called_once_with(
            "https://api.github.com/user",
            headers={"Authorization": "token ghp_test123"},
            timeout=10
        )

    @patch('requests.get')
    def test_validate_github_api_key_invalid(self, mock_get, credential_service):
        """Test GitHub API key validation with invalid key (401)."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        result = credential_service.validate_api_key(
            provider="github",
            api_key="invalid_key",
            base_url="https://api.github.com"
        )

        assert result is False

    @patch('requests.get')
    def test_validate_github_api_key_forbidden(self, mock_get, credential_service):
        """Test GitHub API key validation with insufficient permissions (403)."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_get.return_value = mock_response

        result = credential_service.validate_api_key(
            provider="github",
            api_key="ghp_limited",
            base_url="https://api.github.com"
        )

        assert result is False

    @patch('requests.get')
    def test_validate_api_key_network_error(self, mock_get, credential_service):
        """Test API key validation with network error."""
        mock_get.side_effect = requests.RequestException("Network error")

        result = credential_service.validate_api_key(
            provider="github",
            api_key="ghp_test123",
            base_url="https://api.github.com"
        )

        assert result is False

    @patch('requests.get')
    def test_validate_gitlab_api_key_success(self, mock_get, credential_service):
        """Test successful GitLab API key validation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        result = credential_service.validate_api_key(
            provider="gitlab",
            api_key="glpat-test123",
            base_url="https://gitlab.com"
        )

        assert result is True
        mock_get.assert_called_once_with(
            "https://gitlab.com/api/v4/user",
            headers={"PRIVATE-TOKEN": "glpat-test123"},
            timeout=10
        )

    @patch('requests.get')
    def test_validate_jira_api_key_success(self, mock_get, credential_service):
        """Test successful Jira API key validation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        result = credential_service.validate_api_key(
            provider="jira",
            api_key="jira_token_123",
            base_url="https://example.atlassian.net"
        )

        assert result is True
        mock_get.assert_called_once_with(
            "https://example.atlassian.net/rest/api/2/myself",
            auth=("", "jira_token_123"),
            timeout=10
        )


# Test PAT Validation
class TestPATValidation:
    """Test PAT validation logic."""

    @patch('requests.get')
    def test_validate_pat_success(self, mock_get, credential_service):
        """Test successful PAT validation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        result = credential_service.validate_pat(
            provider="github",
            pat="ghp_pat_test123",
            base_url="https://api.github.com"
        )

        assert result is True

    @patch('requests.get')
    def test_validate_pat_invalid(self, mock_get, credential_service):
        """Test PAT validation with invalid token."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        result = credential_service.validate_pat(
            provider="github",
            pat="invalid_pat",
            base_url="https://api.github.com"
        )

        assert result is False

    @patch('requests.get')
    def test_validate_pat_expired(self, mock_get, credential_service):
        """Test PAT validation with expired token (403)."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_get.return_value = mock_response

        result = credential_service.validate_pat(
            provider="github",
            pat="ghp_expired",
            base_url="https://api.github.com"
        )

        assert result is False


# Test Credential Storage
class TestCredentialStorage:
    """Test credential storage with encryption."""

    def test_store_api_key_credential_new(self, credential_service, db, encryption_key):
        """Test storing a new API key credential."""
        credential = credential_service.store_api_key_credential(
            user_id=1,
            tenant_id=1,
            integration_id=100,
            provider="github",
            api_key="ghp_test_secret",
            metadata={"note": "Test API key"}
        )

        assert credential.id is not None
        assert credential.user_id == 1
        assert credential.tenant_id == 1
        assert credential.integration_id == 100
        assert credential.provider == "github"
        assert credential.credential_type == CredentialType.PAT
        assert credential.provider_metadata == {"note": "Test API key"}

        # Verify encryption
        encryption = CredentialEncryption(encryption_key)
        decrypted = encryption.decrypt(credential.secret_enc)
        assert decrypted == "ghp_test_secret"

    def test_store_pat_credential_new(self, credential_service, db, encryption_key):
        """Test storing a new PAT credential."""
        credential = credential_service.store_pat_credential(
            user_id=1,
            tenant_id=1,
            integration_id=101,
            provider="gitlab",
            pat="glpat_test_secret",
            metadata={"note": "Test PAT"}
        )

        assert credential.id is not None
        assert credential.user_id == 1
        assert credential.tenant_id == 1
        assert credential.integration_id == 101
        assert credential.provider == "gitlab"
        assert credential.credential_type == CredentialType.PAT
        assert credential.provider_metadata == {"note": "Test PAT"}

        # Verify encryption
        encryption = CredentialEncryption(encryption_key)
        decrypted = encryption.decrypt(credential.secret_enc)
        assert decrypted == "glpat_test_secret"

    def test_store_api_key_duplicate_replaces(self, credential_service, db):
        """Test that storing duplicate credential replaces the existing one."""
        # Store first credential
        cred1 = credential_service.store_api_key_credential(
            user_id=1,
            tenant_id=1,
            integration_id=100,
            provider="github",
            api_key="ghp_old_key",
            metadata={"version": "1"}
        )

        # Store second credential for same user/integration
        cred2 = credential_service.store_api_key_credential(
            user_id=1,
            tenant_id=1,
            integration_id=100,
            provider="github",
            api_key="ghp_new_key",
            metadata={"version": "2"}
        )

        # Should have same ID (updated existing)
        assert cred1.id == cred2.id
        assert cred2.provider_metadata == {"version": "2"}

        # Verify only one credential exists
        all_creds = db.query(ExternalCredential).filter(
            ExternalCredential.user_id == 1,
            ExternalCredential.integration_id == 100
        ).all()
        assert len(all_creds) == 1

    def test_store_credential_tenant_isolation(self, credential_service, db):
        """Test that credentials are properly isolated by tenant."""
        # Tenant 1 credential
        cred1 = credential_service.store_api_key_credential(
            user_id=1,
            tenant_id=1,
            integration_id=100,
            provider="github",
            api_key="ghp_tenant1",
            metadata={}
        )

        # Tenant 2 credential
        cred2 = credential_service.store_api_key_credential(
            user_id=2,
            tenant_id=2,
            integration_id=100,
            provider="github",
            api_key="ghp_tenant2",
            metadata={}
        )

        # Verify both exist and are different
        assert cred1.id != cred2.id
        assert cred1.tenant_id == 1
        assert cred2.tenant_id == 2

        # Verify tenant 1 cannot access tenant 2's credential
        tenant1_creds = db.query(ExternalCredential).filter(
            ExternalCredential.tenant_id == 1
        ).all()
        assert len(tenant1_creds) == 1
        assert tenant1_creds[0].id == cred1.id


# Test Get Credential
class TestGetCredential:
    """Test credential retrieval."""

    def test_get_credential_success(self, credential_service, db):
        """Test retrieving an existing credential."""
        # Store credential
        stored = credential_service.store_api_key_credential(
            user_id=1,
            tenant_id=1,
            integration_id=100,
            provider="github",
            api_key="ghp_test",
            metadata={}
        )

        # Retrieve credential
        retrieved = credential_service.get_credential(
            user_id=1,
            tenant_id=1,
            integration_id=100
        )

        assert retrieved is not None
        assert retrieved.id == stored.id

    def test_get_credential_not_found(self, credential_service, db):
        """Test retrieving non-existent credential."""
        retrieved = credential_service.get_credential(
            user_id=1,
            tenant_id=1,
            integration_id=999
        )

        assert retrieved is None

    def test_get_credential_cross_tenant_denied(self, credential_service, db):
        """Test that cross-tenant credential access is denied."""
        # Store credential for tenant 1
        credential_service.store_api_key_credential(
            user_id=1,
            tenant_id=1,
            integration_id=100,
            provider="github",
            api_key="ghp_test",
            metadata={}
        )

        # Try to retrieve with tenant 2's ID
        retrieved = credential_service.get_credential(
            user_id=1,
            tenant_id=2,  # Wrong tenant!
            integration_id=100
        )

        assert retrieved is None


# Test Connection Testing
class TestConnectionTesting:
    """Test credential connection testing."""

    @patch('requests.get')
    def test_test_credential_success(self, mock_get, credential_service, db, encryption_key):
        """Test connection test with valid credential."""
        # Store credential
        credential = credential_service.store_api_key_credential(
            user_id=1,
            tenant_id=1,
            integration_id=100,
            provider="github",
            api_key="ghp_test",
            metadata={}
        )

        # Mock successful API call
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        result = credential_service.test_credential(
            credential,
            base_url="https://api.github.com"
        )

        assert result is True

    @patch('requests.get')
    def test_test_credential_invalid(self, mock_get, credential_service, db):
        """Test connection test with invalid credential."""
        # Store credential
        credential = credential_service.store_api_key_credential(
            user_id=1,
            tenant_id=1,
            integration_id=100,
            provider="github",
            api_key="ghp_invalid",
            metadata={}
        )

        # Mock failed API call
        mock_response = Mock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        result = credential_service.test_credential(
            credential,
            base_url="https://api.github.com"
        )

        assert result is False

    @patch('requests.get')
    def test_test_credential_network_error(self, mock_get, credential_service, db):
        """Test connection test with network error."""
        # Store credential
        credential = credential_service.store_api_key_credential(
            user_id=1,
            tenant_id=1,
            integration_id=100,
            provider="github",
            api_key="ghp_test",
            metadata={}
        )

        # Mock network error
        mock_get.side_effect = requests.RequestException("Network error")

        result = credential_service.test_credential(
            credential,
            base_url="https://api.github.com"
        )

        assert result is False
