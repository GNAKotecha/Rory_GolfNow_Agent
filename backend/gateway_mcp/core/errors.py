"""
Gateway MCP Error Hierarchy

All rejections or failures return a structured GatewayError with:
- code: bounded set of error codes
- message: human-safe message (never includes stdout/stderr/tokens)
- audit_id: correlation to audit record
- retryable: whether client should retry
- reconnect_url: optional URL for credential-related errors
"""

from enum import Enum
from typing import Optional


class ErrorCode(str, Enum):
    """Bounded set of Gateway error codes."""
    
    # Auth & permissions
    PERMISSION_DENIED = "permission_denied"
    ENV_RESTRICTED = "env_restricted"
    
    # Validation
    VALIDATION_FAILED = "validation_failed"
    TOOL_NOT_FOUND = "tool_not_found"
    
    # Execution
    CONTAINER_UNAVAILABLE = "container_unavailable"
    UPSTREAM_ERROR = "upstream_error"
    SUBPROCESS_TIMEOUT = "subprocess_timeout"
    
    # Approval
    APPROVAL_REQUIRED = "approval_required"
    
    # Credentials
    INSUFFICIENT_SCOPE = "insufficient_scope"
    CREDENTIAL_MISSING = "credential_missing"
    TOKEN_REFRESH_FAILED = "token_refresh_failed"
    
    # Internal
    INTERNAL_ERROR = "internal_error"


# HTTP status codes for each error code
ERROR_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.PERMISSION_DENIED: 403,
    ErrorCode.ENV_RESTRICTED: 403,
    ErrorCode.VALIDATION_FAILED: 400,
    ErrorCode.TOOL_NOT_FOUND: 404,
    ErrorCode.CONTAINER_UNAVAILABLE: 503,
    ErrorCode.UPSTREAM_ERROR: 502,
    ErrorCode.SUBPROCESS_TIMEOUT: 504,
    ErrorCode.APPROVAL_REQUIRED: 202,  # Accepted, pending approval
    ErrorCode.INSUFFICIENT_SCOPE: 403,
    ErrorCode.CREDENTIAL_MISSING: 401,
    ErrorCode.TOKEN_REFRESH_FAILED: 401,
    ErrorCode.INTERNAL_ERROR: 500,
}

# Retryable error codes (only for read operations)
RETRYABLE_CODES = {ErrorCode.UPSTREAM_ERROR}


class GatewayError(Exception):
    """
    Base exception for all Gateway MCP errors.
    
    Serializes to structured JSON response:
    {
        "error": {
            "code": "...",
            "message": "...",
            "audit_id": "...",
            "retryable": false,
            "reconnect_url": "..."
        }
    }
    """
    
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        audit_id: Optional[str] = None,
        retryable: Optional[bool] = None,
        reconnect_url: Optional[str] = None,
    ):
        self.code = code.value if isinstance(code, ErrorCode) else code
        self.message = message
        self.audit_id = audit_id
        self.retryable = retryable if retryable is not None else (code in RETRYABLE_CODES)
        self.reconnect_url = reconnect_url
        super().__init__(message)
    
    @property
    def http_status(self) -> int:
        """HTTP status code for this error."""
        code_enum = ErrorCode(self.code) if isinstance(self.code, str) else self.code
        return ERROR_HTTP_STATUS.get(code_enum, 500)
    
    def to_dict(self) -> dict:
        """Serialize to dict for JSON response."""
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "audit_id": self.audit_id,
                "retryable": self.retryable,
                "reconnect_url": self.reconnect_url,
            }
        }


# Convenience subclasses for common errors

class PermissionDeniedError(GatewayError):
    """Caller lacks permission for this operation."""
    
    def __init__(self, message: str = "Permission denied", **kwargs):
        super().__init__(ErrorCode.PERMISSION_DENIED, message, **kwargs)


class EnvRestrictedError(GatewayError):
    """Tool not allowed in this environment."""
    
    def __init__(self, tool: str, env: str, allowed: list[str], **kwargs):
        message = f"Tool '{tool}' not allowed in '{env}' environment (allowed: {', '.join(allowed)})"
        super().__init__(ErrorCode.ENV_RESTRICTED, message, **kwargs)


class ValidationError(GatewayError):
    """Input validation failed."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(ErrorCode.VALIDATION_FAILED, message, **kwargs)


class ContainerUnavailableError(GatewayError):
    """Container or service not reachable."""
    
    def __init__(self, service: str, **kwargs):
        message = f"Service '{service}' is unavailable"
        super().__init__(ErrorCode.CONTAINER_UNAVAILABLE, message, **kwargs)


class UpstreamError(GatewayError):
    """Upstream service returned an error."""
    
    def __init__(self, service: str, detail: str = "", **kwargs):
        message = f"Upstream service '{service}' error"
        if detail:
            message = f"{message}: {detail}"
        super().__init__(ErrorCode.UPSTREAM_ERROR, message, **kwargs)


class SubprocessTimeoutError(GatewayError):
    """Command execution timed out."""
    
    def __init__(self, timeout_seconds: int, **kwargs):
        message = f"Command timed out after {timeout_seconds}s"
        super().__init__(ErrorCode.SUBPROCESS_TIMEOUT, message, retryable=False, **kwargs)


class ApprovalRequiredError(GatewayError):
    """Tool requires approval before execution."""
    
    def __init__(self, tool: str, approval_request_id: str, **kwargs):
        message = f"Tool '{tool}' requires approval (request_id: {approval_request_id})"
        super().__init__(ErrorCode.APPROVAL_REQUIRED, message, retryable=False, **kwargs)


class InsufficientScopeError(GatewayError):
    """User's credential lacks required scopes."""
    
    def __init__(
        self,
        provider: str,
        required_scopes: list[str],
        reconnect_url: str,
        **kwargs,
    ):
        message = f"Insufficient scopes for {provider}. Required: {', '.join(required_scopes)}"
        super().__init__(
            ErrorCode.INSUFFICIENT_SCOPE,
            message,
            reconnect_url=reconnect_url,
            **kwargs,
        )


class CredentialMissingError(GatewayError):
    """User has not connected the required provider."""
    
    def __init__(self, provider: str, reconnect_url: str, **kwargs):
        self.provider = provider  # Store provider for debugging/testing
        message = f"No credential found for {provider}. Please connect your account."
        super().__init__(
            ErrorCode.CREDENTIAL_MISSING,
            message,
            reconnect_url=reconnect_url,
            **kwargs,
        )


class TokenRefreshFailedError(GatewayError):
    """OAuth token refresh failed."""
    
    def __init__(self, provider: str, reconnect_url: str, **kwargs):
        message = f"Token refresh failed for {provider}. Please reconnect your account."
        super().__init__(
            ErrorCode.TOKEN_REFRESH_FAILED,
            message,
            reconnect_url=reconnect_url,
            **kwargs,
        )


class InternalError(GatewayError):
    """Internal server error."""
    
    def __init__(self, message: str = "Internal error", **kwargs):
        super().__init__(ErrorCode.INTERNAL_ERROR, message, **kwargs)


class ToolExecutionError(GatewayError):
    """Tool execution failed due to parsing or processing error."""
    
    def __init__(self, tool_name: str, message: str, **kwargs):
        full_message = f"Tool '{tool_name}' execution failed: {message}"
        super().__init__(ErrorCode.INTERNAL_ERROR, full_message, **kwargs)


class ToolNotFoundError(GatewayError):
    """Requested tool does not exist in the registry."""
    
    def __init__(self, tool_name: str, **kwargs):
        message = f"Tool '{tool_name}' not found"
        super().__init__(ErrorCode.TOOL_NOT_FOUND, message, **kwargs)
