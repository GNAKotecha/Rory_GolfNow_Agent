"""
MCP Proxy Backend

Proxies tool calls to upstream MCP servers (Atlassian, Github).
Injects user credentials transparently.

Upstream MCP tool names are never visible to the agent - Gateway tools
translate between Gateway's business schema and upstream tool schemas.
"""

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

import httpx

from gateway_mcp.core.config import Settings, UpstreamMCPConfig
from gateway_mcp.core.errors import (
    ContainerUnavailableError,
    CredentialMissingError,
    SubprocessTimeoutError,
    UpstreamError,
)
from gateway_mcp.core.executors.base import (
    ExecResult,
    ExecutorBackend,
    HTTPResult,
    JobHandle,
)

logger = logging.getLogger(__name__)


@dataclass
class MCPToolCallResult:
    """Result from an upstream MCP tool call."""
    
    success: bool
    result: Any | None = None
    error: str | None = None
    duration_ms: int = 0


# Type alias for credential fetcher function
# Signature: (user_id: int, provider: str) -> str (bearer token)
CredentialFetcher = Callable[[int, str], str]


class MCPProxyBackend:
    """
    Executor backend that proxies calls to upstream MCP servers.
    
    Gateway acts as an MCP client to external MCP servers (Atlassian, Github)
    and re-exposes their capabilities under Gateway's policy layer.
    
    Upstream MCP tool names are never visible to the agent - Gateway tools
    translate between Gateway's business schema and upstream tool schemas.
    """
    
    def __init__(
        self,
        settings: Settings,
        credential_fetcher: CredentialFetcher | None = None,
    ):
        """
        Initialize MCP Proxy backend.
        
        Args:
            settings: Gateway settings with upstream MCP configs.
            credential_fetcher: Function to fetch bearer tokens for users.
                               Signature: (user_id, provider) -> bearer_token
                               If None, credentials must be passed directly.
        """
        self.settings = settings
        self.upstream_mcps = settings.upstream_mcps
        self._credential_fetcher = credential_fetcher
        self._client: httpx.AsyncClient | None = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0),
                follow_redirects=True,
            )
        return self._client
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    def _get_upstream_config(self, service: str) -> UpstreamMCPConfig:
        """Get upstream MCP config for a service."""
        if service not in self.upstream_mcps:
            raise ContainerUnavailableError(
                service=f"{service} (no upstream MCP configured)"
            )
        return self.upstream_mcps[service]
    
    async def _get_credential(
        self,
        user_id: int | None,
        provider: str,
    ) -> str:
        """
        Get bearer token for user and provider.
        
        Returns:
            Bearer token string (already includes "Bearer " prefix).
            
        Raises:
            CredentialMissingError: If no credential available.
        """
        if user_id is None:
            raise CredentialMissingError(
                provider=provider,
                reconnect_url=f"/api/credentials/{provider}/authorize",
            )
        
        if self._credential_fetcher is None:
            raise CredentialMissingError(
                provider=provider,
                reconnect_url=f"/api/credentials/{provider}/authorize",
            )
        
        try:
            return self._credential_fetcher(user_id, provider)
        except Exception as e:
            logger.warning(f"Failed to fetch credential for {provider}: {e}")
            raise CredentialMissingError(
                provider=provider,
                reconnect_url=f"/api/credentials/{provider}/authorize",
            )
    
    async def call_mcp_tool(
        self,
        upstream_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        timeout: int,
        bearer_token: str | None = None,
        user_id: int | None = None,
    ) -> MCPToolCallResult:
        """
        Call a tool on an upstream MCP server.
        
        This is the low-level method for MCP protocol calls. Gateway tool
        handlers use this to translate between Gateway and upstream schemas.
        
        Args:
            upstream_name: Name of upstream MCP (e.g., "atlassian").
            tool_name: Name of the upstream tool to call.
            arguments: Tool arguments dictionary.
            timeout: Timeout in seconds.
            bearer_token: Pre-fetched bearer token (for testing or direct use).
            user_id: User ID for credential lookup (alternative to bearer_token).
            
        Returns:
            MCPToolCallResult with success/error status and result data.
            
        Raises:
            ContainerUnavailableError: Upstream MCP not configured.
            CredentialMissingError: No credential available.
            UpstreamError: Upstream MCP returned an error.
            SubprocessTimeoutError: Request timed out.
        """
        upstream = self._get_upstream_config(upstream_name)
        
        # Get credential if not provided
        auth_header = None
        if bearer_token:
            auth_header = bearer_token if bearer_token.startswith("Bearer ") else f"Bearer {bearer_token}"
        elif upstream.auth_mode in ("oauth", "pat"):
            auth_header = await self._get_credential(user_id, upstream.provider)
        
        logger.info(
            f"MCP proxy call: upstream={upstream_name}, tool={tool_name}, "
            f"auth_mode={upstream.auth_mode}, has_auth={auth_header is not None}"
        )
        
        client = await self._get_client()
        start_time = time.monotonic()
        
        # Build MCP tools/call request
        # MCP protocol: POST /tools/call with JSON body
        # Body: { "name": tool_name, "arguments": {...} }
        url = upstream.url.rstrip("/")
        if not url.endswith("/tools/call"):
            url = f"{url}/tools/call"
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if auth_header:
            headers["Authorization"] = auth_header
        
        payload = {
            "name": tool_name,
            "arguments": arguments,
        }
        
        try:
            response = await client.post(
                url,
                json=payload,
                headers=headers,
                timeout=timeout,
            )
            
            duration_ms = int((time.monotonic() - start_time) * 1000)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    return MCPToolCallResult(
                        success=True,
                        result=data.get("result", data),
                        duration_ms=duration_ms,
                    )
                except json.JSONDecodeError:
                    return MCPToolCallResult(
                        success=True,
                        result=response.text,
                        duration_ms=duration_ms,
                    )
            
            elif response.status_code == 401:
                # Unauthorized - credential invalid or expired
                raise CredentialMissingError(
                    provider=upstream.provider,
                    reconnect_url=f"/api/credentials/{upstream.provider}/authorize",
                )
            
            elif response.status_code == 403:
                # Forbidden - insufficient scopes
                raise UpstreamError(
                    service=upstream_name,
                    detail=f"Insufficient permissions: {response.text[:200]}",
                )
            
            elif response.status_code == 404:
                # Tool not found
                return MCPToolCallResult(
                    success=False,
                    error=f"Tool not found: {tool_name}",
                    duration_ms=duration_ms,
                )
            
            else:
                # Other error
                error_text = response.text[:500]
                logger.warning(
                    f"Upstream MCP error: {upstream_name} returned {response.status_code}",
                    extra={
                        "upstream": upstream_name,
                        "tool": tool_name,
                        "status": response.status_code,
                        "error": error_text,
                    },
                )
                return MCPToolCallResult(
                    success=False,
                    error=f"Upstream error ({response.status_code}): {error_text}",
                    duration_ms=duration_ms,
                )
                
        except httpx.ConnectError as e:
            raise ContainerUnavailableError(
                service=f"{upstream_name} at {upstream.url}"
            )
        except httpx.TimeoutException:
            raise SubprocessTimeoutError(timeout_seconds=timeout)
        except (CredentialMissingError, UpstreamError, ContainerUnavailableError):
            raise
        except Exception as e:
            logger.exception(f"MCP proxy call failed: {e}")
            raise UpstreamError(
                service=upstream_name,
                detail=str(e)[:200],
            )
    
    async def run_command(
        self,
        service: str,
        argv: list[str],
        timeout: int,
        user_id: int | None = None,
        bearer_token: str | None = None,
    ) -> ExecResult:
        """
        Execute tool call via upstream MCP server.
        
        This method adapts MCP tool calls to the ExecutorBackend interface.
        The argv format is: [tool_name, json_arguments]
        
        Args:
            service: Upstream MCP name (e.g., "atlassian", "github").
            argv: [tool_name, json_arguments] - tool name and JSON-encoded args.
            timeout: Timeout in seconds.
            user_id: User ID for credential lookup.
            bearer_token: Pre-fetched bearer token (alternative to user_id).
            
        Returns:
            ExecResult with stdout containing the JSON result.
        """
        if not argv:
            raise ValueError("argv must contain at least the tool name")
        
        tool_name = argv[0]
        
        # Parse arguments from JSON string or use empty dict
        arguments: dict[str, Any] = {}
        if len(argv) > 1:
            try:
                arguments = json.loads(argv[1])
            except json.JSONDecodeError:
                # Try treating remaining args as key=value pairs
                for arg in argv[1:]:
                    if "=" in arg:
                        key, value = arg.split("=", 1)
                        arguments[key] = value
        
        result = await self.call_mcp_tool(
            upstream_name=service,
            tool_name=tool_name,
            arguments=arguments,
            timeout=timeout,
            bearer_token=bearer_token,
            user_id=user_id,
        )
        
        # Convert to ExecResult
        if result.success:
            stdout = json.dumps(result.result) if result.result else ""
            return ExecResult(
                exit_code=0,
                stdout=stdout,
                stderr="",
                duration_ms=result.duration_ms,
            )
        else:
            return ExecResult(
                exit_code=1,
                stdout="",
                stderr=result.error or "Unknown error",
                duration_ms=result.duration_ms,
            )
    
    async def submit_command(
        self,
        service: str,
        argv: list[str],
        timeout: int,
    ) -> JobHandle:
        """MCP calls are synchronous - no job submission support."""
        raise NotImplementedError(
            "MCP proxy does not support async job submission. "
            "Use run_command instead."
        )
    
    async def query_db(
        self,
        db: str,
        query: str,
        params: list[Any],
    ) -> list[dict[str, Any]]:
        """MCP proxy does not support direct database queries."""
        raise NotImplementedError(
            "MCP proxy does not support database queries. "
            "Use tool-based data access instead."
        )
    
    async def call_http(
        self,
        service: str,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HTTPResult:
        """
        MCP proxy doesn't use raw HTTP - use call_mcp_tool for tool calls.
        
        This could be used for MCP server metadata endpoints in the future.
        """
        raise NotImplementedError(
            "MCP proxy uses MCP protocol, not raw HTTP. "
            "Use call_mcp_tool or run_command to call upstream MCP tools."
        )


# Type check (disabled in runtime, just for static analysis)
def _type_check() -> ExecutorBackend:
    return MCPProxyBackend(Settings())  # type: ignore
