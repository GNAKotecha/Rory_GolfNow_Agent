"""
MCP Protocol Transport

Implements MCP HTTP/SSE transport layer per MCP specification.

Routes:
- POST /mcp/tools/list - List available tools in MCP format
- POST /mcp/tools/call - Execute a tool and return result

The transport layer:
1. Parses MCP JSON-RPC requests
2. Routes to appropriate tool via ToolRegistry
3. Processes through middleware pipeline
4. Formats responses per MCP protocol
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

from gateway_mcp.core.errors import GatewayError, ToolNotFoundError, ValidationError
from gateway_mcp.core.middleware import MiddlewarePipeline, MiddlewareRequest
from gateway_mcp.tools import ToolRegistry

logger = logging.getLogger(__name__)


# ============================================================================
# MCP Protocol Models
# ============================================================================


class MCPToolSchema(BaseModel):
    """MCP tool definition format."""
    
    name: str
    description: str
    inputSchema: dict[str, Any]


class MCPToolsListRequest(BaseModel):
    """Request body for tools/list endpoint."""
    
    # MCP spec allows optional cursor for pagination
    cursor: Optional[str] = None


class MCPToolsListResponse(BaseModel):
    """Response body for tools/list endpoint."""
    
    tools: list[MCPToolSchema]
    # Optional cursor for pagination (not implemented yet)
    nextCursor: Optional[str] = None


class MCPToolCallRequest(BaseModel):
    """Request body for tools/call endpoint."""
    
    name: str = Field(..., description="Name of the tool to call")
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments to pass to the tool",
    )


class MCPToolCallResponse(BaseModel):
    """Response body for tools/call endpoint."""
    
    content: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Tool output content blocks",
    )
    isError: bool = Field(
        default=False,
        description="Whether the tool execution resulted in an error",
    )


class MCPErrorResponse(BaseModel):
    """MCP error response format."""
    
    code: str
    message: str
    data: Optional[dict[str, Any]] = None


# ============================================================================
# Transport Router
# ============================================================================


def create_mcp_router(
    registry: ToolRegistry,
    pipeline: MiddlewarePipeline,
) -> APIRouter:
    """
    Create FastAPI router with MCP transport routes.
    
    Args:
        registry: Tool registry with registered tools
        pipeline: Middleware pipeline for tool execution
        
    Returns:
        FastAPI APIRouter with MCP routes
    """
    router = APIRouter(prefix="/mcp", tags=["mcp"])
    
    @router.post("/tools/list", response_model=MCPToolsListResponse)
    async def tools_list(
        request: MCPToolsListRequest = MCPToolsListRequest(),
    ) -> MCPToolsListResponse:
        """
        List all available tools in MCP format.
        
        Per MCP spec, returns tool definitions with JSON Schema input schemas.
        Pagination via cursor is accepted but not yet implemented.
        """
        tools = registry.to_mcp_list()
        
        return MCPToolsListResponse(
            tools=[
                MCPToolSchema(
                    name=t["name"],
                    description=t["description"],
                    inputSchema=t["inputSchema"],
                )
                for t in tools
            ],
            nextCursor=None,  # Pagination not implemented
        )
    
    @router.post("/tools/call", response_model=MCPToolCallResponse)
    async def tools_call(
        body: MCPToolCallRequest,
        request: Request,
        authorization: Optional[str] = Header(None),
        x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
        x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id"),
        x_workflow_run_id: Optional[str] = Header(None, alias="X-Workflow-Run-Id"),
    ) -> MCPToolCallResponse:
        """
        Execute a tool and return the result.
        
        Headers:
        - Authorization: Bearer service token
        - X-User-Id: User ID for audit
        - X-Correlation-Id: Optional correlation ID for tracing
        - X-Workflow-Run-Id: Optional workflow run ID for approval context
        
        Request body:
        - name: Tool name to execute
        - arguments: Tool arguments as dict
        
        Response:
        - content: Array of content blocks (text result)
        - isError: Whether execution failed
        """
        # Look up tool
        tool = registry.get(body.name)
        if tool is None:
            raise ToolNotFoundError(
                tool_name=body.name,
                audit_id=None,
            )
        
        # Parse workflow run ID
        workflow_run_id = None
        if x_workflow_run_id:
            try:
                workflow_run_id = int(x_workflow_run_id)
            except ValueError:
                pass
        
        # Build middleware request
        middleware_request = MiddlewareRequest(
            tool_name=body.name,
            input_data=body.arguments,
            authorization_header=authorization,
            user_id_header=x_user_id,
            correlation_id=x_correlation_id,
            workflow_run_id=workflow_run_id,
        )
        
        # Process through middleware pipeline
        response = await pipeline.process(tool, middleware_request)
        
        if response.success:
            # Format successful response
            return MCPToolCallResponse(
                content=[
                    {
                        "type": "text",
                        "text": _format_output(response.output_data),
                    }
                ],
                isError=False,
            )
        else:
            # Format error response - include error details in content
            error = response.error
            return MCPToolCallResponse(
                content=[
                    {
                        "type": "text",
                        "text": f"Error: {error.message}" if error else "Unknown error",
                    }
                ],
                isError=True,
            )
    
    return router


def _format_output(output_data: Optional[dict[str, Any]]) -> str:
    """
    Format tool output for MCP text content block.
    
    Args:
        output_data: Tool output dict
        
    Returns:
        Formatted string representation
    """
    import json
    
    if output_data is None:
        return "Success"
    
    return json.dumps(output_data, indent=2, default=str)


# ============================================================================
# SSE Transport (Future - Milestone 12+)
# ============================================================================
# 
# Per the Gateway MCP spec, full HTTP/SSE transport is the target.
# Current implementation: HTTP request/response only.
# 
# SSE will enable:
# - Real-time streaming of long-running tool output
# - Progress updates during workflow execution
# - Bidirectional agent<->gateway communication
#
# Implementation deferred to post-MVP. The MCP protocol compliance tests
# currently cover the HTTP request/response path only.
# ============================================================================


async def create_sse_stream():
    """
    Create SSE stream for real-time tool output.
    
    Not implemented in MVP - reserved for streaming tool output.
    Full HTTP/SSE transport is planned for Milestone 12+.
    
    Current workaround: use polling via /tools endpoint or
    webhook callbacks for long-running operations.
    """
    raise NotImplementedError(
        "SSE streaming not yet implemented. "
        "Current transport is HTTP request/response only. "
        "SSE support is planned for Milestone 12+."
    )
