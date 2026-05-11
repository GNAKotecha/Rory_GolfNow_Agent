"""External Credentials Model.

Database model for storing OAuth tokens and user-pasted PATs
with encrypted storage.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    JSON,
    LargeBinary,
    String,
)
from sqlalchemy.orm import relationship
from sqlalchemy.engine import Engine
import enum

from app.db.session import Base


def _get_json_type():
    """
    Get dialect-safe JSON type.
    
    Returns JSONB for PostgreSQL (better indexing/querying),
    JSON for SQLite and other databases (test compatibility).
    """
    try:
        from sqlalchemy.dialects.postgresql import JSONB
        return JSONB
    except ImportError:
        return JSON


class CredentialType(str, enum.Enum):
    """Credential type - OAuth or PAT."""
    OAUTH = "oauth"
    PAT = "pat"


class ExternalCredential(Base):
    """
    External service credentials (OAuth tokens or PATs).
    
    Credentials are encrypted at rest using AES-GCM via Fernet.
    One credential per (user_id, provider) pair.
    """
    __tablename__ = "external_credentials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(50), nullable=False)  # "atlassian", "github", etc.
    credential_type = Column(SQLEnum(CredentialType), nullable=False)
    
    # Encrypted secrets (AES-GCM via Fernet)
    secret_enc = Column(LargeBinary, nullable=False)  # access_token (OAuth) or PAT
    refresh_token_enc = Column(LargeBinary, nullable=True)  # OAuth only
    
    # OAuth metadata
    scope = Column(String(1000), nullable=True)  # space-separated scope list
    expires_at = Column(DateTime(timezone=True), nullable=True)  # OAuth only
    
    # Provider-specific metadata (e.g., Atlassian cloud_id, GitHub user_login)
    # Uses JSON for SQLite compatibility, JSONB for PostgreSQL
    provider_metadata = Column(JSON, nullable=True)
    
    # Revocation tracking
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationship
    user = relationship("User", backref="external_credentials")

    def __repr__(self) -> str:
        return f"<ExternalCredential(id={self.id}, user_id={self.user_id}, provider={self.provider})>"

    @property
    def is_expired(self) -> bool:
        """Check if OAuth token is expired."""
        if self.expires_at is None:
            return False  # PATs don't expire (unless user-defined)
        return datetime.utcnow() > self.expires_at

    @property
    def is_revoked(self) -> bool:
        """Check if credential has been revoked."""
        return self.revoked_at is not None

    @property
    def is_valid(self) -> bool:
        """Check if credential is valid (not expired and not revoked)."""
        return not self.is_expired and not self.is_revoked

    @property
    def scopes_list(self) -> list[str]:
        """Return scope as a list."""
        if not self.scope:
            return []
        return self.scope.split()
