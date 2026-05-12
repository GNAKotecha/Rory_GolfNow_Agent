"""
Docker Exec Backend

Executes commands via `docker exec` for local BRS containers.
Used when GATEWAY_ENV=local.

REUSE NOTE: This backend integrates with Phase 2 BRS infrastructure:
- Uses app.services.brs_tools.registry.BRSToolRegistry for CLI templates
- Uses app.services.brs_tools.parser.BRSToolOutputParser for stdout parsing
- Tool handlers (not this backend) own the business logic mapping
"""

import asyncio
import logging
import time
from typing import Any

from gateway_mcp.core.config import ServiceConfig, Settings
from gateway_mcp.core.errors import (
    ContainerUnavailableError,
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


class DockerExecBackend:
    """
    Executor backend that uses `docker exec` to run commands in containers.
    
    Resolves logical service names to container names via config.
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.services = settings.services
    
    def _get_container(self, service: str) -> str:
        """Get container name for a service."""
        if service not in self.services:
            raise ContainerUnavailableError(service=service)
        
        config = self.services[service]
        if not config.container:
            raise ContainerUnavailableError(
                service=f"{service} (no container configured)"
            )
        
        return config.container
    
    def _get_service_url(self, service: str) -> str:
        """Get HTTP URL for a service."""
        if service not in self.services:
            raise ContainerUnavailableError(service=service)
        
        config = self.services[service]
        if not config.url:
            raise ContainerUnavailableError(
                service=f"{service} (no URL configured)"
            )
        
        return config.url
    
    async def run_command(
        self,
        service: str,
        argv: list[str],
        timeout: int,
    ) -> ExecResult:
        """
        Execute command via docker exec.
        
        Shells out to the docker CLI rather than using the Docker SDK
        to avoid docker socket mount requirements.
        """
        container = self._get_container(service)
        
        # Build docker exec command
        cmd = ["docker", "exec", container] + argv
        
        logger.debug(f"Executing: {' '.join(cmd)}")
        start_time = time.monotonic()
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise SubprocessTimeoutError(timeout_seconds=timeout)
            
            duration_ms = int((time.monotonic() - start_time) * 1000)
            
            return ExecResult(
                exit_code=proc.returncode or 0,
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                duration_ms=duration_ms,
            )
            
        except FileNotFoundError:
            raise ContainerUnavailableError(
                service="docker CLI not found"
            )
        except Exception as e:
            if isinstance(e, (ContainerUnavailableError, SubprocessTimeoutError)):
                raise
            logger.exception(f"Docker exec failed: {e}")
            raise ContainerUnavailableError(service=service)
    
    async def submit_command(
        self,
        service: str,
        argv: list[str],
        timeout: int,
    ) -> JobHandle:
        """
        Submit command for async execution.
        
        For docker_exec, this just wraps run_command since docker exec
        is inherently synchronous. Real async job support is in job_runner.
        """
        # For local dev, we don't have a real job system
        # Just run synchronously and return a completed handle
        raise NotImplementedError(
            "submit_command not supported in docker_exec backend. "
            "Use run_command instead, or switch to job_runner backend."
        )
    
    async def query_db(
        self,
        db: str,
        query: str,
        params: list[Any],
    ) -> list[dict[str, Any]]:
        """
        Execute database query via docker exec.
        
        SECURITY NOTE: This method is intentionally not implemented with direct
        SQL execution to avoid injection vulnerabilities. Database queries should
        go through typed tool handlers that use parameterized queries.
        
        Future implementation will use BRSToolRegistry CLI templates for safe execution.
        See: app.services.brs_tools.registry
        """
        raise NotImplementedError(
            "Direct database queries not supported in docker_exec. "
            "Use typed tool handlers with BRSToolRegistry CLI templates instead. "
            "See app.services.brs_tools.registry for safe query patterns."
        )
    
    async def call_http(
        self,
        service: str,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        club_id: str | None = None,
    ) -> HTTPResult:
        """
        Make HTTP call to a service.
        
        Uses shared HTTP utility - doesn't require docker exec.
        """
        from gateway_mcp.core.executors.http_utils import make_http_call
        
        return await make_http_call(
            settings=self.settings,
            service=service,
            method=method,
            path=path,
            body=body,
            headers=headers,
            club_id=club_id,
        )


# Type check that we implement the protocol
_: ExecutorBackend = DockerExecBackend(Settings())  # type: ignore
