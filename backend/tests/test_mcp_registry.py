"""Tests for MCP tool registry with role-based access control."""
import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timezone

from app.services.mcp_registry import MCPToolRegistry, ToolCallLog
from app.services.mcp_client import MCPTool, MCPToolResult
from app.config.mcp_config import Environment


# ==============================================================================
# Mock User
# ==============================================================================

class UserRole:
    """Mock user role enum."""
    ADMIN = "admin"
    USER = "user"
    PENDING = "pending"

    def __init__(self, value):
        self.value = value


class MockUser:
    """Mock user for testing."""
    def __init__(self, user_id: int, role_value: str):
        self.id = user_id
        self.role = UserRole(role_value)


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def registry():
    """Create MCP tool registry instance."""
    return MCPToolRegistry(Environment.DEVELOPMENT)


@pytest.fixture
def admin_user():
    """Create admin user."""
    return MockUser(1, "admin")


@pytest.fixture
def regular_user():
    """Create regular user."""
    return MockUser(2, "user")


@pytest.fixture
def pending_user():
    """Create pending user."""
    return MockUser(3, "pending")


# ==============================================================================
# Initialization Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_registry_initialization(registry):
    """Test registry initializes MCP clients."""
    await registry.initialize()

    assert registry._initialized is True
    assert len(registry.clients) > 0


@pytest.mark.asyncio
async def test_registry_initialization_idempotent(registry):
    """Test registry initialization is idempotent."""
    await registry.initialize()
    client_count = len(registry.clients)

    # Initialize again
    await registry.initialize()

    # Should not create duplicate clients
    assert len(registry.clients) == client_count


# ==============================================================================
# Tool Discovery Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_discover_all_tools(registry):
    """Test discovering tools from all servers."""
    mock_tools = [
        MCPTool("search", "Search tool", {}, "test-server"),
        MCPTool("analyze", "Analysis tool", {}, "test-server"),
    ]

    await registry.initialize()

    # Mock client methods properly with AsyncMock
    for client in registry.clients.values():
        client.list_tools = AsyncMock(return_value=mock_tools)

    tools_by_server = await registry.discover_all_tools()

    assert len(tools_by_server) > 0
    # Check that at least one server has tools
    total_tools = sum(len(tools) for tools in tools_by_server.values())
    assert total_tools > 0


@pytest.mark.asyncio
async def test_discover_all_tools_with_failure(registry):
    """Test tool discovery with one server failing."""
    mock_tools = [MCPTool("search", "Search tool", {}, "test-server")]

    await registry.initialize()

    # Mock one client to succeed, one to fail
    clients = list(registry.clients.values())
    if len(clients) >= 2:
        clients[0].list_tools = AsyncMock(return_value=mock_tools)
        clients[1].list_tools = AsyncMock(side_effect=Exception("Connection failed"))

        tools_by_server = await registry.discover_all_tools()

        # Should return results for working servers, empty list for failed ones
        assert len(tools_by_server) > 0


# ==============================================================================
# Access Control Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_execute_tool_allowed_for_admin(registry, admin_user):
    """Test admin can execute any tool."""
    mock_result = MCPToolResult(success=True, result="Success")

    await registry.initialize()

    # Mock _find_tool to return server and mock client
    mock_client = AsyncMock()
    mock_client.call_tool = AsyncMock(return_value=mock_result)
    registry._find_tool = AsyncMock(return_value=("test-server", mock_client))

    result = await registry.execute_tool("any_tool", {}, admin_user)

    assert result.success is True
    assert result.error is None


@pytest.mark.asyncio
async def test_execute_tool_allowed_for_user(registry, regular_user):
    """Test user can execute allowed tools."""
    mock_result = MCPToolResult(success=True, result="Results")

    await registry.initialize()

    mock_client = AsyncMock()
    mock_client.call_tool = AsyncMock(return_value=mock_result)
    registry._find_tool = AsyncMock(return_value=("test-server", mock_client))

    # Tool in user allowlist
    result = await registry.execute_tool("search", {"query": "test"}, regular_user)

    assert result.success is True


@pytest.mark.asyncio
async def test_execute_tool_denied_for_user(registry, regular_user):
    """Test user cannot execute disallowed tools."""
    await registry.initialize()

    # Tool NOT in user allowlist
    result = await registry.execute_tool("admin_tool", {}, regular_user)

    assert result.success is False
    assert "not allowed" in result.error.lower()


@pytest.mark.asyncio
async def test_execute_tool_denied_for_pending(registry, pending_user):
    """Test pending user cannot execute tools."""
    await registry.initialize()

    # Pending users have empty allowlist
    result = await registry.execute_tool("search", {}, pending_user)

    assert result.success is False
    assert "not allowed" in result.error.lower()


@pytest.mark.asyncio
async def test_execute_tool_not_found(registry, admin_user):
    """Test executing non-existent tool."""
    await registry.initialize()

    # Mock tool not found
    registry._find_tool = AsyncMock(return_value=(None, None))

    result = await registry.execute_tool("nonexistent", {}, admin_user)

    assert result.success is False
    assert "not found" in result.error.lower()


# ==============================================================================
# Tool Call Logging Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_tool_call_logged_on_success(registry, admin_user):
    """Test successful tool calls are logged."""
    mock_result = MCPToolResult(success=True, result="Success")

    await registry.initialize()

    mock_client = AsyncMock()
    mock_client.call_tool = AsyncMock(return_value=mock_result)
    registry._find_tool = AsyncMock(return_value=("test-server", mock_client))

    initial_log_count = len(registry.tool_call_logs)

    await registry.execute_tool("search", {"query": "test"}, admin_user)

    # Should have logged the call
    assert len(registry.tool_call_logs) == initial_log_count + 1

    log_entry = registry.tool_call_logs[-1]
    assert log_entry.tool_name == "search"
    assert log_entry.server_name == "test-server"
    assert log_entry.user_id == admin_user.id


@pytest.mark.asyncio
async def test_tool_call_logged_on_failure(registry, admin_user):
    """Test failed tool calls are logged."""
    mock_result = MCPToolResult(success=False, error="Tool failed")

    await registry.initialize()

    mock_client = AsyncMock()
    mock_client.call_tool = AsyncMock(return_value=mock_result)
    registry._find_tool = AsyncMock(return_value=("test-server", mock_client))

    initial_log_count = len(registry.tool_call_logs)

    await registry.execute_tool("analyze", {}, admin_user)

    # Should have logged the failed call
    assert len(registry.tool_call_logs) == initial_log_count + 1

    log_entry = registry.tool_call_logs[-1]
    assert log_entry.result.success is False


@pytest.mark.asyncio
async def test_tool_call_logged_when_denied(registry, regular_user):
    """Test denied tool calls are logged."""
    await registry.initialize()

    initial_log_count = len(registry.tool_call_logs)

    # Try to execute disallowed tool
    await registry.execute_tool("admin_tool", {}, regular_user)

    # Should have logged the denial
    assert len(registry.tool_call_logs) == initial_log_count + 1

    log_entry = registry.tool_call_logs[-1]
    assert log_entry.server_name == "DENIED"


@pytest.mark.asyncio
async def test_get_tool_call_logs(registry, admin_user, regular_user):
    """Test retrieving tool call logs."""
    mock_result = MCPToolResult(success=True)

    await registry.initialize()

    mock_client = AsyncMock()
    mock_client.call_tool = AsyncMock(return_value=mock_result)
    registry._find_tool = AsyncMock(return_value=("test-server", mock_client))

    # Execute tools as different users
    await registry.execute_tool("search", {}, admin_user)
    await registry.execute_tool("analyze", {}, regular_user)

    # Get all logs
    all_logs = registry.get_tool_call_logs()
    assert len(all_logs) >= 2

    # Get logs for specific user
    user_logs = registry.get_tool_call_logs(user_id=admin_user.id)
    assert all(log["user_id"] == admin_user.id for log in user_logs)


# ==============================================================================
# Health Check Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_health_check_all_servers(registry):
    """Test health check for all servers."""
    await registry.initialize()

    # Mock health checks
    for client in registry.clients.values():
        client.health_check = AsyncMock(return_value=True)

    health_status = await registry.health_check_all()

    assert len(health_status) == len(registry.clients)
    assert all(health_status.values())  # All healthy


@pytest.mark.asyncio
async def test_health_check_with_unhealthy_server(registry):
    """Test health check with one unhealthy server."""
    await registry.initialize()

    clients = list(registry.clients.values())
    if len(clients) >= 2:
        # First server healthy, second unhealthy
        clients[0].health_check = AsyncMock(return_value=True)
        clients[1].health_check = AsyncMock(return_value=False)

        health_status = await registry.health_check_all()

        # Should report mixed health status
        assert True in health_status.values()
        assert False in health_status.values()


# ==============================================================================
# Tool Call Log Tests
# ==============================================================================

def test_tool_call_log_to_dict():
    """Test tool call log serialization."""
    result = MCPToolResult(success=True, result="Success", execution_time_ms=150.5)
    mock_user = MockUser(1, "user")

    log = ToolCallLog(
        tool_name="search",
        server_name="test-server",
        user_id=mock_user.id,
        user_role=mock_user.role.value,
        arguments={"query": "test"},
        result=result,
        timestamp=datetime.now(timezone.utc),
    )

    log_dict = log.to_dict()

    assert log_dict["tool_name"] == "search"
    assert log_dict["server_name"] == "test-server"
    assert log_dict["user_id"] == 1
    assert log_dict["success"] is True
    assert log_dict["execution_time_ms"] == 150.5
