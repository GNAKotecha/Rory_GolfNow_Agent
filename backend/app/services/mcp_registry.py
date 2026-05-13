"""MCP tool registry with role-based access control and logging.

Manages multiple MCP clients, enforces tool allowlists, and logs all tool calls.

Task B1: Adds run-scoped ToolCatalog for deterministic tool routing.
Task B2: Adds structured ToolNotFoundReason for precise error classification.

Refactor: Run-scoped catalogs are now immutable copies, not shared mutable state.
"""
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass, field
import logging
import asyncio
import os
import copy

from app.services.mcp_client import MCPClient, MCPTool, MCPToolResult
from app.config.mcp_config import (
    Environment,
    MCPServerConfig,
    is_tool_allowed,
    filter_tools_by_role,
    get_servers_for_environment,
)

logger = logging.getLogger(__name__)

# Default TTL for run-scoped catalog (in seconds)
DEFAULT_CATALOG_TTL_SECONDS = int(os.environ.get("TOOL_CATALOG_TTL_SECONDS", "600"))


# ==============================================================================
# Task B2: Tool Not Found Semantics
# ==============================================================================

class ToolNotFoundReason(Enum):
    """Structured reason for tool-not-found errors.
    
    Task B2: Distinguishes between different causes of tool unavailability
    to enable precise recovery strategies.
    
    Refactor: Split RBAC denial from auth failure for clearer remediation.
    Note: SERVER_UNAVAILABLE removed - health check is telemetry-only, not a gate.
    """
    CATALOG_MISS = "catalog_miss"  # Tool never exposed in any server
    RBAC_DENIED = "rbac_denied"  # Role policy denies access (not credential issue)


@dataclass
class ToolLookupResult:
    """Result of a tool lookup operation.
    
    Task B2: Provides structured information about tool availability.
    """
    found: bool
    server_name: Optional[str] = None
    not_found_reason: Optional[ToolNotFoundReason] = None
    error_message: Optional[str] = None


# ==============================================================================
# Task B1: Run-Scoped Tool Catalog
# ==============================================================================

@dataclass
class ToolCatalog:
    """Run-scoped snapshot of available tools.
    
    Task B1: Captures tool availability at workflow start to ensure
    deterministic routing throughout the run. Avoids repeated discovery
    calls on each tool lookup.
    
    Refactor: Instances are immutable snapshots - do not modify after creation.
    """
    # Flattened list of all tools
    tools: List[MCPTool] = field(default_factory=list)
    
    # Tool name -> server name mapping for O(1) lookup
    tool_to_server: Dict[str, str] = field(default_factory=dict)
    
    # Server name -> list of tool names
    server_to_tools: Dict[str, List[str]] = field(default_factory=dict)
    
    # Server health at snapshot time (for telemetry only, does not gate tool availability)
    server_health: Dict[str, bool] = field(default_factory=dict)
    
    # When this catalog was created
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Optional TTL for auto-invalidation
    ttl_seconds: int = DEFAULT_CATALOG_TTL_SECONDS
    
    # Discovery metrics
    discovery_duration_ms: Optional[float] = None
    total_servers: int = 0
    failed_servers: int = 0
    
    def is_valid(self) -> bool:
        """Check if catalog is still valid (not expired)."""
        if self.ttl_seconds <= 0:
            return True  # No TTL = never expires
        elapsed = (datetime.now(timezone.utc) - self.created_at).total_seconds()
        return elapsed < self.ttl_seconds
    
    def get_tool(self, tool_name: str) -> Optional[MCPTool]:
        """Get tool by name from catalog."""
        for tool in self.tools:
            if tool.name == tool_name:
                return tool
        return None
    
    def get_server_for_tool(self, tool_name: str) -> Optional[str]:
        """Get server name for a tool."""
        return self.tool_to_server.get(tool_name)
    
    def has_tool(self, tool_name: str) -> bool:
        """Check if tool exists in catalog."""
        return tool_name in self.tool_to_server
    
    def lookup_tool(self, tool_name: str, user_role: Optional[str] = None) -> ToolLookupResult:
        """
        Look up a tool with structured not-found information.
        
        Task B2: Returns detailed reason if tool not found.
        
        Note: Server health is NOT checked here - if tool was discovered, it's available.
        Health is tracked for telemetry only.
        """
        # Check if tool exists in catalog
        if tool_name not in self.tool_to_server:
            return ToolLookupResult(
                found=False,
                not_found_reason=ToolNotFoundReason.CATALOG_MISS,
                error_message=f"Tool '{tool_name}' not found in any MCP server catalog",
            )
        
        server_name = self.tool_to_server[tool_name]
        
        # Check role permission if role provided (RBAC policy, not credentials)
        if user_role and not is_tool_allowed(tool_name, user_role):
            return ToolLookupResult(
                found=False,
                server_name=server_name,
                not_found_reason=ToolNotFoundReason.RBAC_DENIED,
                error_message=f"Tool '{tool_name}' not allowed for role '{user_role}'. Contact your administrator to request access.",
            )
        
        # Tool found and accessible
        return ToolLookupResult(
            found=True,
            server_name=server_name,
        )
    
    def to_summary_dict(self) -> Dict[str, Any]:
        """Return a summary for logging/metrics."""
        return {
            "total_tools": len(self.tools),
            "total_servers": self.total_servers,
            "failed_servers": self.failed_servers,
            "created_at": self.created_at.isoformat(),
            "ttl_seconds": self.ttl_seconds,
            "is_valid": self.is_valid(),
            "discovery_duration_ms": self.discovery_duration_ms,
        }


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
    """Registry for managing MCP clients and tool access.
    
    Task B1: Supports run-scoped tool catalog for deterministic routing.
    
    Refactor: Each run gets its own immutable catalog copy.
    Internal discovery cache is shared for performance but not exposed.
    """

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
        
        # Internal shared discovery cache (for performance, not exposed to runs)
        self._discovery_cache: Optional[ToolCatalog] = None
        
        # Async lock to prevent parallel refresh storms during discovery
        self._discovery_lock = asyncio.Lock()
        
        # Metrics for catalog operations
        self._catalog_creation_count = 0
        self._catalog_copy_count = 0

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
    
    # ==========================================================================
    # Task B1: Run-Scoped Tool Catalog Management
    # ==========================================================================
    
    async def create_run_catalog(
        self,
        ttl_seconds: Optional[int] = None,
        force_refresh: bool = False,
    ) -> ToolCatalog:
        """
        Create a fresh, immutable catalog snapshot for a single run.
        
        Refactor: Each run gets its own copy. Two concurrent runs will
        NOT share the same catalog object.
        
        Args:
            ttl_seconds: Optional TTL override (default: DEFAULT_CATALOG_TTL_SECONDS)
            force_refresh: Force rebuilding the internal cache
        
        Returns:
            New ToolCatalog instance (immutable snapshot for this run)
        """
        # Check if internal cache is valid outside lock (fast path)
        if not force_refresh and self._discovery_cache and self._discovery_cache.is_valid():
            self._catalog_copy_count += 1
            # Deep copy to ensure runs don't share mutable state
            return self._copy_catalog(self._discovery_cache, ttl_seconds)
        
        # Acquire lock to prevent parallel refresh storms
        async with self._discovery_lock:
            # Double-check after acquiring lock (another task may have refreshed)
            if not force_refresh and self._discovery_cache and self._discovery_cache.is_valid():
                self._catalog_copy_count += 1
                return self._copy_catalog(self._discovery_cache, ttl_seconds)
            
            # Need fresh discovery
            catalog = await self._build_catalog_internal(ttl_seconds)
            
            # Update internal cache
            self._discovery_cache = catalog
            self._catalog_creation_count += 1
        
        # Return a copy for this run (not the cache itself)
        self._catalog_copy_count += 1
        return self._copy_catalog(catalog, ttl_seconds)
    
    def _copy_catalog(
        self,
        source: ToolCatalog,
        ttl_seconds: Optional[int] = None,
    ) -> ToolCatalog:
        """Create an independent copy of a catalog for run isolation.
        
        Deep copies MCPTool objects to ensure input_schema mutation
        in one run doesn't affect another.
        """
        # Deep copy MCPTool objects to isolate mutable input_schema
        copied_tools = [
            MCPTool(
                name=t.name,
                description=t.description,
                input_schema=copy.deepcopy(t.input_schema),
                server_name=t.server_name,
            )
            for t in source.tools
        ]
        
        return ToolCatalog(
            tools=copied_tools,
            tool_to_server=dict(source.tool_to_server),
            server_to_tools={k: list(v) for k, v in source.server_to_tools.items()},
            server_health=dict(source.server_health),
            created_at=datetime.now(timezone.utc),  # Fresh timestamp for this run
            ttl_seconds=ttl_seconds if ttl_seconds is not None else source.ttl_seconds,
            discovery_duration_ms=source.discovery_duration_ms,
            total_servers=source.total_servers,
            failed_servers=source.failed_servers,
        )
    
    async def _build_catalog_internal(
        self,
        ttl_seconds: Optional[int] = None,
    ) -> ToolCatalog:
        """
        Build catalog from actual discovery.
        
        Refactor: Uses list_tools() as source of truth.
        Health check is for telemetry only - does NOT gate tool inclusion.
        """
        start_time = datetime.now(timezone.utc)
        
        if not self._initialized:
            await self.initialize()
        
        catalog = ToolCatalog(
            ttl_seconds=ttl_seconds if ttl_seconds is not None else DEFAULT_CATALOG_TTL_SECONDS,
            total_servers=len(self.clients),
        )
        
        failed_servers = 0
        
        for server_name, client in self.clients.items():
            # Collect health for telemetry (does NOT gate discovery)
            try:
                is_healthy = await client.health_check()
                catalog.server_health[server_name] = is_healthy
            except Exception:
                catalog.server_health[server_name] = False
            
            # Always attempt tool discovery - list_tools is source of truth
            try:
                tools = await client.list_tools(force_refresh=True)
                catalog.server_to_tools[server_name] = [t.name for t in tools]
                
                for tool in tools:
                    catalog.tools.append(tool)
                    catalog.tool_to_server[tool.name] = server_name
                
                logger.debug(
                    f"Discovered {len(tools)} tools from {server_name}",
                    extra={
                        "server": server_name,
                        "tool_count": len(tools),
                        "health": catalog.server_health.get(server_name, False),
                    }
                )
                
            except Exception as e:
                logger.error(
                    f"Failed to discover tools from {server_name}: {e}",
                    extra={"server": server_name, "error": str(e)}
                )
                catalog.server_to_tools[server_name] = []
                failed_servers += 1
        
        elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        catalog.discovery_duration_ms = elapsed_ms
        catalog.failed_servers = failed_servers
        
        logger.info(
            f"Tool catalog built: {len(catalog.tools)} tools from "
            f"{catalog.total_servers - failed_servers}/{catalog.total_servers} servers",
            extra=catalog.to_summary_dict()
        )
        
        return catalog
    
    async def create_catalog(
        self,
        force_refresh: bool = False,
        ttl_seconds: Optional[int] = None,
    ) -> ToolCatalog:
        """
        Create a run-scoped tool catalog.
        
        DEPRECATED: Use create_run_catalog() for proper run isolation.
        Kept for backward compatibility but now returns copies.
        """
        if force_refresh:
            self._discovery_cache = None
        return await self.create_run_catalog(ttl_seconds)
    
    def get_catalog_metrics(self) -> Dict[str, int]:
        """Get catalog operation metrics."""
        return {
            "creation_count": self._catalog_creation_count,
            "copy_count": self._catalog_copy_count,
        }

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
    
    async def execute_tool_with_catalog(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        user: Any,
        catalog: ToolCatalog,
    ) -> MCPToolResult:
        """
        Execute a tool using a run-scoped catalog for deterministic routing.
        
        Task B1 + B2: Uses catalog for O(1) lookup and provides structured
        not-found semantics.
        
        Refactor: No fallback to legacy path - catalog is authoritative for run.
        
        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments
            user: User object with id, role attributes
            catalog: Run-scoped tool catalog
        
        Returns:
            Tool execution result with structured error info
        """
        if not self._initialized:
            await self.initialize()
        
        # Task B2: Use structured catalog lookup
        lookup = catalog.lookup_tool(tool_name, user.role.value)
        
        if not lookup.found:
            # Build structured error result based on reason
            error_category = None
            http_status = None
            
            if lookup.not_found_reason == ToolNotFoundReason.CATALOG_MISS:
                error_category = "tool_not_found"
                http_status = 404
            elif lookup.not_found_reason == ToolNotFoundReason.RBAC_DENIED:
                # RBAC denial is policy, not credential issue
                error_category = "rbac_denied"
                http_status = 403
            
            logger.warning(
                f"Tool lookup failed: {tool_name} ({lookup.not_found_reason.value})",
                extra={
                    "tool": tool_name,
                    "user_id": user.id,
                    "role": user.role.value,
                    "reason": lookup.not_found_reason.value,
                    "error_category": error_category,
                }
            )
            
            result = MCPToolResult(
                success=False,
                error=lookup.error_message,
                http_status=http_status,
                error_category=error_category,
                is_semantic_error=True,  # All lookup failures are semantic
            )
            
            server_label = lookup.server_name or "CATALOG_MISS"
            self._log_tool_call(tool_name, server_label, user, arguments, result)
            
            return result
        
        # Tool found in catalog - get client from server name
        server_name = lookup.server_name
        client = self.clients.get(server_name)
        
        if client is None:
            # Should not happen if catalog is valid, but handle gracefully
            logger.error(
                f"Client not found for server in catalog: {server_name}",
                extra={"tool": tool_name, "server": server_name}
            )
            result = MCPToolResult(
                success=False,
                error=f"Internal error: server '{server_name}' not available",
                error_category="internal_error",
                is_semantic_error=True,
            )
            self._log_tool_call(tool_name, "INTERNAL_ERROR", user, arguments, result)
            return result
        
        # Execute tool
        logger.info(
            f"Executing tool (catalog): {server_name}.{tool_name}",
            extra={
                "tool": tool_name,
                "server": server_name,
                "user_id": user.id,
                "role": user.role.value,
                "catalog_age_seconds": (
                    datetime.now(timezone.utc) - catalog.created_at
                ).total_seconds(),
            }
        )
        
        result = await client.call_tool(
            tool_name,
            arguments,
            user_id=user.id,
        )
        
        self._log_tool_call(tool_name, server_name, user, arguments, result)
        
        return result

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        user: Any,  # User object with id, role attributes
    ) -> MCPToolResult:
        """
        Execute a tool with role-based access control and logging.
        
        Note: For run-scoped deterministic routing, prefer execute_tool_with_catalog().

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments
            user: User object

        Returns:
            Tool execution result
        """
        if not self._initialized:
            await self.initialize()

        # Check role-based access (Refactor: emit rbac_denied, not permission_denied)
        if not is_tool_allowed(tool_name, user.role.value):
            logger.warning(
                f"Tool access denied (RBAC): {tool_name} for role {user.role.value}",
                extra={
                    "tool": tool_name,
                    "user_id": user.id,
                    "role": user.role.value,
                },
            )

            result = MCPToolResult(
                success=False,
                error=f"Tool '{tool_name}' not allowed for role '{user.role.value}'. Contact your administrator to request access.",
                http_status=403,
                error_category="rbac_denied",
                is_semantic_error=True,
            )

            self._log_tool_call(tool_name, "RBAC_DENIED", user, arguments, result)

            return result

        # Find tool across all servers
        server_name, client = await self._find_tool(tool_name)

        # Self-heal: if tool not found, force refresh all caches and retry once
        if client is None:
            logger.info(
                f"Tool '{tool_name}' not found in cache, forcing discovery refresh...",
                extra={"tool": tool_name, "user_id": user.id},
            )
            await self.discover_all_tools(force_refresh=True)
            server_name, client = await self._find_tool(tool_name)

        if client is None:
            # Log per-server tool counts for diagnostics
            tool_counts = {}
            for srv_name, srv_client in self.clients.items():
                count = len(srv_client._tools_cache or [])
                tool_counts[srv_name] = count
            
            logger.warning(
                f"Tool not found after refresh: {tool_name}. "
                f"Per-server tool counts: {tool_counts}",
                extra={
                    "tool": tool_name,
                    "user_id": user.id,
                    "tool_counts": tool_counts,
                },
            )

            # Task B2: Structured tool-not-found error
            result = MCPToolResult(
                success=False,
                error=f"Tool '{tool_name}' not found on any MCP server",
                http_status=404,
                error_category="tool_not_found",
                is_semantic_error=True,
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

        result = await client.call_tool(
            tool_name,
            arguments,
            user_id=user.id,
        )

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
