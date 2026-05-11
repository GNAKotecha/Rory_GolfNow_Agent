"""
BRS Config Tools

Handlers for club configuration operations:
- get_club_config: Retrieve club configuration settings
"""

import logging
from typing import Any

from gateway_mcp.core.errors import (
    ToolExecutionError,
    UpstreamError,
)
from gateway_mcp.tools.base import (
    Environment,
    RiskLevel,
    Tool,
    ToolContext,
)
from gateway_mcp.tools.schemas import (
    GetClubConfigInput,
    GetClubConfigOutput,
)

logger = logging.getLogger(__name__)


async def get_club_config_handler(
    input: GetClubConfigInput,
    context: ToolContext,
) -> GetClubConfigOutput:
    """
    Retrieve club configuration settings.
    
    Fetches the current configuration for a club including:
    - Enabled modules (teesheet, memberships, payments, etc.)
    - Club-specific settings
    - Configuration version
    
    Args:
        input: Club ID to get config for
        context: Tool context with executor
        
    Returns:
        GetClubConfigOutput with modules, settings, and version
        
    Raises:
        UpstreamError: If BRS config-api fails
        ToolExecutionError: If output cannot be parsed
    """
    executor = await context.get_executor()
    
    # Use config-api to fetch configuration
    # This calls the brs-config-api service
    argv = [
        "brs-config",
        "get",
        "--club-id", str(input.club_id),
        "--output", "json",
    ]
    
    logger.debug(
        f"Fetching config for club: {input.club_id}",
        extra={"correlation_id": context.correlation_id},
    )
    
    result = await executor.run_command(
        service="config_api",
        argv=argv,
        timeout=30,
    )
    
    if not result.success:
        # Check for not found error
        if result.exit_code == 1 and "not found" in result.stderr.lower():
            raise ToolExecutionError(
                tool_name="get_club_config",
                message=f"Club {input.club_id} not found",
                audit_id=context.audit_id,
            )
        
        logger.error(
            f"Failed to get club config: {result.stderr}",
            extra={"correlation_id": context.correlation_id},
        )
        raise UpstreamError(
            service="config_api",
            detail=f"Config API failed: {result.stderr}",
            
            audit_id=context.audit_id,
        )
    
    # Parse CLI output
    import json
    try:
        data = json.loads(result.stdout)
        
        return GetClubConfigOutput(
            club_id=data.get("club_id", input.club_id),
            modules=data.get("modules", []),
            settings=data.get("settings", {}),
            version=data.get("version", data.get("config_version", 1)),
        )
    except json.JSONDecodeError:
        raise ToolExecutionError(
            tool_name="get_club_config",
            message=f"Cannot parse config API output: {result.stdout[:200]}",
            audit_id=context.audit_id,
        )


# Tool definition

get_club_config_tool = Tool(
    name="get_club_config",
    description="Retrieve configuration settings for a golf club including enabled modules",
    input_schema=GetClubConfigInput,
    output_schema=GetClubConfigOutput,
    risk_level=RiskLevel.READ,
    allowed_environments=[Environment.LOCAL, Environment.DEV, Environment.QA, Environment.PROD],
    requires_approval=False,
    timeout_seconds=30,
    handler=get_club_config_handler,
    audit_metadata={"category": "brs", "executor": "docker_exec"},
)


# List of all config tools for registry
CONFIG_TOOLS = [
    get_club_config_tool,
]
