"""
Permission Checks

Validates that the caller has permission to invoke a tool based on:
1. Risk level of the tool (read, low_write, medium_write, high_write)
2. Current environment (local, dev, qa, prod)
3. Caller's role (from auth scopes)

Risk Level Policy:
- read: any authenticated caller
- low_write: requires operator or admin scope
- medium_write: requires operator or admin scope (approval in staging/prod - future)
- high_write: requires explicit approval + admin scope
"""

from typing import Optional

from gateway_mcp.core.auth import AuthResult
from gateway_mcp.core.errors import EnvRestrictedError, PermissionDeniedError
from gateway_mcp.tools.base import Environment, RiskLevel, Tool


class PermissionService:
    """
    Permission gate for tool invocations.
    
    Checks that the tool is allowed in the current environment
    and the caller has sufficient role/scope.
    """
    
    def __init__(self, current_env: Environment):
        """
        Initialize permission service.
        
        Args:
            current_env: Current deployment environment
        """
        self.current_env = current_env
    
    def check_permission(
        self,
        tool: Tool,
        auth: AuthResult,
        audit_id: Optional[str] = None,
    ) -> None:
        """
        Check if caller has permission to invoke tool.
        
        Args:
            tool: Tool being invoked
            auth: Authentication result with scopes
            audit_id: Correlation ID for error responses
            
        Raises:
            EnvRestrictedError: Tool not allowed in current environment
            PermissionDeniedError: Caller lacks required role
        """
        # Check environment restriction
        self._check_env(tool, audit_id)
        
        # Check role/scope requirement based on risk level
        self._check_role(tool, auth, audit_id)
    
    def _check_env(self, tool: Tool, audit_id: Optional[str]) -> None:
        """Check if tool is allowed in current environment."""
        if self.current_env not in tool.allowed_environments:
            allowed = [env.value for env in tool.allowed_environments]
            raise EnvRestrictedError(
                tool=tool.name,
                env=self.current_env.value,
                allowed=allowed,
                audit_id=audit_id,
            )
    
    def _check_role(
        self,
        tool: Tool,
        auth: AuthResult,
        audit_id: Optional[str],
    ) -> None:
        """Check if caller has required role for tool's risk level."""
        risk = tool.risk_level
        
        if risk == RiskLevel.READ:
            # Any authenticated caller can invoke read tools
            return
        
        if risk == RiskLevel.LOW_WRITE:
            # Requires operator or admin
            if not auth.is_operator:
                raise PermissionDeniedError(
                    message=f"Tool '{tool.name}' requires operator role",
                    audit_id=audit_id,
                )
            return
        
        if risk == RiskLevel.MEDIUM_WRITE:
            # Requires operator or admin
            # Future: may also require approval in staging/prod
            if not auth.is_operator:
                raise PermissionDeniedError(
                    message=f"Tool '{tool.name}' requires operator role",
                    audit_id=audit_id,
                )
            return
        
        if risk == RiskLevel.HIGH_WRITE:
            # Requires admin + explicit approval (checked separately)
            if not auth.is_admin:
                raise PermissionDeniedError(
                    message=f"Tool '{tool.name}' requires admin role",
                    audit_id=audit_id,
                )
            return
        
        # Unknown risk level - deny by default
        raise PermissionDeniedError(
            message=f"Unknown risk level for tool '{tool.name}'",
            audit_id=audit_id,
        )
    
    def requires_approval(self, tool: Tool, auth: AuthResult) -> bool:
        """
        Check if tool invocation requires explicit approval.
        
        Returns:
            True if approval gate should be triggered
        """
        import os
        # YOLO_MODE bypasses all approval requirements
        yolo_mode = os.environ.get("YOLO_MODE", "").lower() in ("1", "true", "yes")
        if yolo_mode:
            return False
        
        # Tool-level flag
        if tool.requires_approval:
            return True
        
        # High-risk tools always need approval
        if tool.risk_level == RiskLevel.HIGH_WRITE:
            return True
        
        # Future: medium_write in prod could require approval
        # if tool.risk_level == RiskLevel.MEDIUM_WRITE and self.current_env == Environment.PROD:
        #     return True
        
        return False


def create_permission_service_from_settings(settings) -> PermissionService:
    """
    Factory to create PermissionService from gateway settings.
    
    Args:
        settings: Gateway settings object with env field
        
    Returns:
        Configured PermissionService
    """
    env_str = getattr(settings, "env", "local")
    try:
        current_env = Environment(env_str)
    except ValueError:
        current_env = Environment.LOCAL
    
    return PermissionService(current_env=current_env)
