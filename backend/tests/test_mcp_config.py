"""Tests for MCP configuration and allowlists."""
import pytest

from app.config.mcp_config import (
    Environment,
    MCPServerConfig,
    is_tool_allowed,
    filter_tools_by_role,
    get_allowed_tools,
    get_servers_for_environment,
    get_server_by_name,
    TOOL_ALLOWLIST,
)


# ==============================================================================
# Server Configuration Tests
# ==============================================================================

def test_server_config_creation():
    """Test MCP server configuration creation."""
    config = MCPServerConfig(
        name="test-server",
        url="http://localhost:8080/mcp",
        timeout_seconds=30,
        max_retries=3,
    )

    assert config.name == "test-server"
    assert config.url == "http://localhost:8080/mcp"
    assert config.timeout_seconds == 30
    assert config.max_retries == 3
    assert config.enabled is True


def test_server_config_defaults():
    """Test MCP server configuration defaults."""
    config = MCPServerConfig(
        name="test",
        url="http://test.com",
    )

    assert config.timeout_seconds == 30
    assert config.max_retries == 3
    assert config.enabled is True


# ==============================================================================
# Tool Allowlist Tests
# ==============================================================================

def test_admin_has_wildcard_access():
    """Test admin role has wildcard access."""
    assert is_tool_allowed("any_tool", "admin")
    assert is_tool_allowed("dangerous_tool", "admin")
    assert is_tool_allowed("unrestricted", "admin")


def test_user_has_limited_access():
    """Test user role has limited tool access."""
    # Allowed tools
    assert is_tool_allowed("search", "user")
    assert is_tool_allowed("analyze", "user")
    assert is_tool_allowed("compute", "user")

    # Not allowed tools
    assert not is_tool_allowed("admin_tool", "user")
    assert not is_tool_allowed("delete_database", "user")


def test_pending_has_no_access():
    """Test pending role has no tool access."""
    assert not is_tool_allowed("search", "pending")
    assert not is_tool_allowed("analyze", "pending")
    assert not is_tool_allowed("any_tool", "pending")


def test_unknown_role_has_no_access():
    """Test unknown role has no tool access."""
    assert not is_tool_allowed("search", "unknown_role")
    assert not is_tool_allowed("analyze", "unknown_role")


def test_filter_tools_by_role_admin():
    """Test filtering tools for admin role."""
    tools = ["search", "analyze", "admin_tool", "dangerous"]

    filtered = filter_tools_by_role(tools, "admin")

    # Admin gets all tools
    assert filtered == tools


def test_filter_tools_by_role_user():
    """Test filtering tools for user role."""
    tools = ["search", "analyze", "admin_tool", "compute"]

    filtered = filter_tools_by_role(tools, "user")

    # User only gets allowed tools
    assert "search" in filtered
    assert "analyze" in filtered
    assert "compute" in filtered
    assert "admin_tool" not in filtered


def test_filter_tools_by_role_pending():
    """Test filtering tools for pending role."""
    tools = ["search", "analyze", "compute"]

    filtered = filter_tools_by_role(tools, "pending")

    # Pending gets no tools
    assert filtered == []


def test_get_allowed_tools_admin():
    """Test getting allowed tools list for admin."""
    allowed = get_allowed_tools("admin")

    assert "*" in allowed  # Wildcard


def test_get_allowed_tools_user():
    """Test getting allowed tools list for user."""
    allowed = get_allowed_tools("user")

    assert "search" in allowed
    assert "analyze" in allowed
    assert "compute" in allowed
    assert "*" not in allowed


def test_get_allowed_tools_pending():
    """Test getting allowed tools list for pending."""
    allowed = get_allowed_tools("pending")

    assert allowed == []


# ==============================================================================
# Server Selection Tests
# ==============================================================================

def test_get_servers_for_development():
    """Test getting servers for development environment."""
    servers = get_servers_for_environment(Environment.DEVELOPMENT)

    assert len(servers) > 0
    assert all(s.enabled for s in servers)
    assert any(s.name == "test-mcp" for s in servers)


def test_get_servers_for_staging():
    """Test getting servers for staging environment."""
    servers = get_servers_for_environment(Environment.STAGING)

    assert len(servers) > 0
    assert all(s.enabled for s in servers)


def test_get_servers_for_production():
    """Test getting servers for production environment."""
    servers = get_servers_for_environment(Environment.PRODUCTION)

    assert len(servers) > 0
    assert all(s.enabled for s in servers)


def test_get_server_by_name_found():
    """Test getting server by name when it exists."""
    server = get_server_by_name("test-mcp", Environment.DEVELOPMENT)

    assert server is not None
    assert server.name == "test-mcp"


def test_get_server_by_name_not_found():
    """Test getting server by name when it doesn't exist."""
    server = get_server_by_name("nonexistent", Environment.DEVELOPMENT)

    assert server is None


def test_get_server_by_name_wrong_environment():
    """Test getting server from wrong environment."""
    # test-mcp is in DEVELOPMENT, not PRODUCTION
    server = get_server_by_name("test-mcp", Environment.PRODUCTION)

    assert server is None
