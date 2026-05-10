"""
Middleware Pipeline

Assembles the complete request processing pipeline for tool invocations:

1. Start audit record
2. Authenticate request (service token + X-User-Id)
3. Validate input against tool schema
4. Check environment restrictions
5. Check permission (risk level vs role)
6. Check OAuth scopes (for external tools)
7. Check approval requirement
8. Execute tool handler
9. Finish audit record

Each stage can reject the request with an appropriate error.
All requests are audited regardless of outcome.
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

from pydantic import BaseModel, ValidationError as PydanticValidationError

from gateway_mcp.core.approval import ApprovalBridge
from gateway_mcp.core.audit import AuditLogger, AuditOutcome
from gateway_mcp.core.auth import AuthError, AuthResult, AuthService
from gateway_mcp.core.errors import (
    GatewayError,
    InternalError,
    SubprocessTimeoutError,
    ValidationError,
)
from gateway_mcp.core.permissions import PermissionService
from gateway_mcp.core.scopes import ScopeService
from gateway_mcp.tools.base import Environment, Tool, ToolContext


@dataclass
class MiddlewareRequest:
    """
    Incoming request to the middleware pipeline.
    
    Captures all request headers and body needed for processing.
    """
    
    tool_name: str
    input_data: dict
    authorization_header: Optional[str] = None
    user_id_header: Optional[str] = None
    correlation_id: Optional[str] = None
    workflow_run_id: Optional[int] = None  # If part of a workflow


@dataclass
class MiddlewareResponse:
    """
    Response from the middleware pipeline.
    
    Contains either successful output or error information.
    """
    
    success: bool
    output_data: Optional[dict] = None
    error: Optional[GatewayError] = None
    audit_id: Optional[str] = None


class MiddlewarePipeline:
    """
    Complete middleware pipeline for Gateway MCP.
    
    Orchestrates all middleware stages in order:
    audit → auth → validate → env → permission → scope → approval → execute → audit
    
    Each tool invocation passes through all stages. Early stages can
    reject requests, but audit is always recorded.
    """
    
    def __init__(
        self,
        auth_service: AuthService,
        permission_service: PermissionService,
        scope_service: ScopeService,
        approval_bridge: ApprovalBridge,
        audit_logger: AuditLogger,
        executor_factory=None,
        credential_fetcher=None,
    ):
        """
        Initialize middleware pipeline with all services.
        
        Args:
            auth_service: Service token validator
            permission_service: Role and env checker
            scope_service: OAuth scope validator
            approval_bridge: Approval gate handler
            audit_logger: Structured audit logger
            executor_factory: Factory for executor backends
            credential_fetcher: Async function to fetch OAuth tokens
        """
        self._auth = auth_service
        self._permissions = permission_service
        self._scopes = scope_service
        self._approval = approval_bridge
        self._audit = audit_logger
        self._executor_factory = executor_factory
        self._credential_fetcher = credential_fetcher
    
    async def process(
        self,
        tool: Tool,
        request: MiddlewareRequest,
    ) -> MiddlewareResponse:
        """
        Process a tool invocation through the middleware pipeline.
        
        Args:
            tool: Tool being invoked
            request: Incoming request with headers and input
            
        Returns:
            MiddlewareResponse with output or error
        """
        # Stage 1: Start audit
        audit_record = self._audit.start_audit(
            tool_name=tool.name,
            user_id=0,  # Updated after auth
            input_data=request.input_data,
            correlation_id=request.correlation_id,
        )
        
        try:
            # Stage 2: Authenticate
            auth = self._authenticate(request, audit_record.audit_id)
            audit_record.user_id = auth.user_id
            
            # Stage 3: Validate input schema
            validated_input = self._validate_input(tool, request.input_data, audit_record.audit_id)
            
            # Stage 4 & 5: Check env + permission
            self._permissions.check_permission(tool, auth, audit_record.audit_id)
            
            # Stage 6: Check OAuth scopes (external tools)
            self._scopes.check_scopes(tool, auth.user_id, audit_record.audit_id)
            
            # Stage 7: Check approval requirement
            if self._permissions.requires_approval(tool, auth):
                self._approval.require_approval(
                    tool=tool,
                    user_id=auth.user_id,
                    input_data=request.input_data,
                    audit_id=audit_record.audit_id,
                    workflow_run_id=request.workflow_run_id,
                )
            
            # Stage 8: Execute tool handler
            output = await self._execute_tool(
                tool=tool,
                validated_input=validated_input,
                auth=auth,
                audit_record=audit_record,
            )
            
            # Stage 9: Finish audit (success)
            output_dict = output.model_dump() if isinstance(output, BaseModel) else output
            self._audit.finish_audit(
                record=audit_record,
                outcome=AuditOutcome.SUCCESS,
                output_data=output_dict,
            )
            
            return MiddlewareResponse(
                success=True,
                output_data=output_dict,
                audit_id=audit_record.audit_id,
            )
            
        except GatewayError as e:
            # Known error - map to audit outcome
            outcome = self._map_error_to_outcome(e)
            self._audit.finish_audit(
                record=audit_record,
                outcome=outcome,
                error_code=e.code,
                error_message=e.message,
            )
            
            # Attach audit_id to error if not set
            if e.audit_id is None:
                e.audit_id = audit_record.audit_id
            
            return MiddlewareResponse(
                success=False,
                error=e,
                audit_id=audit_record.audit_id,
            )
            
        except Exception as e:
            # Unexpected error - wrap in InternalError
            self._audit.finish_audit(
                record=audit_record,
                outcome=AuditOutcome.INTERNAL_ERROR,
                error_code="internal_error",
                error_message=str(e),
            )
            
            internal_error = InternalError(
                message="Internal error during tool execution",
                audit_id=audit_record.audit_id,
            )
            
            return MiddlewareResponse(
                success=False,
                error=internal_error,
                audit_id=audit_record.audit_id,
            )
    
    def _authenticate(
        self,
        request: MiddlewareRequest,
        audit_id: str,
    ) -> AuthResult:
        """Stage 2: Authenticate request."""
        try:
            return self._auth.authenticate(
                authorization_header=request.authorization_header,
                user_id_header=request.user_id_header,
            )
        except AuthError as e:
            from gateway_mcp.core.errors import PermissionDeniedError
            raise PermissionDeniedError(
                message=e.message,
                audit_id=audit_id,
            )
    
    def _validate_input(
        self,
        tool: Tool,
        input_data: dict,
        audit_id: str,
    ) -> BaseModel:
        """Stage 3: Validate input against tool schema."""
        try:
            return tool.input_schema(**input_data)
        except PydanticValidationError as e:
            # Extract first error message
            errors = e.errors()
            if errors:
                first = errors[0]
                loc = ".".join(str(l) for l in first.get("loc", []))
                msg = first.get("msg", "validation error")
                raise ValidationError(
                    message=f"Invalid input at '{loc}': {msg}",
                    audit_id=audit_id,
                )
            raise ValidationError(
                message="Input validation failed",
                audit_id=audit_id,
            )
    
    async def _execute_tool(
        self,
        tool: Tool,
        validated_input: BaseModel,
        auth: AuthResult,
        audit_record,
    ) -> BaseModel:
        """Stage 8: Execute tool handler."""
        if tool.handler is None:
            raise InternalError(
                message=f"Tool '{tool.name}' has no handler",
                audit_id=audit_record.audit_id,
            )
        
        # Build tool context
        context = ToolContext(
            user_id=auth.user_id,
            correlation_id=audit_record.correlation_id,
            audit_id=audit_record.audit_id,
            environment=self._permissions.current_env,
            _executor=self._executor_factory() if self._executor_factory else None,
            _credential_fetcher=self._credential_fetcher,
        )
        
        # Execute with timeout
        try:
            result = await asyncio.wait_for(
                tool.handler(validated_input, context),
                timeout=tool.timeout_seconds,
            )
            return result
        except asyncio.TimeoutError:
            raise SubprocessTimeoutError(
                timeout_seconds=tool.timeout_seconds,
                audit_id=audit_record.audit_id,
            )
    
    def _map_error_to_outcome(self, error: GatewayError) -> AuditOutcome:
        """Map GatewayError to AuditOutcome for logging."""
        from gateway_mcp.core.errors import ErrorCode
        
        code = error.code
        
        if code == ErrorCode.PERMISSION_DENIED.value:
            return AuditOutcome.PERMISSION_DENIED
        if code == ErrorCode.ENV_RESTRICTED.value:
            return AuditOutcome.ENV_RESTRICTED
        if code == ErrorCode.VALIDATION_FAILED.value:
            return AuditOutcome.VALIDATION_ERROR
        if code == ErrorCode.APPROVAL_REQUIRED.value:
            return AuditOutcome.APPROVAL_REQUIRED
        if code == ErrorCode.SUBPROCESS_TIMEOUT.value:
            return AuditOutcome.TIMEOUT
        if code in (
            ErrorCode.INSUFFICIENT_SCOPE.value,
            ErrorCode.CREDENTIAL_MISSING.value,
            ErrorCode.TOKEN_REFRESH_FAILED.value,
        ):
            return AuditOutcome.SCOPE_ERROR
        if code in (
            ErrorCode.CONTAINER_UNAVAILABLE.value,
            ErrorCode.UPSTREAM_ERROR.value,
        ):
            return AuditOutcome.EXECUTION_ERROR
        
        return AuditOutcome.INTERNAL_ERROR


def create_middleware_pipeline(
    settings,
    db_session=None,
    executor_factory=None,
    credential_fetcher=None,
) -> MiddlewarePipeline:
    """
    Factory to create MiddlewarePipeline from gateway settings.
    
    Args:
        settings: Gateway settings object
        db_session: Optional database session for ApprovalService
        executor_factory: Optional factory for executor backends
        credential_fetcher: Optional async function for OAuth tokens
        
    Returns:
        Configured MiddlewarePipeline
    """
    from gateway_mcp.core.approval import create_approval_bridge_from_settings
    from gateway_mcp.core.audit import create_audit_logger_from_settings
    from gateway_mcp.core.auth import create_auth_service_from_settings
    from gateway_mcp.core.permissions import create_permission_service_from_settings
    from gateway_mcp.core.scopes import create_scope_service_from_settings
    
    return MiddlewarePipeline(
        auth_service=create_auth_service_from_settings(settings),
        permission_service=create_permission_service_from_settings(settings),
        scope_service=create_scope_service_from_settings(settings),
        approval_bridge=create_approval_bridge_from_settings(settings, db_session),
        audit_logger=create_audit_logger_from_settings(settings),
        executor_factory=executor_factory,
        credential_fetcher=credential_fetcher,
    )
