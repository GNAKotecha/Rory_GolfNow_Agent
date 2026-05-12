"""
Shared HTTP utilities for executor backends.

Extracted to avoid coupling between executor backend implementations.
"""

import logging
import time
from typing import Any, Optional

import httpx

from gateway_mcp.core.brs_auth import get_brs_auth_headers
from gateway_mcp.core.config import Settings
from gateway_mcp.core.errors import (
    ContainerUnavailableError,
    SubprocessTimeoutError,
    UpstreamError,
)
from gateway_mcp.core.executors.base import HTTPResult

logger = logging.getLogger(__name__)


# Services that require BRS OAuth authentication
BRS_AUTHENTICATED_SERVICES = {"teesheet", "memberships", "payments"}


async def make_http_call(
    settings: Settings,
    service: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    club_id: Optional[str] = None,
) -> HTTPResult:
    """
    Make an HTTP call to a service using its configured URL.
    
    This is a shared utility used by docker_exec, k8s_exec, and job_runner
    backends for HTTP calls that don't require container/pod execution.
    
    For BRS services (teesheet, memberships, payments), automatically injects
    OAuth authentication headers if configured.
    
    Args:
        settings: Gateway settings with service configuration
        service: Logical service name (resolved to URL via config)
        method: HTTP method
        path: URL path
        body: Request body
        headers: Additional headers
        timeout: Request timeout in seconds
        club_id: Optional club ID for per-club authentication. If provided,
                 uses cached token from authenticate_club if available.
        
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
    
    # Build headers - start with any provided headers
    request_headers = dict(headers) if headers else {}
    
    # Inject BRS auth for BRS services
    if service in BRS_AUTHENTICATED_SERVICES:
        try:
            # Pass club_id to get cached per-club token if available
            brs_auth = await get_brs_auth_headers(club_id=club_id)
            # Only add if not already provided (allow override)
            if "Authorization" not in request_headers and brs_auth:
                request_headers.update(brs_auth)
                logger.debug(f"Injected BRS auth for service: {service}" + (f" (club: {club_id})" if club_id else ""))
        except Exception as e:
            logger.warning(f"Failed to get BRS auth for {service}: {e}")
            # Continue without auth - will likely get 401
    
    start_time = time.monotonic()
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method=method.upper(),
                url=url,
                json=body if body else None,
                headers=request_headers,
            )
            
            duration_ms = int((time.monotonic() - start_time) * 1000)
            
            try:
                response_body = response.json()
            except Exception:
                response_body = response.text
            
            # If we got a 401, clear the BRS token cache so next call refreshes
            if response.status_code == 401 and service in BRS_AUTHENTICATED_SERVICES:
                from gateway_mcp.core.brs_auth import BRSAuthProvider
                # Clear specific club token if club_id provided, otherwise clear all
                BRSAuthProvider.get_instance().clear_token(club_id=club_id)
                logger.warning(
                    f"Got 401 from {service}, cleared BRS token cache" + 
                    (f" for club: {club_id}" if club_id else " (all)")
                )
            
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
