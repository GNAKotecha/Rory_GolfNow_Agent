"""MCP server configuration and allowlists.

Defines which MCP servers are available per environment and which tools
are accessible per user role.
"""
import os
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum


# ==============================================================================
# Environment Types
# ==============================================================================

class Environment(Enum):
    """Deployment environment."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


# ==============================================================================
# MCP Server Configuration
# ==============================================================================

@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""
    name: str
    url: str
    timeout_seconds: int = 30
    max_retries: int = 3
    enabled: bool = True
    description: Optional[str] = None


# ==============================================================================
# Server Registry
# ==============================================================================

def _normalize_gateway_url(raw_url: str) -> str:
    """
    Normalize gateway URL to ensure clean /mcp suffix.
    
    Handles:
    - Trailing slashes
    - Duplicate /mcp suffixes
    - Missing /mcp suffix
    
    Examples:
        http://localhost:8090 -> http://localhost:8090/mcp
        http://localhost:8090/ -> http://localhost:8090/mcp
        http://localhost:8090/mcp -> http://localhost:8090/mcp
        http://localhost:8090/mcp/ -> http://localhost:8090/mcp
        http://localhost:8090/mcp/mcp -> http://localhost:8090/mcp
    """
    url = raw_url.rstrip("/")
    
    # Strip trailing /mcp repeatedly to handle /mcp/mcp cases
    while url.endswith("/mcp"):
        url = url[:-4].rstrip("/")
    
    # Add single /mcp suffix
    return f"{url}/mcp"


# Prefer MCP_GATEWAY_URL; fall back to legacy MCP_SERVER_URL for compatibility.
_raw_gateway_url = (
    os.environ.get("MCP_GATEWAY_URL")
    or os.environ.get("MCP_SERVER_URL")
    or "http://localhost:8090"
)
_gateway_mcp_url = _normalize_gateway_url(_raw_gateway_url)

# Auxiliary MCP servers (test-mcp, mock-search) are opt-in for development.
# Set ENABLE_AUX_MCP_SERVERS=true to include them (noisy if not running).
_enable_aux_servers = os.environ.get("ENABLE_AUX_MCP_SERVERS", "false").lower() in ("true", "1", "yes")

# Core gateway server - always included in development
_GATEWAY_SERVER = MCPServerConfig(
    name="gateway-mcp",
    url=_gateway_mcp_url,
    timeout_seconds=30,
    max_retries=3,
    description="Gateway MCP - Business-level BRS and Atlassian tools",
)

# Auxiliary servers - only included when ENABLE_AUX_MCP_SERVERS=true
_AUX_SERVERS = [
    MCPServerConfig(
        name="test-mcp",
        url="http://localhost:8080/mcp",
        timeout_seconds=10,
        max_retries=2,
        description="Local test MCP server",
    ),
    MCPServerConfig(
        name="mock-search",
        url="http://localhost:8081/mcp",
        timeout_seconds=5,
        max_retries=1,
        description="Mock search service",
    ),
]

# Development environment servers
DEVELOPMENT_SERVERS = [_GATEWAY_SERVER] + (_AUX_SERVERS if _enable_aux_servers else [])

# Staging environment - subset of production servers
STAGING_SERVERS = [
    MCPServerConfig(
        name="gateway-mcp",
        url="https://gateway-mcp-staging.example.com/mcp",
        timeout_seconds=30,
        max_retries=3,
        description="Gateway MCP - Business-level BRS and Atlassian tools",
    ),
    MCPServerConfig(
        name="search-staging",
        url="https://search-staging.example.com/mcp",
        timeout_seconds=30,
        max_retries=3,
        description="Staging search service",
    ),
]

# Production environment - fully qualified servers
PRODUCTION_SERVERS = [
    MCPServerConfig(
        name="gateway-mcp",
        url="https://gateway-mcp.example.com/mcp",
        timeout_seconds=30,
        max_retries=3,
        description="Gateway MCP - Business-level BRS and Atlassian tools",
    ),
    MCPServerConfig(
        name="search-prod",
        url="https://search.example.com/mcp",
        timeout_seconds=30,
        max_retries=3,
        description="Production search service",
    ),
    MCPServerConfig(
        name="analytics-prod",
        url="https://analytics.example.com/mcp",
        timeout_seconds=45,
        max_retries=3,
        description="Production analytics service",
    ),
]

# Environment-based server selection
MCP_SERVERS: Dict[Environment, List[MCPServerConfig]] = {
    Environment.DEVELOPMENT: DEVELOPMENT_SERVERS,
    Environment.STAGING: STAGING_SERVERS,
    Environment.PRODUCTION: PRODUCTION_SERVERS,
}


# ==============================================================================
# Tool Allowlists
# ==============================================================================
#
# AUTHORIZATION LAYERS:
# This file implements the **backend role-based allowlist** for MCP tool access.
# There is also a **Gateway MCP permission layer** in gateway_mcp/core/permissions.py
# that enforces risk_level checks at the gateway.
#
# How they work together:
# 1. Backend allowlist (this file): Controls which tools a user can even attempt
#    to call based on their role. This is checked by MCPToolRegistry.execute_tool().
#
# 2. Gateway permissions (gateway_mcp/core/permissions.py): Enforces risk_level
#    restrictions (read/low_write/medium_write/high_write) and environment
#    restrictions (local/dev/qa/prod) at the gateway boundary.
#
# Both layers must pass for a tool call to succeed.
# Changes to allowlists here should be coordinated with Gateway tool definitions.
#
# Gateway Tool Risk Levels (for reference):
# - read: get_club_by_name, get_club_config, verify_club_setup, get_ticket_status
# - low_write: create_club, create_ticket, add_comment
# - medium_write: create_admin_user, call_internal_api
# ==============================================================================

# Admin: full access to all tools
ADMIN_ALLOWLIST = ["*"]  # Wildcard = all tools

# User: standard tool access
USER_ALLOWLIST = [
    "search",
    "analyze",
    "compute",
    "summarize",
    "translate",
    "format",
    # Gateway MCP BRS tools (read-only or operator-approved)
    "get_club_by_name",
    "get_club_config",
    "verify_club_setup",
    # Gateway MCP Atlassian tools (read-only)
    "get_ticket_status",
]

# Operator: workflow execution tools
OPERATOR_ALLOWLIST = [
    # User tools
    "search",
    "analyze",
    "compute",
    "summarize",
    "translate",
    "format",
    "get_club_by_name",
    "get_club_config",
    "verify_club_setup",
    "get_ticket_status",
    # Gateway MCP BRS tools (write operations)
    "create_club",
    "create_admin_user",
    "call_internal_api",
    # Gateway MCP Atlassian tools (write operations)
    "create_ticket",
    "add_comment",
]

# Pending: minimal access (awaiting approval)
PENDING_ALLOWLIST: List[str] = []  # No tools until approved

# Role-based tool allowlists
TOOL_ALLOWLIST: Dict[str, List[str]] = {
    "admin": ADMIN_ALLOWLIST,
    "operator": OPERATOR_ALLOWLIST,
    "user": USER_ALLOWLIST,
    "pending": PENDING_ALLOWLIST,
}


# ==============================================================================
# Tool Filtering
# ==============================================================================

def is_tool_allowed(tool_name: str, role: str) -> bool:
    """
    Check if a tool is allowed for a given role.

    Args:
        tool_name: Name of the tool to check
        role: User role (admin, user, pending)

    Returns:
        True if tool is allowed, False otherwise
    """
    allowlist = TOOL_ALLOWLIST.get(role, [])

    # Wildcard grants all tools
    if "*" in allowlist:
        return True

    # Check explicit allowlist
    return tool_name in allowlist


def filter_tools_by_role(tools: List[str], role: str) -> List[str]:
    """
    Filter tool list based on role allowlist.

    Args:
        tools: List of tool names
        role: User role

    Returns:
        Filtered list of allowed tools
    """
    return [tool for tool in tools if is_tool_allowed(tool, role)]


def get_allowed_tools(role: str) -> List[str]:
    """
    Get list of allowed tools for a role.

    Args:
        role: User role

    Returns:
        List of allowed tool names (or ["*"] for wildcard)
    """
    return TOOL_ALLOWLIST.get(role, [])


# ==============================================================================
# Server Selection
# ==============================================================================

def get_servers_for_environment(environment: Environment) -> List[MCPServerConfig]:
    """
    Get MCP servers for a specific environment.

    Args:
        environment: Deployment environment

    Returns:
        List of enabled MCP server configurations
    """
    servers = MCP_SERVERS.get(environment, [])
    return [s for s in servers if s.enabled]


def get_server_by_name(
    name: str,
    environment: Environment,
) -> Optional[MCPServerConfig]:
    """
    Get specific MCP server configuration by name.

    Args:
        name: Server name
        environment: Deployment environment

    Returns:
        Server configuration or None if not found
    """
    servers = get_servers_for_environment(environment)
    for server in servers:
        if server.name == name:
            return server
    return None
