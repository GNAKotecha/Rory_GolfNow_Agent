"""Tests for bash workspace isolation."""
import pytest
import os
from unittest.mock import AsyncMock, Mock, patch
from app.services.bash_tool import BashTool
from app.services.mcp_client import MCPToolResult


# ==============================================================================
# Workspace Isolation Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_bash_tool_uses_isolated_workspace_with_run_id():
    """Test bash tool creates isolated workspace when run_id provided."""
    with patch('app.services.bash_tool.WorkerClient') as MockWorkerClient:
        mock_worker = Mock()
        mock_worker.submit_job = AsyncMock(
            return_value={
                "status": "success",
                "output": {"stdout": "done", "stderr": "", "return_code": 0},
            }
        )
        MockWorkerClient.return_value = mock_worker

        run_id = "test-run-123"
        bash_tool = BashTool(run_id=run_id)

        result = await bash_tool.execute_bash(
            script='echo "test"',
            description="Test isolated workspace",
        )

        # Verify workspace path includes run_id
        call_args = mock_worker.submit_job.call_args
        arguments = call_args[1]["arguments"]
        assert arguments["workspace_path"] == f"/workspace/runs/{run_id}/"
        assert result.success is True


@pytest.mark.asyncio
async def test_bash_tool_falls_back_to_shared_workspace_without_run_id():
    """Test bash tool uses /workspace when run_id not provided."""
    with patch('app.services.bash_tool.WorkerClient') as MockWorkerClient:
        mock_worker = Mock()
        mock_worker.submit_job = AsyncMock(
            return_value={
                "status": "success",
                "output": {"stdout": "done", "stderr": "", "return_code": 0},
            }
        )
        MockWorkerClient.return_value = mock_worker

        bash_tool = BashTool()  # No run_id

        result = await bash_tool.execute_bash(
            script='echo "test"',
            description="Test shared workspace",
        )

        # Verify workspace path is default
        call_args = mock_worker.submit_job.call_args
        arguments = call_args[1]["arguments"]
        assert arguments["workspace_path"] == "/workspace"


@pytest.mark.asyncio
async def test_different_runs_use_different_workspaces():
    """Test two different run_ids use different workspaces."""
    with patch('app.services.bash_tool.WorkerClient') as MockWorkerClient:
        mock_worker = Mock()
        mock_worker.submit_job = AsyncMock(
            return_value={
                "status": "success",
                "output": {"stdout": "done", "stderr": "", "return_code": 0},
            }
        )
        MockWorkerClient.return_value = mock_worker

        bash_tool1 = BashTool(run_id="run-1")
        bash_tool2 = BashTool(run_id="run-2")

        await bash_tool1.execute_bash(script='echo "test1"', description="Run 1")
        await bash_tool2.execute_bash(script='echo "test2"', description="Run 2")

        # Get workspace paths from both calls
        calls = mock_worker.submit_job.call_args_list
        workspace1 = calls[0][1]["arguments"]["workspace_path"]
        workspace2 = calls[1][1]["arguments"]["workspace_path"]

        assert workspace1 != workspace2
        assert workspace1 == "/workspace/runs/run-1/"
        assert workspace2 == "/workspace/runs/run-2/"


# ==============================================================================
# Path Traversal Protection Tests
# ==============================================================================

def test_bash_runner_rejects_path_traversal_parent():
    """Test bash runner rejects ../ path traversal."""
    from app.workers.scripts.bash_runner import run_bash_script

    result = run_bash_script(
        script='echo "test"',
        description="Test path traversal",
        workspace_path="../etc"
    )

    assert result["status"] == "error"
    assert "Invalid workspace path" in result["error"]


def test_bash_runner_rejects_absolute_path_outside_workspace():
    """Test bash runner rejects absolute paths outside /workspace."""
    from app.workers.scripts.bash_runner import run_bash_script

    result = run_bash_script(
        script='echo "test"',
        description="Test absolute path",
        workspace_path="/etc/passwd"
    )

    assert result["status"] == "error"
    assert "Invalid workspace path" in result["error"]


def test_bash_runner_rejects_other_run_workspace():
    """Test bash runner rejects accessing another run's workspace."""
    from app.workers.scripts.bash_runner import run_bash_script

    result = run_bash_script(
        script='echo "test"',
        description="Test cross-run access",
        workspace_path="/workspace/runs/../runs/other-run/"
    )

    assert result["status"] == "error"
    assert "Invalid workspace path" in result["error"]


def test_bash_runner_allows_valid_run_workspace():
    """Test bash runner allows valid /workspace/runs/{id}/ paths."""
    from app.workers.scripts.bash_runner import run_bash_script

    result = run_bash_script(
        script='echo "test"',
        description="Test valid workspace",
        workspace_path="/workspace/runs/valid-run-123/"
    )

    # Should not be rejected for path validation
    assert "Invalid workspace path" not in result.get("error", "")


def test_bash_runner_allows_default_workspace():
    """Test bash runner allows default /workspace path."""
    from app.workers.scripts.bash_runner import run_bash_script

    result = run_bash_script(
        script='echo "test"',
        description="Test default workspace",
        workspace_path="/workspace"
    )

    # Should not be rejected for path validation
    assert "Invalid workspace path" not in result.get("error", "")


# ==============================================================================
# Cleanup Tests
# ==============================================================================

@patch('shutil.rmtree')
@patch('os.makedirs')
def test_bash_runner_cleans_up_isolated_workspace(mock_makedirs, mock_rmtree):
    """Test bash runner removes isolated workspace after execution."""
    from app.workers.scripts.bash_runner import run_bash_script

    result = run_bash_script(
        script='echo "test"',
        description="Test cleanup",
        workspace_path="/workspace/runs/test-run/"
    )

    # Verify shutil.rmtree was called with workspace path
    assert mock_rmtree.called
    call_args = mock_rmtree.call_args[0]
    assert "/workspace/runs/test-run/" in call_args


@patch('shutil.rmtree')
def test_bash_runner_does_not_cleanup_shared_workspace(mock_rmtree):
    """Test bash runner does NOT remove /workspace (shared)."""
    from app.workers.scripts.bash_runner import run_bash_script

    result = run_bash_script(
        script='echo "test"',
        description="Test no cleanup for shared",
        workspace_path="/workspace"
    )

    # Verify shutil.rmtree was NOT called
    assert not mock_rmtree.called


@patch('shutil.rmtree')
def test_bash_runner_cleanup_on_timeout(mock_rmtree):
    """Test bash runner cleans up workspace even on timeout."""
    from app.workers.scripts.bash_runner import run_bash_script

    # Script that will timeout
    result = run_bash_script(
        script='sleep 100',
        description="Test cleanup on timeout",
        timeout=1,
        workspace_path="/workspace/runs/timeout-run/"
    )

    assert result["status"] == "timeout"
    assert mock_rmtree.called


@patch('shutil.rmtree')
def test_bash_runner_cleanup_on_error(mock_rmtree):
    """Test bash runner cleans up workspace even on script error."""
    from app.workers.scripts.bash_runner import run_bash_script

    # Script that will fail
    result = run_bash_script(
        script='exit 1',
        description="Test cleanup on error",
        workspace_path="/workspace/runs/error-run/"
    )

    assert result["status"] == "failed"
    assert mock_rmtree.called


# ==============================================================================
# Integration Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_end_to_end_workspace_isolation():
    """Test complete flow from AgenticService to isolated execution."""
    with patch('app.services.bash_tool.WorkerClient') as MockWorkerClient:
        mock_worker = Mock()
        mock_worker.submit_job = AsyncMock(
            return_value={
                "status": "success",
                "output": {
                    "stdout": "created file",
                    "stderr": "",
                    "return_code": 0
                },
            }
        )
        MockWorkerClient.return_value = mock_worker

        run_id = "integration-test-run"
        bash_tool = BashTool(run_id=run_id)

        # Execute script that creates a file
        result = await bash_tool.execute_bash(
            script='echo "data" > test.txt',
            description="Create file in isolated workspace",
        )

        assert result.success is True

        # Verify workspace path was isolated
        call_args = mock_worker.submit_job.call_args
        workspace_path = call_args[1]["arguments"]["workspace_path"]
        assert workspace_path == f"/workspace/runs/{run_id}/"
