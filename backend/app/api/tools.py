"""Tools discovery API endpoint."""
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
import logging

from app.services.mcp_registry import MCPToolRegistry
from app.api.auth_deps import get_approved_user
from app.models.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("", response_model=Dict[str, Any])
async def list_all_tools(
    user: User = Depends(get_approved_user)
):
    """
    List all tools available from all MCP servers.

    Returns tools from:
    - Internal MCP servers (gateway-mcp)
    - External MCP integrations (tenant-scoped)

    Response format:
    {
        "tools": [
            {
                "name": "tool_name",
                "description": "Tool description",
                "server": "server_name",
                "input_schema": {...}
            }
        ],
        "total": 42,
        "servers": ["gateway-mcp", "tenant_3_weather-mcp"]
    }
    """
    # Import here to avoid circular dependency
    from app.main import get_global_mcp_registry

    registry = get_global_mcp_registry()
    if not registry:
        raise HTTPException(status_code=503, detail="MCP registry not initialized")

    all_tools = []
    servers = []

    for server_name, client in registry.clients.items():
        servers.append(server_name)
        try:
            tools = await client.list_tools()
            for tool in tools:
                all_tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "server": server_name,
                    "input_schema": tool.input_schema
                })
        except Exception as e:
            # Log but don't fail entire request if one server fails
            logger.error(
                f"Failed to list tools from {server_name}: {e}",
                extra={"server": server_name, "error": str(e)}
            )

    return {
        "tools": all_tools,
        "total": len(all_tools),
        "servers": servers
    }
