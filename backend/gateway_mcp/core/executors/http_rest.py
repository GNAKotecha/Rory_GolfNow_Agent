"""
HTTP REST Backend

Direct HTTP client for external systems without MCP servers.
Uses per-tool allowlisting for security.

No free-form URL access - all endpoints must be explicitly allowlisted.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import httpx

from gateway_mcp.core.config import Settings
from gateway_mcp.core.errors import (
    ContainerUnavailableError,
    CredentialMissingError,
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


# Type alias for credential fetcher function
# Signature: (user_id: int, provider: str) -> str (bearer token)
CredentialFetcher = Callable[[int, str], str]


@dataclass
class AllowlistEntry:
    """An allowed HTTP endpoint pattern."""
    
    host: str
    methods: list[str]  # ["GET", "POST", ...]
    path_pattern: str   # e.g., "/api/v1/users/*"
    requires_auth: bool = True
    provider: str | None = None  # Provider name for credential lookup


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
    
    def __init__(
        self,
        settings: Settings,
        allowlist: HTTPAllowlist | None = None,
        credential_fetcher: CredentialFetcher | None = None,
    ):
        """
        Initialize HTTP REST backend.
        
        Args:
            settings: Gateway settings.
            allowlist: HTTP endpoint allowlist. If None, an empty allowlist is used.
            credential_fetcher: Function to fetch bearer tokens for users.
                               Signature: (user_id, provider) -> bearer_token
        """
        self.settings = settings
        self.allowlist = allowlist or HTTPAllowlist()
        self._credential_fetcher = credential_fetcher
        self._client: httpx.AsyncClient | None = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
            )
        return self._client
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def _get_credential(
        self,
        user_id: int,
        provider: str,
    ) -> str:
        """
        Get bearer token for user and provider.
        
        Returns:
            Bearer token string (already includes "Bearer " prefix).
            
        Raises:
            CredentialMissingError: If no credential available.
        """
        if self._credential_fetcher is None:
            raise CredentialMissingError(
                provider=provider,
                reconnect_url=f"/api/credentials/{provider}/authorize",
            )
        
        try:
            return self._credential_fetcher(user_id, provider)
        except Exception as e:
            logger.warning(f"Failed to fetch credential for {provider}: {e}")
            raise CredentialMissingError(
                provider=provider,
                reconnect_url=f"/api/credentials/{provider}/authorize",
            )
    
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
        timeout: int | None = None,
    ) -> HTTPResult:
        """
        Make HTTP call to an allowlisted endpoint.
        
        Args:
            service: Service name (must be in allowlist).
            method: HTTP method (GET, POST, PUT, PATCH, DELETE).
            path: URL path.
            body: Request body (JSON).
            headers: Additional headers.
            user_id: User ID for credential lookup (if requires_auth).
            timeout: Optional timeout override.
            
        Returns:
            HTTPResult with status, body, and headers.
            
        Raises:
            PermissionDeniedError: Endpoint not in allowlist.
            CredentialMissingError: Auth required but no credential.
            ContainerUnavailableError: Connection failed.
            SubprocessTimeoutError: Request timed out.
            UpstreamError: Other HTTP error.
        """
        # Check allowlist
        url, entry = self.allowlist.resolve(service, method, path)
        
        # Get credential if required
        auth_headers: dict[str, str] = {}
        if entry.requires_auth:
            if user_id is None:
                provider = entry.provider or service
                raise CredentialMissingError(
                    provider=provider,
                    reconnect_url=f"/api/credentials/{provider}/authorize",
                )
            
            provider = entry.provider or service
            bearer_token = await self._get_credential(user_id, provider)
            
            # Ensure proper Bearer prefix
            if bearer_token.startswith("Bearer "):
                auth_headers["Authorization"] = bearer_token
            else:
                auth_headers["Authorization"] = f"Bearer {bearer_token}"
        
        client = await self._get_client()
        start_time = time.monotonic()
        
        # Merge headers
        request_headers = {**(headers or {}), **auth_headers}
        
        try:
            response = await client.request(
                method=method.upper(),
                url=url,
                json=body if body else None,
                headers=request_headers,
                timeout=timeout or 30,
            )
            
            duration_ms = int((time.monotonic() - start_time) * 1000)
            
            # Parse response body
            try:
                response_body = response.json()
            except Exception:
                response_body = response.text
            
            # Handle auth errors specially
            if response.status_code == 401:
                provider = entry.provider or service
                raise CredentialMissingError(
                    provider=provider,
                    reconnect_url=f"/api/credentials/{provider}/authorize",
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
            raise SubprocessTimeoutError(timeout_seconds=timeout or 30)
        except (CredentialMissingError, PermissionDeniedError):
            raise
        except Exception as e:
            logger.exception(f"HTTP REST call failed: {e}")
            raise UpstreamError(service=service, detail=str(e)[:200])


# Type check (disabled in runtime, just for static analysis)
def _type_check() -> ExecutorBackend:
    return HTTPRestBackend(Settings())  # type: ignore
