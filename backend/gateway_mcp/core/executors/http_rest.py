"""
HTTP REST Backend

Direct HTTP client for external systems without MCP servers.
Uses per-tool allowlisting for security.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from gateway_mcp.core.config import Settings
from gateway_mcp.core.errors import (
    ContainerUnavailableError,
    PermissionDeniedError,
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


@dataclass
class AllowlistEntry:
    """An allowed HTTP endpoint pattern."""
    
    host: str
    methods: list[str]  # ["GET", "POST", ...]
    path_pattern: str   # e.g., "/api/v1/users/*"
    requires_auth: bool = True


@dataclass  
class HTTPAllowlist:
    """Allowlist of permitted HTTP endpoints."""
    
    entries: dict[str, list[AllowlistEntry]] = field(default_factory=dict)
    
    def add(self, service: str, entry: AllowlistEntry) -> None:
        """Add an allowlist entry for a service."""
        if service not in self.entries:
            self.entries[service] = []
        self.entries[service].append(entry)
    
    def resolve(
        self,
        service: str,
        method: str,
        path: str,
    ) -> tuple[str, AllowlistEntry]:
        """
        Resolve a request against the allowlist.
        
        Returns (full_url, entry) if allowed, raises if not.
        """
        if service not in self.entries:
            raise PermissionDeniedError(
                f"Service '{service}' not in HTTP allowlist"
            )
        
        for entry in self.entries[service]:
            if method.upper() not in entry.methods:
                continue
            
            # Simple pattern matching (supports trailing *)
            if entry.path_pattern.endswith("*"):
                prefix = entry.path_pattern[:-1]
                if path.startswith(prefix):
                    url = f"https://{entry.host}{path}"
                    return url, entry
            elif path == entry.path_pattern:
                url = f"https://{entry.host}{path}"
                return url, entry
        
        raise PermissionDeniedError(
            f"Request {method} {path} not allowed for service '{service}'"
        )


class HTTPRestBackend:
    """
    Executor backend for direct HTTP calls to external systems.
    
    For external systems without an MCP server. Uses per-tool allowlisting
    to prevent free-form URL access.
    
    No free-form URL access - all endpoints must be explicitly allowlisted.
    """
    
    def __init__(self, settings: Settings, allowlist: HTTPAllowlist | None = None):
        self.settings = settings
        self.allowlist = allowlist or HTTPAllowlist()
        self._client: httpx.AsyncClient | None = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def run_command(
        self,
        service: str,
        argv: list[str],
        timeout: int,
    ) -> ExecResult:
        """HTTP REST doesn't support command execution."""
        raise NotImplementedError(
            "HTTP REST backend does not support command execution. "
            "Use call_http instead."
        )
    
    async def submit_command(
        self,
        service: str,
        argv: list[str],
        timeout: int,
    ) -> JobHandle:
        """HTTP REST doesn't support job submission."""
        raise NotImplementedError(
            "HTTP REST backend does not support job submission."
        )
    
    async def query_db(
        self,
        db: str,
        query: str,
        params: list[Any],
    ) -> list[dict[str, Any]]:
        """HTTP REST doesn't support database queries."""
        raise NotImplementedError(
            "HTTP REST backend does not support database queries."
        )
    
    async def call_http(
        self,
        service: str,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        user_id: int | None = None,
    ) -> HTTPResult:
        """
        Make HTTP call to an allowlisted endpoint.
        
        Args:
            service: Service name (must be in allowlist)
            method: HTTP method
            path: URL path
            body: Request body
            headers: Additional headers
            user_id: User ID for credential lookup (if requires_auth)
        """
        # Check allowlist
        url, entry = self.allowlist.resolve(service, method, path)
        
        # Get credential if required
        auth_headers = {}
        if entry.requires_auth and user_id:
            # TODO: Fetch credential from store
            # credential = await self.credential_store.get(user_id, service)
            # auth_headers["Authorization"] = f"Bearer {credential.access_token}"
            pass
        
        client = await self._get_client()
        start_time = time.monotonic()
        
        try:
            response = await client.request(
                method=method.upper(),
                url=url,
                json=body if body else None,
                headers={**(headers or {}), **auth_headers},
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
            raise SubprocessTimeoutError(timeout_seconds=30)
        except Exception as e:
            logger.exception(f"HTTP REST call failed: {e}")
            raise UpstreamError(service=service, detail=str(e)[:200])


# Type check
_: ExecutorBackend = HTTPRestBackend(Settings())  # type: ignore
