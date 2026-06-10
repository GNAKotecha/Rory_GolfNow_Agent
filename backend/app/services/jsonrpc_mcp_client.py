"""JSON-RPC 2.0 MCP client with session management.

Provides support for official MCP servers (Jira, GitHub, etc.) that use
the JSON-RPC 2.0 protocol with stateful sessions.

Protocol flow:
1. Initialize: Establish session and get session ID
2. Tools list: Query available tools using session ID
3. Tool call: Execute tools using session ID

All requests follow JSON-RPC 2.0 format with sequential request IDs.
"""
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import logging
import aiohttp

from app.config.mcp_config import MCPServerConfig
from app.services.mcp_client import MCPTool, MCPToolResult
from .async_event_loop import mcp_async_method

logger = logging.getLogger(__name__)


class JsonRpcMCPClient:
    """
    Client for JSON-RPC 2.0 MCP servers (Jira, GitHub, etc.).

    Implements the official MCP protocol with session management.
    """

    def __init__(self, config: MCPServerConfig, auth_headers: Optional[Dict[str, str]] = None):
        """
        Initialize JSON-RPC MCP client.

        Args:
            config: MCP server configuration
            auth_headers: Optional authentication headers
        """
        self.config = config
        self.auth_headers = auth_headers or {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.session_id: Optional[str] = None
        self._initialized = False
        self._request_id = 0
        self._tools_cache: Optional[List[MCPTool]] = None

    @mcp_async_method
    async def initialize(self):
        """Initialize client and establish MCP session."""
        if not self.session or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
            self.session = aiohttp.ClientSession(timeout=timeout)

        # Send initialize request
        response = await self._jsonrpc_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "rory-agent",
                "version": "1.0.0"
            }
        })

        if response and "result" in response:
            self.session_id = response["result"].get("sessionId")
            self._initialized = True
            logger.info(
                f"Initialized JSON-RPC MCP session: {self.config.name}",
                extra={"server": self.config.name, "session_id": self.session_id}
            )
        else:
            logger.error(
                f"Failed to initialize JSON-RPC MCP session: {self.config.name}",
                extra={"server": self.config.name, "response": response}
            )

    @mcp_async_method
    async def close(self):
        """Close client session."""
        if self.session and not self.session.closed:
            await self.session.close()

    @mcp_async_method
    async def health_check(self) -> bool:
        """Check if MCP server is reachable and responding."""
        if not self._initialized:
            return False

        # Try to list tools as health check
        try:
            tools = await self.list_tools()
            return len(tools) >= 0  # empty list is still valid
        except Exception:
            return False

    @mcp_async_method
    async def list_tools(self, force_refresh: bool = False) -> List[MCPTool]:
        """List available tools from MCP server."""
        if not force_refresh and self._tools_cache:
            return self._tools_cache

        if not self._initialized:
            logger.error(f"Not initialized for {self.config.name} - call initialize() first")
            return []

        # Include sessionId only if present (stateful servers like Atlassian require it;
        # stateless servers like GitHub ignore it)
        params: Dict[str, Any] = {}
        if self.session_id:
            params["sessionId"] = self.session_id

        response = await self._jsonrpc_request("tools/list", params)

        if not response or "result" not in response:
            logger.error(
                f"Failed to list tools from {self.config.name}",
                extra={"server": self.config.name, "response": response}
            )
            return []

        tools = [
            MCPTool(
                name=tool["name"],
                description=tool.get("description", ""),
                input_schema=tool.get("inputSchema", {}),
                server_name=self.config.name,
            )
            for tool in response["result"].get("tools", [])
        ]

        self._tools_cache = tools
        logger.info(
            f"Discovered {len(tools)} tools from {self.config.name}",
            extra={"server": self.config.name, "tool_count": len(tools)},
        )

        return tools

    @mcp_async_method
    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        user_id: Optional[int] = None,
    ) -> MCPToolResult:
        """Call a tool on the MCP server."""
        if not self._initialized:
            return MCPToolResult(
                success=False,
                error="Server not initialized - call initialize() first",
                http_status=None,
            )

        start_time = datetime.now(timezone.utc)

        params: Dict[str, Any] = {"name": tool_name, "arguments": arguments}
        if self.session_id:
            params["sessionId"] = self.session_id

        response = await self._jsonrpc_request("tools/call", params)

        elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

        if not response:
            return MCPToolResult(
                success=False,
                error="No response from server",
                execution_time_ms=elapsed_ms,
                http_status=None,
            )

        if "error" in response:
            error = response["error"]
            return MCPToolResult(
                success=False,
                error=f"{error.get('message', 'Unknown error')} (code: {error.get('code')})",
                execution_time_ms=elapsed_ms,
                http_status=None,
                is_semantic_error=True,
            )

        if "result" in response:
            return MCPToolResult(
                success=True,
                result=response["result"],
                execution_time_ms=elapsed_ms,
                http_status=200,
            )

        return MCPToolResult(
            success=False,
            error="Unexpected response format",
            execution_time_ms=elapsed_ms,
            http_status=None,
        )

    async def _jsonrpc_request(self, method: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send JSON-RPC 2.0 request."""
        self._request_id += 1

        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params
        }

        headers = {"Content-Type": "application/json"}
        headers.update(self.auth_headers)

        try:
            async with self.session.post(self.config.url, json=payload, headers=headers) as response:
                if response.status == 200:
                    content_type = response.headers.get("Content-Type", "")
                    if "text/event-stream" in content_type:
                        # SSE response (GitHub MCP, Atlassian MCP): parse first data event
                        text = await response.text()
                        return self._parse_sse_response(text, method)
                    else:
                        return await response.json()
                else:
                    text = await response.text()
                    logger.error(
                        f"JSON-RPC request failed: {method}",
                        extra={
                            "server": self.config.name,
                            "method": method,
                            "status": response.status,
                            "response": text[:200]
                        }
                    )
                    return None
        except Exception as e:
            logger.error(
                f"JSON-RPC request exception: {method}",
                extra={"server": self.config.name, "method": method, "error": str(e)}
            )
            return None

    def _parse_sse_response(self, text: str, method: str) -> Optional[Dict[str, Any]]:
        """Parse a Server-Sent Events response to extract the JSON-RPC payload."""
        import json as json_module
        data_lines = []
        for line in text.splitlines():
            if line.startswith("data:"):
                data_lines.append(line[5:].strip())
            elif line == "" and data_lines:
                raw = "\n".join(data_lines)
                try:
                    return json_module.loads(raw)
                except Exception:
                    data_lines = []
        # Try last accumulated data if no blank-line terminator
        if data_lines:
            raw = "\n".join(data_lines)
            try:
                return json_module.loads(raw)
            except Exception:
                logger.error(f"Failed to parse SSE data for {method}: {raw[:200]}")
        return None
