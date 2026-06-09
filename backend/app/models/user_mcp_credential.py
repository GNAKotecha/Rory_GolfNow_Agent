"""User MCP Credentials Model.

Database model for storing per-user MCP authentication credentials
for downstream service access (BRS, Jira, etc.).

This model supports:
- OAuth2 tokens (with refresh)
- API keys
- Basic auth
- Token expiry tracking
- Automatic refresh detection
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import relationship

from app.db.session import Base


class UserMCPCredential(Base):
    """
    Per-user MCP authentication credentials.

    Stores credentials for accessing downstream services via Gateway MCP.
    One credential per (user_id, provider) pair.

    Tokens are stored in plaintext for now - encryption will be added
    in a follow-up task once CredentialEncryption service is located.

    Example providers: 'BRS', 'Jira', 'GitHub', 'Confluence'
    """
    __tablename__ = "user_mcp_credentials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(50), nullable=False, index=True)  # 'BRS', 'Jira', etc.
    auth_method = Column(String(20), nullable=False)  # 'oauth2', 'api_key', 'basic'

    # Credentials (TODO: encrypt these fields)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)  # OAuth2 only
    token_type = Column(String(20), nullable=True, default="Bearer")

    # Expiry tracking
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # OAuth2 scopes (PostgreSQL array)
    scopes = Column(ARRAY(Text), nullable=True)

    # Provider-specific metadata (JSONB for PostgreSQL)
    provider_metadata = Column(JSONB, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", backref="mcp_credentials")

    def __repr__(self) -> str:
        return f"<UserMCPCredential(id={self.id}, user_id={self.user_id}, provider={self.provider}, auth_method={self.auth_method})>"

    @property
    def is_expired(self) -> bool:
        """
        Check if token is expired.

        Returns:
            True if expires_at is set and in the past
        """
        if self.expires_at is None:
            return False  # API keys don't expire (unless user-defined)
        return datetime.utcnow() > self.expires_at

    @property
    def expires_soon(self) -> bool:
        """
        Check if token expires within 5 minutes.

        Useful for triggering proactive token refresh.

        Returns:
            True if expires_at is within 5 minutes
        """
        if self.expires_at is None:
            return False
        return datetime.utcnow() + timedelta(minutes=5) > self.expires_at

    @property
    def is_oauth2(self) -> bool:
        """Check if credential uses OAuth2."""
        return self.auth_method == "oauth2"

    @property
    def can_refresh(self) -> bool:
        """Check if credential can be refreshed."""
        return self.is_oauth2 and self.refresh_token is not None

    @property
    def scopes_list(self) -> list[str]:
        """
        Get scopes as a list.

        Returns:
            List of scope strings, or empty list if no scopes
        """
        if not self.scopes:
            return []
        return self.scopes

    def to_dict(self, include_tokens: bool = False) -> dict:
        """
        Convert to dictionary.

        Args:
            include_tokens: If True, include access_token and refresh_token (use with caution!)

        Returns:
            Dictionary representation
        """
        result = {
            "id": self.id,
            "user_id": self.user_id,
            "provider": self.provider,
            "auth_method": self.auth_method,
            "token_type": self.token_type,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_expired": self.is_expired,
            "expires_soon": self.expires_soon,
            "can_refresh": self.can_refresh,
            "scopes": self.scopes_list,
            "provider_metadata": self.provider_metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

        if include_tokens:
            result["access_token"] = self.access_token
            result["refresh_token"] = self.refresh_token

        return result

    @staticmethod
    def get_by_user_and_provider(db, user_id: int, provider: str) -> Optional["UserMCPCredential"]:
        """
        Get credential by user and provider.

        Args:
            db: Database session
            user_id: User ID
            provider: Provider name (e.g., 'BRS', 'Jira')

        Returns:
            UserMCPCredential or None if not found
        """
        return db.query(UserMCPCredential).filter(
            UserMCPCredential.user_id == user_id,
            UserMCPCredential.provider == provider
        ).first()

    @staticmethod
    def get_all_by_user(db, user_id: int) -> list["UserMCPCredential"]:
        """
        Get all credentials for a user.

        Args:
            db: Database session
            user_id: User ID

        Returns:
            List of UserMCPCredential objects
        """
        return db.query(UserMCPCredential).filter(
            UserMCPCredential.user_id == user_id
        ).all()
