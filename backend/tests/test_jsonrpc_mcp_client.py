"""Tests for JSON-RPC 2.0 MCP client."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.jsonrpc_mcp_client import JsonRpcMCPClient
from app.config.mcp_config import MCPServerConfig


@pytest.fixture
def mock_config():
    """Create mock MCP server config."""
    return MCPServerConfig(
        name="test-jsonrpc",
        url="https://mcp.example.com/v1/mcp",
        timeout_seconds=30
    )


@pytest.fixture
def mock_session():
    """Create mock aiohttp session."""
    session = MagicMock()
    session.closed = False
    return session


@pytest.mark.asyncio
async def test_initialize_creates_session(mock_config):
    """Test that initialize creates session and establishes session ID."""
    client = JsonRpcMCPClient(mock_config)

    # Mock aiohttp session
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "protocolVersion": "2024-11-05",
            "sessionId": "test-session-123"
        }
    })

    with patch('aiohttp.ClientSession') as mock_session_class:
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))
        mock_session_class.return_value = mock_session

        await client.initialize()

        # Verify session was created
        assert client.session is not None
        assert client.session_id == "test-session-123"


@pytest.mark.asyncio
async def test_list_tools_uses_session_id(mock_config):
    """Test that list_tools includes session ID in request."""
    client = JsonRpcMCPClient(mock_config)
    client.session_id = "test-session-123"

    # Mock response
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={
        "jsonrpc": "2.0",
        "id": 2,
        "result": {
            "tools": [
                {
                    "name": "test_tool",
                    "description": "Test tool",
                    "inputSchema": {"type": "object"}
                }
            ]
        }
    })

    with patch.object(client, 'session') as mock_session:
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))

        tools = await client.list_tools()

        # Verify tools were returned
        assert len(tools) == 1
        assert tools[0].name == "test_tool"

        # Verify session ID was included
        call_args = mock_session.post.call_args
        json_payload = call_args[1]['json']
        assert json_payload['params']['sessionId'] == "test-session-123"


@pytest.mark.asyncio
async def test_call_tool_uses_session_id(mock_config):
    """Test that call_tool includes session ID in request."""
    client = JsonRpcMCPClient(mock_config)
    client.session_id = "test-session-123"

    # Mock response
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={
        "jsonrpc": "2.0",
        "id": 3,
        "result": {
            "output": "Tool executed successfully"
        }
    })

    with patch.object(client, 'session') as mock_session:
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))

        result = await client.call_tool(
            tool_name="test_tool",
            arguments={"arg1": "value1"}
        )

        # Verify result
        assert result.success is True
        assert result.result["output"] == "Tool executed successfully"

        # Verify session ID was included
        call_args = mock_session.post.call_args
        json_payload = call_args[1]['json']
        assert json_payload['params']['sessionId'] == "test-session-123"
        assert json_payload['params']['name'] == "test_tool"
        assert json_payload['params']['arguments'] == {"arg1": "value1"}


@pytest.mark.asyncio
async def test_call_tool_without_session_returns_error(mock_config):
    """Test that call_tool returns error if no session ID."""
    client = JsonRpcMCPClient(mock_config)
    # Don't set session_id

    result = await client.call_tool(
        tool_name="test_tool",
        arguments={}
    )

    assert result.success is False
    assert "No session ID" in result.error


@pytest.mark.asyncio
async def test_jsonrpc_error_response(mock_config):
    """Test handling of JSON-RPC error response."""
    client = JsonRpcMCPClient(mock_config)
    client.session_id = "test-session-123"

    # Mock error response
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={
        "jsonrpc": "2.0",
        "id": 3,
        "error": {
            "code": -32600,
            "message": "Invalid request"
        }
    })

    with patch.object(client, 'session') as mock_session:
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))

        result = await client.call_tool(
            tool_name="test_tool",
            arguments={}
        )

        assert result.success is False
        assert "Invalid request" in result.error
        assert result.is_semantic_error is True


@pytest.mark.asyncio
async def test_health_check_without_session_returns_false(mock_config):
    """Test that health_check returns False without session ID."""
    client = JsonRpcMCPClient(mock_config)

    is_healthy = await client.health_check()

    assert is_healthy is False


@pytest.mark.asyncio
async def test_request_id_increments(mock_config):
    """Test that request IDs increment sequentially."""
    client = JsonRpcMCPClient(mock_config)
    client.session_id = "test-session-123"

    request_ids = []

    # Mock response
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"tools": []}
    })

    with patch.object(client, 'session') as mock_session:
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))

        # Make multiple requests
        for _ in range(3):
            await client.list_tools(force_refresh=True)
            call_args = mock_session.post.call_args
            json_payload = call_args[1]['json']
            request_ids.append(json_payload['id'])

    # Verify IDs increment
    assert request_ids == [1, 2, 3]
