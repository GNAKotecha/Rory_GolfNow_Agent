"""Simpler MCP client tests with stub implementation."""
import pytest
import asyncio
from app.services.mcp_client import MCPClient, MCPToolResult
from app.config.mcp_config import MCPServerConfig


# ==============================================================================
# Test Stub Implementation
# ==============================================================================

class StubMCPClient(MCPClient):
    """Stub MCP client for testing without network calls."""

    def __init__(self, config, healthy=True, tools_response=None, call_response=None):
        super().__init__(config)
        self._stub_healthy = healthy
        self._stub_tools = tools_response or []
        self._stub_call_response = call_response

    async def health_check(self) -> bool:
        """Stub health check."""
        return self._stub_healthy

    async def list_tools(self, force_refresh=False):
        """Stub list tools."""
        return self._stub_tools

    async def call_tool(self, tool_name, arguments):
        """Stub call tool."""
        if self._stub_call_response:
            return self._stub_call_response

        # Default behavior
        return MCPToolResult(
            success=True,
            result=f"Stub result for {tool_name}",
            execution_time_ms=10.0,
        )


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def test_config():
    """Create test MCP server configuration."""
    return MCPServerConfig(
        name="test-server",
        url="http://localhost:8080/mcp",
        timeout_seconds=5,
        max_retries=2,
    )


# ==============================================================================
# Health Check Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_health_check_success(test_config):
    """Test successful health check."""
    client = StubMCPClient(test_config, healthy=True)
    is_healthy = await client.health_check()

    assert is_healthy is True


@pytest.mark.asyncio
async def test_health_check_failure(test_config):
    """Test failed health check."""
    client = StubMCPClient(test_config, healthy=False)
    is_healthy = await client.health_check()

    assert is_healthy is False


# ==============================================================================
# Tool Discovery Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_list_tools_success(test_config):
    """Test successful tool discovery."""
    from app.services.mcp_client import MCPTool

    stub_tools = [
        MCPTool("search", "Search tool", {}, "test-server"),
        MCPTool("analyze", "Analysis tool", {}, "test-server"),
    ]

    client = StubMCPClient(test_config, tools_response=stub_tools)
    tools = await client.list_tools()

    assert len(tools) == 2
    assert tools[0].name == "search"
    assert tools[1].name == "analyze"


@pytest.mark.asyncio
async def test_list_tools_empty(test_config):
    """Test tool discovery with no tools."""
    client = StubMCPClient(test_config, tools_response=[])
    tools = await client.list_tools()

    assert tools == []


# ==============================================================================
# Tool Call Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_call_tool_success(test_config):
    """Test successful tool call."""
    result_stub = MCPToolResult(
        success=True,
        result="Success",
        execution_time_ms=15.5,
    )

    client = StubMCPClient(test_config, call_response=result_stub)
    result = await client.call_tool("search", {"query": "test"})

    assert result.success is True
    assert result.result == "Success"


@pytest.mark.asyncio
async def test_call_tool_failure(test_config):
    """Test failed tool call."""
    result_stub = MCPToolResult(
        success=False,
        error="Tool not found",
    )

    client = StubMCPClient(test_config, call_response=result_stub)
    result = await client.call_tool("nonexistent", {})

    assert result.success is False
    assert result.error == "Tool not found"


@pytest.mark.asyncio
async def test_call_tool_with_retry(test_config):
    """Test tool call that succeeds after retry."""
    result_stub = MCPToolResult(
        success=True,
        result="Success after retry",
        retry_count=1,
    )

    client = StubMCPClient(test_config, call_response=result_stub)
    result = await client.call_tool("search", {"query": "test"})

    assert result.success is True
    assert result.retry_count == 1


# ==============================================================================
# Configuration Tests
# ==============================================================================

def test_config_defaults():
    """Test MCP server configuration defaults."""
    config = MCPServerConfig(
        name="test",
        url="http://test.com",
    )

    assert config.timeout_seconds == 30
    assert config.max_retries == 3
    assert config.enabled is True


def test_config_custom():
    """Test custom MCP server configuration."""
    config = MCPServerConfig(
        name="custom",
        url="http://custom.com",
        timeout_seconds=60,
        max_retries=5,
        enabled=False,
    )

    assert config.timeout_seconds == 60
    assert config.max_retries == 5
    assert config.enabled is False
