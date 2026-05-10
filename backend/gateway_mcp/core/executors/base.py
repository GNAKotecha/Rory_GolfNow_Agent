"""
Executor Backend Protocol

Defines the interface for all executor backends:
- docker_exec: Local BRS via docker exec
- k8s_exec: QA BRS via kubectl exec  
- job_runner: Prod BRS via workflow API
- mcp_proxy: Upstream MCP servers (Atlassian, Github)
- http_rest: Direct external REST (fallback)
- mock: Testing
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Protocol, runtime_checkable


class JobStatus(str, Enum):
    """Status of a submitted job."""
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ExecResult:
    """Result of a command execution."""
    
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    
    @property
    def success(self) -> bool:
        return self.exit_code == 0
    
    def raise_for_status(self) -> None:
        """Raise if command failed."""
        if not self.success:
            from gateway_mcp.core.errors import ContainerUnavailableError
            raise ContainerUnavailableError(
                service="command",
                audit_id=None,
            )


@dataclass
class HTTPResult:
    """Result of an HTTP call."""
    
    status_code: int
    body: dict[str, Any] | list[Any] | str | None
    headers: dict[str, str] = field(default_factory=dict)
    duration_ms: int = 0
    
    @property
    def success(self) -> bool:
        return 200 <= self.status_code < 300


@dataclass
class JobEvent:
    """Event from a streaming job."""
    
    event_type: str  # "output" | "status" | "error"
    data: str
    timestamp: str


@dataclass
class JobHandle:
    """Handle for a submitted async job."""
    
    job_id: str
    _backend: "ExecutorBackend"
    
    async def status(self) -> JobStatus:
        """Get current job status."""
        raise NotImplementedError("Subclass must implement")
    
    async def stream(self) -> AsyncIterator[JobEvent]:
        """Stream job events."""
        raise NotImplementedError("Subclass must implement")
        yield  # Make this a generator
    
    async def result(self) -> ExecResult:
        """Wait for and return final result."""
        raise NotImplementedError("Subclass must implement")
    
    async def cancel(self) -> None:
        """Cancel the job."""
        raise NotImplementedError("Subclass must implement")


@runtime_checkable
class ExecutorBackend(Protocol):
    """
    Protocol for executor backends.
    
    Each backend implements execution for a specific environment:
    - docker_exec: shells out to `docker exec` for local containers
    - k8s_exec: shells out to `kubectl exec` for k8s pods
    - job_runner: submits jobs via workflow API for prod
    - mcp_proxy: calls upstream MCP servers
    - http_rest: makes direct HTTP calls with allowlisting
    
    The `service` parameter is a logical name (e.g., "teesheet", "mysql")
    resolved to a concrete target via per-env config.
    """
    
    async def run_command(
        self,
        service: str,
        argv: list[str],
        timeout: int,
    ) -> ExecResult:
        """
        Execute a command and wait for completion.
        
        Args:
            service: Logical service name (resolved via config)
            argv: Command arguments
            timeout: Timeout in seconds
            
        Returns:
            ExecResult with exit code, stdout, stderr, duration
            
        Raises:
            ContainerUnavailableError: Service not reachable
            SubprocessTimeoutError: Command timed out
        """
        ...
    
    async def submit_command(
        self,
        service: str,
        argv: list[str],
        timeout: int,
    ) -> JobHandle:
        """
        Submit a command for async execution.
        
        Used for long-running jobs that need progress tracking.
        MVP tools use run_command; this is for future prod jobs.
        
        Args:
            service: Logical service name
            argv: Command arguments
            timeout: Max execution time in seconds
            
        Returns:
            JobHandle for tracking and cancellation
        """
        ...
    
    async def query_db(
        self,
        db: str,
        query: str,
        params: list[Any],
    ) -> list[dict[str, Any]]:
        """
        Execute a database query.
        
        Args:
            db: Database name (e.g., "mysql", "mongo")
            query: SQL or query document
            params: Query parameters (positional)
            
        Returns:
            List of result rows as dicts
            
        Raises:
            ContainerUnavailableError: Database not reachable
            UpstreamError: Query execution failed
        """
        ...
    
    async def call_http(
        self,
        service: str,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HTTPResult:
        """
        Make an HTTP call to a service.
        
        Args:
            service: Logical service name (resolved to URL via config)
            method: HTTP method (GET, POST, PUT, DELETE, PATCH)
            path: URL path (appended to service base URL)
            body: Request body (JSON-serializable)
            headers: Additional headers
            
        Returns:
            HTTPResult with status, body, headers
            
        Raises:
            ContainerUnavailableError: Service not reachable
            UpstreamError: Non-2xx response
        """
        ...
