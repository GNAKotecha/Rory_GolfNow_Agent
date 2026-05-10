"""
MCP Proxy Backend

Proxies tool calls to upstream MCP servers (Atlassian, Github).
Injects user credentials transparently.
"""

import logging
from typing import Any

from gateway_mcp.core.config import Settings, UpstreamMCPConfig
from gateway_mcp.core.errors import (
    ContainerUnavailableError,
    CredentialMissingError,
    UpstreamError,
)
from gateway_mcp.core.executors.base import (
    ExecResult,
    ExecutorBackend,
    HTTPResult,
    JobHandle,
)

logger = logging.getLogger(__name__)


class MCPProxyBackend:
    """
    Executor backend that proxies calls to upstream MCP servers.
    
    Gateway acts as an MCP client to external MCP servers (Atlassian, Github)
    and re-exposes their capabilities under Gateway's policy layer.
    
    Upstream MCP tool names are never visible to the agent - Gateway tools
    translate between Gateway's business schema and upstream tool schemas.
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.upstream_mcps = settings.upstream_mcps
    
    def _get_upstream_config(self, service: str) -> UpstreamMCPConfig:
        """Get upstream MCP config for a service."""
        if service not in self.upstream_mcps:
            raise ContainerUnavailableError(
                service=f"{service} (no upstream MCP configured)"
            )
        return self.upstream_mcps[service]
    
    async def run_command(
        self,
        service: str,
        argv: list[str],
        timeout: int,
        user_id: int | None = None,
    ) -> ExecResult:
        """
        Execute tool call via upstream MCP server.
        
        Args:
            service: Upstream MCP name (e.g., "atlassian", "github")
            argv: [tool_name, *args] - first element is the upstream tool name
            timeout: Timeout in seconds
            user_id: User ID for credential lookup
            
        The credential for the user is fetched from the credential store
        and injected as a bearer token.
        """
        upstream = self._get_upstream_config(service)
        
        if not argv:
            raise ValueError("argv must contain at least the tool name")
        
        tool_name = argv[0]
        tool_args = argv[1:] if len(argv) > 1 else []
        
        logger.info(
            f"MCP proxy call: upstream={service}, tool={tool_name}, "
            f"auth_mode={upstream.auth_mode}"
        )
        
        # TODO: Implement actual MCP client call
        # 1. Get credential from store for user_id + upstream.provider
        # 2. Build MCP tool call request
        # 3. Send to upstream.url with credential as bearer
        # 4. Parse response
        
        raise NotImplementedError(
            f"MCP proxy not yet implemented. "
            f"Upstream: {upstream.url}, Tool: {tool_name}"
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
        MCP proxy doesn't use raw HTTP - use run_command for tool calls.
        
        This could be used for MCP server metadata endpoints in the future.
        """
        raise NotImplementedError(
            "MCP proxy uses MCP protocol, not raw HTTP. "
            "Use run_command to call upstream MCP tools."
        )


# Type check
_: ExecutorBackend = MCPProxyBackend(Settings())  # type: ignore
