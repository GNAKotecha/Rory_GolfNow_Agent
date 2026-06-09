"""RBAC models for principal types and permission profiles.

This module defines the core RBAC model for the Rory Agent system,
supporting local, SSO, and teesheet embedded authentication.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any


class AuthSource(str, Enum):
    """Authentication source for a principal."""
    LOCAL = "local"
    SSO = "sso"
    TEESHEET_EMBED = "teesheet_embed"


class ScopeType(str, Enum):
    """Permission scope type."""
    GLOBAL = "global"  # All tenants/clubs
    TENANT = "tenant"  # Specific tenant
    CLUB = "club"      # Specific club


@dataclass
class PermissionProfile:
    """Effective permissions for a principal.

    This class represents the unified permission model that determines
    what actions and resources a principal can access.
    """

    # Identity
    profile_id: str  # e.g., "local-admin", "sso-support", "teesheet-admin"
    description: str

    # Scope
    scope_type: ScopeType
    scope_id: Optional[int] = None  # tenant_id or club_id if scoped

    # Tool Access
    allowed_tools: List[str] = field(default_factory=list)  # MCP tool names or patterns
    denied_tools: List[str] = field(default_factory=list)   # Explicit denials

    # Data Access
    can_read_all_conversations: bool = False
    can_read_own_conversations: bool = True
    can_write_conversations: bool = False
    can_access_admin_apis: bool = False

    # Actions
    can_create_skills: bool = False
    can_modify_skills: bool = False
    can_delete_skills: bool = False
    can_create_workflows: bool = False
    can_modify_workflows: bool = False
    can_delete_workflows: bool = False
    can_approve_users: bool = False

    # Workflow
    can_trigger_workflows: bool = False
    max_workflow_cost: Optional[int] = None  # Max tokens per workflow

    # Rate Limits
    max_requests_per_minute: int = 60
    max_tokens_per_day: Optional[int] = None

    def can_use_tool(self, tool_name: str) -> bool:
        """Check if this profile allows using a specific tool.

        Args:
            tool_name: Name of the MCP tool

        Returns:
            True if tool is allowed, False otherwise
        """
        # Explicit denials take precedence
        if tool_name in self.denied_tools:
            return False

        # Check explicit allows
        if tool_name in self.allowed_tools:
            return True

        # Check wildcard patterns
        if "*" in self.allowed_tools:
            return True

        # Check prefix patterns (e.g., "brs_*")
        for pattern in self.allowed_tools:
            if pattern.endswith("*"):
                prefix = pattern[:-1]
                if tool_name.startswith(prefix):
                    return True

        # Default deny
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "profile_id": self.profile_id,
            "description": self.description,
            "scope_type": self.scope_type.value,
            "scope_id": self.scope_id,
            "allowed_tools": self.allowed_tools,
            "denied_tools": self.denied_tools,
            "permissions": {
                "read_all_conversations": self.can_read_all_conversations,
                "read_own_conversations": self.can_read_own_conversations,
                "write_conversations": self.can_write_conversations,
                "access_admin_apis": self.can_access_admin_apis,
                "create_skills": self.can_create_skills,
                "modify_skills": self.can_modify_skills,
                "delete_skills": self.can_delete_skills,
                "create_workflows": self.can_create_workflows,
                "modify_workflows": self.can_modify_workflows,
                "delete_workflows": self.can_delete_workflows,
                "approve_users": self.can_approve_users,
                "trigger_workflows": self.can_trigger_workflows,
            },
            "limits": {
                "max_workflow_cost": self.max_workflow_cost,
                "max_requests_per_minute": self.max_requests_per_minute,
                "max_tokens_per_day": self.max_tokens_per_day,
            }
        }


@dataclass
class Principal(ABC):
    """Base class for all principal types (users accessing the system).

    A principal represents an authenticated entity with associated permissions.
    Subclasses implement specific authentication methods.
    """

    # Core Identity
    user_id: int  # Database user ID
    tenant_id: int  # Tenant ID
    email: str
    name: str
    auth_source: AuthSource

    # Timestamps
    authenticated_at: datetime

    # External Identity (for SSO and embed)
    external_id: Optional[str] = None  # ID from external system

    @abstractmethod
    def get_role(self) -> str:
        """Get the role name for permission mapping."""
        pass

    @abstractmethod
    def get_context(self) -> Dict[str, Any]:
        """Get additional context for permission evaluation."""
        pass

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "email": self.email,
            "name": self.name,
            "auth_source": self.auth_source.value,
            "external_id": self.external_id,
            "authenticated_at": self.authenticated_at.isoformat(),
            "role": self.get_role(),
            "context": self.get_context(),
        }


@dataclass
class LocalPrincipal(Principal):
    """Principal authenticated via local email/password.

    This is the current authentication method, representing users
    stored in the local database with hashed passwords.
    """

    role: str  # "admin" or "user"
    approval_status: str  # "pending", "approved", "rejected"

    def __post_init__(self):
        """Set auth source after initialization."""
        self.auth_source = AuthSource.LOCAL

    def get_role(self) -> str:
        """Get the role name for permission mapping."""
        return self.role

    def get_context(self) -> Dict[str, Any]:
        """Get additional context for permission evaluation."""
        return {
            "approval_status": self.approval_status,
        }


@dataclass
class SSOPrincipal(Principal):
    """Principal authenticated via Single Sign-On.

    Represents users authenticated through sso.golfnow.com with
    OIDC/SAML. The Job_Role claim from SSO determines permissions.
    """

    job_role: str  # Job_Role from SSO claims (e.g., "support", "implementation")
    sso_claims: Dict[str, Any] = field(default_factory=dict)  # Full SSO token claims
    issuer: str = ""  # SSO issuer

    def __post_init__(self):
        """Set auth source after initialization."""
        self.auth_source = AuthSource.SSO

    def get_role(self) -> str:
        """Get the role name for permission mapping."""
        return self.job_role

    def get_context(self) -> Dict[str, Any]:
        """Get additional context for permission evaluation."""
        return {
            "job_role": self.job_role,
            "issuer": self.issuer,
            "sso_claims": self.sso_claims,
        }


@dataclass
class TeesheetPrincipal(Principal):
    """Principal authenticated via BRS Teesheet embedded token.

    Represents users embedded from the brs-teesheet application.
    These are short-lived sessions with club-scoped permissions.
    """

    club_id: int  # Club ID from embed token
    club_name: str  # Club name for display
    teesheet_role: str  # Role at this club (e.g., "admin", "staff", "member")
    embed_claims: Dict[str, Any] = field(default_factory=dict)  # Full embed token claims
    token_jti: str = ""  # JWT ID for replay protection

    def __post_init__(self):
        """Set auth source after initialization."""
        self.auth_source = AuthSource.TEESHEET_EMBED

    def get_role(self) -> str:
        """Get the role name for permission mapping."""
        return self.teesheet_role

    def get_context(self) -> Dict[str, Any]:
        """Get additional context for permission evaluation."""
        return {
            "club_id": self.club_id,
            "club_name": self.club_name,
            "teesheet_role": self.teesheet_role,
            "token_jti": self.token_jti,
            "embed_claims": self.embed_claims,
        }


@dataclass
class AuthenticatedSession:
    """Represents an authenticated session with principal and permissions.

    This is what gets stored in the request context and used for
    all authorization decisions.
    """

    principal: Principal
    permission_profile: PermissionProfile
    session_token: str  # JWT token for this session
    expires_at: datetime

    def is_expired(self) -> bool:
        """Check if session has expired."""
        return datetime.utcnow() > self.expires_at

    def can_use_tool(self, tool_name: str) -> bool:
        """Check if session can use a tool."""
        if self.is_expired():
            return False
        return self.permission_profile.can_use_tool(tool_name)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "principal": self.principal.to_dict(),
            "permission_profile": self.permission_profile.to_dict(),
            "expires_at": self.expires_at.isoformat(),
            "is_expired": self.is_expired(),
        }


# Type alias for convenience
PrincipalType = LocalPrincipal | SSOPrincipal | TeesheetPrincipal
