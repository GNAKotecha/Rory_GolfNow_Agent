"""Tests for MCP client with mocked HTTP responses."""
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime, timezone

from app.services.mcp_client import MCPClient, MCPTool, MCPToolResult
from app.config.mcp_config import MCPServerConfig


# ==============================================================================
# Test Helpers
# ==============================================================================

class AsyncContextManagerMock:
    """Mock for async context manager."""
    def __init__(self, return_value):
        self.return_value = return_value

    async def __aenter__(self):
        return self.return_value

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


def make_async_context_manager(return_value):
    """Create an async context manager mock that won't be wrapped by AsyncMock."""
    return AsyncContextManagerMock(return_value)


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


@pytest.fixture
def client(test_config):
    """Create MCP client instance."""
    return MCPClient(test_config)


# ==============================================================================
# Health Check Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_health_check_success(client):
    """Test successful health check."""
    mock_response = Mock()
    mock_response.status = 200

    mock_session = AsyncMock()
    mock_session.get.return_value = AsyncContextManagerMock(mock_response)

    with patch.object(client, "_get_session", return_value=mock_session):
        is_healthy = await client.health_check()

        assert is_healthy is True


@pytest.mark.asyncio
async def test_health_check_failure(client):
    """Test failed health check."""
    mock_response = Mock()
    mock_response.status = 500

    mock_session = AsyncMock()
    mock_session.get.return_value = AsyncContextManagerMock(mock_response)

    with patch.object(client, "_get_session", return_value=mock_session):
        is_healthy = await client.health_check()

        assert is_healthy is False


@pytest.mark.asyncio
async def test_health_check_connection_error(client):
    """Test health check with connection error."""
    mock_session = AsyncMock()
    mock_session.get.side_effect = ConnectionError("Connection refused")

    with patch.object(client, "_get_session", return_value=mock_session):
        is_healthy = await client.health_check()

        assert is_healthy is False


# ==============================================================================
# List Tools Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_list_tools_success(client):
    """Test successful tool discovery."""
    mock_response = Mock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={
        "tools": [
            {
                "name": "search",
                "description": "Search tool",
                "inputSchema": {"type": "object"},
            },
            {
                "name": "analyze",
                "description": "Analysis tool",
                "inputSchema": {"type": "object"},
            },
        ]
    })

    mock_session = AsyncMock()
    mock_session.get.return_value = AsyncContextManagerMock(mock_response)

    with patch.object(client, "_get_session", return_value=mock_session):
        tools = await client.list_tools()

        assert len(tools) == 2
        assert tools[0].name == "search"
        assert tools[0].description == "Search tool"
        assert tools[0].server_name == "test-server"
        assert tools[1].name == "analyze"


@pytest.mark.asyncio
async def test_list_tools_empty(client):
    """Test tool discovery with no tools."""
    mock_response = Mock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"tools": []})

    mock_session = AsyncMock()
    mock_session.get.return_value = AsyncContextManagerMock(mock_response)

    with patch.object(client, "_get_session", return_value=mock_session):
        tools = await client.list_tools()

        assert tools == []


@pytest.mark.asyncio
async def test_list_tools_server_error(client):
    """Test tool discovery with server error."""
    mock_response = Mock()
    mock_response.status = 500

    mock_session = AsyncMock()
    mock_session.get.return_value = AsyncContextManagerMock(mock_response)

    with patch.object(client, "_get_session", return_value=mock_session):
        tools = await client.list_tools()

        assert tools == []


@pytest.mark.asyncio
async def test_list_tools_caching(client):
    """Test tool discovery uses cache."""
    mock_response = Mock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={
        "tools": [{"name": "search", "description": "Search"}]
    })

    mock_session = AsyncMock()
    mock_session.get.return_value = AsyncContextManagerMock(mock_response)

    with patch.object(client, "_get_session", return_value=mock_session):
        # First call - should fetch
        tools1 = await client.list_tools()

        # Second call - should use cache
        tools2 = await client.list_tools()

        # Should only make one HTTP request
        assert mock_session.get.call_count == 1
        assert tools1[0].name == tools2[0].name


@pytest.mark.asyncio
async def test_list_tools_force_refresh(client):
    """Test tool discovery with forced cache refresh."""
    mock_response = Mock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={
        "tools": [{"name": "search", "description": "Search"}]
    })

    mock_session = AsyncMock()
    mock_session.get.return_value = AsyncContextManagerMock(mock_response)

    with patch.object(client, "_get_session", return_value=mock_session):
        # First call
        await client.list_tools()

        # Second call with force_refresh
        await client.list_tools(force_refresh=True)

        # Should make two HTTP requests
        assert mock_session.get.call_count == 2


# ==============================================================================
# Call Tool Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_call_tool_success(client):
    """Test successful tool call."""
    mock_response = Mock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"result": "Success"})

    mock_session = AsyncMock()
    mock_session.post.return_value = AsyncContextManagerMock(mock_response)

    with patch.object(client, "_get_session", return_value=mock_session):
        result = await client.call_tool("search", {"query": "test"})

        assert result.success is True
        assert result.result == "Success"
        assert result.error is None
        assert result.execution_time_ms is not None
        assert result.retry_count == 0


@pytest.mark.asyncio
async def test_call_tool_not_found(client):
    """Test tool call with 404 error."""
    mock_response = Mock()
    mock_response.status = 404

    mock_session = AsyncMock()
    mock_session.post.return_value = AsyncContextManagerMock(mock_response)

    with patch.object(client, "_get_session", return_value=mock_session):
        result = await client.call_tool("nonexistent", {})

        assert result.success is False
        assert "not found" in result.error.lower()
        assert result.retry_count == 0  # Don't retry 404


@pytest.mark.asyncio
async def test_call_tool_server_error_with_retry(client):
    """Test tool call with server error and retry."""
    # First attempt fails, second succeeds
    mock_response_fail = Mock()
    mock_response_fail.status = 500
    mock_response_fail.text = AsyncMock(return_value="Internal error")

    mock_response_success = Mock()
    mock_response_success.status = 200
    mock_response_success.json = AsyncMock(return_value={"result": "Success after retry"})

    mock_session = AsyncMock()
    mock_session.post.side_effect = [
        AsyncContextManagerMock(mock_response_fail),
        AsyncContextManagerMock(mock_response_success),
    ]

    with patch.object(client, "_get_session", return_value=mock_session):
        result = await client.call_tool("search", {"query": "test"})

        assert result.success is True
        assert result.retry_count == 1


@pytest.mark.asyncio
async def test_call_tool_timeout(client):
    """Test tool call timeout."""
    mock_session = AsyncMock()
    # Make the context manager itself raise the timeout
    async def raise_timeout():
        raise asyncio.TimeoutError()

    mock_session.post.return_value.__aenter__ = raise_timeout

    with patch.object(client, "_get_session", return_value=mock_session):
        result = await client.call_tool("search", {"query": "test"})

        assert result.success is False
        assert "Timeout" in result.error
        assert result.retry_count == client.config.max_retries


@pytest.mark.asyncio
async def test_call_tool_connection_error(client):
    """Test tool call with connection error."""
    mock_session = AsyncMock()
    mock_session.post.side_effect = ConnectionError("Cannot connect")

    with patch.object(client, "_get_session", return_value=mock_session):
        result = await client.call_tool("search", {"query": "test"})

        assert result.success is False
        assert "Connection error" in result.error
        assert result.retry_count == client.config.max_retries


@pytest.mark.asyncio
async def test_call_tool_max_retries_exceeded(client):
    """Test tool call exceeds max retries."""
    mock_response = Mock()
    mock_response.status = 503  # Service unavailable
    mock_response.text = AsyncMock(return_value="Service unavailable")

    mock_session = AsyncMock()
    mock_session.post.return_value = AsyncContextManagerMock(mock_response)

    with patch.object(client, "_get_session", return_value=mock_session):
        result = await client.call_tool("search", {"query": "test"})

        assert result.success is False
        assert result.retry_count == client.config.max_retries
        # Should have tried: initial + 2 retries = 3 attempts
        assert mock_session.post.call_count == client.config.max_retries + 1


# ==============================================================================
# Client Lifecycle Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_client_close(client):
    """Test client session closure."""
    # Create a mock session
    mock_session = AsyncMock()
    mock_session.closed = False
    client.session = mock_session

    await client.close()

    mock_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_client_close_already_closed(client):
    """Test closing already closed client."""
    mock_session = AsyncMock()
    mock_session.closed = True
    client.session = mock_session

    # Should not raise error
    await client.close()
