"""
Shared HTTP utilities for executor backends.

Extracted to avoid coupling between executor backend implementations.
"""

import logging
import time
from typing import Any

import httpx

from gateway_mcp.core.config import Settings
from gateway_mcp.core.errors import (
    ContainerUnavailableError,
    SubprocessTimeoutError,
    UpstreamError,
)
from gateway_mcp.core.executors.base import HTTPResult

logger = logging.getLogger(__name__)


async def make_http_call(
    settings: Settings,
    service: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> HTTPResult:
    """
    Make an HTTP call to a service using its configured URL.
    
    This is a shared utility used by docker_exec, k8s_exec, and job_runner
    backends for HTTP calls that don't require container/pod execution.
    
    Args:
        settings: Gateway settings with service configuration
        service: Logical service name (resolved to URL via config)
        method: HTTP method
        path: URL path
        body: Request body
        headers: Additional headers
        timeout: Request timeout in seconds
        
    Returns:
        HTTPResult with status, body, headers
    """
    if service not in settings.services:
        raise ContainerUnavailableError(service=service)
    
    config = settings.services[service]
    if not config.url:
        raise ContainerUnavailableError(
            service=f"{service} (no URL configured)"
        )
    
    base_url = config.url
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    
    start_time = time.monotonic()
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method=method.upper(),
                url=url,
                json=body if body else None,
                headers=headers or {},
            )
            
            duration_ms = int((time.monotonic() - start_time) * 1000)
            
            try:
                response_body = response.json()
            except Exception:
                response_body = response.text
            
            return HTTPResult(
                status_code=response.status_code,
                body=response_body,
                headers=dict(response.headers),
                duration_ms=duration_ms,
            )
            
    except httpx.ConnectError:
        raise ContainerUnavailableError(service=service)
    except httpx.TimeoutException:
        raise SubprocessTimeoutError(timeout_seconds=int(timeout))
    except Exception as e:
        logger.exception(f"HTTP call failed: {e}")
        raise UpstreamError(service=service, detail=str(e)[:200])
