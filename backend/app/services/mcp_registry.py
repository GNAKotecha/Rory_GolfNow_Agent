"""MCP tool registry with role-based access control and logging.

Manages multiple MCP clients, enforces tool allowlists, and logs all tool calls.
"""
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import logging

from app.services.mcp_client import MCPClient, MCPTool, MCPToolResult
from app.config.mcp_config import (
    Environment,
    MCPServerConfig,
    is_tool_allowed,
    filter_tools_by_role,
    get_servers_for_environment,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# Tool Call Log Entry
# ==============================================================================

class ToolCallLog:
    """Represents a logged tool call."""

    def __init__(
        self,
        tool_name: str,
        server_name: str,
        user_id: int,
        user_role: str,
        arguments: Dict[str, Any],
        result: MCPToolResult,
        timestamp: datetime,
    ):
        self.tool_name = tool_name
        self.server_name = server_name
        self.user_id = user_id
        self.user_role = user_role
        self.arguments = arguments
        self.result = result
        self.timestamp = timestamp

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/logging."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "tool_name": self.tool_name,
            "server_name": self.server_name,
            "user_id": self.user_id,
            "user_role": self.user_role,
            "arguments": self.arguments,
            "success": self.result.success,
            "error": self.result.error,
            "execution_time_ms": self.result.execution_time_ms,
            "retry_count": self.result.retry_count,
        }


# ==============================================================================
# MCP Tool Registry
# ==============================================================================

class MCPToolRegistry:
    """Registry for managing MCP clients and tool access."""

    def __init__(self, environment: Environment):
        """
        Initialize tool registry.

        Args:
            environment: Deployment environment
        """
        self.environment = environment
        self.clients: Dict[str, MCPClient] = {}
        self.tool_call_logs: List[ToolCallLog] = []
        self._initialized = False

    async def initialize(self):
        """Initialize MCP clients for all configured servers."""
        if self._initialized:
            return

        server_configs = get_servers_for_environment(self.environment)

        for config in server_configs:
            client = MCPClient(config)
            self.clients[config.name] = client

            logger.info(
                f"Initialized MCP client: {config.name}",
                extra={"server": config.name, "url": config.url},
            )

        self._initialized = True

    async def close(self):
        """Close all MCP client connections."""
        for client in self.clients.values():
            await client.close()

    async def discover_all_tools(
        self,
        force_refresh: bool = False,
    ) -> Dict[str, List[MCPTool]]:
        """
        Discover tools from all MCP servers.

        Args:
            force_refresh: Force cache refresh

        Returns:
            Dictionary mapping server name to list of tools
        """
        if not self._initialized:
            await self.initialize()

        tools_by_server: Dict[str, List[MCPTool]] = {}

        for server_name, client in self.clients.items():
            try:
                tools = await client.list_tools(force_refresh=force_refresh)
                tools_by_server[server_name] = tools

                logger.info(
                    f"Discovered {len(tools)} tools from {server_name}",
                    extra={"server": server_name, "tool_count": len(tools)},
                )

            except Exception as e:
                logger.error(
                    f"Failed to discover tools from {server_name}: {e}",
                    extra={"server": server_name, "error": str(e)},
                )
                tools_by_server[server_name] = []

        return tools_by_server

    def get_available_tools(self, role: str) -> List[str]:
        """
        Get list of available tool names for a role (cached).

        Args:
            role: User role

        Returns:
            List of tool names available to the role
        """
        all_tools = []

        for client in self.clients.values():
            if client._tools_cache:
                tool_names = [tool.name for tool in client._tools_cache]
                all_tools.extend(tool_names)

        # Filter by role allowlist
        return filter_tools_by_role(all_tools, role)

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        user: Any,  # User object with id, role attributes
    ) -> MCPToolResult:
        """
        Execute a tool with role-based access control and logging.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments
            user: User object

        Returns:
            Tool execution result
        """
        if not self._initialized:
            await self.initialize()

        # Check role-based access
        if not is_tool_allowed(tool_name, user.role.value):
            logger.warning(
                f"Tool access denied: {tool_name} for role {user.role.value}",
                extra={
                    "tool": tool_name,
                    "user_id": user.id,
                    "role": user.role.value,
                },
            )

            result = MCPToolResult(
                success=False,
                error=f"Tool '{tool_name}' not allowed for role '{user.role.value}'",
            )

            self._log_tool_call(tool_name, "DENIED", user, arguments, result)

            return result

        # Find tool across all servers
        server_name, client = await self._find_tool(tool_name)

        if client is None:
            logger.warning(
                f"Tool not found: {tool_name}",
                extra={"tool": tool_name, "user_id": user.id},
            )

            result = MCPToolResult(
                success=False,
                error=f"Tool '{tool_name}' not found on any MCP server",
            )

            self._log_tool_call(tool_name, "NOT_FOUND", user, arguments, result)

            return result

        # Execute tool
        logger.info(
            f"Executing tool: {server_name}.{tool_name}",
            extra={
                "tool": tool_name,
                "server": server_name,
                "user_id": user.id,
                "role": user.role.value,
            },
        )

        result = await client.call_tool(tool_name, arguments)

        # Log tool call
        self._log_tool_call(tool_name, server_name, user, arguments, result)

        return result

    async def _find_tool(self, tool_name: str) -> tuple[Optional[str], Optional[MCPClient]]:
        """
        Find which server provides a tool.

        Returns:
            (server_name, client) or (None, None) if not found
        """
        for server_name, client in self.clients.items():
            # Check cache first
            if client._tools_cache:
                for tool in client._tools_cache:
                    if tool.name == tool_name:
                        return server_name, client

            # If not in cache, try to refresh
            tools = await client.list_tools()
            for tool in tools:
                if tool.name == tool_name:
                    return server_name, client

        return None, None

    def _log_tool_call(
        self,
        tool_name: str,
        server_name: str,
        user: Any,
        arguments: Dict[str, Any],
        result: MCPToolResult,
    ):
        """Log a tool call for audit purposes."""
        log_entry = ToolCallLog(
            tool_name=tool_name,
            server_name=server_name,
            user_id=user.id,
            user_role=user.role.value,
            arguments=arguments,
            result=result,
            timestamp=datetime.now(timezone.utc),
        )

        self.tool_call_logs.append(log_entry)

        # Log to application logger
        logger.info(
            f"Tool call logged: {tool_name}",
            extra=log_entry.to_dict(),
        )

    def get_tool_call_logs(
        self,
        user_id: Optional[int] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get tool call logs.

        Args:
            user_id: Optional user ID filter
            limit: Maximum number of logs to return

        Returns:
            List of tool call log dictionaries
        """
        logs = self.tool_call_logs

        if user_id is not None:
            logs = [log for log in logs if log.user_id == user_id]

        # Return most recent logs
        logs = logs[-limit:]

        return [log.to_dict() for log in logs]

    async def health_check_all(self) -> Dict[str, bool]:
        """
        Check health of all MCP servers.

        Returns:
            Dictionary mapping server name to health status
        """
        if not self._initialized:
            await self.initialize()

        health_status = {}

        for server_name, client in self.clients.items():
            is_healthy = await client.health_check()
            health_status[server_name] = is_healthy

            logger.info(
                f"Health check: {server_name} - {'healthy' if is_healthy else 'unhealthy'}",
                extra={"server": server_name, "healthy": is_healthy},
            )

        return health_status
