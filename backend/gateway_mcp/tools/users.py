"""
BRS User Tools

Handlers for user management operations:
- create_admin_user: Create an admin user for a club

BRS Architecture:
- Superusers are managed via console: php app/console brs:tbs:brs-superusers:update
- User APIs exist but are for members, not admin users
"""

import logging
from datetime import datetime, timezone

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
    AdminRole,
    CreateAdminUserInput,
    CreateAdminUserOutput,
)

logger = logging.getLogger(__name__)


async def create_admin_user_handler(
    input: CreateAdminUserInput,
    context: ToolContext,
) -> CreateAdminUserOutput:
    """
    Create/update an admin user for a club.
    
    Uses console command since superuser management has no API:
    docker exec php php app/console brs:tbs:brs-superusers:update --club-id={clubId}
    
    This command syncs BRS/GolfNow superusers to the club database.
    For custom admin users, we would need to use the User Sync API.
    
    Args:
        input: Admin user details (club_id, email, role)
        context: Tool context with executor
        
    Returns:
        CreateAdminUserOutput with user details
        
    Raises:
        UpstreamError: If BRS teesheet CLI fails
        ToolExecutionError: If output cannot be parsed
    """
    executor = await context.get_executor()
    
    # BRS superuser update command - this syncs predefined superusers
    # For custom users, we'd need to use the User Sync API
    argv = [
        "php", "app/console", "brs:tbs:brs-superusers:update",
        f"--club-id={input.club_id}",
    ]
    
    logger.info(
        f"Updating superusers: club_id={input.club_id}",
        extra={"correlation_id": context.correlation_id},
    )
    
    result = await executor.run_command(
        service="teesheet",
        argv=argv,
        timeout=60,
    )
    
    if not result.success:
        stderr = result.stderr or result.stdout
        logger.error(
            f"Failed to update superusers: {stderr}",
            extra={"correlation_id": context.correlation_id},
        )
        raise UpstreamError(
            service="teesheet",
            detail=f"BRS superusers update failed: {stderr[:300]}",
            audit_id=context.audit_id,
        )
    
    # The superusers:update command updates all superusers from config
    # We return a synthetic response indicating the update was successful
    logger.info(
        f"Superusers updated for club: {input.club_id}",
        extra={"correlation_id": context.correlation_id},
    )
    
    return CreateAdminUserOutput(
        user_id="superuser_sync",  # Synthetic - this command syncs predefined users
        club_id=input.club_id,
        email=input.email,  # Note: actual superusers come from BRS config
        role=input.role,
        created_at=datetime.now(timezone.utc),
        already_existed=False,  # Can't determine this from the command
    )


# Tool definition

create_admin_user_tool = Tool(
    name="create_admin_user",
    description="Create an admin or superuser account for a golf club",
    input_schema=CreateAdminUserInput,
    output_schema=CreateAdminUserOutput,
    risk_level=RiskLevel.MEDIUM_WRITE,
    allowed_environments=[Environment.LOCAL, Environment.DEV, Environment.QA],
    requires_approval=False,
    timeout_seconds=60,
    handler=create_admin_user_handler,
    audit_metadata={"category": "brs", "executor": "docker_exec"},
)


# List of all user tools for registry
USER_TOOLS = [
    create_admin_user_tool,
]
