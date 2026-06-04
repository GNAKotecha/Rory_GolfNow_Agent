"""MCP client abstraction with timeout, retry, and error handling.

Provides a unified interface for calling remote MCP servers with:
- Connection pooling
- Timeout enforcement
- Automatic retries
- Graceful error handling
- Request/response logging

Task C2: MCP error envelope enrichment - structured fields for precise error classification.
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import asyncio
import os
import json
import aiohttp
from enum import Enum

from app.config.mcp_config import MCPServerConfig
from .async_event_loop import (
    mcp_event_loop_manager,
    safe_async_call,
    mcp_async_method
)

logger = logging.getLogger(__name__)


# ==============================================================================
# Data Models
# ==============================================================================

@dataclass
class MCPTool:
    """Represents an MCP tool."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    server_name: str


@dataclass
class MCPToolResult:
    """Result from MCP tool execution.
    
    Task A2: Retry ownership clarification
    - is_semantic_error: True if this was a semantic error (isError response, validation, auth)
      Semantic errors should NOT be transport-retried; only agent-level recovery applies.
    - transport_retries_exhausted: True if MCP client exhausted its transport retry budget.
      Agent layer can use this to avoid retry amplification.
    
    Task C2: Error envelope enrichment
    - error_category: Machine-readable error category (e.g., "container_unavailable")
    - upstream_status: HTTP status from the upstream service (distinct from MCP layer status)
    - terminal_hint: True if this error is definitively terminal (no recovery possible)
    - error_metadata: Additional structured error context
    """
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    execution_time_ms: Optional[float] = None
    retry_count: int = 0
    http_status: Optional[int] = None  # HTTP status from MCP server response
    error_category: Optional[str] = None  # Machine-readable error category
    # Task A2: Retry ownership fields
    is_semantic_error: bool = False  # True for isError/validation/auth - agent handles recovery
    transport_retries_exhausted: bool = False  # True if MCP client exhausted transport retries
    # Task C2: Enhanced error envelope
    upstream_status: Optional[int] = None  # HTTP status from upstream service (e.g., BRS API)
    terminal_hint: bool = False  # True if error is definitively terminal
    error_metadata: Dict[str, Any] = field(default_factory=dict)  # Additional error context
    
    def is_terminal_error(self) -> bool:
        """
        Determine if this error should terminate the workflow.
        
        Task C2: Use structured fields over message parsing.
        """
        if self.terminal_hint:
            return True
        
        terminal_categories = {
            "auth_failure", "permission_denied", "rbac_denied",
            "tool_not_found", "catalog_miss", "catalog_stale",
            "validation_error", "invalid_arguments",
        }
        if self.error_category in terminal_categories:
            return True
        
        terminal_statuses = {401, 403, 404, 422}
        if self.http_status in terminal_statuses:
            return True
        
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize to dictionary for logging/tracing.
        
        Task C2: Include all structured fields.
        """
        return {
            "success": self.success,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "retry_count": self.retry_count,
            "http_status": self.http_status,
            "error_category": self.error_category,
            "is_semantic_error": self.is_semantic_error,
            "transport_retries_exhausted": self.transport_retries_exhausted,
            "upstream_status": self.upstream_status,
            "terminal_hint": self.terminal_hint,
            "error_metadata": self.error_metadata,
        }


class MCPErrorType(Enum):
    """Types of MCP errors."""
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    SERVER_ERROR = "server_error"
    NOT_FOUND = "not_found"
    INVALID_REQUEST = "invalid_request"
    UNKNOWN = "unknown"


# ==============================================================================
# MCP Client
# ==============================================================================

class MCPClient:
    """Client for interacting with a remote MCP server."""

    def __init__(self, config: MCPServerConfig):
        """
        Initialize MCP client.

        Args:
            config: MCP server configuration
        """
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self._tools_cache: Optional[List[MCPTool]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl_seconds = 300  # 5 minutes

    @mcp_async_method
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    @mcp_async_method
    async def close(self):
        """Close client session."""
        if self.session and not self.session.closed:
            await self.session.close()

    @mcp_async_method
    async def health_check(self) -> bool:
        """
        Check if MCP server is reachable.

        Returns:
            True if server is healthy, False otherwise
        """
        try:
            session = await safe_async_call(self._get_session)
            url = f"{self.config.url}/health"

            async with session.get(url) as response:
                return response.status == 200

        except Exception as e:
            logger.warning(
                f"Health check failed for {self.config.name}: {e}",
                extra={"server": self.config.name, "error": str(e)},
            )
            return False

    @mcp_async_method
    async def list_tools(self, force_refresh: bool = False) -> List[MCPTool]:
        """
        List available tools from MCP server.

        Args:
            force_refresh: Force cache refresh

        Returns:
            List of available tools
        """
        # Check cache
        if not force_refresh and self._is_cache_valid():
            return self._tools_cache or []

        try:
            session = await self._get_session()
            url = f"{self.config.url}/mcp/tools/list"
            
            # Build auth headers (gateway-mcp requires service token)
            headers = self._build_auth_headers(user_id=None)

            # Prefer POST for Gateway MCP transport; fallback to GET for legacy servers.
            response_data = None
            response_status = None
            response_content_type = None
            response_body_snippet = None
            
            async with session.post(url, json={}, headers=headers) as response:
                response_status = response.status
                response_content_type = response.headers.get("Content-Type", "")
                
                if response.status == 200:
                    response_data = await self._parse_json_response(response)
                elif response.status in (404, 405):
                    async with session.get(url, headers=headers) as get_response:
                        response_status = get_response.status
                        response_content_type = get_response.headers.get("Content-Type", "")
                        
                        if get_response.status == 200:
                            response_data = await self._parse_json_response(get_response)
                        else:
                            response_body_snippet = await self._get_body_snippet(get_response)
                else:
                    response_body_snippet = await self._get_body_snippet(response)
            
            # Handle parse failures with diagnostic logging
            if response_data is None:
                logger.error(
                    f"Failed to list tools from {self.config.name}: "
                    f"HTTP {response_status}, Content-Type: {response_content_type}, "
                    f"Body: {response_body_snippet or '(empty)'}",
                    extra={
                        "server": self.config.name,
                        "status": response_status,
                        "content_type": response_content_type,
                    },
                )
                return []

            data = response_data or {}
            tools = [
                MCPTool(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    input_schema=tool.get("inputSchema", {}),
                    server_name=self.config.name,
                )
                for tool in data.get("tools", [])
            ]

            # Update cache
            self._tools_cache = tools
            self._cache_timestamp = datetime.now(timezone.utc)

            logger.info(
                f"Discovered {len(tools)} tools from {self.config.name}",
                extra={"server": self.config.name, "tool_count": len(tools)},
            )

            return tools

        except Exception as e:
            logger.error(
                f"Error listing tools from {self.config.name}: {e}",
                extra={"server": self.config.name, "error": str(e)},
            )
            return []
    
    async def _parse_json_response(self, response: aiohttp.ClientResponse) -> Optional[Dict[str, Any]]:
        """
        Parse JSON response with tolerant content-type handling.
        
        Returns None on parse failure (caller should log diagnostics).
        """
        try:
            # Use content_type=None to skip content-type validation
            # (some servers return text/html for JSON, or have charset issues)
            return await response.json(content_type=None)
        except (json.JSONDecodeError, aiohttp.ContentTypeError) as e:
            # Try fallback: read as text and parse manually
            try:
                text = await response.text()
                return json.loads(text)
            except Exception:
                return None
    
    async def _get_body_snippet(self, response: aiohttp.ClientResponse, max_len: int = 300) -> str:
        """Get first N chars of response body for diagnostic logging."""
        try:
            text = await response.text()
            if len(text) > max_len:
                return text[:max_len] + "..."
            return text
        except Exception:
            return "(could not read body)"

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        user_id: Optional[int] = None,
    ) -> MCPToolResult:
        """
        Call a tool on the MCP server with retry logic.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        start_time = datetime.now(timezone.utc)
        retry_count = 0

        for attempt in range(self.config.max_retries + 1):
            try:
                session = await self._get_session()
                url = f"{self.config.url}/mcp/tools/call"

                payload = {
                    "name": tool_name,
                    "arguments": arguments,
                }

                headers = self._build_auth_headers(user_id)

                async with session.post(url, json=payload, headers=headers) as response:
                    elapsed_ms = (
                        datetime.now(timezone.utc) - start_time
                    ).total_seconds() * 1000

                    if response.status == 200:
                        data = await response.json()

                        # Gateway MCP format: {"content": [...], "isError": bool}
                        if "isError" in data:
                            if data.get("isError", False):
                                # MCP semantic error: HTTP transport succeeded but tool reported error.
                                # Task A2: Mark as semantic error - agent handles recovery, no transport retry
                                # Task C2: Parse structured error envelope for precise classification
                                error_text = self._extract_error_text(data)
                                error_envelope = self._parse_error_envelope(data, error_text)
                                
                                return MCPToolResult(
                                    success=False,
                                    error=error_text,
                                    execution_time_ms=elapsed_ms,
                                    retry_count=retry_count,
                                    http_status=None,  # Let classifier parse error text
                                    error_category=error_envelope["error_category"],
                                    is_semantic_error=True,  # A2: Agent handles recovery
                                    upstream_status=error_envelope["upstream_status"],
                                    terminal_hint=error_envelope["terminal_hint"],
                                    error_metadata=error_envelope["error_metadata"],
                                )

                            parsed_result = self._extract_success_result(data)
                            return MCPToolResult(
                                success=True,
                                result=parsed_result,
                                execution_time_ms=elapsed_ms,
                                retry_count=retry_count,
                                http_status=200,
                            )

                        logger.info(
                            f"Tool call succeeded: {self.config.name}.{tool_name}",
                            extra={
                                "server": self.config.name,
                                "tool": tool_name,
                                "elapsed_ms": elapsed_ms,
                                "retry_count": retry_count,
                            },
                        )

                        return MCPToolResult(
                            success=True,
                            result=data.get("result"),
                            execution_time_ms=elapsed_ms,
                            retry_count=retry_count,
                            http_status=200,
                        )

                    elif response.status == 404:
                        # Task A2: Tool not found is a semantic error - don't retry at transport level
                        error_msg = f"Tool not found: {tool_name}"
                        logger.error(
                            f"Tool not found: {self.config.name}.{tool_name}",
                            extra={"server": self.config.name, "tool": tool_name},
                        )
                        return MCPToolResult(
                            success=False,
                            error=error_msg,
                            execution_time_ms=elapsed_ms,
                            retry_count=retry_count,
                            http_status=404,
                            is_semantic_error=True,  # A2: Agent handles not-found recovery
                        )

                    elif response.status in (401, 403):
                        # Task A2: Auth errors are semantic - agent handles recovery
                        error_text = await response.text()
                        logger.error(
                            f"Auth error calling {self.config.name}.{tool_name}: HTTP {response.status}",
                            extra={
                                "server": self.config.name,
                                "tool": tool_name,
                                "status": response.status,
                            },
                        )
                        return MCPToolResult(
                            success=False,
                            error=f"Auth error: HTTP {response.status} - {error_text[:200]}",
                            execution_time_ms=elapsed_ms,
                            retry_count=retry_count,
                            http_status=response.status,
                            is_semantic_error=True,  # A2: Agent handles auth recovery
                        )

                    elif response.status in (400, 422):
                        # Task A2: Validation errors are semantic - agent handles recovery
                        error_text = await response.text()
                        logger.warning(
                            f"Validation error calling {self.config.name}.{tool_name}: HTTP {response.status}",
                            extra={
                                "server": self.config.name,
                                "tool": tool_name,
                                "status": response.status,
                            },
                        )
                        return MCPToolResult(
                            success=False,
                            error=f"Validation error: {error_text[:500]}",
                            execution_time_ms=elapsed_ms,
                            retry_count=retry_count,
                            http_status=response.status,
                            is_semantic_error=True,  # A2: Agent handles validation recovery
                        )

                    else:
                        # Server error (5xx) - transport retry if attempts remaining
                        error_text = await response.text()
                        logger.warning(
                            f"Tool call failed (attempt {attempt + 1}): {self.config.name}.{tool_name} - HTTP {response.status}",
                            extra={
                                "server": self.config.name,
                                "tool": tool_name,
                                "status": response.status,
                                "attempt": attempt + 1,
                            },
                        )

                        if attempt < self.config.max_retries:
                            retry_count += 1
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                            continue

                        # Task A2: Transport retries exhausted - agent should NOT retry this
                        return MCPToolResult(
                            success=False,
                            error=f"Server error: HTTP {response.status}",
                            execution_time_ms=elapsed_ms,
                            retry_count=retry_count,
                            http_status=response.status,
                            transport_retries_exhausted=True,  # A2: Don't retry at agent level
                        )

            except asyncio.TimeoutError:
                logger.warning(
                    f"Timeout calling {self.config.name}.{tool_name} (attempt {attempt + 1})",
                    extra={
                        "server": self.config.name,
                        "tool": tool_name,
                        "attempt": attempt + 1,
                    },
                )

                if attempt < self.config.max_retries:
                    retry_count += 1
                    await asyncio.sleep(2 ** attempt)
                    continue

                elapsed_ms = (
                    datetime.now(timezone.utc) - start_time
                ).total_seconds() * 1000

                # Task A2: Transport retries exhausted - agent should NOT retry
                return MCPToolResult(
                    success=False,
                    error=f"Timeout after {self.config.timeout_seconds}s",
                    execution_time_ms=elapsed_ms,
                    retry_count=retry_count,
                    transport_retries_exhausted=True,  # A2: Don't retry at agent level
                )

            except Exception as e:
                logger.error(
                    f"Error calling {self.config.name}.{tool_name} (attempt {attempt + 1}): {e}",
                    extra={
                        "server": self.config.name,
                        "tool": tool_name,
                        "error": str(e),
                        "attempt": attempt + 1,
                    },
                )

                if attempt < self.config.max_retries:
                    retry_count += 1
                    await asyncio.sleep(2 ** attempt)
                    continue

                elapsed_ms = (
                    datetime.now(timezone.utc) - start_time
                ).total_seconds() * 1000

                # Task A2: Transport retries exhausted - agent should NOT retry
                return MCPToolResult(
                    success=False,
                    error=f"Connection error: {str(e)}",
                    execution_time_ms=elapsed_ms,
                    retry_count=retry_count,
                    transport_retries_exhausted=True,  # A2: Don't retry at agent level
                )

        # Should never reach here, but mark as exhausted if it does
        elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        return MCPToolResult(
            success=False,
            error="Max retries exceeded",
            execution_time_ms=elapsed_ms,
            retry_count=retry_count,
            transport_retries_exhausted=True,  # A2: Don't retry at agent level
        )

    def _build_auth_headers(self, user_id: Optional[int]) -> Dict[str, str]:
        """
        Build auth headers for Gateway MCP calls.

        Gateway enforces service-token auth + X-User-Id.
        Other MCP servers may not require these headers.
        """
        headers: Dict[str, str] = {}

        if self.config.name != "gateway-mcp":
            return headers

        token = os.environ.get("GATEWAY_SERVICE_TOKEN", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if user_id is not None:
            headers["X-User-Id"] = str(user_id)

        return headers

    def _extract_error_text(self, data: Dict[str, Any]) -> str:
        """Extract error text from MCP content blocks."""
        content = data.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text")
                    if isinstance(text, str) and text.strip():
                        return text
        return "Tool execution failed"
    
    def _parse_error_envelope(self, data: Dict[str, Any], error_text: str) -> Dict[str, Any]:
        """
        Parse MCP error response into structured error envelope.
        
        Task C2: Extract all available structured fields for precise classification.
        
        Returns:
            Dict with keys:
            - error_category: Machine-readable category
            - upstream_status: HTTP status from upstream service (if present)
            - terminal_hint: True if definitively terminal
            - error_metadata: Additional context
        """
        result = {
            "error_category": None,
            "upstream_status": None,
            "terminal_hint": False,
            "error_metadata": {},
        }
        
        # Check for structured error fields in the MCP response
        # Some gateways provide these directly
        if "error_category" in data:
            result["error_category"] = data["error_category"]
        if "upstream_status" in data:
            result["upstream_status"] = data["upstream_status"]
        if "terminal" in data:
            result["terminal_hint"] = bool(data["terminal"])
        
        # Check content blocks for structured error info
        content = data.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    # Check for structured error block
                    if block.get("type") == "error":
                        if "category" in block:
                            result["error_category"] = block["category"]
                        if "upstream_status" in block:
                            result["upstream_status"] = block["upstream_status"]
                        if "terminal" in block:
                            result["terminal_hint"] = bool(block["terminal"])
                        if "metadata" in block:
                            result["error_metadata"].update(block["metadata"])
        
        # If no structured category found, classify from error text
        if not result["error_category"]:
            result["error_category"] = self._classify_error_category(error_text)
        
        # If still no category but have upstream_status, derive terminal hint
        if result["upstream_status"] in {401, 403, 404, 422}:
            result["terminal_hint"] = True
        
        # Set terminal hint for known terminal categories
        terminal_categories = {
            "auth_failure", "permission_denied", "rbac_denied",
            "tool_not_found", "catalog_miss", "validation_error",
        }
        if result["error_category"] in terminal_categories:
            result["terminal_hint"] = True
        
        return result
    
    def _classify_error_category(self, error_text: str) -> Optional[str]:
        """
        Classify error into machine-readable category.
        
        Returns a category string for use by error handlers,
        avoiding brittle substring matching in downstream code.
        """
        if not error_text:
            return None
        
        msg_lower = error_text.lower()
        
        # Container/Docker errors
        if any(p in msg_lower for p in [
            "no such container",
            "container not running",
            "container unavailable",
            "oci runtime exec failed",
        ]):
            return "container_unavailable"
        
        if "docker daemon" in msg_lower or "cannot connect to docker" in msg_lower:
            return "docker_unavailable"
        
        # Connection errors
        if "connection refused" in msg_lower:
            return "connection_refused"
        
        # Upstream UNAVAILABLE (infrastructure issue) - terminal
        if "upstream" in msg_lower and "unavailable" in msg_lower:
            return "upstream_unavailable"
        
        # Upstream returned an error response (data/query issue) - retryable
        # e.g., "Upstream service 'teesheet-db' error: SQL query failed: Unknown database"
        # This is NOT infrastructure unavailable - the service responded, just with an error
        if "upstream" in msg_lower and "error" in msg_lower:
            return "upstream_error"
        
        # Auth errors
        if any(p in msg_lower for p in ["401", "unauthorized", "invalid token", "expired token"]):
            return "auth_failure"
        
        if any(p in msg_lower for p in ["403", "forbidden", "permission denied"]):
            return "permission_denied"
        
        # Validation
        if any(p in msg_lower for p in ["validation", "invalid", "400", "422"]):
            return "validation_error"
        
        # Rate limiting
        if any(p in msg_lower for p in ["rate limit", "429", "throttl"]):
            return "rate_limited"
        
        # Timeout
        if any(p in msg_lower for p in ["timeout", "timed out"]):
            return "timeout"
        
        return None

    def _extract_success_result(self, data: Dict[str, Any]) -> Any:
        """
        Extract successful tool result from MCP content blocks.

        If text block contains JSON, parse it into structured output.
        Otherwise return raw text.
        """
        content = data.get("content", [])
        if not isinstance(content, list):
            return None

        for block in content:
            if not isinstance(block, dict) or block.get("type") != "text":
                continue
            text = block.get("text")
            if not isinstance(text, str):
                continue

            stripped = text.strip()
            if not stripped:
                return None

            try:
                return json.loads(stripped)
            except Exception:
                return stripped

        return None

    def _is_cache_valid(self) -> bool:
        """Check if tools cache is still valid."""
        if self._tools_cache is None or self._cache_timestamp is None:
            return False

        elapsed = (datetime.now(timezone.utc) - self._cache_timestamp).total_seconds()
        return elapsed < self._cache_ttl_seconds
