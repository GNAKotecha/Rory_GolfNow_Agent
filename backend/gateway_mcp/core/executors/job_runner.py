"""
Job Runner Backend (Stub)

Submits commands via workflow API for production BRS jobs.
Used when GATEWAY_ENV=prod.

This is a placeholder implementation - actual job runner integration
will be implemented when production workflow API is available.
"""

import logging
from typing import Any

from gateway_mcp.core.config import Settings
from gateway_mcp.core.executors.base import (
    ExecResult,
    ExecutorBackend,
    HTTPResult,
    JobHandle,
)

logger = logging.getLogger(__name__)


class JobRunnerBackend:
    """
    Executor backend that submits jobs via workflow API.
    
    Resolves logical service names to job templates via config.
    Jobs are submitted asynchronously and can be tracked via JobHandle.
    
    NOTE: This is a stub implementation. Real job runner integration
    pending when production workflow API is available.
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.services = settings.services
    
    async def run_command(
        self,
        service: str,
        argv: list[str],
        timeout: int,
    ) -> ExecResult:
        """
        Execute command via job runner.
        
        Submits a job and waits for completion.
        For truly async execution, use submit_command instead.
        """
        raise NotImplementedError(
            "job_runner backend not yet implemented. "
            "This requires workflow API integration. "
            f"Service: {service}, Command: {argv}"
        )
    
    async def submit_command(
        self,
        service: str,
        argv: list[str],
        timeout: int,
    ) -> JobHandle:
        """
        Submit command for async execution.
        
        This is the primary interface for job_runner - jobs are submitted
        to the workflow API and tracked via JobHandle.
        """
        raise NotImplementedError(
            "job_runner submit_command not yet implemented. "
            "This requires workflow API job submission support."
        )
    
    async def query_db(
        self,
        db: str,
        query: str,
        params: list[Any],
    ) -> list[dict[str, Any]]:
        """
        Execute database query via read-only job.
        
        Submits a read-only query job using the appropriate job template.
        """
        raise NotImplementedError(
            "job_runner query_db not yet implemented. "
            "This requires read-only query job templates."
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
        Make HTTP call to a production service.
        
        Uses shared HTTP utility with service URL from config.
        HTTP calls work directly without job submission.
        """
        from gateway_mcp.core.executors.http_utils import make_http_call
        
        return await make_http_call(
            settings=self.settings,
            service=service,
            method=method,
            path=path,
            body=body,
            headers=headers,
        )


# Type check
_: ExecutorBackend = JobRunnerBackend(Settings())  # type: ignore
