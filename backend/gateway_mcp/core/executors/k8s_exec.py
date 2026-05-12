"""
Kubernetes Exec Backend (Stub)

Executes commands via `kubectl exec` for QA BRS pods.
Used when GATEWAY_ENV=qa.

This is a placeholder implementation - actual k8s integration
will be implemented when QA infrastructure is available.
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


class K8sExecBackend:
    """
    Executor backend that uses `kubectl exec` to run commands in k8s pods.
    
    Resolves logical service names to pod selectors via config.
    
    NOTE: This is a stub implementation. Real k8s integration pending
    when QA infrastructure details are finalized.
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
        Execute command via kubectl exec.
        
        Will use pod_selector from config to find the target pod,
        then execute via kubectl exec.
        """
        raise NotImplementedError(
            "k8s_exec backend not yet implemented. "
            "This requires QA infrastructure to be available. "
            f"Service: {service}, Command: {argv}"
        )
    
    async def submit_command(
        self,
        service: str,
        argv: list[str],
        timeout: int,
    ) -> JobHandle:
        """Submit command for async execution via k8s Job."""
        raise NotImplementedError(
            "k8s_exec submit_command not yet implemented. "
            "This requires k8s Job creation support."
        )
    
    async def query_db(
        self,
        db: str,
        query: str,
        params: list[Any],
    ) -> list[dict[str, Any]]:
        """Execute database query via kubectl exec into db pod."""
        raise NotImplementedError(
            "k8s_exec query_db not yet implemented. "
            "This requires kubectl exec to database pods."
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
        Make HTTP call to a k8s service.
        
        Uses shared HTTP utility with service URL from config.
        HTTP calls don't require kubectl exec.
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


# Type check
_: ExecutorBackend = K8sExecBackend(Settings())  # type: ignore
