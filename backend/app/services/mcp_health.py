"""MCP health check infrastructure.

Provides:
- Health probes for MCP servers
- Required vs optional server classification
- Degraded mode support
- Fail-closed for required write tools
- Bounded, cached, jittered probes
"""
from typing import Dict, List, Optional, Set, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
import asyncio
import threading
import random
import logging

logger = logging.getLogger(__name__)


class ServerRequirement(Enum):
    """Whether an MCP server is required or optional."""
    REQUIRED = "required"  # Fail closed if unavailable
    OPTIONAL = "optional"  # Degrade gracefully if unavailable


class HealthStatus(Enum):
    """Health status of an MCP server."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    CHECKING = "checking"


@dataclass
class ServerHealthConfig:
    """Configuration for server health checking."""
    server_name: str
    requirement: ServerRequirement = ServerRequirement.OPTIONAL
    check_interval_seconds: int = 30
    unhealthy_threshold: int = 3  # Consecutive failures before unhealthy
    healthy_threshold: int = 2   # Consecutive successes before healthy
    timeout_seconds: int = 5
    
    # Tool categorization
    write_tools: Set[str] = field(default_factory=set)  # Tools that require approval
    required_tools: Set[str] = field(default_factory=set)  # Tools that must be available


@dataclass
class ServerHealthState:
    """Current health state of an MCP server."""
    server_name: str
    status: HealthStatus = HealthStatus.UNKNOWN
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_check_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    last_failure_time: Optional[datetime] = None
    last_error: Optional[str] = None
    discovered_tools: List[str] = field(default_factory=list)
    
    def record_success(self, config: ServerHealthConfig, tools: List[str]):
        """Record a successful health check."""
        self.consecutive_successes += 1
        self.consecutive_failures = 0
        self.last_check_time = datetime.now(timezone.utc)
        self.last_success_time = self.last_check_time
        self.last_error = None
        self.discovered_tools = tools
        
        if self.consecutive_successes >= config.healthy_threshold:
            if self.status != HealthStatus.HEALTHY:
                logger.info(f"MCP server {self.server_name} is now HEALTHY")
            self.status = HealthStatus.HEALTHY
    
    def record_failure(self, config: ServerHealthConfig, error: str):
        """Record a failed health check."""
        self.consecutive_failures += 1
        self.consecutive_successes = 0
        self.last_check_time = datetime.now(timezone.utc)
        self.last_failure_time = self.last_check_time
        self.last_error = error
        
        if self.consecutive_failures >= config.unhealthy_threshold:
            if self.status != HealthStatus.UNHEALTHY:
                logger.warning(
                    f"MCP server {self.server_name} is now UNHEALTHY: {error}"
                )
            self.status = HealthStatus.UNHEALTHY


@dataclass
class MCPHealthCheckConfig:
    """Global configuration for MCP health checking."""
    # Default health check settings
    default_check_interval_seconds: int = 30
    default_unhealthy_threshold: int = 3
    default_healthy_threshold: int = 2
    default_timeout_seconds: int = 5
    
    # Server-specific configurations
    server_configs: Dict[str, ServerHealthConfig] = field(default_factory=dict)
    
    # Degraded mode settings
    allow_degraded_mode: bool = True  # Allow operation when optional servers down
    
    # Bounded probe settings
    max_concurrent_probes: int = 3  # Never probe more than N servers in parallel
    min_probe_interval_seconds: int = 5  # Minimum time between probes to same server
    probe_jitter_range: float = 0.3  # ±30% jitter on probe intervals
    
    # Startup validation
    required_server_startup_timeout: int = 10  # Fail startup if required servers don't respond
    lazy_connect_optional: bool = True  # Don't probe optional servers at startup
    
    # Write tool patterns - tools matching these patterns require approval
    write_tool_patterns: List[str] = field(default_factory=lambda: [
        "create", "update", "delete", "write", "modify",
        "insert", "remove", "drop", "set", "patch", "put"
    ])
    
    # Auto-approve patterns - low-risk actions that can skip approval
    auto_approve_patterns: List[str] = field(default_factory=lambda: [
        "get", "list", "read", "search", "query", "fetch",
        "describe", "show", "count", "exists", "check"
    ])


class MCPHealthChecker:
    """
    Manages health checking for MCP servers.
    
    Responsibilities:
    - Probe server health periodically
    - Track healthy/unhealthy state
    - Expose only healthy tools
    - Support degraded mode for optional servers
    - Fail closed for required write tools
    """
    
    def __init__(self, config: Optional[MCPHealthCheckConfig] = None):
        self.config = config or MCPHealthCheckConfig()
        self._server_states: Dict[str, ServerHealthState] = {}
        self._server_configs: Dict[str, ServerHealthConfig] = {}
        self._check_tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._running = False
    
    # =========================================================================
    # Configuration
    # =========================================================================
    
    def register_server(
        self,
        server_name: str,
        requirement: ServerRequirement = ServerRequirement.OPTIONAL,
        write_tools: Optional[Set[str]] = None,
        required_tools: Optional[Set[str]] = None,
    ):
        """Register an MCP server for health checking."""
        config = ServerHealthConfig(
            server_name=server_name,
            requirement=requirement,
            check_interval_seconds=self.config.default_check_interval_seconds,
            unhealthy_threshold=self.config.default_unhealthy_threshold,
            healthy_threshold=self.config.default_healthy_threshold,
            timeout_seconds=self.config.default_timeout_seconds,
            write_tools=write_tools or set(),
            required_tools=required_tools or set(),
        )
        
        self._server_configs[server_name] = config
        self._server_states[server_name] = ServerHealthState(server_name=server_name)
        
        logger.info(
            f"Registered MCP server for health checking: {server_name} ({requirement.value})"
        )
    
    # =========================================================================
    # Health Checking
    # =========================================================================
    
    def _should_skip_probe(self, server_name: str) -> bool:
        """Check if probe should be skipped due to recent check (caching)."""
        state = self._server_states.get(server_name)
        if state is None or state.last_check_time is None:
            return False
        
        elapsed = datetime.now(timezone.utc) - state.last_check_time
        return elapsed.total_seconds() < self.config.min_probe_interval_seconds
    
    def _get_jittered_delay(self) -> float:
        """Get random jitter delay to avoid thundering herd."""
        base = 0.1  # Base delay in seconds
        jitter = base * self.config.probe_jitter_range
        return base + random.uniform(-jitter, jitter)
    
    async def check_server_health(
        self,
        server_name: str,
        probe_func: Callable,
        force: bool = False,
    ) -> bool:
        """
        Check health of a single server with caching.
        
        Args:
            server_name: Name of the server to check
            probe_func: Async function that returns (success: bool, tools: List[str], error: Optional[str])
            force: If True, bypass cache and probe immediately
        
        Returns:
            True if healthy, False otherwise
        """
        if server_name not in self._server_configs:
            self.register_server(server_name)
        
        config = self._server_configs[server_name]
        state = self._server_states[server_name]
        
        # Skip if recently checked (unless forced)
        if not force and self._should_skip_probe(server_name):
            logger.debug(f"Skipping probe for {server_name} (recently checked)")
            return state.status == HealthStatus.HEALTHY
        
        try:
            state.status = HealthStatus.CHECKING
            
            # Call probe with timeout
            success, tools, error = await asyncio.wait_for(
                probe_func(),
                timeout=config.timeout_seconds
            )
            
            if success:
                state.record_success(config, tools)
                return True
            else:
                state.record_failure(config, error or "Unknown error")
                return False
                
        except asyncio.TimeoutError:
            state.record_failure(config, f"Health check timeout after {config.timeout_seconds}s")
            return False
        except Exception as e:
            state.record_failure(config, str(e))
            return False
    
    async def check_all_servers(
        self,
        probe_funcs: Dict[str, Callable],
        force: bool = False,
    ) -> Dict[str, bool]:
        """
        Check health of all registered servers with bounded concurrency.
        
        Args:
            probe_funcs: Dict mapping server_name to probe function
            force: If True, bypass cache and probe all immediately
        
        Returns:
            Dict mapping server_name to health status
        """
        results = {}
        semaphore = asyncio.Semaphore(self.config.max_concurrent_probes)
        
        async def check_one_bounded(server_name: str, probe_func: Callable):
            async with semaphore:
                # Add jittered delay to avoid thundering herd
                await asyncio.sleep(self._get_jittered_delay())
                results[server_name] = await self.check_server_health(
                    server_name, probe_func, force=force
                )
        
        # Check all servers with bounded parallelism
        await asyncio.gather(*[
            check_one_bounded(name, func)
            for name, func in probe_funcs.items()
        ], return_exceptions=True)
        
        return results
    
    # =========================================================================
    # Health Status Queries
    # =========================================================================
    
    def is_server_healthy(self, server_name: str) -> bool:
        """Check if a server is healthy."""
        state = self._server_states.get(server_name)
        return state is not None and state.status == HealthStatus.HEALTHY
    
    def is_server_required(self, server_name: str) -> bool:
        """Check if a server is required."""
        config = self._server_configs.get(server_name)
        return config is not None and config.requirement == ServerRequirement.REQUIRED
    
    def get_server_status(self, server_name: str) -> Dict[str, Any]:
        """Get detailed status for a server."""
        config = self._server_configs.get(server_name)
        state = self._server_states.get(server_name)
        
        if state is None:
            return {"status": "unknown", "registered": False}
        
        return {
            "status": state.status.value,
            "requirement": config.requirement.value if config else "unknown",
            "consecutive_failures": state.consecutive_failures,
            "consecutive_successes": state.consecutive_successes,
            "last_check": state.last_check_time.isoformat() if state.last_check_time else None,
            "last_success": state.last_success_time.isoformat() if state.last_success_time else None,
            "last_error": state.last_error,
            "tools_available": len(state.discovered_tools),
        }
    
    def get_all_server_statuses(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all registered servers."""
        return {
            name: self.get_server_status(name)
            for name in self._server_states
        }
    
    def get_healthy_tools(self) -> Set[str]:
        """Get set of tools from healthy servers only."""
        healthy_tools: Set[str] = set()
        
        for server_name, state in self._server_states.items():
            if state.status == HealthStatus.HEALTHY:
                healthy_tools.update(state.discovered_tools)
        
        return healthy_tools
    
    # =========================================================================
    # Tool Availability
    # =========================================================================
    
    def is_tool_available(self, tool_name: str) -> tuple[bool, str]:
        """
        Check if a tool is available (from a healthy server).
        
        Returns:
            (available, reason)
        """
        # Find which server provides this tool
        for server_name, state in self._server_states.items():
            if tool_name in state.discovered_tools:
                config = self._server_configs.get(server_name)
                
                if state.status == HealthStatus.HEALTHY:
                    return True, ""
                
                # Tool exists but server unhealthy
                if config and config.requirement == ServerRequirement.REQUIRED:
                    return False, f"Required server {server_name} is unhealthy"
                
                # Optional server - allow degraded mode
                if self.config.allow_degraded_mode:
                    return False, f"Optional server {server_name} is unhealthy (degraded mode)"
                else:
                    return False, f"Server {server_name} is unhealthy"
        
        return False, f"Tool {tool_name} not found on any server"
    
    def is_write_tool(self, tool_name: str) -> bool:
        """Check if a tool is a write operation requiring approval."""
        tool_lower = tool_name.lower()
        
        # Check explicit configuration first
        for config in self._server_configs.values():
            if tool_name in config.write_tools:
                return True
        
        # Check patterns
        return any(
            pattern in tool_lower
            for pattern in self.config.write_tool_patterns
        )
    
    def can_auto_approve(self, tool_name: str) -> bool:
        """Check if a tool action can be auto-approved (low-risk read operations)."""
        tool_lower = tool_name.lower()
        
        # Must match an auto-approve pattern
        matches_auto = any(
            pattern in tool_lower
            for pattern in self.config.auto_approve_patterns
        )
        
        # And must NOT be a write tool
        return matches_auto and not self.is_write_tool(tool_name)
    
    def check_tool_for_execution(self, tool_name: str, is_write: bool = False) -> tuple[bool, str]:
        """
        Check if a tool can be executed.
        
        For write tools on required servers, fails closed if server unhealthy.
        
        Returns:
            (can_execute, reason)
        """
        available, reason = self.is_tool_available(tool_name)
        
        if not available:
            # For write tools, always fail closed
            if is_write or self.is_write_tool(tool_name):
                return False, f"Write tool unavailable: {reason}"
            
            # For read tools on optional servers, may allow degraded mode
            return False, reason
        
        return True, ""
    
    # =========================================================================
    # Degraded Mode
    # =========================================================================
    
    def is_degraded(self) -> bool:
        """Check if system is operating in degraded mode."""
        for server_name, state in self._server_states.items():
            config = self._server_configs.get(server_name)
            
            if state.status != HealthStatus.HEALTHY:
                if config and config.requirement == ServerRequirement.OPTIONAL:
                    return True  # Optional server down = degraded
        
        return False
    
    def check_required_servers(self) -> tuple[bool, List[str]]:
        """
        Check if all required servers are healthy.
        
        Returns:
            (all_healthy, list_of_unhealthy_required_servers)
        """
        unhealthy_required = []
        
        for server_name, config in self._server_configs.items():
            if config.requirement == ServerRequirement.REQUIRED:
                state = self._server_states.get(server_name)
                if state is None or state.status != HealthStatus.HEALTHY:
                    unhealthy_required.append(server_name)
        
        return len(unhealthy_required) == 0, unhealthy_required
    
    async def validate_startup(
        self,
        probe_funcs: Dict[str, Callable],
    ) -> tuple[bool, List[str]]:
        """
        Validate that all required servers are available at startup.
        
        - Required servers are probed immediately with startup timeout
        - Optional servers are skipped if lazy_connect_optional is True
        
        Args:
            probe_funcs: Dict mapping server_name to probe function
        
        Returns:
            (success, list_of_failed_required_servers)
        
        Raises:
            RuntimeError: If required servers fail to respond within timeout
        """
        required_probes = {}
        optional_servers = []
        
        for server_name, probe_func in probe_funcs.items():
            config = self._server_configs.get(server_name)
            if config and config.requirement == ServerRequirement.REQUIRED:
                required_probes[server_name] = probe_func
            else:
                optional_servers.append(server_name)
        
        # Log startup plan
        logger.info(
            f"Startup validation: {len(required_probes)} required servers, "
            f"{len(optional_servers)} optional servers "
            f"({'lazy connect' if self.config.lazy_connect_optional else 'immediate connect'})"
        )
        
        # Validate required servers with startup timeout
        if required_probes:
            try:
                await asyncio.wait_for(
                    self.check_all_servers(required_probes, force=True),
                    timeout=self.config.required_server_startup_timeout
                )
            except asyncio.TimeoutError:
                failed = list(required_probes.keys())
                logger.error(
                    f"Required servers failed startup validation (timeout): {failed}"
                )
                return False, failed
        
        # Check results
        all_healthy, unhealthy = self.check_required_servers()
        
        if not all_healthy:
            logger.error(
                f"Required servers failed startup validation: {unhealthy}"
            )
            return False, unhealthy
        
        # Optionally probe optional servers
        if not self.config.lazy_connect_optional:
            optional_probes = {
                name: probe_funcs[name]
                for name in optional_servers
                if name in probe_funcs
            }
            if optional_probes:
                await self.check_all_servers(optional_probes, force=True)
        else:
            logger.info(f"Deferring optional server connections: {optional_servers}")
        
        return True, []
    
    def get_available_tools_for_workflow(self, workflow_type: str) -> List[str]:
        """
        Get tools available for a specific workflow type.
        
        For required workflows, only returns tools if all required servers are healthy.
        For optional workflows, returns tools from healthy servers only.
        """
        healthy_tools = list(self.get_healthy_tools())
        
        # TODO: Implement workflow-specific tool filtering
        # For now, return all healthy tools
        return healthy_tools


# Global health checker instance (thread-safe singleton)
_health_checker: Optional[MCPHealthChecker] = None
_health_checker_lock = threading.Lock()


def get_health_checker(config: Optional[MCPHealthCheckConfig] = None) -> MCPHealthChecker:
    """Get or create the global health checker (thread-safe)."""
    global _health_checker
    
    # Fast path: already initialized
    if _health_checker is not None:
        return _health_checker
    
    # Slow path: double-checked locking
    with _health_checker_lock:
        if _health_checker is None:
            _health_checker = MCPHealthChecker(config)
    return _health_checker


def reset_health_checker():
    """Reset the global health checker (for testing)."""
    global _health_checker
    with _health_checker_lock:
        _health_checker = None
