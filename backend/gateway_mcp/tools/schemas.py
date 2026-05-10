"""
Gateway MCP Schemas

Pydantic models for all Gateway tool inputs and outputs.

This module adapts Phase 2 BRS tool schemas and adds new schemas for:
- BRS tools (6): create_club, get_club_by_name, get_club_config, 
                 create_admin_user, call_internal_api, verify_club_setup
- Atlassian tools (3): create_ticket, get_ticket_status, add_comment

Schemas define the contract between the agent and the Gateway.
Input schemas are validated before handler execution.
Output schemas ensure consistent response format.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ============================================================================
# Enums
# ============================================================================

class IssueType(str, Enum):
    """Jira issue types."""
    TASK = "Task"
    BUG = "Bug"
    STORY = "Story"


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
        description="ISO 3166-1 alpha-2 country code (e.g., 'US', 'IE')",
        min_length=2,
        max_length=2,
    )
    timezone: str = Field(
        ...,
        description="IANA timezone (e.g., 'America/Los_Angeles', 'Europe/Dublin')",
    )
    currency: str = Field(
        ...,
        description="ISO 4217 currency code (e.g., 'USD', 'EUR')",
        min_length=3,
        max_length=3,
    )
    
    @field_validator("country")
    @classmethod
    def validate_country(cls, v: str) -> str:
        return v.upper()
    
    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        return v.upper()


class CreateClubOutput(BaseModel):
    """Output for create_club tool."""
    
    club_id: int = Field(..., description="Created club ID")
    club_name: str = Field(..., description="Club name as stored")
    database_name: str = Field(..., description="Name of created database")
    created_at: datetime = Field(..., description="Creation timestamp")


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
    
    club_id: Optional[int] = Field(None, description="Club ID if found")
    name: Optional[str] = Field(None, description="Club name")
    country: Optional[str] = Field(None, description="ISO 3166-1 alpha-2 country code")
    timezone: Optional[str] = Field(None, description="IANA timezone")
    currency: Optional[str] = Field(None, description="ISO 4217 currency code")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    found: bool = Field(False, description="Whether club was found")


# --- get_club_config ---

class GetClubConfigInput(BaseModel):
    """Input for get_club_config tool."""
    
    club_id: int = Field(..., description="Club ID to get config for", gt=0)


class GetClubConfigOutput(BaseModel):
    """Output for get_club_config tool."""
    
    club_id: int = Field(..., description="Club ID")
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
    
    club_id: int = Field(..., description="Club ID to create admin for", gt=0)
    email: str = Field(
        ...,
        description="Admin email address",
        min_length=5,
    )
    role: AdminRole = Field(
        default=AdminRole.ADMIN,
        description="Admin role (admin or superuser)",
    )


class CreateAdminUserOutput(BaseModel):
    """Output for create_admin_user tool."""
    
    user_id: int = Field(..., description="Created user ID")
    club_id: int = Field(..., description="Club ID")
    email: str = Field(..., description="Admin email")
    role: AdminRole = Field(..., description="Assigned role")
    created_at: datetime = Field(..., description="Creation timestamp")
    already_existed: bool = Field(
        default=False,
        description="True if user already existed (idempotent return)",
    )


# --- call_internal_api ---

class CallInternalApiInput(BaseModel):
    """Input for call_internal_api tool."""
    
    club_id: int = Field(..., description="Club ID", gt=0)
    operation: InternalApiOperation = Field(
        ...,
        description="Operation to perform (enum, not free-form)",
    )


class CallInternalApiOutput(BaseModel):
    """Output for call_internal_api tool."""
    
    club_id: int = Field(..., description="Club ID")
    enabled_features: list[str] = Field(
        default_factory=list,
        description="List of features that are now enabled",
    )


# --- verify_club_setup ---

class VerifyClubSetupInput(BaseModel):
    """Input for verify_club_setup tool."""
    
    club_id: int = Field(..., description="Club ID to verify", gt=0)


class VerifyClubSetupOutput(BaseModel):
    """Output for verify_club_setup tool."""
    
    club_exists: bool = Field(..., description="Whether club exists")
    config_valid: bool = Field(..., description="Whether config is valid")
    has_admin: bool = Field(..., description="Whether club has an admin user")
    features_enabled: list[str] = Field(
        default_factory=list,
        description="List of enabled features",
    )
    issues: list[str] = Field(
        default_factory=list,
        description="List of issues found during verification",
    )


# ============================================================================
# Atlassian Tool Schemas (3 tools)
# ============================================================================

# --- create_ticket ---

class CreateTicketInput(BaseModel):
    """Input for create_ticket tool."""
    
    project_key: str = Field(
        ...,
        description="Jira project key (e.g., 'GOLF')",
        min_length=1,
        max_length=10,
    )
    summary: str = Field(
        ...,
        description="Ticket summary/title",
        min_length=1,
        max_length=255,
    )
    description: Optional[str] = Field(
        None,
        description="Ticket description (markdown supported)",
        max_length=32768,  # 32KB
    )
    issue_type: IssueType = Field(
        default=IssueType.TASK,
        description="Issue type (Task, Bug, Story)",
    )
    labels: list[str] = Field(
        default_factory=list,
        description="Labels to apply",
    )
    
    @field_validator("project_key")
    @classmethod
    def validate_project_key(cls, v: str) -> str:
        return v.upper()


class CreateTicketOutput(BaseModel):
    """Output for create_ticket tool."""
    
    ticket_id: str = Field(..., description="Jira internal ticket ID")
    ticket_key: str = Field(..., description="Ticket key (e.g., 'GOLF-123')")
    url: str = Field(..., description="URL to view ticket")
    status: str = Field(..., description="Initial ticket status")
    created_at: datetime = Field(..., description="Creation timestamp")


# --- get_ticket_status ---

class GetTicketStatusInput(BaseModel):
    """Input for get_ticket_status tool."""
    
    ticket_key: str = Field(
        ...,
        description="Ticket key (e.g., 'GOLF-123')",
        min_length=1,
    )


class GetTicketStatusOutput(BaseModel):
    """Output for get_ticket_status tool. Returns None values if not found."""
    
    ticket_key: Optional[str] = Field(None, description="Ticket key")
    summary: Optional[str] = Field(None, description="Ticket summary")
    status: Optional[str] = Field(None, description="Current status")
    assignee: Optional[str] = Field(None, description="Assignee email/name")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    url: Optional[str] = Field(None, description="URL to view ticket")
    found: bool = Field(False, description="Whether ticket was found")


# --- add_comment ---

class AddCommentInput(BaseModel):
    """Input for add_comment tool."""
    
    ticket_key: str = Field(
        ...,
        description="Ticket key (e.g., 'GOLF-123')",
        min_length=1,
    )
    comment_body: str = Field(
        ...,
        description="Comment text (markdown supported)",
        min_length=1,
        max_length=32768,  # 32KB
    )


class AddCommentOutput(BaseModel):
    """Output for add_comment tool."""
    
    ticket_key: str = Field(..., description="Ticket key")
    comment_id: str = Field(..., description="Comment ID")
    author: str = Field(..., description="Comment author")
    created_at: datetime = Field(..., description="Comment creation timestamp")


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
    "IssueType",
    "AdminRole",
    "InternalApiOperation",
    # BRS Input schemas
    "CreateClubInput",
    "GetClubByNameInput",
    "GetClubConfigInput",
    "CreateAdminUserInput",
    "CallInternalApiInput",
    "VerifyClubSetupInput",
    # BRS Output schemas
    "CreateClubOutput",
    "GetClubByNameOutput",
    "GetClubConfigOutput",
    "CreateAdminUserOutput",
    "CallInternalApiOutput",
    "VerifyClubSetupOutput",
    # Atlassian Input schemas
    "CreateTicketInput",
    "GetTicketStatusInput",
    "AddCommentInput",
    # Atlassian Output schemas
    "CreateTicketOutput",
    "GetTicketStatusOutput",
    "AddCommentOutput",
    # Phase 2 adapters
    "BRSTeesheetInitOutput",
    "BRSSuperuserCreateOutput",
    "BRSConfigValidateOutput",
]
