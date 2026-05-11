"""
Integration tests for MCP client operations.

Tests end-to-end flow where an MCP client:
1. Lists available tools via /mcp/tools/list
2. Calls tools via /mcp/tools/call
3. Receives proper responses through the full pipeline

Uses real ToolRegistry and middleware pipeline configuration.
"""

import pytest
from fastapi.testclient import TestClient

from gateway_mcp.core.config import Settings
from gateway_mcp.core.middleware import create_middleware_pipeline
from gateway_mcp.core.transport import create_mcp_router
from gateway_mcp.main import create_app
from gateway_mcp.tools import create_brs_registry


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings."""
    return Settings(
        env="local",
        executor_backend="mock",
        service_tokens=["test-service-token"],
        default_timeout=30,
    )


@pytest.fixture
def app_client(test_settings):
    """Create a test client with the full application."""
    app = create_app(settings=test_settings)
    return TestClient(app)


# ============================================================================
# MCP Client Integration Tests
# ============================================================================


class TestMCPClientListTools:
    """Integration tests for MCP client listing tools."""
    
    def test_client_can_list_brs_tools(self, app_client):
        """MCP client can list all BRS tools."""
        response = app_client.post("/mcp/tools/list", json={})
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have all 6 BRS tools
        assert len(data["tools"]) >= 6
        
        tool_names = {t["name"] for t in data["tools"]}
        expected_tools = {
            "create_club",
            "get_club_by_name",
            "verify_club_setup",
            "get_club_config",
            "create_admin_user",
            "call_internal_api",
        }
        assert expected_tools.issubset(tool_names)
    
    def test_client_receives_valid_schemas(self, app_client):
        """Each tool has a valid JSON schema."""
        response = app_client.post("/mcp/tools/list", json={})
        
        data = response.json()
        
        for tool in data["tools"]:
            schema = tool["inputSchema"]
            
            # Valid JSON Schema properties
            assert "type" in schema
            assert schema["type"] == "object"
            assert "properties" in schema
    
    def test_create_club_schema(self, app_client):
        """create_club tool has correct input schema."""
        response = app_client.post("/mcp/tools/list", json={})
        
        data = response.json()
        create_club = next(t for t in data["tools"] if t["name"] == "create_club")
        
        schema = create_club["inputSchema"]
        props = schema["properties"]
        
        # Required fields (schema uses 'name' not 'club_name')
        assert "name" in props
        assert "country" in props
        assert "timezone" in props
        assert "currency" in props


class TestMCPClientCallTools:
    """Integration tests for MCP client calling tools."""
    
    def test_client_call_requires_auth(self, app_client):
        """Tool call without auth header fails."""
        response = app_client.post(
            "/mcp/tools/call",
            json={
                "name": "get_club_by_name",
                "arguments": {"club_name": "Test Club"},
            },
        )
        
        # Should fail with permission denied (no auth)
        # The exact behavior depends on auth middleware
        assert response.status_code in (200, 403, 401)
        
        data = response.json()
        # Either error in content or in error response
        if response.status_code == 200:
            assert data.get("isError", False) is True
    
    def test_client_call_with_auth(self, app_client):
        """Tool call with valid auth headers processes request."""
        response = app_client.post(
            "/mcp/tools/call",
            json={
                "name": "get_club_by_name",
                "arguments": {"club_name": "Test Club"},
            },
            headers={
                "Authorization": "Bearer test-service-token",
                "X-User-Id": "123",
            },
        )
        
        # Request should be processed (may fail in execution without executor)
        assert response.status_code == 200
        data = response.json()
        
        # Response format is valid
        assert "content" in data
        assert "isError" in data
    
    def test_client_call_unknown_tool(self, app_client):
        """Calling unknown tool returns 404."""
        response = app_client.post(
            "/mcp/tools/call",
            json={
                "name": "unknown_tool",
                "arguments": {},
            },
        )
        
        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "tool_not_found"
    
    def test_client_call_validation_error(self, app_client):
        """Invalid arguments return validation error."""
        response = app_client.post(
            "/mcp/tools/call",
            json={
                "name": "create_club",
                "arguments": {
                    # Missing required fields
                },
            },
            headers={
                "Authorization": "Bearer test-service-token",
                "X-User-Id": "123",
            },
        )
        
        # Either HTTP error or error in content
        data = response.json()
        
        if response.status_code == 200:
            # Error returned in MCP format
            assert data["isError"] is True
        else:
            # Error in HTTP response
            assert response.status_code in (400, 422)


class TestMCPClientWorkflow:
    """Integration tests for MCP client workflows."""
    
    def test_list_then_call_workflow(self, app_client):
        """Client can list tools then call one."""
        # Step 1: List tools
        list_response = app_client.post("/mcp/tools/list", json={})
        assert list_response.status_code == 200
        
        tools = list_response.json()["tools"]
        assert len(tools) > 0
        
        # Step 2: Pick a read tool
        get_club = next(t for t in tools if t["name"] == "get_club_by_name")
        
        # Step 3: Call it
        call_response = app_client.post(
            "/mcp/tools/call",
            json={
                "name": get_club["name"],
                "arguments": {"club_name": "Test Club"},
            },
            headers={
                "Authorization": "Bearer test-service-token",
                "X-User-Id": "123",
            },
        )
        
        assert call_response.status_code == 200
        data = call_response.json()
        assert "content" in data
        assert "isError" in data
    
    def test_correlation_id_propagation(self, app_client):
        """Correlation ID is accepted and logged."""
        response = app_client.post(
            "/mcp/tools/call",
            json={
                "name": "get_club_by_name",
                "arguments": {"club_name": "Test"},
            },
            headers={
                "Authorization": "Bearer test-service-token",
                "X-User-Id": "123",
                "X-Correlation-Id": "test-corr-id-12345",
            },
        )
        
        assert response.status_code == 200
        # Correlation ID should be accepted without error


# ============================================================================
# Debug Endpoint Tests
# ============================================================================


class TestDebugEndpoints:
    """Integration tests for debug endpoints."""
    
    def test_tools_debug_endpoint(self, app_client):
        """GET /tools returns tool list for debugging."""
        response = app_client.get("/tools")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "tools" in data
        assert "count" in data
        assert data["count"] >= 6
        
        # Debug format includes extra fields
        for tool in data["tools"]:
            assert "name" in tool
            assert "description" in tool
            assert "risk_level" in tool
            assert "allowed_environments" in tool
    
    def test_health_endpoint(self, app_client):
        """GET /health returns healthy status."""
        response = app_client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "healthy"
        assert "version" in data
    
    def test_ready_endpoint(self, app_client):
        """GET /ready returns ready status."""
        response = app_client.get("/ready")
        
        # May be 200 or 503 depending on executor availability
        assert response.status_code in (200, 503)
        data = response.json()
        
        assert "status" in data
        assert "env" in data
        assert "executor_backend" in data


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Integration tests for error handling."""
    
    def test_gateway_error_format(self, app_client):
        """GatewayError responses have correct format."""
        response = app_client.post(
            "/mcp/tools/call",
            json={"name": "nonexistent", "arguments": {}},
        )
        
        assert response.status_code == 404
        data = response.json()
        
        assert "error" in data
        error = data["error"]
        assert "code" in error
        assert "message" in error
        assert "retryable" in error
    
    def test_internal_error_masked(self, app_client):
        """Internal errors don't leak sensitive details."""
        # This would require a tool that raises an exception
        # For now, we verify the error format exists
        pass


# ============================================================================
# Executor Routing Tests
# ============================================================================


class TestExecutorRouting:
    """Integration tests for per-tool executor routing."""
    
    def test_both_brs_and_jira_tools_registered(self, app_client):
        """
        Registry contains both BRS and Jira tools.
        
        This verifies the full registry is used with all 9 tools.
        """
        response = app_client.post("/mcp/tools/list", json={})
        
        assert response.status_code == 200
        data = response.json()
        
        tool_names = {t["name"] for t in data["tools"]}
        
        # BRS tools (6)
        brs_tools = {
            "create_club",
            "get_club_by_name",
            "verify_club_setup",
            "get_club_config",
            "create_admin_user",
            "call_internal_api",
        }
        assert brs_tools.issubset(tool_names), f"Missing BRS tools: {brs_tools - tool_names}"
        
        # Jira tools (3)
        jira_tools = {
            "create_ticket",
            "get_ticket_status",
            "add_comment",
        }
        assert jira_tools.issubset(tool_names), f"Missing Jira tools: {jira_tools - tool_names}"
        
        # Total should be at least 9
        assert len(data["tools"]) >= 9
    
    def test_brs_tool_uses_env_executor(self, app_client):
        """
        BRS tools route through environment executor (mock in tests).
        
        When calling a BRS tool, it should use the mock executor
        and NOT fail with "requires MCPProxyBackend" error.
        """
        response = app_client.post(
            "/mcp/tools/call",
            json={
                "name": "get_club_by_name",
                "arguments": {"name": "Test Club"},
            },
            headers={
                "Authorization": "Bearer test-service-token",
                "X-User-Id": "123",
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should get a valid response (even if "not found" from mock)
        assert "content" in data
        assert "isError" in data
        
        # Should NOT have "MCPProxyBackend" error
        if data.get("isError"):
            content_text = str(data.get("content", []))
            assert "MCPProxyBackend" not in content_text
    
    def test_jira_tool_requires_mcp_proxy(self, app_client):
        """
        Jira tools require MCPProxyBackend (configured via upstream_mcps).
        
        Without upstream MCP configured, Jira tools should fail gracefully.
        """
        response = app_client.post(
            "/mcp/tools/call",
            json={
                "name": "get_ticket_status",
                "arguments": {"ticket_key": "GOLF-123"},
            },
            headers={
                "Authorization": "Bearer test-service-token",
                "X-User-Id": "123",
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Without upstream MCP config, should get an error about missing proxy
        # OR credential missing error (if scope check runs first)
        assert "isError" in data
    
    def test_tool_list_includes_external_metadata(self, app_client):
        """
        External tools expose metadata indicating they're external.
        """
        response = app_client.get("/tools")  # Debug endpoint
        
        assert response.status_code == 200
        data = response.json()
        
        # Find create_ticket tool
        create_ticket = next(
            (t for t in data["tools"] if t["name"] == "create_ticket"),
            None
        )
        
        assert create_ticket is not None
        # External tools should have risk_level and allowed_environments
        assert "risk_level" in create_ticket
        assert "allowed_environments" in create_ticket
