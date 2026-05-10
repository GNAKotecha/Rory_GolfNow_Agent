"""
Integration tests for the complete middleware pipeline.

Tests the end-to-end flow through all middleware stages:
- Authentication
- Input validation  
- Environment checks
- Permission checks
- Scope checks
- Approval gates
- Tool execution
- Audit logging

Verifies that middleware stages execute in correct order
and audit records capture the full request lifecycle.
"""

import pytest
from pydantic import BaseModel

from gateway_mcp.core.approval import ApprovalBridge
from gateway_mcp.core.audit import AuditLogger, AuditOutcome
from gateway_mcp.core.auth import AuthService
from gateway_mcp.core.errors import (
    ApprovalRequiredError,
    EnvRestrictedError,
    PermissionDeniedError,
    ValidationError,
)
from gateway_mcp.core.middleware import MiddlewarePipeline, MiddlewareRequest
from gateway_mcp.core.permissions import PermissionService
from gateway_mcp.core.scopes import ScopeService
from gateway_mcp.tools.base import Environment, RiskLevel, Tool, ToolContext


# --------------------
# Test schemas
# --------------------


class CreateClubInput(BaseModel):
    """Input schema for create_club tool."""
    club_name: str
    country: str = "IE"
    timezone: str = "Europe/Dublin"


class CreateClubOutput(BaseModel):
    """Output schema for create_club tool."""
    club_id: str
    status: str


# --------------------
# Test handlers
# --------------------


async def mock_create_club_handler(
    input_data: CreateClubInput,
    context: ToolContext,
) -> CreateClubOutput:
    """Mock handler that returns success."""
    return CreateClubOutput(
        club_id=f"club-{input_data.club_name.lower().replace(' ', '-')}",
        status="created",
    )


async def mock_failing_handler(
    input_data: CreateClubInput,
    context: ToolContext,
) -> CreateClubOutput:
    """Mock handler that raises an error."""
    raise RuntimeError("Simulated handler error")


# --------------------
# Fixtures
# --------------------


@pytest.fixture
def service_tokens():
    """Test service tokens."""
    return {
        "operator-token": ["operator"],
        "admin-token": ["admin"],
        "readonly-token": [],
    }


@pytest.fixture
def auth_service(service_tokens):
    """Auth service with test tokens."""
    return AuthService(
        service_tokens=service_tokens,
        require_user_id=True,
    )


@pytest.fixture
def permission_service():
    """Permission service for local environment."""
    return PermissionService(current_env=Environment.LOCAL)


@pytest.fixture
def scope_service():
    """Scope service without credential store."""
    return ScopeService()


@pytest.fixture
def approval_bridge():
    """Approval bridge without DB."""
    return ApprovalBridge()


@pytest.fixture
def audit_logger():
    """Audit logger for local environment."""
    return AuditLogger(environment="local")


@pytest.fixture
def pipeline(
    auth_service,
    permission_service,
    scope_service,
    approval_bridge,
    audit_logger,
):
    """Complete middleware pipeline."""
    return MiddlewarePipeline(
        auth_service=auth_service,
        permission_service=permission_service,
        scope_service=scope_service,
        approval_bridge=approval_bridge,
        audit_logger=audit_logger,
    )


@pytest.fixture
def create_club_tool():
    """Create club tool (low write, local only)."""
    return Tool(
        name="create_club",
        description="Create a new golf club",
        input_schema=CreateClubInput,
        output_schema=CreateClubOutput,
        risk_level=RiskLevel.LOW_WRITE,
        allowed_environments=[Environment.LOCAL, Environment.DEV],
        handler=mock_create_club_handler,
        timeout_seconds=30,
    )


@pytest.fixture
def read_tool():
    """Read-only tool for all environments."""
    return Tool(
        name="get_club",
        description="Get club details",
        input_schema=CreateClubInput,
        output_schema=CreateClubOutput,
        risk_level=RiskLevel.READ,
        allowed_environments=list(Environment),
        handler=mock_create_club_handler,
    )


@pytest.fixture
def high_risk_tool():
    """High-risk tool requiring approval."""
    return Tool(
        name="delete_club",
        description="Delete a club (dangerous)",
        input_schema=CreateClubInput,
        output_schema=CreateClubOutput,
        risk_level=RiskLevel.HIGH_WRITE,
        allowed_environments=[Environment.LOCAL],
        requires_approval=True,
        handler=mock_create_club_handler,
    )


@pytest.fixture
def failing_tool():
    """Tool with handler that fails."""
    return Tool(
        name="failing_tool",
        description="Tool that fails",
        input_schema=CreateClubInput,
        output_schema=CreateClubOutput,
        risk_level=RiskLevel.READ,
        allowed_environments=list(Environment),
        handler=mock_failing_handler,
    )


# --------------------
# Integration tests
# --------------------


class TestMiddlewarePipelineIntegration:
    """Integration tests for the complete middleware pipeline."""
    
    @pytest.mark.asyncio
    async def test_successful_tool_execution(self, pipeline, create_club_tool):
        """Should execute tool successfully with proper auth."""
        request = MiddlewareRequest(
            tool_name="create_club",
            input_data={"club_name": "Test Golf Club"},
            authorization_header="Bearer operator-token",
            user_id_header="123",
            correlation_id="test-correlation-1",
        )
        
        response = await pipeline.process(create_club_tool, request)
        
        assert response.success is True
        assert response.output_data is not None
        assert response.output_data["club_id"] == "club-test-golf-club"
        assert response.output_data["status"] == "created"
        assert response.audit_id is not None
    
    @pytest.mark.asyncio
    async def test_auth_failure_missing_token(self, pipeline, create_club_tool):
        """Should reject request with missing auth token."""
        request = MiddlewareRequest(
            tool_name="create_club",
            input_data={"club_name": "Test Club"},
            authorization_header=None,
            user_id_header="123",
        )
        
        response = await pipeline.process(create_club_tool, request)
        
        assert response.success is False
        assert response.error is not None
        assert response.error.code == "permission_denied"
        assert response.audit_id is not None
    
    @pytest.mark.asyncio
    async def test_auth_failure_invalid_token(self, pipeline, create_club_tool):
        """Should reject request with invalid token."""
        request = MiddlewareRequest(
            tool_name="create_club",
            input_data={"club_name": "Test Club"},
            authorization_header="Bearer invalid-token",
            user_id_header="123",
        )
        
        response = await pipeline.process(create_club_tool, request)
        
        assert response.success is False
        assert response.error.code == "permission_denied"
    
    @pytest.mark.asyncio
    async def test_validation_failure_missing_field(self, pipeline, create_club_tool):
        """Should reject request with invalid input."""
        request = MiddlewareRequest(
            tool_name="create_club",
            input_data={},  # Missing required club_name
            authorization_header="Bearer operator-token",
            user_id_header="123",
        )
        
        response = await pipeline.process(create_club_tool, request)
        
        assert response.success is False
        assert response.error.code == "validation_failed"
        assert "club_name" in response.error.message
    
    @pytest.mark.asyncio
    async def test_permission_denied_for_readonly_user(self, pipeline, create_club_tool):
        """Should reject write tool for readonly user."""
        request = MiddlewareRequest(
            tool_name="create_club",
            input_data={"club_name": "Test Club"},
            authorization_header="Bearer readonly-token",  # No operator scope
            user_id_header="123",
        )
        
        response = await pipeline.process(create_club_tool, request)
        
        assert response.success is False
        assert response.error.code == "permission_denied"
        assert "operator role" in response.error.message
    
    @pytest.mark.asyncio
    async def test_read_tool_allowed_for_readonly(self, pipeline, read_tool):
        """Should allow read tool for readonly user."""
        request = MiddlewareRequest(
            tool_name="get_club",
            input_data={"club_name": "Test Club"},
            authorization_header="Bearer readonly-token",
            user_id_header="123",
        )
        
        response = await pipeline.process(read_tool, request)
        
        assert response.success is True
    
    @pytest.mark.asyncio
    async def test_approval_required_for_high_risk(self, pipeline, high_risk_tool):
        """Should require approval for high-risk tools."""
        request = MiddlewareRequest(
            tool_name="delete_club",
            input_data={"club_name": "Test Club"},
            authorization_header="Bearer admin-token",  # Admin for high-risk
            user_id_header="123",
        )
        
        response = await pipeline.process(high_risk_tool, request)
        
        assert response.success is False
        assert response.error.code == "approval_required"
        assert "requires approval" in response.error.message
    
    @pytest.mark.asyncio
    async def test_handler_error_captured(self, pipeline, failing_tool):
        """Should capture handler errors in audit."""
        request = MiddlewareRequest(
            tool_name="failing_tool",
            input_data={"club_name": "Test Club"},
            authorization_header="Bearer readonly-token",
            user_id_header="123",
        )
        
        response = await pipeline.process(failing_tool, request)
        
        assert response.success is False
        assert response.error.code == "internal_error"
        assert response.audit_id is not None
    
    @pytest.mark.asyncio
    async def test_audit_records_full_lifecycle(
        self,
        auth_service,
        permission_service,
        scope_service,
        approval_bridge,
        create_club_tool,
    ):
        """Should record full request lifecycle in audit."""
        # Create audit logger we can inspect
        audit_logger = AuditLogger(environment="local")
        captured_records = []
        
        # Patch finish_audit to capture records
        original_finish = audit_logger.finish_audit
        
        def capture_finish(record, **kwargs):
            captured_records.append(record)
            original_finish(record, **kwargs)
        
        audit_logger.finish_audit = capture_finish
        
        pipeline = MiddlewarePipeline(
            auth_service=auth_service,
            permission_service=permission_service,
            scope_service=scope_service,
            approval_bridge=approval_bridge,
            audit_logger=audit_logger,
        )
        
        request = MiddlewareRequest(
            tool_name="create_club",
            input_data={"club_name": "Audit Test Club"},
            authorization_header="Bearer operator-token",
            user_id_header="456",
        )
        
        await pipeline.process(create_club_tool, request)
        
        # Verify audit record
        assert len(captured_records) == 1
        record = captured_records[0]
        
        assert record.tool_name == "create_club"
        assert record.user_id == 456
        assert record.outcome == AuditOutcome.SUCCESS
        assert record.finished_at is not None
        assert record.duration_ms >= 0
        assert record.output_data is not None
    
    @pytest.mark.asyncio
    async def test_middleware_order_verified(self, pipeline, create_club_tool):
        """Should process middleware stages in correct order."""
        # This test verifies the order by checking that:
        # 1. Auth happens before permission check
        # 2. Validation happens before execution
        # 3. All stages have audit_id available
        
        # Test 1: Auth before permission
        # Invalid token should fail at auth, not permission
        request = MiddlewareRequest(
            tool_name="create_club",
            input_data={"club_name": "Test Club"},
            authorization_header="Bearer bad-token",
            user_id_header="123",
        )
        
        response = await pipeline.process(create_club_tool, request)
        
        # Should fail at auth (permission_denied), not later stages
        assert response.error.code == "permission_denied"
        assert "Invalid service token" in response.error.message
        
        # Test 2: Validation before execution
        # Valid auth but invalid input should fail at validation
        request2 = MiddlewareRequest(
            tool_name="create_club",
            input_data={"invalid_field": "value"},  # Missing club_name
            authorization_header="Bearer operator-token",
            user_id_header="123",
        )
        
        response2 = await pipeline.process(create_club_tool, request2)
        
        assert response2.error.code == "validation_failed"


class TestMiddlewareEnvRestrictions:
    """Tests for environment-based restrictions."""
    
    @pytest.mark.asyncio
    async def test_prod_restricted_tool_blocked_in_prod(self):
        """Should block local-only tool in prod environment."""
        # Create pipeline for prod environment
        auth_service = AuthService(
            service_tokens={"token": ["operator"]},
            require_user_id=True,
        )
        permission_service = PermissionService(current_env=Environment.PROD)
        
        pipeline = MiddlewarePipeline(
            auth_service=auth_service,
            permission_service=permission_service,
            scope_service=ScopeService(),
            approval_bridge=ApprovalBridge(),
            audit_logger=AuditLogger(environment="prod"),
        )
        
        # Tool only allowed in local/dev
        local_only_tool = Tool(
            name="local_tool",
            description="Local only tool",
            input_schema=CreateClubInput,
            output_schema=CreateClubOutput,
            risk_level=RiskLevel.LOW_WRITE,
            allowed_environments=[Environment.LOCAL, Environment.DEV],
            handler=mock_create_club_handler,
        )
        
        request = MiddlewareRequest(
            tool_name="local_tool",
            input_data={"club_name": "Test"},
            authorization_header="Bearer token",
            user_id_header="1",
        )
        
        response = await pipeline.process(local_only_tool, request)
        
        assert response.success is False
        assert response.error.code == "env_restricted"
        assert "prod" in response.error.message
