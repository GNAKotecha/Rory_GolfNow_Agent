"""Tests for worker executor."""
import pytest
from datetime import datetime
from app.workers.worker import (
    WorkerExecutor,
    JobRequest,
    JobResult,
    JobStatus,
)


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def executor():
    """Create worker executor instance."""
    return WorkerExecutor()


# ==============================================================================
# Job Execution Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_worker_execute_success(executor):
    """Test successful job execution."""
    request = JobRequest(
        script_name="calculate",
        arguments={"operation": "add", "a": 5, "b": 3},
        timeout_seconds=10
    )

    result = await executor.execute_job(request)

    assert result.status == JobStatus.SUCCESS
    assert result.error is None
    assert result.execution_time_ms > 0
    assert result.job_id is not None
    assert '"result": 8' in result.output


@pytest.mark.asyncio
async def test_worker_execute_multiply(executor):
    """Test multiplication operation."""
    request = JobRequest(
        script_name="calculate",
        arguments={"operation": "multiply", "a": 4, "b": 7},
        timeout_seconds=10
    )

    result = await executor.execute_job(request)

    assert result.status == JobStatus.SUCCESS
    assert '"result": 28' in result.output


@pytest.mark.asyncio
async def test_worker_execute_divide(executor):
    """Test division operation."""
    request = JobRequest(
        script_name="calculate",
        arguments={"operation": "divide", "a": 10, "b": 2},
        timeout_seconds=10
    )

    result = await executor.execute_job(request)

    assert result.status == JobStatus.SUCCESS
    assert '"result": 5' in result.output


@pytest.mark.asyncio
async def test_worker_execute_script_error(executor):
    """Test job execution with script error (division by zero)."""
    request = JobRequest(
        script_name="calculate",
        arguments={"operation": "divide", "a": 10, "b": 0},
        timeout_seconds=10
    )

    result = await executor.execute_job(request)

    assert result.status == JobStatus.FAILED
    assert result.error is not None
    assert "Division by zero" in result.error


@pytest.mark.asyncio
async def test_worker_execute_invalid_operation(executor):
    """Test job execution with invalid operation."""
    request = JobRequest(
        script_name="calculate",
        arguments={"operation": "invalid", "a": 5, "b": 3},
        timeout_seconds=10
    )

    result = await executor.execute_job(request)

    assert result.status == JobStatus.FAILED
    assert "Unknown operation" in result.error


@pytest.mark.asyncio
async def test_worker_execute_missing_script(executor):
    """Test job execution with nonexistent script."""
    request = JobRequest(
        script_name="nonexistent",
        arguments={},
        timeout_seconds=10
    )

    result = await executor.execute_job(request)

    assert result.status == JobStatus.FAILED
    assert result.error is not None
    assert "Script not found" in result.error


@pytest.mark.asyncio
async def test_worker_job_storage(executor):
    """Test that job results are stored."""
    request = JobRequest(
        script_name="calculate",
        arguments={"operation": "add", "a": 1, "b": 2},
        timeout_seconds=10
    )

    result = await executor.execute_job(request)

    # Verify job is stored
    stored_job = executor.get_job(result.job_id)
    assert stored_job is not None
    assert stored_job.job_id == result.job_id
    assert stored_job.status == result.status


@pytest.mark.asyncio
async def test_worker_get_all_jobs(executor):
    """Test retrieving all jobs."""
    # Execute multiple jobs
    request1 = JobRequest(
        script_name="calculate",
        arguments={"operation": "add", "a": 1, "b": 2},
    )
    request2 = JobRequest(
        script_name="calculate",
        arguments={"operation": "subtract", "a": 5, "b": 3},
    )

    await executor.execute_job(request1)
    await executor.execute_job(request2)

    # Get all jobs
    all_jobs = executor.get_all_jobs()

    assert len(all_jobs) >= 2


@pytest.mark.asyncio
async def test_worker_get_nonexistent_job(executor):
    """Test getting nonexistent job returns None."""
    result = executor.get_job("nonexistent-id")
    assert result is None


# ==============================================================================
# Job Result Tests
# ==============================================================================

def test_job_result_to_dict():
    """Test job result serialization."""
    result = JobResult(
        job_id="test-123",
        status=JobStatus.SUCCESS,
        output='{"result": 42}',
        error=None,
        execution_time_ms=123.45,
        timestamp=datetime(2024, 1, 1, 12, 0, 0),
    )

    result_dict = result.to_dict()

    assert result_dict["job_id"] == "test-123"
    assert result_dict["status"] == "success"
    assert result_dict["output"] == '{"result": 42}'
    assert result_dict["error"] is None
    assert result_dict["execution_time_ms"] == 123.45
    assert "timestamp" in result_dict
