"""MCP server configuration and allowlists.

Defines which MCP servers are available per environment and which tools
are accessible per user role.
"""
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

# Development environment - includes test servers
DEVELOPMENT_SERVERS = [
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

# Staging environment - subset of production servers
STAGING_SERVERS = [
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
]

# Pending: minimal access (awaiting approval)
PENDING_ALLOWLIST: List[str] = []  # No tools until approved

# Role-based tool allowlists
TOOL_ALLOWLIST: Dict[str, List[str]] = {
    "admin": ADMIN_ALLOWLIST,
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
