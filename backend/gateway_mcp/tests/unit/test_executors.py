"""
Unit tests for executor backends.
"""

import pytest

from gateway_mcp.core.errors import (
    ContainerUnavailableError,
    PermissionDeniedError,
    SubprocessTimeoutError,
)
from gateway_mcp.core.executors import (
    DockerExecBackend,
    ExecResult,
    HTTPAllowlist,
    HTTPRestBackend,
    HTTPResult,
    JobStatus,
    MockExecutorBackend,
    MockResponse,
)
from gateway_mcp.core.executors.http_rest import AllowlistEntry


class TestMockExecutorBackend:
    """Tests for MockExecutorBackend."""
    
    @pytest.fixture
    def mock_backend(self):
        return MockExecutorBackend()
    
    @pytest.mark.asyncio
    async def test_run_command_default_response(self, mock_backend):
        """Default response returns success."""
        result = await mock_backend.run_command("teesheet", ["new-club"], 30)
        
        assert result.exit_code == 0
        assert result.stdout == ""
        assert result.success
    
    @pytest.mark.asyncio
    async def test_run_command_custom_response(self, mock_backend):
        """Custom response is returned."""
        mock_backend.set_response("teesheet", MockResponse(
            exit_code=0,
            stdout='{"club_id": 123}',
        ))
        
        result = await mock_backend.run_command("teesheet", ["new-club"], 30)
        
        assert result.stdout == '{"club_id": 123}'
    
    @pytest.mark.asyncio
    async def test_run_command_failure(self, mock_backend):
        """Failed command returns non-zero exit code."""
        mock_backend.set_response("teesheet", MockResponse(
            exit_code=1,
            stderr="Command failed",
        ))
        
        result = await mock_backend.run_command("teesheet", ["bad-command"], 30)
        
        assert not result.success
        assert result.exit_code == 1
        assert result.stderr == "Command failed"
    
    @pytest.mark.asyncio
    async def test_run_command_raises_error(self, mock_backend):
        """Configured error is raised."""
        mock_backend.set_response("teesheet", MockResponse(
            raise_error=ContainerUnavailableError(service="teesheet"),
        ))
        
        with pytest.raises(ContainerUnavailableError):
            await mock_backend.run_command("teesheet", ["new-club"], 30)
    
    @pytest.mark.asyncio
    async def test_calls_are_recorded(self, mock_backend):
        """All calls are recorded for verification."""
        await mock_backend.run_command("teesheet", ["cmd1"], 30)
        await mock_backend.run_command("mysql", ["cmd2"], 15)
        
        assert len(mock_backend.calls) == 2
        assert mock_backend.calls[0].service == "teesheet"
        assert mock_backend.calls[0].args["argv"] == ["cmd1"]
        assert mock_backend.calls[1].service == "mysql"
    
    @pytest.mark.asyncio
    async def test_query_db(self, mock_backend):
        """Database query returns configured rows."""
        mock_backend.set_response("mysql", MockResponse(
            rows=[
                {"id": 1, "name": "Club One"},
                {"id": 2, "name": "Club Two"},
            ],
        ))
        
        rows = await mock_backend.query_db("mysql", "SELECT * FROM clubs", [])
        
        assert len(rows) == 2
        assert rows[0]["name"] == "Club One"
    
    @pytest.mark.asyncio
    async def test_call_http(self, mock_backend):
        """HTTP call returns configured response."""
        mock_backend.set_response("admin_api", MockResponse(
            status_code=200,
            body={"success": True},
        ))
        
        result = await mock_backend.call_http(
            "admin_api",
            "POST",
            "/clubs/1/features",
            body={"features": ["teesheet"]},
        )
        
        assert result.status_code == 200
        assert result.body == {"success": True}
    
    @pytest.mark.asyncio
    async def test_submit_command(self, mock_backend):
        """Job submission returns a handle."""
        mock_backend.set_response("teesheet", MockResponse(
            exit_code=0,
            stdout="Job completed",
        ))
        
        handle = await mock_backend.submit_command("teesheet", ["long-job"], 300)
        
        assert handle.job_id.startswith("mock-job-")
        assert await handle.status() == JobStatus.SUCCEEDED
        
        result = await handle.result()
        assert result.stdout == "Job completed"
    
    @pytest.mark.asyncio
    async def test_job_cancellation(self, mock_backend):
        """Job can be cancelled."""
        handle = await mock_backend.submit_command("teesheet", ["job"], 30)
        
        await handle.cancel()
        
        assert await handle.status() == JobStatus.CANCELLED
    
    def test_reset_clears_state(self, mock_backend):
        """Reset clears all calls and responses."""
        mock_backend.set_response("test", MockResponse(exit_code=1))
        mock_backend.calls.append(None)  # type: ignore
        
        mock_backend.reset()
        
        assert len(mock_backend.calls) == 0
        assert len(mock_backend.responses) == 0
    
    @pytest.mark.asyncio
    async def test_response_callback(self, mock_backend):
        """Dynamic response callback is used."""
        def dynamic_response(method, service, args):
            if service == "teesheet":
                return MockResponse(stdout="dynamic teesheet")
            return MockResponse(stdout="other")
        
        mock_backend.set_response_callback(dynamic_response)
        
        result1 = await mock_backend.run_command("teesheet", ["cmd"], 30)
        result2 = await mock_backend.run_command("other", ["cmd"], 30)
        
        assert result1.stdout == "dynamic teesheet"
        assert result2.stdout == "other"


class TestHTTPAllowlist:
    """Tests for HTTP allowlist."""
    
    def test_resolve_allowed_endpoint(self):
        """Allowed endpoint resolves successfully."""
        allowlist = HTTPAllowlist()
        allowlist.add("github", AllowlistEntry(
            host="api.github.com",
            methods=["GET", "POST"],
            path_pattern="/user",
        ))
        
        url, entry = allowlist.resolve("github", "GET", "/user")
        
        assert url == "https://api.github.com/user"
        assert entry.requires_auth
    
    def test_resolve_wildcard_path(self):
        """Wildcard path pattern matches."""
        allowlist = HTTPAllowlist()
        allowlist.add("github", AllowlistEntry(
            host="api.github.com",
            methods=["GET"],
            path_pattern="/repos/*",
        ))
        
        url, _ = allowlist.resolve("github", "GET", "/repos/owner/repo")
        
        assert url == "https://api.github.com/repos/owner/repo"
    
    def test_resolve_method_not_allowed(self):
        """Wrong method raises PermissionDeniedError."""
        allowlist = HTTPAllowlist()
        allowlist.add("github", AllowlistEntry(
            host="api.github.com",
            methods=["GET"],
            path_pattern="/user",
        ))
        
        with pytest.raises(PermissionDeniedError):
            allowlist.resolve("github", "POST", "/user")
    
    def test_resolve_path_not_allowed(self):
        """Wrong path raises PermissionDeniedError."""
        allowlist = HTTPAllowlist()
        allowlist.add("github", AllowlistEntry(
            host="api.github.com",
            methods=["GET"],
            path_pattern="/user",
        ))
        
        with pytest.raises(PermissionDeniedError):
            allowlist.resolve("github", "GET", "/repos")
    
    def test_resolve_service_not_found(self):
        """Unknown service raises PermissionDeniedError."""
        allowlist = HTTPAllowlist()
        
        with pytest.raises(PermissionDeniedError):
            allowlist.resolve("unknown", "GET", "/path")


class TestExecResult:
    """Tests for ExecResult."""
    
    def test_success_property(self):
        """Success is True for exit_code 0."""
        result = ExecResult(exit_code=0, stdout="", stderr="", duration_ms=10)
        assert result.success
        
        result = ExecResult(exit_code=1, stdout="", stderr="", duration_ms=10)
        assert not result.success
    
    def test_raise_for_status_success(self):
        """raise_for_status does nothing on success."""
        result = ExecResult(exit_code=0, stdout="ok", stderr="", duration_ms=10)
        result.raise_for_status()  # Should not raise
    
    def test_raise_for_status_failure(self):
        """raise_for_status raises on failure."""
        result = ExecResult(exit_code=1, stdout="", stderr="error", duration_ms=10)
        
        with pytest.raises(ContainerUnavailableError):
            result.raise_for_status()


class TestHTTPResult:
    """Tests for HTTPResult."""
    
    def test_success_property(self):
        """Success is True for 2xx status codes."""
        assert HTTPResult(status_code=200, body=None).success
        assert HTTPResult(status_code=201, body=None).success
        assert HTTPResult(status_code=204, body=None).success
        assert HTTPResult(status_code=299, body=None).success
        
        assert not HTTPResult(status_code=400, body=None).success
        assert not HTTPResult(status_code=404, body=None).success
        assert not HTTPResult(status_code=500, body=None).success
