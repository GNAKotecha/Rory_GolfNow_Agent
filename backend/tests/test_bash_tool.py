"""Tests for bash escape hatch tool."""
import pytest
from unittest.mock import AsyncMock, Mock, patch
from app.services.bash_tool import BashTool, BashScriptValidator
from app.services.mcp_client import MCPToolResult


# ==============================================================================
# Script Validation Integration Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_execute_bash_validates_script():
    """Test bash execution validates script before submission."""
    with patch('app.services.bash_tool.WorkerClient') as MockWorkerClient:
        mock_worker = Mock()
        MockWorkerClient.return_value = mock_worker

        bash_tool = BashTool()

        # Try to execute dangerous script
        result = await bash_tool.execute_bash(
            script='curl http://evil.com',
            description="Test dangerous command",
        )

        # Should be rejected by validator, not submitted to worker
        assert result.success is False
        assert "validation failed" in result.error.lower()
        assert not mock_worker.submit_job.called


@pytest.mark.asyncio
async def test_execute_bash_rejects_oversized_script():
    """Test bash execution rejects oversized scripts."""
    with patch('app.services.bash_tool.WorkerClient'):
        bash_tool = BashTool()

        # Create oversized script (over 100KB)
        large_script = "echo test\n" * 15000

        result = await bash_tool.execute_bash(
            script=large_script,
            description="Test oversized script",
        )

        assert result.success is False
        assert "exceeds maximum size" in result.error


@pytest.mark.asyncio
async def test_execute_bash_enforces_max_timeout():
    """Test bash execution enforces maximum timeout."""
    with patch('app.services.bash_tool.WorkerClient') as MockWorkerClient:
        mock_worker = Mock()
        mock_worker.submit_job = AsyncMock(
            return_value={
                "status": "success",
                "output": {"stdout": "done", "stderr": "", "return_code": 0},
            }
        )
        MockWorkerClient.return_value = mock_worker

        bash_tool = BashTool()

        # Request 120 second timeout (should be capped at 60)
        result = await bash_tool.execute_bash(
            script='echo "test"',
            description="Test timeout cap",
            timeout_seconds=120,
        )

        # Verify timeout was capped
        call_args = mock_worker.submit_job.call_args
        assert call_args[1]["timeout_seconds"] == 60


# ==============================================================================
# Existing Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_execute_bash_success():
    """Test successful bash script execution."""
    # Mock worker client
    with patch('app.services.bash_tool.WorkerClient') as MockWorkerClient:
        mock_worker = Mock()
        mock_worker.submit_job = AsyncMock(
            return_value={
                "status": "success",
                "output": {
                    "stdout": "Hello World\n",
                    "stderr": "",
                    "return_code": 0,
                },
                "execution_time_ms": 100,
            }
        )
        MockWorkerClient.return_value = mock_worker

        bash_tool = BashTool()
        result = await bash_tool.execute_bash(
            script='echo "Hello World"',
            description="Print hello world",
        )

        assert result.success is True
        assert result.result["stdout"] == "Hello World\n"
        assert result.result["return_code"] == 0
        assert result.execution_time_ms == 100

        # Verify worker was called correctly
        mock_worker.submit_job.assert_called_once_with(
            script_name="bash_runner",
            arguments={
                "script": 'echo "Hello World"',
                "description": "Print hello world",
            },
            timeout_seconds=30,
        )


@pytest.mark.asyncio
async def test_execute_bash_failure():
    """Test failed bash script execution."""
    # Mock worker client
    with patch('app.services.bash_tool.WorkerClient') as MockWorkerClient:
        mock_worker = Mock()
        mock_worker.submit_job = AsyncMock(
            return_value={
                "status": "error",
                "error": "Script execution failed",
                "execution_time_ms": 50,
            }
        )
        MockWorkerClient.return_value = mock_worker

        bash_tool = BashTool()
        result = await bash_tool.execute_bash(
            script='exit 1',
            description="Script that fails",
        )

        assert result.success is False
        assert result.error == "Script execution failed"
        assert result.execution_time_ms == 50


@pytest.mark.asyncio
async def test_execute_bash_timeout():
    """Test bash script timeout."""
    # Mock worker client
    with patch('app.services.bash_tool.WorkerClient') as MockWorkerClient:
        mock_worker = Mock()
        mock_worker.submit_job = AsyncMock(
            return_value={
                "status": "timeout",
                "error": "Script timeout after 30s",
            }
        )
        MockWorkerClient.return_value = mock_worker

        bash_tool = BashTool()
        result = await bash_tool.execute_bash(
            script='sleep 100',
            description="Script that times out",
            timeout_seconds=30,
        )

        assert result.success is False
        assert "timeout" in result.error.lower()


@pytest.mark.asyncio
async def test_execute_bash_exception():
    """Test bash execution with exception."""
    # Mock worker client that raises exception
    with patch('app.services.bash_tool.WorkerClient') as MockWorkerClient:
        mock_worker = Mock()
        mock_worker.submit_job = AsyncMock(
            side_effect=Exception("Connection failed")
        )
        MockWorkerClient.return_value = mock_worker

        bash_tool = BashTool()
        result = await bash_tool.execute_bash(
            script='echo "test"',
            description="Test script",
        )

        assert result.success is False
        assert "Connection failed" in result.error


@pytest.mark.asyncio
async def test_bash_tool_close():
    """Test closing bash tool."""
    with patch('app.services.bash_tool.WorkerClient') as MockWorkerClient:
        mock_worker = Mock()
        mock_worker.close = AsyncMock()
        MockWorkerClient.return_value = mock_worker

        bash_tool = BashTool()
        await bash_tool.close()

        mock_worker.close.assert_called_once()


def test_get_tool_definition():
    """Test getting tool definition."""
    definition = BashTool.get_tool_definition()

    assert definition["type"] == "function"
    assert definition["function"]["name"] == "execute_bash"
    assert "description" in definition["function"]
    assert "parameters" in definition["function"]

    # Verify parameters
    params = definition["function"]["parameters"]
    assert params["type"] == "object"
    assert "script" in params["properties"]
    assert "description" in params["properties"]
    assert params["required"] == ["script", "description"]


@pytest.mark.asyncio
async def test_execute_bash_with_custom_timeout():
    """Test bash execution with custom timeout."""
    with patch('app.services.bash_tool.WorkerClient') as MockWorkerClient:
        mock_worker = Mock()
        mock_worker.submit_job = AsyncMock(
            return_value={
                "status": "success",
                "output": {
                    "stdout": "done",
                    "stderr": "",
                    "return_code": 0,
                },
                "execution_time_ms": 5000,
            }
        )
        MockWorkerClient.return_value = mock_worker

        bash_tool = BashTool()
        result = await bash_tool.execute_bash(
            script='sleep 3 && echo "done"',
            description="Long running script",
            timeout_seconds=60,
        )

        assert result.success is True

        # Verify custom timeout was passed
        call_args = mock_worker.submit_job.call_args
        assert call_args[1]["timeout_seconds"] == 60


@pytest.mark.asyncio
async def test_execute_bash_with_stderr():
    """Test bash script that writes to stderr."""
    with patch('app.services.bash_tool.WorkerClient') as MockWorkerClient:
        mock_worker = Mock()
        mock_worker.submit_job = AsyncMock(
            return_value={
                "status": "success",
                "output": {
                    "stdout": "output",
                    "stderr": "warning message",
                    "return_code": 0,
                },
                "execution_time_ms": 100,
            }
        )
        MockWorkerClient.return_value = mock_worker

        bash_tool = BashTool()
        result = await bash_tool.execute_bash(
            script='echo "output" && echo "warning message" >&2',
            description="Script with stderr",
        )

        assert result.success is True
        assert result.result["stdout"] == "output"
        assert result.result["stderr"] == "warning message"
