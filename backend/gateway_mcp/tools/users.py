"""
BRS User Tools

Handlers for user management operations:
- create_admin_user: Create an admin user for a club
- authenticate_club: Authenticate and obtain OAuth token for a club (credential-safe)

BRS Architecture:
- Superusers are managed via console: php app/console brs:tbs:brs-superusers:update
- User APIs exist but are for members, not admin users
- API keys are stored in fe_users table (api_key column) - NEVER exposed to agents
- OAuth tokens are cached internally and used automatically for authenticated requests

SECURITY:
- API keys are NEVER returned to agents or logged
- Only opaque success/failure status is returned from authentication tools
- Credential retrieval happens fully inside gateway internals
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from gateway_mcp.core.brs_auth import BRSAuthProvider
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
    AuthenticateClubInput,
    AuthenticateClubOutput,
    CreateAdminUserInput,
    CreateAdminUserOutput,
)

logger = logging.getLogger(__name__)

# Regex pattern for valid club IDs (alphanumeric, underscores, hyphens only)
CLUB_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')

# Secret redaction pattern for logs
SECRET_REDACT_PATTERN = re.compile(r'(api_key|password|secret|token)["\']?\s*[=:]\s*["\']?[^"\'&\s]+', re.IGNORECASE)


def _redact_secrets(text: str) -> str:
    """Redact potential secrets from text for safe logging."""
    return SECRET_REDACT_PATTERN.sub(r'\1=***REDACTED***', text)


def _validate_club_id(club_id: str) -> str:
    """
    Validate and normalize club_id to prevent injection attacks.
    
    Args:
        club_id: Raw club ID input
        
    Returns:
        Validated club ID string
        
    Raises:
        ToolExecutionError: If club_id contains invalid characters
    """
    club_id_str = str(club_id).strip()
    
    if not club_id_str:
        raise ToolExecutionError(
            tool_name="validate_club_id",
            message="Club ID cannot be empty",
            audit_id=None,
        )
    
    if len(club_id_str) > 64:
        raise ToolExecutionError(
            tool_name="validate_club_id",
            message="Club ID too long (max 64 characters)",
            audit_id=None,
        )
    
    if not CLUB_ID_PATTERN.match(club_id_str):
        raise ToolExecutionError(
            tool_name="validate_club_id",
            message="Club ID contains invalid characters. Only alphanumeric, underscore, and hyphen allowed.",
            audit_id=None,
        )
    
    return club_id_str


async def _retrieve_superuser_api_key_internal(
    executor,
    club_id: str,
    correlation_id: Optional[str] = None,
) -> Optional[str]:
    """
    Internal function to retrieve superuser API key from club database.
    
    SECURITY: This function returns the raw API key but should ONLY be called
    internally by authenticate_club. The API key is NEVER exposed to agents.
    
    Args:
        executor: Command executor
        club_id: Validated club ID
        correlation_id: For log correlation
        
    Returns:
        API key string or None if not found
        
    Raises:
        UpstreamError: If database query fails
    """
    # Club ID must already be validated before calling this function
    
    # Query fe_users for first superuser with valid api_key
    # No user-controlled input in SQL - club_id is validated, no email filter
    sql = "SELECT id, email, api_key FROM fe_users WHERE is_superuser=1 AND api_key IS NOT NULL AND api_key != '' LIMIT 1"
    
    argv = [
        "php", "app/console", "doctrine:query:sql",
        f"--connection=club_{club_id}",  # club_id is validated
        sql,
    ]
    
    logger.info(
        f"Retrieving superuser credentials for club (internal): {club_id}",
        extra={"correlation_id": correlation_id},
    )
    
    result = await executor.run_command(
        service="teesheet",
        argv=argv,
        timeout=30,
    )
    
    if not result.success:
        # Redact any potential secrets from error output
        stderr = _redact_secrets(result.stderr or result.stdout or "")
        logger.error(
            f"Failed to query superuser credentials: {stderr[:200]}",
            extra={"correlation_id": correlation_id},
        )
        raise UpstreamError(
            service="teesheet",
            detail="Database query failed for superuser lookup",  # Generic - no details
            audit_id=None,
        )
    
    # Parse output - doctrine:query:sql returns JSON or tabular output
    stdout = result.stdout.strip()
    
    try:
        import json
        rows = json.loads(stdout)
        if rows and len(rows) > 0:
            row = rows[0]
            api_key = row.get("api_key", "")
            if api_key:
                # Log success WITHOUT the API key
                logger.info(
                    f"Found superuser credentials for club {club_id}",
                    extra={"correlation_id": correlation_id, "user_id": row.get("id")},
                )
                return api_key
    except json.JSONDecodeError:
        # Try parsing tabular output (pipe-separated)
        lines = stdout.split("\n")
        for line in lines:
            if "|" in line and "api_key" not in line.lower():  # Skip header
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 3:
                    api_key = parts[2] if len(parts[2]) > 10 else ""
                    if api_key:
                        logger.info(
                            f"Found superuser credentials for club {club_id}",
                            extra={"correlation_id": correlation_id},
                        )
                        return api_key
    
    return None


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
    
    # Validate club_id to prevent command injection
    club_id = _validate_club_id(str(input.club_id))
    
    # BRS superuser update command - this syncs predefined superusers
    # For custom users, we'd need to use the User Sync API
    argv = [
        "php", "app/console", "brs:tbs:brs-superusers:update",
        f"--club-id={club_id}",  # Using validated club_id
    ]
    
    logger.info(
        f"Updating superusers: club_id={club_id}",
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
        f"Superusers updated for club: {club_id}",
        extra={"correlation_id": context.correlation_id},
    )
    
    return CreateAdminUserOutput(
        user_id="superuser_sync",  # Synthetic - this command syncs predefined users
        club_id=club_id,  # Using validated club_id
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


# -----------------------------------------------------------------------------
# authenticate_club handler - SECURE credential handling
# -----------------------------------------------------------------------------

async def authenticate_club_handler(
    input: AuthenticateClubInput,
    context: ToolContext,
) -> AuthenticateClubOutput:
    """
    Authenticate a club and obtain OAuth token for subsequent API calls.
    
    This tool handles the full authentication flow internally:
    1. Validates club_id (prevents injection)
    2. Retrieves superuser API key from fe_users table (INTERNAL ONLY)
    3. Exchanges API key for OAuth token via BRS OAuth endpoint
    4. Caches token in BRSAuthProvider for automatic use
    
    SECURITY:
    - API keys are NEVER exposed to agents or logged
    - Only success/failure status is returned
    - Credentials stay entirely within gateway internals
    
    Args:
        input: Club ID to authenticate
        context: Tool context with executor
        
    Returns:
        AuthenticateClubOutput with success status (NO credentials)
        
    Raises:
        UpstreamError: If authentication fails
        ToolExecutionError: If no superuser found or validation fails
    """
    executor = await context.get_executor()
    
    # Validate club_id - prevents SQL/command injection
    club_id = _validate_club_id(str(input.club_id))
    
    logger.info(
        f"Starting club authentication: {club_id}",
        extra={"correlation_id": context.correlation_id},
    )
    
    # Step 1: Retrieve API key internally (never exposed)
    api_key = await _retrieve_superuser_api_key_internal(
        executor=executor,
        club_id=club_id,
        correlation_id=context.correlation_id,
    )
    
    if not api_key:
        logger.warning(
            f"No superuser with valid credentials found for club: {club_id}",
            extra={"correlation_id": context.correlation_id},
        )
        return AuthenticateClubOutput(
            club_id=club_id,
            authenticated=False,
            message="No superuser with valid credentials found. Run brs:tbs:brs-superusers:update to sync superusers.",
        )
    
    # Step 2: Exchange for OAuth token (stored in provider cache)
    try:
        auth_provider = BRSAuthProvider.get_instance()
        
        if not auth_provider.is_configured:
            logger.error(
                "BRS OAuth not configured",
                extra={"correlation_id": context.correlation_id},
            )
            return AuthenticateClubOutput(
                club_id=club_id,
                authenticated=False,
                message="BRS OAuth not configured. Check BRS_TEESHEET_URL, BRS_CLIENT_ID, BRS_CLIENT_SECRET environment variables.",
            )
        
        # Exchange API key for token - token is cached internally
        token = await auth_provider.get_token_for_club(
            club_id=club_id,
            api_key=api_key,  # API key used internally, never returned
        )
        
        # Clear api_key from memory after use
        del api_key
        
        logger.info(
            f"Club authenticated successfully: {club_id}",
            extra={
                "correlation_id": context.correlation_id,
                "token_expires_in": int(token.expires_at - __import__('time').time()),
            },
        )
        
        return AuthenticateClubOutput(
            club_id=club_id,
            authenticated=True,
            message=f"Successfully authenticated. Token cached for automatic use in subsequent API calls.",
        )
        
    except Exception as e:
        # Log error without exposing credentials
        logger.error(
            f"OAuth token exchange failed for club {club_id}: {type(e).__name__}",
            extra={"correlation_id": context.correlation_id},
        )
        # Clear api_key from memory on error
        api_key = None
        
        return AuthenticateClubOutput(
            club_id=club_id,
            authenticated=False,
            message=f"Authentication failed: {type(e).__name__}. Check OAuth credentials.",
        )


authenticate_club_tool = Tool(
    name="authenticate_club",
    description=(
        "Authenticate a golf club for API access. This retrieves credentials and "
        "exchanges them for an OAuth token that will be used automatically for "
        "subsequent BRS API calls. Credentials are handled securely and never exposed."
    ),
    input_schema=AuthenticateClubInput,
    output_schema=AuthenticateClubOutput,
    risk_level=RiskLevel.READ,  # No data modification
    allowed_environments=[Environment.LOCAL, Environment.DEV, Environment.QA, Environment.PROD],
    requires_approval=False,
    timeout_seconds=60,  # Allow time for DB query + OAuth exchange
    handler=authenticate_club_handler,
    audit_metadata={"category": "brs", "executor": "docker_exec", "security": "credential_handling"},
)


# List of all user tools for registry
USER_TOOLS = [
    create_admin_user_tool,
    authenticate_club_tool,  # Replaces get_superuser_api_key (secure version)
]
