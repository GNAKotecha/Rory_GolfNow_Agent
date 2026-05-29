"""
Encrypted Credential Store

DB-backed credential store with AES-GCM encryption via Fernet.
Handles both OAuth tokens and user-pasted PATs with unified interface.

Key features:
- Encryption at rest using Fernet (AES-128-CBC with HMAC)
- Transparent token refresh for OAuth credentials
- Concurrent refresh serialization using PostgreSQL advisory locks
- Automatic expiry checking and revocation handling
"""
import asyncio
import hashlib
import os
from datetime import datetime, timedelta
from typing import Optional, Tuple

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.external_credential import CredentialType, ExternalCredential
from gateway_mcp.core.errors import (
    CredentialMissingError,
    InternalError,
    TokenRefreshFailedError,
)


class CredentialEncryption:
    """
    Handles encryption and decryption of credential secrets.
    
    Uses Fernet (AES-128-CBC + HMAC-SHA256) for symmetric encryption.
    Key is derived from environment variable GATEWAY_CREDENTIAL_ENCRYPTION_KEY.
    """
    
    def __init__(self, encryption_key: Optional[str] = None):
        """
        Initialize encryption with key from env or parameter.
        
        Args:
            encryption_key: Base64-encoded Fernet key. If not provided,
                           reads from GATEWAY_CREDENTIAL_ENCRYPTION_KEY env var.
        
        Raises:
            ValueError: If no encryption key is available.
        """
        key = encryption_key or os.environ.get("GATEWAY_CREDENTIAL_ENCRYPTION_KEY")
        
        if not key:
            raise ValueError(
                "GATEWAY_CREDENTIAL_ENCRYPTION_KEY environment variable is required"
            )
        
        # Validate and create Fernet instance
        try:
            self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
        except Exception as e:
            raise ValueError(f"Invalid encryption key: {e}")
    
    def encrypt(self, plaintext: str) -> bytes:
        """
        Encrypt a plaintext string.
        
        Args:
            plaintext: The secret to encrypt.
            
        Returns:
            Encrypted bytes.
        """
        return self._fernet.encrypt(plaintext.encode())
    
    def decrypt(self, ciphertext: bytes) -> str:
        """
        Decrypt ciphertext bytes.
        
        Args:
            ciphertext: The encrypted data.
            
        Returns:
            Decrypted plaintext string.
            
        Raises:
            InvalidToken: If decryption fails.
        """
        return self._fernet.decrypt(ciphertext).decode()


class Credential:
    """
    Decrypted credential object returned from the store.
    
    This is a read-only view of a credential with decrypted secrets.
    Never persisted - only exists in memory during request handling.
    """
    
    def __init__(
        self,
        user_id: int,
        provider: str,
        credential_type: CredentialType,
        access_token: str,
        refresh_token: Optional[str] = None,
        scopes: Optional[list[str]] = None,
        expires_at: Optional[datetime] = None,
        metadata: Optional[dict] = None,
    ):
        self.user_id = user_id
        self.provider = provider
        self.credential_type = credential_type
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.scopes = scopes or []
        self.expires_at = expires_at
        self.metadata = metadata or {}
    
    def as_bearer(self) -> str:
        """Return access token formatted as Bearer header value."""
        return f"Bearer {self.access_token}"
    
    @property
    def is_expired(self) -> bool:
        """Check if token is expired or expiring soon (within 60s)."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > (self.expires_at - timedelta(seconds=60))
    
    def has_scope(self, scope: str) -> bool:
        """Check if credential has a specific scope."""
        return scope in self.scopes
    
    def has_all_scopes(self, required_scopes: list[str]) -> bool:
        """Check if credential has all required scopes."""
        return all(self.has_scope(s) for s in required_scopes)


class CredentialStore:
    """
    Database-backed credential store with encryption and refresh.
    
    Provides unified access to OAuth tokens and PATs with:
    - Encryption at rest
    - Automatic token refresh for OAuth
    - Concurrent refresh serialization
    - Revocation tracking
    """
    
    # Refresh tokens expiring within this window
    REFRESH_WINDOW_SECONDS = 60
    
    def __init__(
        self,
        db_session: Session,
        encryption: CredentialEncryption,
        oauth_flow: Optional["OAuthFlow"] = None,  # Forward reference
        oauth_base_url: str = "/api/credentials",
    ):
        """
        Initialize credential store.
        
        Args:
            db_session: SQLAlchemy database session.
            encryption: Encryption handler for secrets.
            oauth_flow: OAuth flow handler for token refresh.
            oauth_base_url: Base URL for OAuth redirect hints.
        """
        self._db = db_session
        self._encryption = encryption
        self._oauth_flow = oauth_flow
        self._oauth_base_url = oauth_base_url
        
        # Lock for concurrent refresh handling (in-process)
        self._refresh_locks: dict[Tuple[int, str], asyncio.Lock] = {}
    
    def get_credential(
        self,
        user_id: int,
        tenant_id: int,
        provider: str,
        audit_id: Optional[str] = None,
    ) -> Credential:
        """
        Get decrypted credential for user and provider within tenant.

        For OAuth credentials, automatically refreshes if expired.

        Args:
            user_id: ID of the user.
            tenant_id: Tenant ID for isolation (from JWT).
            provider: Provider name (e.g., "atlassian", "github").
            audit_id: Correlation ID for errors.

        Returns:
            Decrypted Credential object.

        Raises:
            CredentialMissingError: No credential found for this user/provider.
            TokenRefreshFailedError: OAuth refresh failed.
        """
        # Query for credential (scoped to tenant)
        record = (
            self._db.query(ExternalCredential)
            .filter(
                and_(
                    ExternalCredential.user_id == user_id,
                    ExternalCredential.tenant_id == tenant_id,
                    ExternalCredential.provider == provider,
                    ExternalCredential.revoked_at.is_(None),
                )
            )
            .first()
        )
        
        if record is None:
            reconnect_url = f"{self._oauth_base_url}/{provider}/authorize"
            raise CredentialMissingError(
                provider=provider,
                reconnect_url=reconnect_url,
                audit_id=audit_id,
            )
        
        # Decrypt secrets
        try:
            access_token = self._encryption.decrypt(record.secret_enc)
            refresh_token = None
            if record.refresh_token_enc:
                refresh_token = self._encryption.decrypt(record.refresh_token_enc)
        except InvalidToken:
            # Encryption key changed or data corrupted
            raise InternalError(
                message="Failed to decrypt credential",
                audit_id=audit_id,
            )
        
        credential = Credential(
            user_id=record.user_id,
            provider=record.provider,
            credential_type=record.credential_type,
            access_token=access_token,
            refresh_token=refresh_token,
            scopes=record.scopes_list,
            expires_at=record.expires_at,
            metadata=record.provider_metadata or {},
        )
        
        # Check if OAuth token needs refresh
        if (
            credential.credential_type == CredentialType.OAUTH
            and credential.is_expired
            and credential.refresh_token
        ):
            credential = self._refresh_token(record, credential, audit_id)
        
        return credential
    
    def _refresh_token(
        self,
        record: ExternalCredential,
        credential: Credential,
        audit_id: Optional[str] = None,
    ) -> Credential:
        """
        Refresh an OAuth token.
        
        Uses PostgreSQL advisory lock to prevent concurrent refresh.
        
        Args:
            record: Database record to update.
            credential: Current credential with refresh token.
            audit_id: Correlation ID for errors.
            
        Returns:
            Updated Credential with new access token.
            
        Raises:
            TokenRefreshFailedError: Refresh failed.
        """
        if self._oauth_flow is None:
            reconnect_url = f"{self._oauth_base_url}/{credential.provider}/authorize"
            raise TokenRefreshFailedError(
                provider=credential.provider,
                reconnect_url=reconnect_url,
                audit_id=audit_id,
            )
        
        # Acquire PostgreSQL advisory lock to serialize concurrent refreshes
        lock_key = self._compute_lock_key(credential.user_id, credential.provider)
        
        try:
            # Try to acquire lock (non-blocking)
            result = self._db.execute(
                text("SELECT pg_try_advisory_lock(:key)"),
                {"key": lock_key},
            )
            got_lock = result.scalar()
            
            if not got_lock:
                # Another process is refreshing, wait briefly and retry
                import time
                time.sleep(0.5)
                
                # Re-fetch the credential (may have been refreshed)
                return self.get_credential(
                    credential.user_id,
                    credential.provider,
                    audit_id,
                )
            
            try:
                # Perform the refresh
                new_tokens = self._oauth_flow.refresh_token(
                    provider=credential.provider,
                    refresh_token=credential.refresh_token,
                )
                
                # Update database record
                record.secret_enc = self._encryption.encrypt(new_tokens["access_token"])
                
                if "refresh_token" in new_tokens:
                    record.refresh_token_enc = self._encryption.encrypt(
                        new_tokens["refresh_token"]
                    )
                
                if "expires_in" in new_tokens:
                    record.expires_at = datetime.utcnow() + timedelta(
                        seconds=new_tokens["expires_in"]
                    )
                
                if "scope" in new_tokens:
                    record.scope = new_tokens["scope"]
                
                record.updated_at = datetime.utcnow()
                self._db.commit()
                
                # Return updated credential
                return Credential(
                    user_id=credential.user_id,
                    provider=credential.provider,
                    credential_type=credential.credential_type,
                    access_token=new_tokens["access_token"],
                    refresh_token=new_tokens.get("refresh_token", credential.refresh_token),
                    scopes=new_tokens.get("scope", "").split() or credential.scopes,
                    expires_at=record.expires_at,
                    metadata=credential.metadata,
                )
                
            except Exception as e:
                # Refresh failed - mark credential as revoked
                record.revoked_at = datetime.utcnow()
                self._db.commit()
                
                reconnect_url = f"{self._oauth_base_url}/{credential.provider}/authorize"
                raise TokenRefreshFailedError(
                    provider=credential.provider,
                    reconnect_url=reconnect_url,
                    audit_id=audit_id,
                )
                
        finally:
            # Release advisory lock
            self._db.execute(
                text("SELECT pg_advisory_unlock(:key)"),
                {"key": lock_key},
            )
    
    def _compute_lock_key(self, user_id: int, provider: str) -> int:
        """
        Compute a PostgreSQL advisory lock key.
        
        Uses hash to fit into int64 range.
        """
        key_str = f"credential:{user_id}:{provider}"
        hash_bytes = hashlib.sha256(key_str.encode()).digest()
        # Use first 8 bytes as signed int64
        return int.from_bytes(hash_bytes[:8], byteorder="big", signed=True)
    
    def store_oauth_credential(
        self,
        user_id: int,
        tenant_id: int,
        provider: str,
        access_token: str,
        refresh_token: Optional[str],
        scope: str,
        expires_in: int,
        metadata: Optional[dict] = None,
    ) -> ExternalCredential:
        """
        Store a new OAuth credential or update existing.

        Args:
            user_id: ID of the user.
            tenant_id: Tenant ID for isolation (from JWT).
            provider: Provider name.
            access_token: The access token.
            refresh_token: The refresh token (optional).
            scope: Space-separated scope string.
            expires_in: Token lifetime in seconds.
            metadata: Provider-specific metadata.

        Returns:
            The created or updated ExternalCredential record.
        """
        # Check for existing credential (scoped to tenant)
        record = (
            self._db.query(ExternalCredential)
            .filter(
                and_(
                    ExternalCredential.user_id == user_id,
                    ExternalCredential.tenant_id == tenant_id,
                    ExternalCredential.provider == provider,
                )
            )
            .first()
        )
        
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=expires_in)
        
        if record:
            # Update existing
            record.secret_enc = self._encryption.encrypt(access_token)
            record.refresh_token_enc = (
                self._encryption.encrypt(refresh_token) if refresh_token else None
            )
            record.scope = scope
            record.expires_at = expires_at
            record.provider_metadata = metadata
            record.revoked_at = None  # Clear any previous revocation
            record.updated_at = now
        else:
            # Create new
            record = ExternalCredential(
                user_id=user_id,
                tenant_id=tenant_id,
                provider=provider,
                credential_type=CredentialType.OAUTH,
                secret_enc=self._encryption.encrypt(access_token),
                refresh_token_enc=(
                    self._encryption.encrypt(refresh_token) if refresh_token else None
                ),
                scope=scope,
                expires_at=expires_at,
                provider_metadata=metadata,
                created_at=now,
                updated_at=now,
            )
            self._db.add(record)
        
        self._db.commit()
        self._db.refresh(record)
        return record
    
    def store_pat_credential(
        self,
        user_id: int,
        tenant_id: int,
        provider: str,
        pat: str,
        metadata: Optional[dict] = None,
    ) -> ExternalCredential:
        """
        Store a new PAT credential or update existing.

        Args:
            user_id: ID of the user.
            tenant_id: Tenant ID for isolation (from JWT).
            provider: Provider name (e.g., "github").
            pat: The personal access token.
            metadata: Provider-specific metadata (e.g., user_login, scopes).

        Returns:
            The created or updated ExternalCredential record.
        """
        # Check for existing credential (scoped to tenant)
        record = (
            self._db.query(ExternalCredential)
            .filter(
                and_(
                    ExternalCredential.user_id == user_id,
                    ExternalCredential.tenant_id == tenant_id,
                    ExternalCredential.provider == provider,
                )
            )
            .first()
        )
        
        now = datetime.utcnow()
        
        if record:
            # Update existing
            record.secret_enc = self._encryption.encrypt(pat)
            record.credential_type = CredentialType.PAT
            record.refresh_token_enc = None  # PATs don't have refresh tokens
            record.scope = None  # PAT scopes are embedded in the token
            record.expires_at = None  # PATs don't expire (unless user-defined)
            record.provider_metadata = metadata
            record.revoked_at = None  # Clear any previous revocation
            record.updated_at = now
        else:
            # Create new
            record = ExternalCredential(
                user_id=user_id,
                tenant_id=tenant_id,
                provider=provider,
                credential_type=CredentialType.PAT,
                secret_enc=self._encryption.encrypt(pat),
                refresh_token_enc=None,
                scope=None,
                expires_at=None,
                provider_metadata=metadata,
                created_at=now,
                updated_at=now,
            )
            self._db.add(record)
        
        self._db.commit()
        self._db.refresh(record)
        return record
    
    def revoke_credential(
        self,
        user_id: int,
        tenant_id: int,
        provider: str,
    ) -> bool:
        """
        Revoke a credential (soft delete).

        Args:
            user_id: ID of the user.
            tenant_id: Tenant ID for isolation (from JWT).
            provider: Provider name.

        Returns:
            True if credential was found and revoked, False otherwise.
        """
        record = (
            self._db.query(ExternalCredential)
            .filter(
                and_(
                    ExternalCredential.user_id == user_id,
                    ExternalCredential.tenant_id == tenant_id,
                    ExternalCredential.provider == provider,
                    ExternalCredential.revoked_at.is_(None),
                )
            )
            .first()
        )
        
        if record is None:
            return False
        
        record.revoked_at = datetime.utcnow()
        self._db.commit()
        return True
    
    def list_credentials(
        self,
        user_id: int,
        tenant_id: int,
        include_revoked: bool = False,
    ) -> list[dict]:
        """
        List user's credentials within tenant (without secrets).

        Args:
            user_id: ID of the user.
            tenant_id: Tenant ID for isolation (from JWT).
            include_revoked: Whether to include revoked credentials.

        Returns:
            List of credential metadata dicts (no secrets).
        """
        query = self._db.query(ExternalCredential).filter(
            and_(
                ExternalCredential.user_id == user_id,
                ExternalCredential.tenant_id == tenant_id
            )
        )

        if not include_revoked:
            query = query.filter(ExternalCredential.revoked_at.is_(None))
        
        records = query.all()
        
        return [
            {
                "provider": r.provider,
                "credential_type": r.credential_type.value,
                "scopes": r.scopes_list,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                "is_expired": r.is_expired,
                "is_revoked": r.is_revoked,
                "metadata": r.provider_metadata or {},
                "created_at": r.created_at.isoformat(),
                "updated_at": r.updated_at.isoformat(),
            }
            for r in records
        ]


def create_credential_store(
    db_session: Session,
    encryption_key: Optional[str] = None,
    oauth_flow: Optional["OAuthFlow"] = None,
    oauth_base_url: str = "/api/credentials",
) -> CredentialStore:
    """
    Factory function to create a CredentialStore.
    
    Args:
        db_session: SQLAlchemy database session.
        encryption_key: Optional encryption key (defaults to env var).
        oauth_flow: Optional OAuth flow handler.
        oauth_base_url: Base URL for OAuth redirect hints.
        
    Returns:
        Configured CredentialStore instance.
    """
    encryption = CredentialEncryption(encryption_key)
    return CredentialStore(
        db_session=db_session,
        encryption=encryption,
        oauth_flow=oauth_flow,
        oauth_base_url=oauth_base_url,
    )


def generate_encryption_key() -> str:
    """
    Generate a new Fernet encryption key.
    
    Use this to create GATEWAY_CREDENTIAL_ENCRYPTION_KEY.
    
    Returns:
        Base64-encoded Fernet key.
    """
    return Fernet.generate_key().decode()
