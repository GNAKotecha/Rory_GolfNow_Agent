"""Stdio-based MCP client with subprocess management.

Provides support for local MCP servers (Playwright, filesystem, etc.) that use
stdio-based communication via subprocess spawning.

Protocol flow:
1. Spawn subprocess with command + args
2. Initialize: Send initialize request via stdin
3. Tools list/call: Send JSON-RPC requests via stdin, read responses from stdout

All communication follows JSON-RPC 2.0 format over newline-delimited JSON.
"""
import asyncio
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

from app.services.mcp_client import MCPTool, MCPToolResult
from .async_event_loop import mcp_async_method

logger = logging.getLogger(__name__)


class StdioMCPClient:
    """
    Client for stdio-based MCP servers (Playwright, filesystem, etc.).

    Spawns subprocess and communicates via stdin/stdout.
    """

    def __init__(self, command: str, args: List[str], server_name: str):
        """
        Initialize stdio MCP client.

        Args:
            command: Command to spawn (e.g., "npx", "node")
            args: Arguments to pass to command
            server_name: Unique name for this server instance
        """
        self.command = command
        self.args = args
        self.server_name = server_name
        self.process: Optional[asyncio.subprocess.Process] = None
        self._request_id = 0
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._tools_cache: Optional[List[MCPTool]] = None

    @mcp_async_method
    async def initialize(self):
        """Start subprocess and initialize MCP session."""
        try:
            self.process = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Start reader task
            self._reader_task = asyncio.create_task(self._read_responses())

            # Send initialize request
            response = await self._jsonrpc_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "rory-agent",
                    "version": "1.0.0"
                }
            })

            logger.info(
                f"Initialized stdio MCP: {self.server_name}",
                extra={"server": self.server_name, "pid": self.process.pid}
            )

        except Exception as e:
            logger.error(
                f"Failed to start stdio MCP: {self.server_name}",
                extra={"server": self.server_name, "error": str(e)}
            )
            raise

    @mcp_async_method
    async def close(self):
        """Close subprocess."""
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()

    @mcp_async_method
    async def health_check(self) -> bool:
        """Check if subprocess is running."""
        if not self.process:
            return False
        return self.process.returncode is None

    @mcp_async_method
    async def list_tools(self, force_refresh: bool = False) -> List[MCPTool]:
        """List available tools from MCP server."""
        if not force_refresh and self._tools_cache:
            return self._tools_cache

        response = await self._jsonrpc_request("tools/list", {})

        if not response or "result" not in response:
            return []

        tools = [
            MCPTool(
                name=tool["name"],
                description=tool.get("description", ""),
                input_schema=tool.get("inputSchema", {}),
                server_name=self.server_name,
            )
            for tool in response["result"].get("tools", [])
        ]

        self._tools_cache = tools
        logger.info(
            f"Discovered {len(tools)} tools from {self.server_name}",
            extra={"server": self.server_name, "tool_count": len(tools)},
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
        start_time = datetime.now(timezone.utc)

        response = await self._jsonrpc_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })

        elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

        if not response:
            return MCPToolResult(
                success=False,
                error="No response from server",
                execution_time_ms=elapsed_ms,
            )

        if "error" in response:
            error = response["error"]
            return MCPToolResult(
                success=False,
                error=f"{error.get('message', 'Unknown error')} (code: {error.get('code')})",
                execution_time_ms=elapsed_ms,
                is_semantic_error=True,
            )

        if "result" in response:
            return MCPToolResult(
                success=True,
                result=response["result"],
                execution_time_ms=elapsed_ms,
            )

        return MCPToolResult(
            success=False,
            error="Unexpected response format",
            execution_time_ms=elapsed_ms,
        )

    async def _jsonrpc_request(self, method: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send JSON-RPC 2.0 request via stdin."""
        if not self.process or not self.process.stdin:
            return None

        self._request_id += 1
        request_id = self._request_id

        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params
        }

        # Create future for response
        future = asyncio.Future()
        self._pending_requests[request_id] = future

        try:
            # Send request
            message = json.dumps(payload) + "\n"
            self.process.stdin.write(message.encode())
            await self.process.stdin.drain()

            # Wait for response with timeout
            response = await asyncio.wait_for(future, timeout=30.0)
            return response

        except asyncio.TimeoutError:
            logger.error(
                f"Stdio MCP request timeout: {method}",
                extra={"server": self.server_name, "method": method}
            )
            return None
        except Exception as e:
            logger.error(
                f"Stdio MCP request error: {method}",
                extra={"server": self.server_name, "method": method, "error": str(e)}
            )
            return None
        finally:
            self._pending_requests.pop(request_id, None)

    async def _read_responses(self):
        """Read responses from stdout."""
        if not self.process or not self.process.stdout:
            return

        try:
            while True:
                line = await self.process.stdout.readline()
                if not line:
                    break

                try:
                    response = json.loads(line.decode())
                    request_id = response.get("id")

                    if request_id in self._pending_requests:
                        future = self._pending_requests[request_id]
                        if not future.done():
                            future.set_result(response)

                except json.JSONDecodeError:
                    logger.warning(
                        f"Invalid JSON from stdio MCP: {self.server_name}",
                        extra={"server": self.server_name, "line": line[:100]}
                    )

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(
                f"Error reading stdio MCP responses: {self.server_name}",
                extra={"server": self.server_name, "error": str(e)}
            )
