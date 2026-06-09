"""Role-Based Access Control (RBAC) module for Rory Agent.

This module implements a unified permission model supporting three principal types:
- Local users (email/password)
- SSO users (from sso.golfnow.com)
- Teesheet embedded users (from brs-teesheet)

See backend/docs/RBAC_MODEL.md for complete documentation.
"""

from .models import (
    AuthSource,
    ScopeType,
    PermissionProfile,
    Principal,
    LocalPrincipal,
    SSOPrincipal,
    TeesheetPrincipal,
    AuthenticatedSession,
    PrincipalType,
)

__all__ = [
    "AuthSource",
    "ScopeType",
    "PermissionProfile",
    "Principal",
    "LocalPrincipal",
    "SSOPrincipal",
    "TeesheetPrincipal",
    "AuthenticatedSession",
    "PrincipalType",
]
