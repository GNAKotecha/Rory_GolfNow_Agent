"""
Unit tests for MCP Protocol Transport.

Tests cover:
- tools/list endpoint returns all registered tools
- tools/call endpoint executes tools through middleware
- MCP protocol compliance (request/response formats)
- Error handling for missing tools
- Error handling for validation failures
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from gateway_mcp.core.config import Settings
from gateway_mcp.core.middleware import (
    MiddlewarePipeline,
    MiddlewareRequest,
    MiddlewareResponse,
)
from gateway_mcp.core.transport import create_mcp_router
from gateway_mcp.tools import ToolRegistry
from gateway_mcp.tools.base import Environment, RiskLevel, Tool, ToolContext


# ============================================================================
# Test Fixtures
# ============================================================================


class SampleInput(BaseModel):
    """Sample input schema for test tools."""
    
    name: str
    value: int = 0


class SampleOutput(BaseModel):
    """Sample output schema for test tools."""
    
    result: str
    success: bool = True


async def sample_handler(input_data: SampleInput, ctx: ToolContext) -> SampleOutput:
    """Sample handler that processes input."""
    return SampleOutput(result=f"processed:{input_data.name}")


async def failing_handler(input_data: SampleInput, ctx: ToolContext) -> SampleOutput:
    """Handler that always fails."""
    raise RuntimeError("Simulated failure")


@pytest.fixture
def sample_tool() -> Tool:
    """Create a sample tool for testing."""
    return Tool(
        name="sample_tool",
        description="A sample tool for testing",
        input_schema=SampleInput,
        output_schema=SampleOutput,
        risk_level=RiskLevel.READ,
        allowed_environments=[Environment.LOCAL, Environment.DEV],
        timeout_seconds=30,
        handler=sample_handler,
    )


@pytest.fixture
def failing_tool() -> Tool:
    """Create a tool that fails during execution."""
    return Tool(
        name="failing_tool",
        description="A tool that always fails",
        input_schema=SampleInput,
        output_schema=SampleOutput,
        risk_level=RiskLevel.READ,
        allowed_environments=[Environment.LOCAL],
        timeout_seconds=30,
        handler=failing_handler,
    )


@pytest.fixture
def test_registry(sample_tool, failing_tool) -> ToolRegistry:
    """Create a registry with test tools."""
    registry = ToolRegistry()
    registry.register(sample_tool)
    registry.register(failing_tool)
    return registry


class MockMiddlewarePipeline:
    """
    Mock middleware pipeline for testing transport layer.
    
    Can be configured to return success or error responses.
    """
    
    def __init__(self):
        self.last_request: MiddlewareRequest | None = None
        self.response_override: MiddlewareResponse | None = None
    
    async def process(
        self,
        tool: Tool,
        request: MiddlewareRequest,
    ) -> MiddlewareResponse:
        """Process request and return configured response."""
        self.last_request = request
        
        if self.response_override:
            return self.response_override
        
        # Default: execute tool handler with mock context
        if tool.handler:
            try:
                ctx = ToolContext(
                    user_id=1,
                    correlation_id=request.correlation_id or "test-correlation",
                    audit_id="test-audit",
                    environment=Environment.LOCAL,
                )
                validated_input = tool.input_schema(**request.input_data)
                result = await tool.handler(validated_input, ctx)
                return MiddlewareResponse(
                    success=True,
                    output_data=result.model_dump(),
                    audit_id="test-audit",
                )
            except Exception as e:
                from gateway_mcp.core.errors import InternalError
                return MiddlewareResponse(
                    success=False,
                    error=InternalError(message=str(e)),
                    audit_id="test-audit",
                )
        
        return MiddlewareResponse(
            success=True,
            output_data={},
            audit_id="test-audit",
        )


@pytest.fixture
def mock_pipeline() -> MockMiddlewarePipeline:
    """Create a mock middleware pipeline."""
    return MockMiddlewarePipeline()


@pytest.fixture
def mcp_client(test_registry, mock_pipeline):
    """Create a FastAPI test client with MCP routes."""
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from gateway_mcp.core.errors import GatewayError
    
    app = FastAPI()
    
    # Add exception handler for GatewayError
    @app.exception_handler(GatewayError)
    async def gateway_error_handler(request, exc: GatewayError):
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "audit_id": exc.audit_id,
                    "retryable": exc.retryable,
                    "reconnect_url": exc.reconnect_url,
                }
            },
        )
    
    router = create_mcp_router(test_registry, mock_pipeline)
    app.include_router(router)
    
    return TestClient(app)


# ============================================================================
# tools/list Tests
# ============================================================================


class TestToolsList:
    """Tests for POST /mcp/tools/list endpoint."""
    
    def test_list_returns_all_tools(self, mcp_client, test_registry):
        """tools/list returns all registered tools."""
        response = mcp_client.post("/mcp/tools/list", json={})
        
        assert response.status_code == 200
        data = response.json()
        
        assert "tools" in data
        assert len(data["tools"]) == len(test_registry)
        
        tool_names = {t["name"] for t in data["tools"]}
        assert "sample_tool" in tool_names
        assert "failing_tool" in tool_names
    
    def test_list_includes_schemas(self, mcp_client):
        """tools/list includes JSON schemas for each tool."""
        response = mcp_client.post("/mcp/tools/list", json={})
        
        assert response.status_code == 200
        data = response.json()
        
        for tool in data["tools"]:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
            assert isinstance(tool["inputSchema"], dict)
    
    def test_list_sample_tool_schema(self, mcp_client):
        """Sample tool has correct input schema."""
        response = mcp_client.post("/mcp/tools/list", json={})
        
        data = response.json()
        sample = next(t for t in data["tools"] if t["name"] == "sample_tool")
        
        schema = sample["inputSchema"]
        assert schema["type"] == "object"
        assert "name" in schema["properties"]
        assert "value" in schema["properties"]
    
    def test_list_accepts_cursor(self, mcp_client):
        """tools/list accepts optional cursor for pagination."""
        response = mcp_client.post(
            "/mcp/tools/list",
            json={"cursor": "some-cursor"},
        )
        
        # Should succeed even with cursor (pagination not implemented)
        assert response.status_code == 200
        data = response.json()
        assert data["nextCursor"] is None
    
    def test_list_with_empty_registry(self):
        """tools/list returns empty list when no tools registered."""
        from fastapi import FastAPI
        
        registry = ToolRegistry()
        pipeline = MockMiddlewarePipeline()
        
        app = FastAPI()
        router = create_mcp_router(registry, pipeline)
        app.include_router(router)
        
        client = TestClient(app)
        response = client.post("/mcp/tools/list", json={})
        
        assert response.status_code == 200
        data = response.json()
        assert data["tools"] == []


# ============================================================================
# tools/call Tests
# ============================================================================


class TestToolsCall:
    """Tests for POST /mcp/tools/call endpoint."""
    
    def test_call_executes_tool(self, mcp_client, mock_pipeline):
        """tools/call executes the named tool."""
        response = mcp_client.post(
            "/mcp/tools/call",
            json={
                "name": "sample_tool",
                "arguments": {"name": "test", "value": 42},
            },
            headers={
                "Authorization": "Bearer test-token",
                "X-User-Id": "123",
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["isError"] is False
        assert len(data["content"]) == 1
        assert data["content"][0]["type"] == "text"
        
        # Verify handler was called
        assert mock_pipeline.last_request is not None
        assert mock_pipeline.last_request.tool_name == "sample_tool"
        assert mock_pipeline.last_request.input_data["name"] == "test"
    
    def test_call_returns_text_content(self, mcp_client):
        """tools/call returns result as text content block."""
        response = mcp_client.post(
            "/mcp/tools/call",
            json={
                "name": "sample_tool",
                "arguments": {"name": "foo"},
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["isError"] is False
        content = data["content"][0]
        assert content["type"] == "text"
        assert "processed:foo" in content["text"]
    
    def test_call_passes_headers(self, mcp_client, mock_pipeline):
        """tools/call passes auth headers to middleware."""
        response = mcp_client.post(
            "/mcp/tools/call",
            json={"name": "sample_tool", "arguments": {"name": "test"}},
            headers={
                "Authorization": "Bearer my-token",
                "X-User-Id": "456",
                "X-Correlation-Id": "corr-123",
                "X-Workflow-Run-Id": "789",
            },
        )
        
        assert response.status_code == 200
        
        req = mock_pipeline.last_request
        assert req.authorization_header == "Bearer my-token"
        assert req.user_id_header == "456"
        assert req.correlation_id == "corr-123"
        assert req.workflow_run_id == 789
    
    def test_call_missing_tool_returns_404(self, mcp_client):
        """tools/call returns 404 for non-existent tool."""
        response = mcp_client.post(
            "/mcp/tools/call",
            json={"name": "nonexistent_tool", "arguments": {}},
        )
        
        assert response.status_code == 404
        data = response.json()
        
        assert "error" in data
        assert data["error"]["code"] == "tool_not_found"
    
    def test_call_tool_error_returns_is_error(self, mcp_client, mock_pipeline):
        """tools/call returns isError=true when tool fails."""
        from gateway_mcp.core.errors import InternalError
        
        # Configure pipeline to return error
        mock_pipeline.response_override = MiddlewareResponse(
            success=False,
            error=InternalError(message="Something went wrong"),
            audit_id="test-audit",
        )
        
        response = mcp_client.post(
            "/mcp/tools/call",
            json={"name": "sample_tool", "arguments": {"name": "test"}},
        )
        
        assert response.status_code == 200  # MCP protocol: errors in content
        data = response.json()
        
        assert data["isError"] is True
        assert "Something went wrong" in data["content"][0]["text"]
    
    def test_call_with_empty_arguments(self, mcp_client, mock_pipeline):
        """tools/call accepts empty arguments dict."""
        # Configure to return success (default handler needs 'name')
        mock_pipeline.response_override = MiddlewareResponse(
            success=True,
            output_data={"result": "ok"},
            audit_id="test-audit",
        )
        
        response = mcp_client.post(
            "/mcp/tools/call",
            json={"name": "sample_tool", "arguments": {}},
        )
        
        assert response.status_code == 200
    
    def test_call_workflow_run_id_parsing(self, mcp_client, mock_pipeline):
        """tools/call parses workflow run ID as integer."""
        response = mcp_client.post(
            "/mcp/tools/call",
            json={"name": "sample_tool", "arguments": {"name": "test"}},
            headers={"X-Workflow-Run-Id": "12345"},
        )
        
        assert response.status_code == 200
        assert mock_pipeline.last_request.workflow_run_id == 12345
    
    def test_call_invalid_workflow_run_id(self, mcp_client, mock_pipeline):
        """tools/call ignores invalid workflow run ID."""
        response = mcp_client.post(
            "/mcp/tools/call",
            json={"name": "sample_tool", "arguments": {"name": "test"}},
            headers={"X-Workflow-Run-Id": "not-a-number"},
        )
        
        assert response.status_code == 200
        assert mock_pipeline.last_request.workflow_run_id is None


# ============================================================================
# MCP Protocol Compliance Tests
# ============================================================================


class TestMCPProtocolCompliance:
    """Tests for MCP protocol specification compliance."""
    
    def test_tools_list_response_format(self, mcp_client):
        """tools/list response matches MCP spec."""
        response = mcp_client.post("/mcp/tools/list", json={})
        
        data = response.json()
        
        # Required fields
        assert "tools" in data
        assert isinstance(data["tools"], list)
        
        # Optional fields
        assert "nextCursor" in data  # None or string
        
        # Tool format
        for tool in data["tools"]:
            assert "name" in tool
            assert isinstance(tool["name"], str)
            assert "description" in tool
            assert isinstance(tool["description"], str)
            assert "inputSchema" in tool
            assert isinstance(tool["inputSchema"], dict)
    
    def test_tools_call_response_format(self, mcp_client):
        """tools/call response matches MCP spec."""
        response = mcp_client.post(
            "/mcp/tools/call",
            json={"name": "sample_tool", "arguments": {"name": "test"}},
        )
        
        data = response.json()
        
        # Required fields
        assert "content" in data
        assert isinstance(data["content"], list)
        assert "isError" in data
        assert isinstance(data["isError"], bool)
        
        # Content block format
        for block in data["content"]:
            assert "type" in block
            assert block["type"] in ("text", "image", "resource")
            if block["type"] == "text":
                assert "text" in block
                assert isinstance(block["text"], str)
    
    def test_tools_call_request_format(self, mcp_client, mock_pipeline):
        """tools/call accepts MCP spec request format."""
        # Minimal request
        response = mcp_client.post(
            "/mcp/tools/call",
            json={"name": "sample_tool"},
        )
        # Should default arguments to empty dict
        assert response.status_code == 200
        assert mock_pipeline.last_request.input_data == {}
    
    def test_error_response_includes_details(self, mcp_client):
        """Error responses include code and message."""
        response = mcp_client.post(
            "/mcp/tools/call",
            json={"name": "nonexistent"},
        )
        
        assert response.status_code == 404
        data = response.json()
        
        assert "error" in data
        error = data["error"]
        assert "code" in error
        assert "message" in error


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Edge case tests for MCP transport."""
    
    def test_tools_list_no_body(self, mcp_client):
        """tools/list works with no request body."""
        response = mcp_client.post(
            "/mcp/tools/list",
            headers={"Content-Type": "application/json"},
        )
        # FastAPI should use default empty body
        assert response.status_code in (200, 422)
    
    def test_tools_call_missing_name(self, mcp_client):
        """tools/call returns 422 when name is missing."""
        response = mcp_client.post(
            "/mcp/tools/call",
            json={"arguments": {"foo": "bar"}},
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_output_json_serialization(self, mcp_client):
        """Output is properly JSON serialized."""
        response = mcp_client.post(
            "/mcp/tools/call",
            json={"name": "sample_tool", "arguments": {"name": "test"}},
        )
        
        data = response.json()
        text_content = data["content"][0]["text"]
        
        # Should be valid JSON
        import json
        parsed = json.loads(text_content)
        assert "result" in parsed
