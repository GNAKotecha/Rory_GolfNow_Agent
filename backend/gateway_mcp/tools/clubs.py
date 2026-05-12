"""
BRS Club Tools

Handlers for club-related operations:
- create_club: Create a new golf club in the BRS system
- get_club_by_name: Look up a club by name
- verify_club_setup: Verify club configuration is complete

BRS Architecture:
- API endpoints on brs-teesheet: /{clubId}/api/v3/... and /api/admin/v1/...
- Console commands via docker exec for operations without API (create-installation, update-superusers)
- Databases: brsgolf_admin (installation cross_ref table), brsgolf_{clubId} (per-club)
"""

import logging
from datetime import datetime, timezone
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
from gateway_mcp.tools.parser import OutputParser
from gateway_mcp.tools.schemas import (
    CreateClubInput,
    CreateClubOutput,
    GetClubByNameInput,
    GetClubByNameOutput,
    VerifyClubSetupInput,
    VerifyClubSetupOutput,
)

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# create_club handler
# -----------------------------------------------------------------------------

async def create_club_handler(
    input: CreateClubInput,
    context: ToolContext,
) -> CreateClubOutput:
    """
    Create a new golf club in the BRS system.
    
    Uses console command since there's no API for club creation:
    docker exec php php app/console brs:tbs:create-installation
    
    Args:
        input: Club creation parameters (name, country, timezone, currency)
        context: Tool context with executor and credentials
        
    Returns:
        CreateClubOutput with club_id, database_name, and creation timestamp
        
    Raises:
        UpstreamError: If BRS CLI fails
        ToolExecutionError: If output cannot be parsed
    """
    executor = await context.get_executor()
    
    # Derive club_id from name (BRS convention: lowercase, underscores)
    club_id = input.name.lower().replace(" ", "_").replace("-", "_")
    # Remove non-alphanumeric except underscore
    club_id = "".join(c for c in club_id if c.isalnum() or c == "_")
    
    # Build Symfony console command for brs-teesheet
    # php app/console brs:tbs:create-installation --club-id=<id> --name=<name> ...
    argv = [
        "php", "app/console", "brs:tbs:create-installation",
        "--no-interaction",
        f"--club-id={club_id}",
        f"--name={input.name}",
        f"--country={input.country}",
        # Timezone and currency go into configuration table
        f"--latitude=54.5441561",  # Default Belfast coordinates
        f"--longitude=-5.9710524",
        "--member-module=y",
        "--visitor-module=y", 
        "--facility-module=y",
        "--mobile-enabled=y",
    ]
    
    logger.info(
        f"Creating club: name={input.name}, club_id={club_id}, country={input.country}",
        extra={"correlation_id": context.correlation_id},
    )
    
    result = await executor.run_command(
        service="teesheet",
        argv=argv,
        timeout=120,
    )
    
    if not result.success:
        stderr = result.stderr or result.stdout
        logger.error(
            f"Failed to create club: {stderr}",
            extra={"correlation_id": context.correlation_id},
        )
        raise UpstreamError(
            service="teesheet",
            detail=f"BRS create-installation failed: {stderr[:300]}",
            audit_id=context.audit_id,
        )
    
    # Parse output - look for success indicators
    stdout = result.stdout
    
    # Check for "SUCCESS" in output (from CreateTbsInstallationCommand)
    if "SUCCESS" in stdout or result.exit_code == 0:
        return CreateClubOutput(
            club_id=club_id,
            club_name=input.name,
            database_name=f"brsgolf_{club_id}",
            created_at=datetime.now(timezone.utc),
        )
    
    raise ToolExecutionError(
        tool_name="create_club",
        message=f"Unexpected output from create-installation: {stdout[:300]}",
        audit_id=context.audit_id,
    )


# -----------------------------------------------------------------------------
# get_club_by_name handler
# -----------------------------------------------------------------------------

async def get_club_by_name_handler(
    input: GetClubByNameInput,
    context: ToolContext,
) -> GetClubByNameOutput:
    """
    Look up a club by name using the BRS Admin API.
    
    Uses: GET /api/admin/v1/clubs?keyword={name}
    
    Args:
        input: Club name to search for
        context: Tool context with executor
        
    Returns:
        GetClubByNameOutput with club details or found=False
    """
    executor = await context.get_executor()
    
    logger.debug(
        f"Looking up club by name: {input.name}",
        extra={"correlation_id": context.correlation_id},
    )
    
    # Use the Admin API to search clubs
    # This calls GET /api/admin/v1/clubs?keyword={name}
    try:
        result = await executor.call_http(
            service="teesheet",  # teesheet has the URL configured
            method="GET",
            path=f"/api/admin/v1/clubs?keyword={input.name}",
        )
    except Exception as e:
        logger.error(
            f"Failed to lookup club via API: {e}",
            extra={"correlation_id": context.correlation_id},
        )
        raise UpstreamError(
            service="teesheet",
            detail=f"API call failed: {str(e)[:200]}",
            audit_id=context.audit_id,
        )
    
    if result.status_code == 404:
        return GetClubByNameOutput(found=False)
    
    if result.status_code != 200:
        raise UpstreamError(
            service="teesheet",
            detail=f"API returned {result.status_code}: {str(result.body)[:200]}",
            audit_id=context.audit_id,
        )
    
    # Parse response - API returns { data: [...] }
    data = result.body
    if isinstance(data, dict):
        clubs = data.get("data", [])
    elif isinstance(data, list):
        clubs = data
    else:
        clubs = []
    
    # Find exact match or first partial match
    matching_club = None
    for club in clubs:
        club_name = club.get("name", "") or club.get("instName", "")
        if club_name.lower() == input.name.lower():
            matching_club = club
            break
        elif input.name.lower() in club_name.lower() and not matching_club:
            matching_club = club
    
    if not matching_club:
        return GetClubByNameOutput(found=False)
    
    # Map API response fields to output schema
    # API may use camelCase (clubId) or snake_case (club_id)
    club_id = (
        matching_club.get("clubId")
        or matching_club.get("club_id")
        or matching_club.get("instClubId")
        or matching_club.get("id")
    )
    
    # Parse timestamp if present
    created_at = None
    created_str = matching_club.get("created_at") or matching_club.get("installDate")
    if created_str:
        try:
            if isinstance(created_str, str):
                created_at = datetime.fromisoformat(
                    created_str.replace("Z", "+00:00")
                )
        except (ValueError, TypeError):
            pass
    
    return GetClubByNameOutput(
        club_id=club_id,
        name=matching_club.get("name") or matching_club.get("instName"),
        country=matching_club.get("country") or matching_club.get("instCountry"),
        timezone=matching_club.get("timezone"),
        currency=matching_club.get("currency"),
        created_at=created_at,
        found=True,
    )


# -----------------------------------------------------------------------------
# verify_club_setup handler
# -----------------------------------------------------------------------------

async def verify_club_setup_handler(
    input: VerifyClubSetupInput,
    context: ToolContext,
) -> VerifyClubSetupOutput:
    """
    Verify that a club's setup is complete using BRS APIs.
    
    Checks:
    1. Club exists via /api/admin/v1/clubs?keyword={club_id}
    2. Configuration is valid via /{clubId}/api/v3/ (ClubConfigurationController)
    
    Args:
        input: Club ID to verify
        context: Tool context with executor
        
    Returns:
        VerifyClubSetupOutput with verification results and any issues found
    """
    executor = await context.get_executor()
    issues = []
    
    club_id = input.club_id
    
    logger.info(
        f"Verifying club setup: club_id={club_id}",
        extra={"correlation_id": context.correlation_id},
    )
    
    # Step 1: Check if club exists via Admin API
    club_exists = False
    try:
        result = await executor.call_http(
            service="teesheet",
            method="GET",
            path=f"/api/admin/v1/clubs?keyword={club_id}",
        )
        if result.status_code == 200:
            data = result.body
            clubs = data.get("data", []) if isinstance(data, dict) else data
            # Check for exact club_id match (supports both camelCase and snake_case)
            for club in clubs:
                found_id = (
                    club.get("clubId")
                    or club.get("club_id")
                    or club.get("instClubId")
                    or club.get("id")
                )
                if str(found_id) == str(club_id):
                    club_exists = True
                    break
    except Exception as e:
        issues.append(f"Failed to check club existence: {str(e)[:100]}")
    
    if not club_exists:
        issues.append(f"Club '{club_id}' not found in installation registry")
        return VerifyClubSetupOutput(
            club_exists=False,
            config_valid=False,
            has_admin=False,
            features_enabled=[],
            issues=issues,
        )
    
    # Step 2: Check club configuration via /{clubId}/api/v3/
    config_valid = False
    features_enabled = []
    try:
        result = await executor.call_http(
            service="teesheet",
            method="GET",
            path=f"/{club_id}/api/v3/",  # ClubConfigurationController
            club_id=str(club_id),  # Use cached per-club auth token
        )
        if result.status_code == 200:
            config_valid = True
            data = result.body
            # Extract enabled features from configuration
            if isinstance(data, dict):
                configs = data.get("configurations", {})
                if isinstance(configs, dict):
                    for key, value in configs.items():
                        if isinstance(value, str) and value.lower() in ("yes", "true", "1"):
                            if "supported" in key or "enabled" in key or "module" in key:
                                features_enabled.append(key)
        elif result.status_code == 404:
            issues.append(f"Club configuration endpoint not found for '{club_id}'")
        else:
            issues.append(f"Config API returned {result.status_code}")
    except Exception as e:
        issues.append(f"Failed to fetch club config: {str(e)[:100]}")
    
    # Step 3: Check for admin user (superusers)
    # This is harder to verify via API - we'll check if member_booking_feature_supported is set
    # as that's typically enabled when club is properly configured
    has_admin = "member_booking_feature_supported" in features_enabled
    
    if not has_admin:
        issues.append("No indication of admin user (member_booking_feature not enabled)")
    
    return VerifyClubSetupOutput(
        club_exists=club_exists,
        config_valid=config_valid,
        has_admin=has_admin,
        features_enabled=features_enabled,
        issues=issues,
    )


# -----------------------------------------------------------------------------
# Tool definitions
# -----------------------------------------------------------------------------

create_club_tool = Tool(
    name="create_club",
    description="Create a new golf club in the BRS system with database and initial configuration",
    input_schema=CreateClubInput,
    output_schema=CreateClubOutput,
    risk_level=RiskLevel.LOW_WRITE,
    allowed_environments=[Environment.LOCAL, Environment.DEV, Environment.QA],
    requires_approval=False,
    timeout_seconds=120,
    handler=create_club_handler,
    audit_metadata={"category": "brs", "executor": "docker_exec"},
)

get_club_by_name_tool = Tool(
    name="get_club_by_name",
    description="Look up a golf club by name and return its details",
    input_schema=GetClubByNameInput,
    output_schema=GetClubByNameOutput,
    risk_level=RiskLevel.READ,
    allowed_environments=[Environment.LOCAL, Environment.DEV, Environment.QA, Environment.PROD],
    requires_approval=False,
    timeout_seconds=30,
    handler=get_club_by_name_handler,
    audit_metadata={"category": "brs", "executor": "docker_exec"},
)

verify_club_setup_tool = Tool(
    name="verify_club_setup",
    description="Verify that a club's setup is complete (database, config, admin, features)",
    input_schema=VerifyClubSetupInput,
    output_schema=VerifyClubSetupOutput,
    risk_level=RiskLevel.READ,
    allowed_environments=[Environment.LOCAL, Environment.DEV, Environment.QA, Environment.PROD],
    requires_approval=False,
    timeout_seconds=60,
    handler=verify_club_setup_handler,
    audit_metadata={"category": "brs", "executor": "docker_exec"},
)


# List of all club tools for registry
CLUB_TOOLS = [
    create_club_tool,
    get_club_by_name_tool,
    verify_club_setup_tool,
]
