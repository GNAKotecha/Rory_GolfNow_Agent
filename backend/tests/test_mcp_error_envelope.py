"""Tests for MCP error envelope enrichment (Task C2)."""

import pytest
from app.services.mcp_client import MCPToolResult
from app.services.error_handler import (
    ErrorType,
    classify_from_mcp_result,
    AgentErrorHandler,
    is_error_retryable,
)


class TestMCPToolResultEnrichment:
    """Tests for MCPToolResult structured fields."""

    def test_default_values_for_new_fields(self):
        """New fields should have sensible defaults."""
        result = MCPToolResult(success=True)
        
        assert result.upstream_status is None
        assert result.terminal_hint is False
        assert result.error_metadata == {}

    def test_error_with_all_fields_populated(self):
        """All error envelope fields can be populated."""
        result = MCPToolResult(
            success=False,
            error="Auth error: 401 Unauthorized",
            error_category="auth_failure",
            upstream_status=401,
            terminal_hint=True,
            error_metadata={"service": "brs-api", "request_id": "abc123"},
        )
        
        assert result.error_category == "auth_failure"
        assert result.upstream_status == 401
        assert result.terminal_hint is True
        assert result.error_metadata["service"] == "brs-api"

    def test_to_dict_includes_new_fields(self):
        """to_dict() should include all enriched fields."""
        result = MCPToolResult(
            success=False,
            error="Validation failed",
            error_category="validation_error",
            upstream_status=422,
            terminal_hint=True,
            error_metadata={"field": "name"},
        )
        
        d = result.to_dict()
        
        assert "upstream_status" in d
        assert d["upstream_status"] == 422
        assert "terminal_hint" in d
        assert d["terminal_hint"] is True
        assert "error_metadata" in d
        assert d["error_metadata"]["field"] == "name"


class TestIsTerminalError:
    """Tests for MCPToolResult.is_terminal_error()."""

    def test_terminal_hint_true_is_terminal(self):
        """terminal_hint=True should be terminal."""
        result = MCPToolResult(
            success=False,
            error="Some error",
            terminal_hint=True,
        )
        
        assert result.is_terminal_error() is True

    def test_auth_failure_category_is_terminal(self):
        """auth_failure category should be terminal."""
        result = MCPToolResult(
            success=False,
            error="Unauthorized",
            error_category="auth_failure",
        )
        
        assert result.is_terminal_error() is True

    def test_validation_error_category_is_terminal(self):
        """validation_error category should be terminal."""
        result = MCPToolResult(
            success=False,
            error="Invalid input",
            error_category="validation_error",
        )
        
        assert result.is_terminal_error() is True

    def test_tool_not_found_category_is_terminal(self):
        """tool_not_found category should be terminal."""
        result = MCPToolResult(
            success=False,
            error="Tool not found",
            error_category="tool_not_found",
        )
        
        assert result.is_terminal_error() is True

    def test_http_401_is_terminal(self):
        """HTTP 401 should be terminal."""
        result = MCPToolResult(
            success=False,
            error="Unauthorized",
            http_status=401,
        )
        
        assert result.is_terminal_error() is True

    def test_http_404_is_terminal(self):
        """HTTP 404 should be terminal."""
        result = MCPToolResult(
            success=False,
            error="Not found",
            http_status=404,
        )
        
        assert result.is_terminal_error() is True

    def test_container_unavailable_is_not_terminal(self):
        """container_unavailable should NOT be terminal (retryable)."""
        result = MCPToolResult(
            success=False,
            error="Container not running",
            error_category="container_unavailable",
        )
        
        assert result.is_terminal_error() is False

    def test_timeout_is_not_terminal(self):
        """timeout should NOT be terminal (retryable)."""
        result = MCPToolResult(
            success=False,
            error="Request timed out",
            error_category="timeout",
        )
        
        assert result.is_terminal_error() is False


class TestClassifyFromMCPResult:
    """Tests for classify_from_mcp_result function."""

    def test_priority_error_category_over_http_status(self):
        """error_category should take priority over http_status."""
        result = MCPToolResult(
            success=False,
            error="Auth error",
            error_category="auth_failure",
            http_status=500,  # Would normally be TOOL_FAILURE
        )
        
        error_type = classify_from_mcp_result(result)
        
        assert error_type == ErrorType.AUTH_FAILURE

    def test_priority_upstream_status_when_no_category(self):
        """upstream_status should be used when error_category is missing."""
        result = MCPToolResult(
            success=False,
            error="Not found",
            upstream_status=404,
            http_status=200,  # MCP layer succeeded
        )
        
        error_type = classify_from_mcp_result(result)
        
        assert error_type == ErrorType.TOOL_NOT_FOUND

    def test_fallback_to_http_status(self):
        """http_status should be used when other fields are missing."""
        result = MCPToolResult(
            success=False,
            error="Server error",
            http_status=503,
        )
        
        error_type = classify_from_mcp_result(result)
        
        assert error_type == ErrorType.TOOL_FAILURE

    def test_fallback_to_message_parsing(self):
        """Error message should be parsed when structured fields are missing."""
        result = MCPToolResult(
            success=False,
            error="no such container: brs-executor",
        )
        
        error_type = classify_from_mcp_result(result)
        
        assert error_type == ErrorType.RESOURCE_EXHAUSTED

    def test_validation_error_classification(self):
        """Validation errors should be classified correctly."""
        result = MCPToolResult(
            success=False,
            error="Invalid request",
            error_category="validation_error",
        )
        
        error_type = classify_from_mcp_result(result)
        
        assert error_type == ErrorType.VALIDATION_ERROR

    def test_rbac_denied_classification(self):
        """RBAC denied should be classified correctly."""
        result = MCPToolResult(
            success=False,
            error="Role policy denies access",
            error_category="rbac_denied",
        )
        
        error_type = classify_from_mcp_result(result)
        
        assert error_type == ErrorType.RBAC_DENIED

    def test_terminal_hint_makes_error_non_retryable(self):
        """terminal_hint=True should return non-retryable error type."""
        result = MCPToolResult(
            success=False,
            error="Custom server error with no category",
            terminal_hint=True,
        )
        
        error_type = classify_from_mcp_result(result)
        
        # Should return CONTRACT_ERROR (non-retryable) when terminal_hint=True
        assert error_type == ErrorType.CONTRACT_ERROR
        assert not is_error_retryable(error_type)

    def test_terminal_hint_with_category_uses_category(self):
        """terminal_hint=True with non-retryable error_category should use category type."""
        result = MCPToolResult(
            success=False,
            error="Auth error",
            error_category="auth_failure",
            terminal_hint=True,
        )
        
        error_type = classify_from_mcp_result(result)
        
        # Should use the specific category type (already non-retryable)
        assert error_type == ErrorType.AUTH_FAILURE
        assert not is_error_retryable(error_type)

    def test_terminal_hint_overrides_retryable_category(self):
        """terminal_hint=True should override a retryable category to non-retryable."""
        # docker_unavailable maps to RESOURCE_EXHAUSTED which is retryable
        result = MCPToolResult(
            success=False,
            error="Container not available",
            error_category="docker_unavailable",
            terminal_hint=True,  # But server says this is terminal!
        )
        
        error_type = classify_from_mcp_result(result)
        
        # Should NOT be RESOURCE_EXHAUSTED because terminal_hint overrides
        assert error_type == ErrorType.CONTRACT_ERROR
        assert not is_error_retryable(error_type)

    def test_terminal_hint_false_does_not_force_non_retryable(self):
        """terminal_hint=False should allow normal classification flow."""
        result = MCPToolResult(
            success=False,
            error="Generic error",
            terminal_hint=False,
        )
        
        error_type = classify_from_mcp_result(result)
        
        # Should fall through to TOOL_FAILURE which is retryable
        assert error_type == ErrorType.TOOL_FAILURE
        assert is_error_retryable(error_type)


class TestAgentErrorHandlerWithMCPResult:
    """Tests for AgentErrorHandler using MCPToolResult."""

    def test_classify_from_result_method(self):
        """classify_from_result should use the new function."""
        handler = AgentErrorHandler()
        result = MCPToolResult(
            success=False,
            error="Unauthorized",
            error_category="auth_failure",
        )
        
        error_type = handler.classify_from_result(result)
        
        assert error_type == ErrorType.AUTH_FAILURE

    def test_is_terminal_from_result_uses_terminal_hint(self):
        """is_terminal_from_result should use terminal_hint."""
        handler = AgentErrorHandler()
        result = MCPToolResult(
            success=False,
            error="Custom terminal error",
            terminal_hint=True,
        )
        
        is_terminal = handler.is_terminal_from_result(result)
        
        assert is_terminal is True

    def test_is_terminal_from_result_for_retryable(self):
        """is_terminal_from_result should return False for retryable."""
        handler = AgentErrorHandler()
        result = MCPToolResult(
            success=False,
            error="Connection refused",
            error_category="connection_refused",
        )
        
        is_terminal = handler.is_terminal_from_result(result)
        
        assert is_terminal is False


class TestMCPClientErrorEnvelope:
    """Tests for MCP client error envelope parsing."""

    def test_parse_error_envelope_from_structured_response(self):
        """_parse_error_envelope should extract structured fields."""
        from app.services.mcp_client import MCPClient
        from app.config.mcp_config import MCPServerConfig
        
        config = MCPServerConfig(
            name="test-server",
            url="http://localhost:8080",
        )
        client = MCPClient(config)
        
        data = {
            "isError": True,
            "error_category": "auth_failure",
            "upstream_status": 401,
            "terminal": True,
            "content": [{"type": "text", "text": "Unauthorized"}],
        }
        
        envelope = client._parse_error_envelope(data, "Unauthorized")
        
        assert envelope["error_category"] == "auth_failure"
        assert envelope["upstream_status"] == 401
        assert envelope["terminal_hint"] is True

    def test_parse_error_envelope_from_content_block(self):
        """_parse_error_envelope should extract from content blocks."""
        from app.services.mcp_client import MCPClient
        from app.config.mcp_config import MCPServerConfig
        
        config = MCPServerConfig(
            name="test-server",
            url="http://localhost:8080",
        )
        client = MCPClient(config)
        
        data = {
            "isError": True,
            "content": [
                {
                    "type": "error",
                    "category": "validation_error",
                    "upstream_status": 422,
                    "terminal": True,
                    "metadata": {"field": "name"},
                },
                {"type": "text", "text": "Validation failed"},
            ],
        }
        
        envelope = client._parse_error_envelope(data, "Validation failed")
        
        assert envelope["error_category"] == "validation_error"
        assert envelope["upstream_status"] == 422
        assert envelope["terminal_hint"] is True
        assert envelope["error_metadata"]["field"] == "name"

    def test_parse_error_envelope_falls_back_to_classification(self):
        """_parse_error_envelope should classify from text if no structure."""
        from app.services.mcp_client import MCPClient
        from app.config.mcp_config import MCPServerConfig
        
        config = MCPServerConfig(
            name="test-server",
            url="http://localhost:8080",
        )
        client = MCPClient(config)
        
        data = {
            "isError": True,
            "content": [{"type": "text", "text": "no such container: abc"}],
        }
        
        envelope = client._parse_error_envelope(data, "no such container: abc")
        
        assert envelope["error_category"] == "container_unavailable"
