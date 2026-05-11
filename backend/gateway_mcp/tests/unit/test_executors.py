"""
Unit tests for executor backends.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

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


def create_mock_response(status_code: int, json_data=None, text_data=None):
    """Create a mock httpx response."""
    response = MagicMock()
    response.status_code = status_code
    response.headers = {}
    if json_data is not None:
        response.json.return_value = json_data
        response.text = json.dumps(json_data)
    elif text_data is not None:
        response.json.side_effect = json.JSONDecodeError("", "", 0)
        response.text = text_data
    else:
        response.json.return_value = {}
        response.text = ""
    return response


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


class TestMCPProxyBackend:
    """Tests for MCPProxyBackend with mocked upstream."""
    
    @pytest.fixture
    def settings(self):
        """Create settings with upstream MCP config."""
        from gateway_mcp.core.config import Settings, UpstreamMCPConfig
        
        settings = Settings()
        settings.upstream_mcps = {
            "atlassian": UpstreamMCPConfig(
                url="https://mcp.atlassian.com/v1/mcp",
                auth_mode="oauth",
                provider="atlassian",
            ),
            "github": UpstreamMCPConfig(
                url="https://api.githubcopilot.com/mcp/",
                auth_mode="pat",
                provider="github",
            ),
        }
        return settings
    
    @pytest.fixture
    def mock_credential_fetcher(self):
        """Mock credential fetcher that returns a test token."""
        def fetcher(user_id: int, provider: str) -> str:
            return f"Bearer test-token-{provider}-{user_id}"
        return fetcher
    
    @pytest.fixture
    def mcp_backend(self, settings, mock_credential_fetcher):
        from gateway_mcp.core.executors.mcp_proxy import MCPProxyBackend
        return MCPProxyBackend(settings, credential_fetcher=mock_credential_fetcher)
    
    @pytest.mark.asyncio
    async def test_call_mcp_tool_success(self, mcp_backend):
        """Successful MCP tool call returns result."""
        mock_response = create_mock_response(200, {"result": {"issue_key": "PROJ-123"}})
        
        with patch.object(mcp_backend, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client
            
            result = await mcp_backend.call_mcp_tool(
                upstream_name="atlassian",
                tool_name="create_issue",
                arguments={"project": "PROJ", "summary": "Test issue"},
                timeout=30,
                user_id=1,
            )
        
        assert result.success
        assert result.result == {"issue_key": "PROJ-123"}
        assert result.duration_ms >= 0
    
    @pytest.mark.asyncio
    async def test_call_mcp_tool_with_bearer_token(self, mcp_backend):
        """MCP tool call with explicit bearer token."""
        mock_response = create_mock_response(200, {"result": {"success": True}})
        
        with patch.object(mcp_backend, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client
            
            result = await mcp_backend.call_mcp_tool(
                upstream_name="atlassian",
                tool_name="test_tool",
                arguments={},
                timeout=30,
                bearer_token="Bearer explicit-token",
            )
        
        assert result.success
        
        # Verify the request had the correct auth header
        call_kwargs = mock_client.post.call_args
        assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer explicit-token"
    
    @pytest.mark.asyncio
    async def test_call_mcp_tool_unauthorized(self, mcp_backend):
        """401 response raises CredentialMissingError."""
        from gateway_mcp.core.errors import CredentialMissingError
        
        mock_response = create_mock_response(401)
        
        with patch.object(mcp_backend, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client
            
            with pytest.raises(CredentialMissingError) as exc_info:
                await mcp_backend.call_mcp_tool(
                    upstream_name="atlassian",
                    tool_name="test_tool",
                    arguments={},
                    timeout=30,
                    user_id=1,
                )
        
        assert exc_info.value.provider == "atlassian"
    
    @pytest.mark.asyncio
    async def test_call_mcp_tool_forbidden(self, mcp_backend):
        """403 response raises UpstreamError."""
        from gateway_mcp.core.errors import UpstreamError
        
        mock_response = create_mock_response(403, text_data="Insufficient permissions")
        
        with patch.object(mcp_backend, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client
            
            with pytest.raises(UpstreamError):
                await mcp_backend.call_mcp_tool(
                    upstream_name="atlassian",
                    tool_name="test_tool",
                    arguments={},
                    timeout=30,
                    user_id=1,
                )
    
    @pytest.mark.asyncio
    async def test_call_mcp_tool_not_found(self, mcp_backend):
        """404 response returns failure result."""
        mock_response = create_mock_response(404)
        
        with patch.object(mcp_backend, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client
            
            result = await mcp_backend.call_mcp_tool(
                upstream_name="atlassian",
                tool_name="unknown_tool",
                arguments={},
                timeout=30,
                user_id=1,
            )
        
        assert not result.success
        assert "not found" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_call_mcp_tool_server_error(self, mcp_backend):
        """500 response returns failure result."""
        mock_response = create_mock_response(500, text_data="Internal server error")
        
        with patch.object(mcp_backend, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client
            
            result = await mcp_backend.call_mcp_tool(
                upstream_name="atlassian",
                tool_name="test_tool",
                arguments={},
                timeout=30,
                user_id=1,
            )
        
        assert not result.success
        assert "500" in result.error
    
    @pytest.mark.asyncio
    async def test_run_command_success(self, mcp_backend):
        """run_command adapts MCP call to ExecResult."""
        mock_response = create_mock_response(200, {"result": {"key": "value"}})
        
        with patch.object(mcp_backend, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client
            
            result = await mcp_backend.run_command(
                service="atlassian",
                argv=["test_tool", '{"arg1": "value1"}'],
                timeout=30,
                user_id=1,
            )
        
        assert result.success
        assert result.exit_code == 0
        assert '"key"' in result.stdout
        assert '"value"' in result.stdout
    
    @pytest.mark.asyncio
    async def test_run_command_failure(self, mcp_backend):
        """run_command returns non-zero exit code on failure."""
        mock_response = create_mock_response(404)
        
        with patch.object(mcp_backend, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client
            
            result = await mcp_backend.run_command(
                service="atlassian",
                argv=["unknown_tool"],
                timeout=30,
                user_id=1,
            )
        
        assert not result.success
        assert result.exit_code == 1
        assert "not found" in result.stderr.lower()
    
    @pytest.mark.asyncio
    async def test_unknown_upstream(self, mcp_backend):
        """Unknown upstream raises ContainerUnavailableError."""
        with pytest.raises(ContainerUnavailableError):
            await mcp_backend.call_mcp_tool(
                upstream_name="unknown",
                tool_name="test",
                arguments={},
                timeout=30,
                user_id=1,
            )
    
    @pytest.mark.asyncio
    async def test_no_user_id_raises_error(self, settings):
        """Missing user_id without bearer_token raises error."""
        from gateway_mcp.core.errors import CredentialMissingError
        from gateway_mcp.core.executors.mcp_proxy import MCPProxyBackend
        
        backend = MCPProxyBackend(settings, credential_fetcher=None)
        
        with pytest.raises(CredentialMissingError):
            await backend.call_mcp_tool(
                upstream_name="atlassian",
                tool_name="test",
                arguments={},
                timeout=30,
                user_id=None,
            )
    
    @pytest.mark.asyncio
    async def test_submit_command_not_supported(self, mcp_backend):
        """submit_command raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await mcp_backend.submit_command("atlassian", ["tool"], 30)
    
    @pytest.mark.asyncio
    async def test_query_db_not_supported(self, mcp_backend):
        """query_db raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await mcp_backend.query_db("db", "query", [])
    
    @pytest.mark.asyncio
    async def test_call_http_not_supported(self, mcp_backend):
        """call_http raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await mcp_backend.call_http("service", "GET", "/path")
    
    @pytest.mark.asyncio
    async def test_connection_error(self, mcp_backend):
        """Connection error raises ContainerUnavailableError."""
        import httpx
        
        with patch.object(mcp_backend, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_get_client.return_value = mock_client
            
            with pytest.raises(ContainerUnavailableError):
                await mcp_backend.call_mcp_tool(
                    upstream_name="atlassian",
                    tool_name="test",
                    arguments={},
                    timeout=30,
                    user_id=1,
                )
    
    @pytest.mark.asyncio
    async def test_timeout_error(self, mcp_backend):
        """Timeout raises SubprocessTimeoutError."""
        import httpx
        
        with patch.object(mcp_backend, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_get_client.return_value = mock_client
            
            with pytest.raises(SubprocessTimeoutError):
                await mcp_backend.call_mcp_tool(
                    upstream_name="atlassian",
                    tool_name="test",
                    arguments={},
                    timeout=30,
                    user_id=1,
                )


class TestHTTPRestBackendWithCredentials:
    """Tests for HTTPRestBackend with credential injection."""
    
    @pytest.fixture
    def settings(self):
        """Create minimal settings."""
        from gateway_mcp.core.config import Settings
        return Settings()
    
    @pytest.fixture
    def mock_credential_fetcher(self):
        """Mock credential fetcher."""
        def fetcher(user_id: int, provider: str) -> str:
            return f"Bearer test-token-{provider}-{user_id}"
        return fetcher
    
    @pytest.fixture
    def allowlist(self):
        """Create allowlist with test entries."""
        allowlist = HTTPAllowlist()
        allowlist.add("github", AllowlistEntry(
            host="api.github.com",
            methods=["GET", "POST"],
            path_pattern="/user",
            requires_auth=True,
            provider="github",
        ))
        allowlist.add("github", AllowlistEntry(
            host="api.github.com",
            methods=["GET"],
            path_pattern="/repos/*",
            requires_auth=True,
            provider="github",
        ))
        allowlist.add("public", AllowlistEntry(
            host="api.example.com",
            methods=["GET"],
            path_pattern="/public/*",
            requires_auth=False,
        ))
        return allowlist
    
    @pytest.fixture
    def http_backend(self, settings, allowlist, mock_credential_fetcher):
        return HTTPRestBackend(settings, allowlist, credential_fetcher=mock_credential_fetcher)
    
    @pytest.mark.asyncio
    async def test_call_http_with_auth(self, http_backend):
        """HTTP call with auth injects bearer token."""
        mock_response = create_mock_response(200, {"login": "testuser"})
        
        with patch.object(http_backend, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client
            
            result = await http_backend.call_http(
                service="github",
                method="GET",
                path="/user",
                user_id=42,
            )
        
        assert result.success
        assert result.body == {"login": "testuser"}
        
        # Verify auth header was set
        call_kwargs = mock_client.request.call_args
        assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer test-token-github-42"
    
    @pytest.mark.asyncio
    async def test_call_http_without_auth(self, http_backend):
        """HTTP call to public endpoint works without user_id."""
        mock_response = create_mock_response(200, {"data": "public"})
        
        with patch.object(http_backend, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client
            
            result = await http_backend.call_http(
                service="public",
                method="GET",
                path="/public/data",
            )
        
        assert result.success
        assert result.body == {"data": "public"}
    
    @pytest.mark.asyncio
    async def test_call_http_requires_user_id_for_auth(self, http_backend):
        """Auth-required endpoint without user_id raises error."""
        from gateway_mcp.core.errors import CredentialMissingError
        
        with pytest.raises(CredentialMissingError) as exc_info:
            await http_backend.call_http(
                service="github",
                method="GET",
                path="/user",
                user_id=None,
            )
        
        assert exc_info.value.provider == "github"
    
    @pytest.mark.asyncio
    async def test_call_http_401_raises_credential_error(self, http_backend):
        """401 response raises CredentialMissingError."""
        from gateway_mcp.core.errors import CredentialMissingError
        
        mock_response = create_mock_response(401)
        
        with patch.object(http_backend, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client
            
            with pytest.raises(CredentialMissingError):
                await http_backend.call_http(
                    service="github",
                    method="GET",
                    path="/user",
                    user_id=1,
                )
    
    @pytest.mark.asyncio
    async def test_call_http_with_body(self, http_backend):
        """POST request sends JSON body."""
        mock_response = create_mock_response(201, {"created": True})
        
        with patch.object(http_backend, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client
            
            result = await http_backend.call_http(
                service="github",
                method="POST",
                path="/user",
                body={"name": "test"},
                user_id=1,
            )
        
        assert result.status_code == 201
        
        # Verify body was sent
        call_kwargs = mock_client.request.call_args
        assert call_kwargs.kwargs["json"] == {"name": "test"}
    
    @pytest.mark.asyncio
    async def test_call_http_with_custom_headers(self, http_backend):
        """Custom headers are merged with auth."""
        mock_response = create_mock_response(200, {})
        
        with patch.object(http_backend, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client
            
            await http_backend.call_http(
                service="github",
                method="GET",
                path="/user",
                headers={"X-Custom": "value"},
                user_id=1,
            )
        
        call_kwargs = mock_client.request.call_args
        assert call_kwargs.kwargs["headers"]["X-Custom"] == "value"
        assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer test-token-github-1"
    
    @pytest.mark.asyncio
    async def test_call_http_not_in_allowlist(self, http_backend):
        """Request to non-allowlisted path raises error."""
        with pytest.raises(PermissionDeniedError):
            await http_backend.call_http(
                service="github",
                method="GET",
                path="/not-allowed",
                user_id=1,
            )
    
    @pytest.mark.asyncio
    async def test_call_http_wrong_method(self, http_backend):
        """Request with wrong method raises error."""
        with pytest.raises(PermissionDeniedError):
            await http_backend.call_http(
                service="github",
                method="DELETE",
                path="/user",
                user_id=1,
            )
    
    @pytest.mark.asyncio
    async def test_run_command_not_supported(self, http_backend):
        """run_command raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await http_backend.run_command("service", ["cmd"], 30)
    
    @pytest.mark.asyncio
    async def test_credential_fetcher_failure(self, settings, allowlist):
        """Failed credential fetch raises CredentialMissingError."""
        from gateway_mcp.core.errors import CredentialMissingError
        
        def failing_fetcher(user_id: int, provider: str) -> str:
            raise RuntimeError("Credential fetch failed")
        
        backend = HTTPRestBackend(settings, allowlist, credential_fetcher=failing_fetcher)
        
        with pytest.raises(CredentialMissingError):
            await backend.call_http(
                service="github",
                method="GET",
                path="/user",
                user_id=1,
            )
    
    @pytest.mark.asyncio
    async def test_connection_error(self, http_backend):
        """Connection error raises ContainerUnavailableError."""
        import httpx
        
        with patch.object(http_backend, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_get_client.return_value = mock_client
            
            with pytest.raises(ContainerUnavailableError):
                await http_backend.call_http(
                    service="github",
                    method="GET",
                    path="/user",
                    user_id=1,
                )
    
    @pytest.mark.asyncio
    async def test_timeout_error(self, http_backend):
        """Timeout raises SubprocessTimeoutError."""
        import httpx
        
        with patch.object(http_backend, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_get_client.return_value = mock_client
            
            with pytest.raises(SubprocessTimeoutError):
                await http_backend.call_http(
                    service="github",
                    method="GET",
                    path="/user",
                    user_id=1,
                )
