"""MCP client abstraction with timeout, retry, and error handling.

Provides a unified interface for calling remote MCP servers with:
- Connection pooling
- Timeout enforcement
- Automatic retries
- Graceful error handling
- Request/response logging
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import asyncio
import aiohttp
from enum import Enum

from app.config.mcp_config import MCPServerConfig

logger = logging.getLogger(__name__)


# ==============================================================================
# Data Models
# ==============================================================================

@dataclass
class MCPTool:
    """Represents an MCP tool."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    server_name: str


@dataclass
class MCPToolResult:
    """Result from MCP tool execution."""
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    execution_time_ms: Optional[float] = None
    retry_count: int = 0


class MCPErrorType(Enum):
    """Types of MCP errors."""
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    SERVER_ERROR = "server_error"
    NOT_FOUND = "not_found"
    INVALID_REQUEST = "invalid_request"
    UNKNOWN = "unknown"


# ==============================================================================
# MCP Client
# ==============================================================================

class MCPClient:
    """Client for interacting with a remote MCP server."""

    def __init__(self, config: MCPServerConfig):
        """
        Initialize MCP client.

        Args:
            config: MCP server configuration
        """
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self._tools_cache: Optional[List[MCPTool]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl_seconds = 300  # 5 minutes

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    async def close(self):
        """Close client session."""
        if self.session and not self.session.closed:
            await self.session.close()

    async def health_check(self) -> bool:
        """
        Check if MCP server is reachable.

        Returns:
            True if server is healthy, False otherwise
        """
        try:
            session = await self._get_session()
            url = f"{self.config.url}/health"

            async with session.get(url) as response:
                return response.status == 200

        except Exception as e:
            logger.warning(
                f"Health check failed for {self.config.name}: {e}",
                extra={"server": self.config.name, "error": str(e)},
            )
            return False

    async def list_tools(self, force_refresh: bool = False) -> List[MCPTool]:
        """
        List available tools from MCP server.

        Args:
            force_refresh: Force cache refresh

        Returns:
            List of available tools
        """
        # Check cache
        if not force_refresh and self._is_cache_valid():
            return self._tools_cache or []

        try:
            session = await self._get_session()
            url = f"{self.config.url}/tools/list"

            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(
                        f"Failed to list tools from {self.config.name}: HTTP {response.status}"
                    )
                    return []

                data = await response.json()
                tools = [
                    MCPTool(
                        name=tool["name"],
                        description=tool.get("description", ""),
                        input_schema=tool.get("inputSchema", {}),
                        server_name=self.config.name,
                    )
                    for tool in data.get("tools", [])
                ]

                # Update cache
                self._tools_cache = tools
                self._cache_timestamp = datetime.now(timezone.utc)

                logger.info(
                    f"Discovered {len(tools)} tools from {self.config.name}",
                    extra={"server": self.config.name, "tool_count": len(tools)},
                )

                return tools

        except Exception as e:
            logger.error(
                f"Error listing tools from {self.config.name}: {e}",
                extra={"server": self.config.name, "error": str(e)},
            )
            return []

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> MCPToolResult:
        """
        Call a tool on the MCP server with retry logic.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        start_time = datetime.now(timezone.utc)
        retry_count = 0

        for attempt in range(self.config.max_retries + 1):
            try:
                session = await self._get_session()
                url = f"{self.config.url}/tools/call"

                payload = {
                    "name": tool_name,
                    "arguments": arguments,
                }

                async with session.post(url, json=payload) as response:
                    elapsed_ms = (
                        datetime.now(timezone.utc) - start_time
                    ).total_seconds() * 1000

                    if response.status == 200:
                        data = await response.json()

                        logger.info(
                            f"Tool call succeeded: {self.config.name}.{tool_name}",
                            extra={
                                "server": self.config.name,
                                "tool": tool_name,
                                "elapsed_ms": elapsed_ms,
                                "retry_count": retry_count,
                            },
                        )

                        return MCPToolResult(
                            success=True,
                            result=data.get("result"),
                            execution_time_ms=elapsed_ms,
                            retry_count=retry_count,
                        )

                    elif response.status == 404:
                        # Tool not found - don't retry
                        error_msg = f"Tool not found: {tool_name}"
                        logger.error(
                            f"Tool not found: {self.config.name}.{tool_name}",
                            extra={"server": self.config.name, "tool": tool_name},
                        )
                        return MCPToolResult(
                            success=False,
                            error=error_msg,
                            execution_time_ms=elapsed_ms,
                            retry_count=retry_count,
                        )

                    else:
                        # Server error - retry if attempts remaining
                        error_text = await response.text()
                        logger.warning(
                            f"Tool call failed (attempt {attempt + 1}): {self.config.name}.{tool_name} - HTTP {response.status}",
                            extra={
                                "server": self.config.name,
                                "tool": tool_name,
                                "status": response.status,
                                "attempt": attempt + 1,
                            },
                        )

                        if attempt < self.config.max_retries:
                            retry_count += 1
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                            continue

                        return MCPToolResult(
                            success=False,
                            error=f"Server error: HTTP {response.status}",
                            execution_time_ms=elapsed_ms,
                            retry_count=retry_count,
                        )

            except asyncio.TimeoutError:
                logger.warning(
                    f"Timeout calling {self.config.name}.{tool_name} (attempt {attempt + 1})",
                    extra={
                        "server": self.config.name,
                        "tool": tool_name,
                        "attempt": attempt + 1,
                    },
                )

                if attempt < self.config.max_retries:
                    retry_count += 1
                    await asyncio.sleep(2 ** attempt)
                    continue

                elapsed_ms = (
                    datetime.now(timezone.utc) - start_time
                ).total_seconds() * 1000

                return MCPToolResult(
                    success=False,
                    error=f"Timeout after {self.config.timeout_seconds}s",
                    execution_time_ms=elapsed_ms,
                    retry_count=retry_count,
                )

            except Exception as e:
                logger.error(
                    f"Error calling {self.config.name}.{tool_name} (attempt {attempt + 1}): {e}",
                    extra={
                        "server": self.config.name,
                        "tool": tool_name,
                        "error": str(e),
                        "attempt": attempt + 1,
                    },
                )

                if attempt < self.config.max_retries:
                    retry_count += 1
                    await asyncio.sleep(2 ** attempt)
                    continue

                elapsed_ms = (
                    datetime.now(timezone.utc) - start_time
                ).total_seconds() * 1000

                return MCPToolResult(
                    success=False,
                    error=f"Connection error: {str(e)}",
                    execution_time_ms=elapsed_ms,
                    retry_count=retry_count,
                )

        # Should never reach here
        elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        return MCPToolResult(
            success=False,
            error="Max retries exceeded",
            execution_time_ms=elapsed_ms,
            retry_count=retry_count,
        )

    def _is_cache_valid(self) -> bool:
        """Check if tools cache is still valid."""
        if self._tools_cache is None or self._cache_timestamp is None:
            return False

        elapsed = (datetime.now(timezone.utc) - self._cache_timestamp).total_seconds()
        return elapsed < self._cache_ttl_seconds
