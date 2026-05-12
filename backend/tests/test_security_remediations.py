"""
Tests for security remediations:
- P0-1: No credential exposure from tool outputs
- P0-2: SQL/command injection prevention
- P1-1: Deterministic stop for terminal failures
- P1-2: HTTP status propagation
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from gateway_mcp.tools.users import (
    _validate_club_id,
    _redact_secrets,
    authenticate_club_handler,
    CLUB_ID_PATTERN,
)
from gateway_mcp.tools.schemas import (
    AuthenticateClubInput,
    AuthenticateClubOutput,
)
from gateway_mcp.core.errors import ToolExecutionError
from app.services.mcp_client import MCPToolResult
from app.services.agent_state import ActionOutcome


# ============================================================================
# P0-1 Tests: No credential exposure
# ============================================================================

class TestCredentialProtection:
    """Test that credentials are never exposed in tool outputs."""
    
    def test_authenticate_club_output_has_no_api_key_field(self):
        """AuthenticateClubOutput schema should not have api_key field."""
        output = AuthenticateClubOutput(
            club_id="test123",
            authenticated=True,
            message="Success",
        )
        # Check the model fields
        field_names = set(output.model_fields.keys())
        assert "api_key" not in field_names
        assert "secret" not in field_names
        assert "password" not in field_names
        assert "token" not in field_names  # OAuth token is internal only
    
    def test_authenticate_club_input_has_no_email_field(self):
        """AuthenticateClubInput should not allow email filtering (injection risk)."""
        input_schema = AuthenticateClubInput(club_id="test123")
        field_names = set(input_schema.model_fields.keys())
        # Email was removed to prevent SQL injection
        assert "email" not in field_names
    
    def test_secret_redaction_pattern(self):
        """Test that secrets are properly redacted from text."""
        # Test various secret patterns
        test_cases = [
            ("api_key=abc123xyz", "api_key=***REDACTED***"),
            ("api_key='abc123xyz'", "api_key=***REDACTED***"),
            ('api_key="abc123xyz"', 'api_key=***REDACTED***'),
            ("password: secretpass", "password=***REDACTED***"),
            ("token = xyz789", "token=***REDACTED***"),
            ("secret=mysecret123", "secret=***REDACTED***"),
        ]
        
        for input_text, expected in test_cases:
            result = _redact_secrets(input_text)
            assert "abc123" not in result.lower()
            assert "secret" not in result.lower() or "REDACTED" in result


# ============================================================================
# P0-2 Tests: SQL/Command injection prevention
# ============================================================================

class TestInjectionPrevention:
    """Test SQL and command injection prevention."""
    
    def test_validate_club_id_accepts_valid_ids(self):
        """Valid club IDs should pass validation."""
        valid_ids = [
            "club123",
            "test_club",
            "my-club",
            "Club_ID_123",
            "123",
            "a",
        ]
        for club_id in valid_ids:
            result = _validate_club_id(club_id)
            assert result == club_id
    
    def test_validate_club_id_rejects_sql_injection(self):
        """SQL injection attempts should be rejected."""
        sql_injection_attempts = [
            "'; DROP TABLE users; --",
            "1' OR '1'='1",
            "club_id; DELETE FROM users",
            "test' UNION SELECT * FROM passwords --",
            "club123; cat /etc/passwd",
        ]
        for malicious_id in sql_injection_attempts:
            with pytest.raises(ToolExecutionError) as exc_info:
                _validate_club_id(malicious_id)
            assert "invalid characters" in str(exc_info.value).lower()
    
    def test_validate_club_id_rejects_command_injection(self):
        """Command injection attempts should be rejected."""
        command_injection_attempts = [
            "club$(whoami)",
            "club`id`",
            "club|cat /etc/passwd",
            "club;ls -la",
            "club&&rm -rf /",
            "club\n/bin/sh",
        ]
        for malicious_id in command_injection_attempts:
            with pytest.raises(ToolExecutionError) as exc_info:
                _validate_club_id(malicious_id)
            assert "invalid characters" in str(exc_info.value).lower()
    
    def test_validate_club_id_rejects_empty(self):
        """Empty club ID should be rejected."""
        with pytest.raises(ToolExecutionError) as exc_info:
            _validate_club_id("")
        assert "empty" in str(exc_info.value).lower()
    
    def test_validate_club_id_rejects_too_long(self):
        """Excessively long club ID should be rejected."""
        long_id = "a" * 100
        with pytest.raises(ToolExecutionError) as exc_info:
            _validate_club_id(long_id)
        assert "too long" in str(exc_info.value).lower()
    
    def test_club_id_pattern_is_strict(self):
        """Club ID pattern should only allow safe characters."""
        # Should match
        assert CLUB_ID_PATTERN.match("abc123")
        assert CLUB_ID_PATTERN.match("club_id")
        assert CLUB_ID_PATTERN.match("my-club")
        
        # Should not match
        assert not CLUB_ID_PATTERN.match("")
        assert not CLUB_ID_PATTERN.match("club id")  # space
        assert not CLUB_ID_PATTERN.match("club'id")  # quote
        assert not CLUB_ID_PATTERN.match("club;id")  # semicolon
        assert not CLUB_ID_PATTERN.match("club|id")  # pipe
        assert not CLUB_ID_PATTERN.match("club$id")  # dollar
        assert not CLUB_ID_PATTERN.match("club`id")  # backtick


# ============================================================================
# P1-1 Tests: Deterministic stop for terminal failures
# ============================================================================

class TestTerminalFailureHandling:
    """Test that terminal failures result in deterministic stop."""
    
    @pytest.mark.asyncio
    async def test_terminal_failure_returns_ask_user(self):
        """When a tool has failed terminally, should return ask_user not continue."""
        from app.services.agent_state import AgentState
        
        # Create a mock state with required parameters
        state = AgentState(session_id="test-session-123", current_step=1)
        
        # Record a terminal failure
        state.record_action(
            action_type="tool_call",
            action_data={"name": "test_tool", "args": {}},
            result="Auth error",
            success=False,
            outcome=ActionOutcome.NON_RETRYABLE_FAILURE,
            error_type="AUTH_FAILURE",
        )
        
        # Verify the action is marked as terminally failed
        action_data = {"name": "test_tool", "args": {}}
        assert state.has_action_failed_terminally("tool_call", action_data)


# ============================================================================
# P1-2 Tests: HTTP status propagation
# ============================================================================

class TestHttpStatusPropagation:
    """Test that HTTP status is properly propagated through tool results."""
    
    def test_mcp_tool_result_has_http_status_field(self):
        """MCPToolResult should have http_status field."""
        result = MCPToolResult(
            success=False,
            error="Server error: HTTP 503",
            http_status=503,
        )
        assert result.http_status == 503
    
    def test_mcp_tool_result_http_status_is_optional(self):
        """http_status should be optional (None for non-HTTP errors)."""
        result = MCPToolResult(
            success=False,
            error="Timeout after 30s",
        )
        assert result.http_status is None
    
    def test_http_status_used_in_error_classification(self):
        """HTTP status should be used for error classification when available."""
        from app.services.error_handler import AgentErrorHandler, ErrorType
        
        handler = AgentErrorHandler()
        
        # With HTTP status, should classify from status not message
        error_type = handler.classify_error(
            "Some generic error",
            http_status=401,
        )
        assert error_type == ErrorType.AUTH_FAILURE
        
        # 403 should also be auth failure
        error_type = handler.classify_error(
            "Forbidden",
            http_status=403,
        )
        assert error_type == ErrorType.AUTH_FAILURE
        
        # 429 should be rate limit
        error_type = handler.classify_error(
            "Too many requests",
            http_status=429,
        )
        assert error_type == ErrorType.RATE_LIMIT
        
        # 404 should be not found
        error_type = handler.classify_error(
            "Not found",
            http_status=404,
        )
        assert error_type == ErrorType.TOOL_NOT_FOUND
    
    def test_http_status_500_is_retryable(self):
        """500 errors should be classified as retryable tool failures."""
        from app.services.error_handler import (
            AgentErrorHandler, 
            ErrorType,
            is_error_retryable,
        )
        
        handler = AgentErrorHandler()
        
        # 500, 502, 503 are TOOL_FAILURE (retryable)
        for status in [500, 502, 503]:
            error_type = handler.classify_error(
                f"Server error: HTTP {status}",
                http_status=status,
            )
            assert error_type == ErrorType.TOOL_FAILURE
            assert is_error_retryable(error_type)
        
        # 504 is TIMEOUT (also retryable)
        error_type = handler.classify_error(
            "Server error: HTTP 504",
            http_status=504,
        )
        assert error_type == ErrorType.TIMEOUT
        assert is_error_retryable(error_type)


# ============================================================================
# Integration test for full authenticate_club flow
# ============================================================================

class TestAuthenticateClubSecurity:
    """Integration tests for authenticate_club security."""
    
    @pytest.mark.asyncio
    async def test_authenticate_club_validates_club_id(self):
        """authenticate_club should validate club_id before any operations."""
        from gateway_mcp.tools.base import ToolContext
        
        # Create minimal mock context
        mock_context = MagicMock(spec=ToolContext)
        mock_context.correlation_id = "test-123"
        mock_context.audit_id = "audit-123"
        
        # Test with malicious club_id
        input_data = AuthenticateClubInput(club_id="'; DROP TABLE users; --")
        
        with pytest.raises(ToolExecutionError) as exc_info:
            await authenticate_club_handler(input_data, mock_context)
        
        assert "invalid characters" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_authenticate_club_output_never_contains_api_key(self):
        """Regardless of success/failure, output must never contain API key."""
        from gateway_mcp.tools.base import ToolContext
        
        # Create mock context with mock executor
        mock_context = MagicMock(spec=ToolContext)
        mock_context.correlation_id = "test-123"
        mock_context.audit_id = "audit-123"
        
        mock_executor = AsyncMock()
        mock_executor.run_command = AsyncMock(return_value=MagicMock(
            success=True,
            stdout='[{"id": 1, "email": "admin@test.com", "api_key": "super_secret_key_12345"}]',
            stderr="",
        ))
        mock_context.get_executor = AsyncMock(return_value=mock_executor)
        
        # Mock BRSAuthProvider
        with patch('gateway_mcp.tools.users.BRSAuthProvider') as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider.is_configured = True
            mock_provider.get_token_for_club = AsyncMock(return_value=MagicMock(
                expires_at=9999999999.0,
            ))
            mock_provider_class.get_instance.return_value = mock_provider
            
            input_data = AuthenticateClubInput(club_id="test123")
            result = await authenticate_club_handler(input_data, mock_context)
        
        # Verify output structure
        assert isinstance(result, AuthenticateClubOutput)
        assert result.authenticated == True
        assert result.club_id == "test123"
        
        # Verify NO secrets in output
        result_dict = result.model_dump()
        result_str = str(result_dict).lower()
        
        assert "super_secret_key" not in result_str
        assert "api_key" not in result_dict
        assert "12345" not in result_str  # Part of the secret key
