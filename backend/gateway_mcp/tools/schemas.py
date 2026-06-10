"""
Gateway MCP Schemas

Pydantic models for all Gateway tool inputs and outputs.

This module adapts Phase 2 BRS tool schemas and adds new schemas for:
- BRS tools (6): create_club, get_club_by_name, get_club_config,
                 create_admin_user, call_internal_api, verify_club_setup

Schemas define the contract between the agent and the Gateway.
Input schemas are validated before handler execution.
Output schemas ensure consistent response format.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ============================================================================
# Enums
# ============================================================================

class AdminRole(str, Enum):
    """Admin user roles."""
    ADMIN = "admin"
    SUPERUSER = "superuser"


class InternalApiOperation(str, Enum):
    """
    Allowed operations for call_internal_api.
    
    This is an enum, not free-form - the Gateway owns the operation mapping.
    """
    ENABLE_REQUIRED_FEATURES = "enable_required_features"


# ============================================================================
# BRS Tool Schemas (6 tools)
# ============================================================================

# --- create_club ---

class CreateClubInput(BaseModel):
    """Input for create_club tool."""
    
    name: str = Field(
        ..., 
        description="Name of the golf club (e.g., 'Pebble Beach')",
        min_length=1,
        max_length=255,
    )
    country: str = Field(
        ...,
        description="Country for the golf club. Must be one of: 'Australia', 'Bermuda', 'Canada', 'England', 'Ireland', 'Mexico', 'Scotland', 'South Africa', 'United States', 'Wales'. Use the exact name as shown (case-sensitive). Example: 'United States'",
        min_length=2,
    )
    timezone: str = Field(
        ...,
        description="IANA timezone (e.g., 'America/Los_Angeles', 'Europe/Dublin')",
    )
    currency: str = Field(
        ...,
        description="ISO 4217 currency code. Supported: USD (US/Mexico/Bermuda), CAD (Canada), AUD (Australia), ZAR (South Africa). Example: 'USD'. Note: Currency is typically auto-determined by country.",
        min_length=3,
        max_length=3,
    )
    
    # Country should NOT be uppercased - BRS expects proper case like "Ireland", "United States"
    # Removed: @field_validator("country")
    
    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        return v.upper()


class CreateClubOutput(BaseModel):
    """Output for create_club tool."""
    
    club_id: int | str = Field(..., description="Created club ID (string in BRS)")
    club_name: str = Field(..., description="Club name as stored", alias="name")
    database_name: str = Field(..., description="Name of created database")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp")
    
    model_config = {"populate_by_name": True}


# --- get_club_by_name ---

class GetClubByNameInput(BaseModel):
    """Input for get_club_by_name tool."""
    
    name: str = Field(
        ...,
        description="Club name to search for",
        min_length=1,
    )


class GetClubByNameOutput(BaseModel):
    """Output for get_club_by_name tool. Returns None if not found."""
    
    club_id: Optional[int | str] = Field(None, description="Club ID if found")
    name: Optional[str] = Field(None, description="Club name")
    country: Optional[str] = Field(None, description="ISO 3166-1 alpha-2 country code")
    timezone: Optional[str] = Field(None, description="IANA timezone")
    currency: Optional[str] = Field(None, description="ISO 4217 currency code")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    found: bool = Field(False, description="Whether club was found")


# --- get_club_config ---

class GetClubConfigInput(BaseModel):
    """Input for get_club_config tool."""
    
    club_id: int | str = Field(..., description="Club ID to get config for")


class GetClubConfigOutput(BaseModel):
    """Output for get_club_config tool."""
    
    club_id: int | str = Field(..., description="Club ID")
    modules: list[str] = Field(
        default_factory=list,
        description="Enabled module names",
    )
    settings: dict[str, Any] = Field(
        default_factory=dict,
        description="Configuration settings",
    )
    version: int = Field(..., description="Config version number")


# --- create_admin_user ---

class CreateAdminUserInput(BaseModel):
    """Input for create_admin_user tool."""
    
    club_id: int | str = Field(..., description="Club ID to create admin for")
    email: str = Field(
        ...,
        description="Admin email address",
        min_length=5,
    )
    username: Optional[str] = Field(
        None,
        description="Username for the admin (defaults to email prefix if not provided)",
        min_length=1,
        max_length=64,
    )
    role: AdminRole = Field(
        default=AdminRole.ADMIN,
        description="Admin role (admin or superuser)",
    )


class CreateAdminUserOutput(BaseModel):
    """Output for create_admin_user tool."""
    
    user_id: int | str = Field(..., description="User ID (or placeholder for sync operation)")
    club_id: int | str = Field(..., description="Club ID")
    email: str = Field(default="", description="Admin email")
    role: AdminRole = Field(..., description="Assigned role")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp")
    already_existed: bool = Field(
        default=False,
        description="True if user already existed (idempotent return)",
    )


# --- call_internal_api ---

class CallInternalApiInput(BaseModel):
    """Input for call_internal_api tool."""
    
    club_id: int | str = Field(..., description="Club ID")
    operation: InternalApiOperation = Field(
        ...,
        description="Operation to perform (enum, not free-form)",
    )


class CallInternalApiOutput(BaseModel):
    """Output for call_internal_api tool."""
    
    club_id: int | str = Field(..., description="Club ID")
    enabled_features: list[str] = Field(
        default_factory=list,
        description="List of features that are now enabled",
    )


# --- verify_club_setup ---

class VerifyClubSetupInput(BaseModel):
    """Input for verify_club_setup tool."""
    
    club_id: int | str = Field(..., description="Club ID to verify")


class VerifyClubSetupOutput(BaseModel):
    """Output for verify_club_setup tool."""
    
    club_exists: bool = Field(..., description="Whether club exists")
    config_valid: bool = Field(..., description="Whether config is valid")
    has_admin: bool = Field(default=False, description="Whether club has an admin user")
    features_enabled: list[str] = Field(
        default_factory=list,
        description="List of enabled features",
    )
    issues: list[str] = Field(
        default_factory=list,
        description="List of issues found during verification",
    )


# --- authenticate_club (replaces get_superuser_api_key) ---

class AuthenticateClubInput(BaseModel):
    """
    Input for authenticate_club tool.
    
    SECURITY: This tool handles credential retrieval and OAuth token exchange
    internally. No credentials are exposed to the agent.
    """
    
    club_id: int | str = Field(
        ...,
        description="Club ID to authenticate for BRS API access",
    )


class AuthenticateClubOutput(BaseModel):
    """
    Output for authenticate_club tool.
    
    SECURITY: Does NOT include any credentials. Only returns success status.
    The OAuth token is cached internally for automatic use in subsequent API calls.
    """
    
    club_id: int | str = Field(..., description="Club ID that was authenticated")
    authenticated: bool = Field(..., description="Whether authentication was successful")
    message: str = Field(
        ..., 
        description="Status message (success confirmation or error details - never credentials)"
    )



# ============================================================================
# Phase 2 Schema Adapters
# ============================================================================

# Re-export Phase 2 schemas for backward compatibility with existing BRS code
# These are used by the parser when translating CLI output

try:
    from app.services.brs_tools.schemas import (
        ConfigValidateOutput as BRSConfigValidateOutput,
        SuperuserCreateOutput as BRSSuperuserCreateOutput,
        TeesheetInitOutput as BRSTeesheetInitOutput,
    )
except ImportError:
    # Fallback for when running outside main app context (tests, standalone)
    # Define minimal compatible schemas
    
    class BRSTeesheetInitOutput(BaseModel):
        """Fallback for Phase 2 TeesheetInitOutput."""
        success: bool
        database_name: str
        stdout: str
        error: Optional[str] = None
    
    class BRSSuperuserCreateOutput(BaseModel):
        """Fallback for Phase 2 SuperuserCreateOutput."""
        success: bool
        user_id: Optional[int] = None
        email: str
        stdout: str
        error: Optional[str] = None
    
    class BRSConfigValidateOutput(BaseModel):
        """Fallback for Phase 2 ConfigValidateOutput."""
        success: bool
        errors: list[str] = []
        warnings: list[str] = []
        stdout: str


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    # Enums
    "AdminRole",
    "InternalApiOperation",
    # BRS Input schemas
    "CreateClubInput",
    "GetClubByNameInput",
    "GetClubConfigInput",
    "CreateAdminUserInput",
    "CallInternalApiInput",
    "VerifyClubSetupInput",
    "AuthenticateClubInput",
    # BRS Output schemas
    "CreateClubOutput",
    "GetClubByNameOutput",
    "GetClubConfigOutput",
    "CreateAdminUserOutput",
    "CallInternalApiOutput",
    "VerifyClubSetupOutput",
    "AuthenticateClubOutput",
    # Phase 2 adapters
    "BRSTeesheetInitOutput",
    "BRSSuperuserCreateOutput",
    "BRSConfigValidateOutput",
]
