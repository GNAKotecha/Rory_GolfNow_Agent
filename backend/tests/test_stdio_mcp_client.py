"""Tests for Stdio MCP client."""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.stdio_mcp_client import StdioMCPClient


@pytest.mark.asyncio
async def test_initialize_spawns_subprocess():
    """Test that initialize spawns subprocess."""
    client = StdioMCPClient(
        command="node",
        args=["test-mcp-server.js"],
        server_name="test-stdio"
    )

    # Mock subprocess
    mock_process = MagicMock()
    mock_process.pid = 12345
    mock_process.returncode = None
    mock_process.stdin = MagicMock()
    mock_process.stdin.write = MagicMock()
    mock_process.stdin.drain = AsyncMock()
    mock_process.stdout = AsyncMock()
    mock_process.stdout.readline = AsyncMock(return_value=b'{"jsonrpc":"2.0","id":1,"result":{}}\n')

    with patch('asyncio.create_subprocess_exec', return_value=mock_process):
        await client.initialize()

        assert client.process is not None
        assert client.process.pid == 12345


@pytest.mark.asyncio
async def test_list_tools_sends_jsonrpc_request():
    """Test that list_tools sends correct JSON-RPC request."""
    client = StdioMCPClient(
        command="node",
        args=["test-mcp-server.js"],
        server_name="test-stdio"
    )

    # Mock process with stdin/stdout
    mock_stdin = MagicMock()
    mock_stdin.write = MagicMock()
    mock_stdin.drain = AsyncMock()

    mock_stdout = AsyncMock()

    client.process = MagicMock()
    client.process.stdin = mock_stdin
    client.process.stdout = mock_stdout
    client.process.returncode = None

    # Mock response
    response_json = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "tools": [
                {
                    "name": "test_tool",
                    "description": "Test tool",
                    "inputSchema": {"type": "object"}
                }
            ]
        }
    }) + "\n"

    # Setup future to resolve immediately
    future = asyncio.Future()
    future.set_result(json.loads(response_json))

    with patch.object(client, '_pending_requests', {1: future}):
        # Manually increment request ID to match
        client._request_id = 0

        tools = await client.list_tools()

        # Verify request was sent
        assert mock_stdin.write.called
        written_data = mock_stdin.write.call_args[0][0]
        request = json.loads(written_data.decode())

        assert request["jsonrpc"] == "2.0"
        assert request["method"] == "tools/list"
        assert "id" in request

        # Verify tools were parsed
        assert len(tools) == 1
        assert tools[0].name == "test_tool"


@pytest.mark.asyncio
async def test_call_tool_sends_arguments():
    """Test that call_tool sends correct arguments."""
    client = StdioMCPClient(
        command="node",
        args=["test-mcp-server.js"],
        server_name="test-stdio"
    )

    # Mock process
    mock_stdin = MagicMock()
    mock_stdin.write = MagicMock()
    mock_stdin.drain = AsyncMock()

    client.process = MagicMock()
    client.process.stdin = mock_stdin
    client.process.returncode = None

    # Mock response
    response = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"output": "Success"}
    }

    # Setup future
    future = asyncio.Future()
    future.set_result(response)

    with patch.object(client, '_pending_requests', {1: future}):
        client._request_id = 0

        result = await client.call_tool(
            tool_name="test_tool",
            arguments={"arg1": "value1", "arg2": 42}
        )

        # Verify request was sent
        written_data = mock_stdin.write.call_args[0][0]
        request = json.loads(written_data.decode())

        assert request["method"] == "tools/call"
        assert request["params"]["name"] == "test_tool"
        assert request["params"]["arguments"] == {"arg1": "value1", "arg2": 42}

        # Verify result
        assert result.success is True
        assert result.result["output"] == "Success"


@pytest.mark.asyncio
async def test_call_tool_handles_error_response():
    """Test that call_tool handles JSON-RPC error responses."""
    client = StdioMCPClient(
        command="node",
        args=["test-mcp-server.js"],
        server_name="test-stdio"
    )

    # Mock process
    mock_stdin = MagicMock()
    mock_stdin.write = MagicMock()
    mock_stdin.drain = AsyncMock()

    client.process = MagicMock()
    client.process.stdin = mock_stdin
    client.process.returncode = None

    # Mock error response
    response = {
        "jsonrpc": "2.0",
        "id": 1,
        "error": {
            "code": -32602,
            "message": "Invalid params"
        }
    }

    # Setup future
    future = asyncio.Future()
    future.set_result(response)

    with patch.object(client, '_pending_requests', {1: future}):
        client._request_id = 0

        result = await client.call_tool(
            tool_name="test_tool",
            arguments={}
        )

        assert result.success is False
        assert "Invalid params" in result.error
        assert result.is_semantic_error is True


@pytest.mark.asyncio
async def test_close_terminates_subprocess():
    """Test that close terminates subprocess."""
    client = StdioMCPClient(
        command="node",
        args=["test-mcp-server.js"],
        server_name="test-stdio"
    )

    # Mock process
    mock_process = MagicMock()
    mock_process.terminate = MagicMock()
    mock_process.wait = AsyncMock()
    mock_process.returncode = 0

    client.process = mock_process

    # Mock reader task
    mock_reader_task = MagicMock()
    mock_reader_task.cancel = MagicMock()
    mock_reader_task.__await__ = lambda self: iter([])

    client._reader_task = mock_reader_task

    await client.close()

    # Verify subprocess was terminated
    assert mock_process.terminate.called


@pytest.mark.asyncio
async def test_health_check_returns_true_when_running():
    """Test that health_check returns True when subprocess is running."""
    client = StdioMCPClient(
        command="node",
        args=["test-mcp-server.js"],
        server_name="test-stdio"
    )

    # Mock running process
    mock_process = MagicMock()
    mock_process.returncode = None  # Still running

    client.process = mock_process

    is_healthy = await client.health_check()

    assert is_healthy is True


@pytest.mark.asyncio
async def test_health_check_returns_false_when_stopped():
    """Test that health_check returns False when subprocess stopped."""
    client = StdioMCPClient(
        command="node",
        args=["test-mcp-server.js"],
        server_name="test-stdio"
    )

    # Mock stopped process
    mock_process = MagicMock()
    mock_process.returncode = 1  # Exited

    client.process = mock_process

    is_healthy = await client.health_check()

    assert is_healthy is False


@pytest.mark.asyncio
async def test_request_timeout_returns_none():
    """Test that request timeout returns None."""
    client = StdioMCPClient(
        command="node",
        args=["test-mcp-server.js"],
        server_name="test-stdio"
    )

    # Mock process
    mock_stdin = MagicMock()
    mock_stdin.write = MagicMock()
    mock_stdin.drain = AsyncMock()

    client.process = MagicMock()
    client.process.stdin = mock_stdin
    client.process.returncode = None

    # Create future that never resolves (simulates timeout)
    future = asyncio.Future()

    with patch.object(client, '_pending_requests', {1: future}):
        with patch('asyncio.wait_for', side_effect=asyncio.TimeoutError):
            client._request_id = 0

            response = await client._jsonrpc_request("tools/list", {})

            assert response is None
