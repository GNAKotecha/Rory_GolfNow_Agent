"""
Credential Service

Handles validation and storage of API keys and Personal Access Tokens (PATs)
for external integrations.

Key features:
- Provider-specific validation (GitHub, GitLab, Jira)
- Encrypted storage using Fernet (AES-GCM)
- Tenant-scoped credentials
"""
import base64
import logging
from typing import Optional

import requests
from sqlalchemy.orm import Session

from app.models.external_credential import CredentialType, ExternalCredential
from gateway_mcp.core.credentials.store import CredentialEncryption


logger = logging.getLogger(__name__)


class CredentialService:
    """
    Service for validating and storing API keys and PATs.

    All credentials are validated before storage by making test requests
    to the provider's API.
    """

    def __init__(self, db: Session, encryption_key: Optional[str] = None):
        """
        Initialize credential service.

        Args:
            db: Database session
            encryption_key: Optional encryption key (uses env var if not provided)
        """
        self.db = db
        self.encryption = CredentialEncryption(encryption_key)

    def validate_api_key(self, provider: str, api_key: str, base_url: str) -> bool:
        """
        Validate an API key by making a test request to the provider.

        Args:
            provider: Provider name (github, gitlab, jira)
            api_key: The API key to validate
            base_url: Base URL for the provider API

        Returns:
            True if API key is valid, False otherwise
        """
        try:
            if provider.lower() == "github":
                # GitHub API: GET /user with Authorization: token {api_key}
                response = requests.get(
                    "https://api.github.com/user",
                    headers={"Authorization": f"token {api_key}"},
                    timeout=10
                )
                return response.status_code == 200

            elif provider.lower() == "gitlab":
                # GitLab API: GET /api/v4/user with PRIVATE-TOKEN header
                url = f"{base_url.rstrip('/')}/api/v4/user"
                response = requests.get(
                    url,
                    headers={"PRIVATE-TOKEN": api_key},
                    timeout=10
                )
                return response.status_code == 200

            elif provider.lower() == "jira":
                # Jira API: GET /rest/api/2/myself with basic auth
                # For API tokens, username can be email or empty, token is the password
                url = f"{base_url.rstrip('/')}/rest/api/2/myself"
                # Use token as password in basic auth
                response = requests.get(
                    url,
                    auth=("", api_key),
                    timeout=10
                )
                return response.status_code == 200

            else:
                # Generic validation - try a basic request
                logger.warning(f"Unknown provider {provider}, attempting generic validation")
                response = requests.get(
                    base_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=10
                )
                return response.status_code in (200, 201)

        except requests.RequestException as e:
            logger.error(f"API key validation failed for {provider}: {e}")
            return False

    def validate_pat(self, provider: str, pat: str, base_url: str) -> bool:
        """
        Validate a Personal Access Token by making a test request.

        PATs are validated the same way as API keys.

        Args:
            provider: Provider name (github, gitlab, jira)
            pat: The PAT to validate
            base_url: Base URL for the provider API

        Returns:
            True if PAT is valid, False otherwise
        """
        # PATs and API keys are validated the same way
        return self.validate_api_key(provider, pat, base_url)

    def store_api_key_credential(
        self,
        user_id: int,
        tenant_id: int,
        integration_id: int,
        provider: str,
        api_key: str,
        metadata: Optional[dict] = None
    ) -> ExternalCredential:
        """
        Store an encrypted API key credential.

        Args:
            user_id: User ID who owns the credential
            tenant_id: Tenant ID for isolation
            integration_id: Integration ID this credential belongs to
            provider: Provider name (github, gitlab, jira)
            api_key: The API key to store (will be encrypted)
            metadata: Optional metadata dict

        Returns:
            The created ExternalCredential
        """
        # Encrypt the API key
        encrypted_key = self.encryption.encrypt(api_key)

        # Check if credential already exists for this user/integration
        existing = self.db.query(ExternalCredential).filter(
            ExternalCredential.user_id == user_id,
            ExternalCredential.tenant_id == tenant_id,
            ExternalCredential.integration_id == integration_id,
            ExternalCredential.credential_type == CredentialType.PAT  # Using PAT type for API keys
        ).first()

        if existing:
            # Update existing credential
            existing.secret_enc = encrypted_key
            existing.provider = provider
            existing.provider_metadata = metadata or {}
            existing.revoked_at = None  # Un-revoke if previously revoked
            self.db.commit()
            self.db.refresh(existing)
            logger.info(f"Updated API key credential for user {user_id}, integration {integration_id}")
            return existing

        # Create new credential
        credential = ExternalCredential(
            user_id=user_id,
            tenant_id=tenant_id,
            integration_id=integration_id,
            provider=provider,
            credential_type=CredentialType.PAT,  # Using PAT type for API keys
            secret_enc=encrypted_key,
            provider_metadata=metadata or {}
        )

        self.db.add(credential)
        self.db.commit()
        self.db.refresh(credential)

        logger.info(f"Stored API key credential for user {user_id}, integration {integration_id}")
        return credential

    def store_pat_credential(
        self,
        user_id: int,
        tenant_id: int,
        integration_id: int,
        provider: str,
        pat: str,
        metadata: Optional[dict] = None
    ) -> ExternalCredential:
        """
        Store an encrypted Personal Access Token credential.

        Args:
            user_id: User ID who owns the credential
            tenant_id: Tenant ID for isolation
            integration_id: Integration ID this credential belongs to
            provider: Provider name (github, gitlab, jira)
            pat: The PAT to store (will be encrypted)
            metadata: Optional metadata dict

        Returns:
            The created ExternalCredential
        """
        # Encrypt the PAT
        encrypted_pat = self.encryption.encrypt(pat)

        # Check if credential already exists for this user/integration
        existing = self.db.query(ExternalCredential).filter(
            ExternalCredential.user_id == user_id,
            ExternalCredential.tenant_id == tenant_id,
            ExternalCredential.integration_id == integration_id,
            ExternalCredential.credential_type == CredentialType.PAT
        ).first()

        if existing:
            # Update existing credential
            existing.secret_enc = encrypted_pat
            existing.provider = provider
            existing.provider_metadata = metadata or {}
            existing.revoked_at = None  # Un-revoke if previously revoked
            self.db.commit()
            self.db.refresh(existing)
            logger.info(f"Updated PAT credential for user {user_id}, integration {integration_id}")
            return existing

        # Create new credential
        credential = ExternalCredential(
            user_id=user_id,
            tenant_id=tenant_id,
            integration_id=integration_id,
            provider=provider,
            credential_type=CredentialType.PAT,
            secret_enc=encrypted_pat,
            provider_metadata=metadata or {}
        )

        self.db.add(credential)
        self.db.commit()
        self.db.refresh(credential)

        logger.info(f"Stored PAT credential for user {user_id}, integration {integration_id}")
        return credential

    def get_credential(
        self,
        user_id: int,
        tenant_id: int,
        integration_id: int
    ) -> Optional[ExternalCredential]:
        """
        Retrieve a credential for testing.

        Args:
            user_id: User ID
            tenant_id: Tenant ID
            integration_id: Integration ID

        Returns:
            ExternalCredential if found, None otherwise
        """
        return self.db.query(ExternalCredential).filter(
            ExternalCredential.user_id == user_id,
            ExternalCredential.tenant_id == tenant_id,
            ExternalCredential.integration_id == integration_id,
            ExternalCredential.revoked_at.is_(None)
        ).first()

    def test_credential(
        self,
        credential: ExternalCredential,
        base_url: str
    ) -> bool:
        """
        Test an existing credential by making a validation request.

        Args:
            credential: The credential to test
            base_url: Base URL for the provider

        Returns:
            True if credential is valid, False otherwise
        """
        # Decrypt the credential
        try:
            decrypted_secret = self.encryption.decrypt(credential.secret_enc)

            # Validate using the appropriate method
            return self.validate_api_key(
                credential.provider,
                decrypted_secret,
                base_url
            )
        except Exception as e:
            logger.error(f"Failed to test credential {credential.id}: {e}")
            return False
