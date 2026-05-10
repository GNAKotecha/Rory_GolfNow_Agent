"""
Unit tests for core middleware components.

Tests each middleware stage independently:
- Auth: token validation, user ID parsing
- Permissions: risk level checks, env restrictions
- Scopes: OAuth scope validation
- Approval: approval request creation
- Audit: record creation, sanitization
"""

import pytest
from pydantic import BaseModel

from gateway_mcp.core.auth import AuthError, AuthResult, AuthService
from gateway_mcp.core.permissions import PermissionService
from gateway_mcp.core.scopes import ScopeService
from gateway_mcp.core.approval import ApprovalBridge
from gateway_mcp.core.audit import (
    AuditLogger,
    AuditOutcome,
    AuditRecord,
    sanitize_data,
)
from gateway_mcp.core.errors import (
    EnvRestrictedError,
    PermissionDeniedError,
    ApprovalRequiredError,
    CredentialMissingError,
)
from gateway_mcp.tools.base import Environment, RiskLevel, Tool


# --------------------
# Test fixtures
# --------------------


class DummyInput(BaseModel):
    """Test input schema."""
    name: str
    count: int = 1


class DummyOutput(BaseModel):
    """Test output schema."""
    result: str


@pytest.fixture
def auth_service():
    """Auth service with test tokens."""
    return AuthService(
        service_tokens={
            "test-token": ["operator"],
            "admin-token": ["admin"],
            "readonly-token": [],
        },
        require_user_id=True,
    )


@pytest.fixture
def auth_service_optional_user():
    """Auth service with optional user ID."""
    return AuthService(
        service_tokens={"test-token": ["operator"]},
        require_user_id=False,
    )


@pytest.fixture
def permission_service_local():
    """Permission service for local environment."""
    return PermissionService(current_env=Environment.LOCAL)


@pytest.fixture
def permission_service_prod():
    """Permission service for prod environment."""
    return PermissionService(current_env=Environment.PROD)


@pytest.fixture
def scope_service():
    """Scope service without credential store (stub mode)."""
    return ScopeService(credential_store=None)


@pytest.fixture
def approval_bridge():
    """Approval bridge without DB connection."""
    return ApprovalBridge()


@pytest.fixture
def audit_logger():
    """Audit logger for local environment."""
    return AuditLogger(environment="local")


@pytest.fixture
def read_tool():
    """Read-only tool for testing."""
    return Tool(
        name="test_read",
        description="Test read tool",
        input_schema=DummyInput,
        output_schema=DummyOutput,
        risk_level=RiskLevel.READ,
        allowed_environments=[Environment.LOCAL, Environment.DEV, Environment.QA, Environment.PROD],
    )


@pytest.fixture
def write_tool():
    """Low-write tool for testing."""
    return Tool(
        name="test_write",
        description="Test write tool",
        input_schema=DummyInput,
        output_schema=DummyOutput,
        risk_level=RiskLevel.LOW_WRITE,
        allowed_environments=[Environment.LOCAL, Environment.DEV],
    )


@pytest.fixture
def high_risk_tool():
    """High-write tool requiring approval."""
    return Tool(
        name="test_high_risk",
        description="Test high risk tool",
        input_schema=DummyInput,
        output_schema=DummyOutput,
        risk_level=RiskLevel.HIGH_WRITE,
        allowed_environments=[Environment.LOCAL],
        requires_approval=True,
    )


@pytest.fixture
def external_tool():
    """External tool with required scopes."""
    return Tool(
        name="test_external",
        description="Test external tool",
        input_schema=DummyInput,
        output_schema=DummyOutput,
        risk_level=RiskLevel.READ,
        allowed_environments=list(Environment),
        required_scopes=["jira:read", "jira:write"],
    )


# --------------------
# Auth tests
# --------------------


class TestAuthService:
    """Tests for AuthService."""
    
    def test_authenticate_valid_token(self, auth_service):
        """Should authenticate with valid service token."""
        result = auth_service.authenticate(
            authorization_header="Bearer test-token",
            user_id_header="123",
        )
        
        assert isinstance(result, AuthResult)
        assert result.user_id == 123
        assert "operator" in result.token_scopes
        assert result.is_operator is True
    
    def test_authenticate_admin_token(self, auth_service):
        """Should recognize admin scopes."""
        result = auth_service.authenticate(
            authorization_header="Bearer admin-token",
            user_id_header="1",
        )
        
        assert result.is_admin is True
        assert result.is_operator is True  # admin implies operator
    
    def test_authenticate_missing_auth_header(self, auth_service):
        """Should reject missing Authorization header."""
        with pytest.raises(AuthError) as exc_info:
            auth_service.authenticate(None, "123")
        
        assert "Missing Authorization header" in str(exc_info.value)
    
    def test_authenticate_invalid_token(self, auth_service):
        """Should reject invalid service token."""
        with pytest.raises(AuthError) as exc_info:
            auth_service.authenticate("Bearer invalid-token", "123")
        
        assert "Invalid service token" in str(exc_info.value)
    
    def test_authenticate_missing_user_id(self, auth_service):
        """Should reject missing X-User-Id when required."""
        with pytest.raises(AuthError) as exc_info:
            auth_service.authenticate("Bearer test-token", None)
        
        assert "Missing X-User-Id header" in str(exc_info.value)
    
    def test_authenticate_optional_user_id(self, auth_service_optional_user):
        """Should allow missing X-User-Id when optional."""
        result = auth_service_optional_user.authenticate(
            authorization_header="Bearer test-token",
            user_id_header=None,
        )
        
        assert result.user_id == 0  # default
    
    def test_authenticate_invalid_user_id(self, auth_service):
        """Should reject non-integer X-User-Id."""
        with pytest.raises(AuthError) as exc_info:
            auth_service.authenticate("Bearer test-token", "not-a-number")
        
        assert "must be a valid integer" in str(exc_info.value)
    
    def test_authenticate_malformed_bearer(self, auth_service):
        """Should reject malformed Bearer token."""
        with pytest.raises(AuthError) as exc_info:
            auth_service.authenticate("Basic test-token", "123")
        
        assert "Invalid Authorization header format" in str(exc_info.value)


# --------------------
# Permission tests
# --------------------


class TestPermissionService:
    """Tests for PermissionService."""
    
    def test_check_read_tool_allowed(self, permission_service_local, read_tool):
        """Should allow read tool for any authenticated user."""
        auth = AuthResult(user_id=1, token_scopes=[])
        
        # Should not raise
        permission_service_local.check_permission(read_tool, auth)
    
    def test_check_write_tool_requires_operator(self, permission_service_local, write_tool):
        """Should require operator scope for write tools."""
        auth = AuthResult(user_id=1, token_scopes=[])
        
        with pytest.raises(PermissionDeniedError) as exc_info:
            permission_service_local.check_permission(write_tool, auth)
        
        assert "requires operator role" in str(exc_info.value)
    
    def test_check_write_tool_allowed_for_operator(self, permission_service_local, write_tool):
        """Should allow write tool for operator."""
        auth = AuthResult(user_id=1, token_scopes=["operator"])
        
        # Should not raise
        permission_service_local.check_permission(write_tool, auth)
    
    def test_check_env_restriction(self, permission_service_prod, write_tool):
        """Should deny tool not allowed in current environment."""
        auth = AuthResult(user_id=1, token_scopes=["operator"])
        
        with pytest.raises(EnvRestrictedError) as exc_info:
            permission_service_prod.check_permission(write_tool, auth)
        
        assert "not allowed in 'prod'" in str(exc_info.value)
    
    def test_check_high_risk_requires_admin(self, permission_service_local, high_risk_tool):
        """Should require admin scope for high-risk tools."""
        auth = AuthResult(user_id=1, token_scopes=["operator"])
        
        with pytest.raises(PermissionDeniedError) as exc_info:
            permission_service_local.check_permission(high_risk_tool, auth)
        
        assert "requires admin role" in str(exc_info.value)
    
    def test_check_high_risk_allowed_for_admin(self, permission_service_local, high_risk_tool):
        """Should allow high-risk tool for admin."""
        auth = AuthResult(user_id=1, token_scopes=["admin"])
        
        # Should not raise
        permission_service_local.check_permission(high_risk_tool, auth)
    
    def test_requires_approval_high_write(self, permission_service_local, high_risk_tool):
        """Should require approval for high-write tools."""
        auth = AuthResult(user_id=1, token_scopes=["admin"])
        
        assert permission_service_local.requires_approval(high_risk_tool, auth) is True
    
    def test_requires_approval_flagged_tool(self, permission_service_local, read_tool):
        """Should require approval if tool.requires_approval is True."""
        read_tool.requires_approval = True
        auth = AuthResult(user_id=1, token_scopes=[])
        
        assert permission_service_local.requires_approval(read_tool, auth) is True


# --------------------
# Scope tests
# --------------------


class TestScopeService:
    """Tests for ScopeService."""
    
    def test_check_brs_tool_no_scopes(self, scope_service, read_tool):
        """Should skip scope check for BRS tools (no required_scopes)."""
        # Should not raise
        scope_service.check_scopes(read_tool, user_id=1)
    
    def test_check_external_tool_missing_credential(self, scope_service, external_tool):
        """Should raise CredentialMissingError for external tool without credential."""
        with pytest.raises(CredentialMissingError) as exc_info:
            scope_service.check_scopes(external_tool, user_id=1)
        
        assert "atlassian" in str(exc_info.value)
        assert "reconnect_url" in str(exc_info.value.to_dict()["error"])
    
    def test_get_provider_from_jira_scopes(self, scope_service):
        """Should detect Atlassian provider from jira scopes."""
        provider = scope_service._get_provider_from_scopes(["jira:read"])
        assert provider == "atlassian"
    
    def test_get_provider_from_github_scopes(self, scope_service):
        """Should detect GitHub provider from repo scope."""
        provider = scope_service._get_provider_from_scopes(["repo"])
        assert provider == "github"


# --------------------
# Approval tests
# --------------------


class TestApprovalBridge:
    """Tests for ApprovalBridge."""
    
    def test_request_approval_creates_record(self, approval_bridge, high_risk_tool):
        """Should create approval request with unique ID."""
        request = approval_bridge.request_approval(
            tool=high_risk_tool,
            user_id=1,
            input_data={"name": "test"},
        )
        
        assert request.request_id is not None
        assert request.tool_name == "test_high_risk"
        assert request.user_id == 1
        assert "test" in request.input_data["name"]
        assert "Approval Required" in request.approval_prompt
    
    def test_require_approval_raises_error(self, approval_bridge, high_risk_tool):
        """Should raise ApprovalRequiredError with request ID."""
        with pytest.raises(ApprovalRequiredError) as exc_info:
            approval_bridge.require_approval(
                tool=high_risk_tool,
                user_id=1,
                input_data={"name": "test"},
            )
        
        assert "requires approval" in str(exc_info.value)
        assert exc_info.value.code == "approval_required"
    
    def test_check_approval_status_pending(self, approval_bridge, high_risk_tool):
        """Should return pending for new request."""
        request = approval_bridge.request_approval(
            tool=high_risk_tool,
            user_id=1,
            input_data={},
        )
        
        status = approval_bridge.check_approval_status(request.request_id)
        assert status == "pending"
    
    def test_check_approval_status_not_found(self, approval_bridge):
        """Should return None for unknown request ID."""
        status = approval_bridge.check_approval_status("unknown-id")
        assert status is None


# --------------------
# Audit tests
# --------------------


class TestAuditLogger:
    """Tests for AuditLogger and sanitization."""
    
    def test_start_audit_creates_record(self, audit_logger):
        """Should create audit record with unique ID."""
        record = audit_logger.start_audit(
            tool_name="test_tool",
            user_id=123,
            input_data={"name": "test"},
        )
        
        assert record.audit_id is not None
        assert record.tool_name == "test_tool"
        assert record.user_id == 123
        assert record.outcome == AuditOutcome.SUCCESS  # default
    
    def test_finish_audit_updates_record(self, audit_logger):
        """Should update record with outcome and duration."""
        record = audit_logger.start_audit(
            tool_name="test_tool",
            user_id=1,
            input_data={},
        )
        
        audit_logger.finish_audit(
            record=record,
            outcome=AuditOutcome.SUCCESS,
            output_data={"result": "ok"},
        )
        
        assert record.finished_at is not None
        assert record.duration_ms >= 0
        assert record.outcome == AuditOutcome.SUCCESS
        assert record.output_data == {"result": "ok"}
    
    def test_finish_audit_with_error(self, audit_logger):
        """Should record error details."""
        record = audit_logger.start_audit(
            tool_name="test_tool",
            user_id=1,
            input_data={},
        )
        
        audit_logger.finish_audit(
            record=record,
            outcome=AuditOutcome.PERMISSION_DENIED,
            error_code="permission_denied",
            error_message="Access denied",
        )
        
        assert record.outcome == AuditOutcome.PERMISSION_DENIED
        assert record.error_code == "permission_denied"
        assert record.error_message == "Access denied"
    
    def test_sanitize_data_redacts_password(self):
        """Should redact password fields."""
        data = {"username": "test", "password": "secret123"}
        sanitized = sanitize_data(data)
        
        assert sanitized["username"] == "test"
        assert sanitized["password"] == "[REDACTED]"
    
    def test_sanitize_data_redacts_nested_secrets(self):
        """Should redact secrets in nested structures."""
        data = {
            "config": {
                "api_key": "abc123",
                "endpoint": "https://api.example.com",
            }
        }
        sanitized = sanitize_data(data)
        
        assert sanitized["config"]["api_key"] == "[REDACTED]"
        assert sanitized["config"]["endpoint"] == "https://api.example.com"
    
    def test_sanitize_data_truncates_long_strings(self):
        """Should truncate very long strings."""
        data = {"content": "x" * 2000}
        sanitized = sanitize_data(data)
        
        assert len(sanitized["content"]) < 2000
        assert "TRUNCATED" in sanitized["content"]
    
    def test_audit_record_to_dict(self, audit_logger):
        """Should serialize audit record to dict."""
        record = audit_logger.start_audit(
            tool_name="test_tool",
            user_id=1,
            input_data={"name": "test"},
        )
        
        data = record.to_dict()
        
        assert data["audit_id"] == record.audit_id
        assert data["tool_name"] == "test_tool"
        assert data["user_id"] == 1
        assert "started_at" in data
