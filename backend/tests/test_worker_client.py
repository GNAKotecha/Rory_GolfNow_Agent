"""Tests for worker client."""
import pytest
from unittest.mock import AsyncMock, patch, Mock
import httpx

from app.services.worker_client import WorkerClient, WorkerConfig


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def worker_config():
    """Create worker configuration."""
    return WorkerConfig(url="http://worker:8080", timeout_seconds=60)


@pytest.fixture
def worker_client(worker_config):
    """Create worker client instance."""
    return WorkerClient(worker_config)


# ==============================================================================
# Job Submission Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_submit_job_success(worker_client):
    """Test successful job submission."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "job_id": "test-123",
        "status": "success",
        "output": '{"result": 8}',
        "error": None,
        "execution_time_ms": 45.2,
        "timestamp": "2024-01-01T12:00:00Z",
    }

    with patch.object(worker_client.client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        result = await worker_client.submit_job(
            "calculate",
            {"operation": "add", "a": 5, "b": 3}
        )

        assert result["status"] == "success"
        assert result["job_id"] == "test-123"
        mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_submit_job_with_timeout(worker_client):
    """Test job submission with custom timeout."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "job_id": "test-456",
        "status": "success",
        "output": "result",
        "error": None,
        "execution_time_ms": 100.0,
        "timestamp": "2024-01-01T12:00:00Z",
    }

    with patch.object(worker_client.client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        result = await worker_client.submit_job(
            "calculate",
            {"operation": "multiply", "a": 3, "b": 4},
            timeout_seconds=60
        )

        assert result["status"] == "success"

        # Verify timeout was passed in request
        call_args = mock_post.call_args
        assert call_args[1]["json"]["timeout_seconds"] == 60


@pytest.mark.asyncio
async def test_submit_job_http_error(worker_client):
    """Test job submission with HTTP error."""
    with patch.object(worker_client.client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.HTTPError("Connection failed")

        with pytest.raises(httpx.HTTPError):
            await worker_client.submit_job("calculate", {})


@pytest.mark.asyncio
async def test_submit_job_500_error(worker_client):
    """Test job submission with server error."""
    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Server error", request=Mock(), response=mock_response
    )

    with patch.object(worker_client.client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        with pytest.raises(httpx.HTTPStatusError):
            await worker_client.submit_job("calculate", {})


# ==============================================================================
# Get Job Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_get_job_success(worker_client):
    """Test getting job by ID."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "job_id": "test-789",
        "status": "success",
        "output": "result",
        "error": None,
        "execution_time_ms": 50.0,
        "timestamp": "2024-01-01T12:00:00Z",
    }

    with patch.object(worker_client.client, 'get', new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        result = await worker_client.get_job("test-789")

        assert result["job_id"] == "test-789"
        mock_get.assert_called_once_with("http://worker:8080/jobs/test-789")


@pytest.mark.asyncio
async def test_get_job_not_found(worker_client):
    """Test getting nonexistent job."""
    mock_response = Mock()
    mock_response.status_code = 404
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Not found", request=Mock(), response=mock_response
    )

    with patch.object(worker_client.client, 'get', new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        with pytest.raises(httpx.HTTPStatusError):
            await worker_client.get_job("nonexistent")


# ==============================================================================
# List Jobs Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_list_jobs(worker_client):
    """Test listing all jobs."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "job_id": "job-1",
            "status": "success",
            "output": "result1",
            "error": None,
            "execution_time_ms": 10.0,
            "timestamp": "2024-01-01T12:00:00Z",
        },
        {
            "job_id": "job-2",
            "status": "failed",
            "output": None,
            "error": "error",
            "execution_time_ms": 20.0,
            "timestamp": "2024-01-01T12:01:00Z",
        }
    ]

    with patch.object(worker_client.client, 'get', new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        results = await worker_client.list_jobs()

        assert len(results) == 2
        assert results[0]["job_id"] == "job-1"
        assert results[1]["job_id"] == "job-2"


# ==============================================================================
# Health Check Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_health_check_healthy(worker_client):
    """Test health check when worker is healthy."""
    mock_response = Mock()
    mock_response.status_code = 200

    with patch.object(worker_client.client, 'get', new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        is_healthy = await worker_client.health_check()

        assert is_healthy is True
        mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_health_check_unhealthy(worker_client):
    """Test health check when worker is unhealthy."""
    with patch.object(worker_client.client, 'get', new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.ConnectError("Connection refused")

        is_healthy = await worker_client.health_check()

        assert is_healthy is False


# ==============================================================================
# Client Lifecycle Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_client_close(worker_client):
    """Test client closure."""
    with patch.object(worker_client.client, 'aclose', new_callable=AsyncMock) as mock_close:
        await worker_client.close()

        mock_close.assert_called_once()
