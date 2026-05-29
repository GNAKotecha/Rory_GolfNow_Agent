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
    
    # Query fe_users for first BRS admin user with valid api_key
    # BRS admins are typically in usergroup 1 or have username starting with 'brs_'
    # Using MySQL client directly to avoid Doctrine connection issues
    database = f"brsgolf_{club_id}"
    sql = "SELECT uid, username, api_key FROM fe_users WHERE api_key IS NOT NULL AND api_key != '' AND (usergroup=1 OR username LIKE 'brs_%') LIMIT 1"
    
    # Execute via mysql client on teesheet-db container
    argv = [
        "mysql",
        "-u", "root",
        database,
        "-e", sql,
        "--batch",  # Tab-separated output
        "-N",  # No column headers
    ]
    
    logger.info(
        f"Retrieving superuser credentials for club (internal): {club_id}",
        extra={"correlation_id": correlation_id},
    )
    
    result = await executor.run_command(
        service="teesheet-db",  # Use MySQL container directly
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
            service="teesheet-db",
            detail="Database query failed for superuser lookup",  # Generic - no details
            audit_id=None,
        )
    
    # Parse MySQL batch output: tab-separated, no headers (using -N flag)
    # Format: uid\tusername\tapi_key
    stdout = result.stdout.strip()
    
    if not stdout:
        logger.info(
            f"No superuser found for club {club_id}",
            extra={"correlation_id": correlation_id},
        )
        return None
    
    # Split by tab - first line is the data row
    lines = stdout.split("\n")
    for line in lines:
        parts = line.split("\t")
        if len(parts) >= 3:
            user_id = parts[0].strip()
            username = parts[1].strip()
            api_key = parts[2].strip()
            
            if api_key and len(api_key) > 10:
                # Log success WITHOUT the API key
                logger.info(
                    f"Found superuser credentials for club {club_id}",
                    extra={"correlation_id": correlation_id, "user_id": user_id, "username": username},
                )
                return api_key
    
    return None


# Club ID to database slug mapping (for local development)
# In production, this would come from a clubs service or config
_CLUB_DATABASE_MAP = {
    "7": "brsgolfclubsales",  # Stackstown test club
    "brsgolfclubsales": "brsgolfclubsales",  # Also allow slug directly
}


def _resolve_club_slug(club_id: str) -> str:
    """
    Resolve club ID to club slug.
    
    Handles both numeric IDs (7) and slugs (brsgolfclubsales).
    Falls back to club_id if not in mapping.
    """
    return _CLUB_DATABASE_MAP.get(str(club_id), club_id)


def _resolve_database_name(club_id: str) -> str:
    """
    Resolve club ID to database name.
    
    Handles both numeric IDs (7) and slugs (brsgolfclubsales).
    Falls back to brsgolf_{club_id} if not in mapping.
    """
    slug = _resolve_club_slug(club_id)
    return f"brsgolf_{slug}"


async def _retrieve_oauth_credentials_internal(
    executor,
    club_id: str,
    correlation_id: Optional[str] = None,
) -> Optional[tuple[str, str, str, str]]:
    """
    Internal function to retrieve OAuth credentials from club database.
    
    Retrieves:
    - api_key from fe_users (api_golfnow user)
    - client_id from oauth_client (VisitorsModule: "{id}_{random_id}")
    - client_secret from oauth_client (VisitorsModule: secret field)
    - club_slug: The slug to use for OAuth URLs
    
    SECURITY: These credentials are NEVER exposed to agents.
    
    Args:
        executor: Command executor
        club_id: Validated club ID
        correlation_id: For log correlation
        
    Returns:
        Tuple of (api_key, client_id, client_secret, club_slug) or None if not found
    """
    club_slug = _resolve_club_slug(club_id)
    database = f"brsgolf_{club_slug}"
    
    logger.info(
        f"Retrieving OAuth credentials from database: {database}",
        extra={"correlation_id": correlation_id, "club_id": club_id, "club_slug": club_slug},
    )
    
    # Query 1: Get api_key from fe_users (api_golfnow or similar API user)
    api_key_sql = "SELECT api_key FROM fe_users WHERE username='api_golfnow' AND api_key IS NOT NULL AND api_key != '' LIMIT 1"
    
    result = await executor.run_command(
        service="teesheet-db",
        argv=["mysql", "-u", "root", database, "-e", api_key_sql, "--batch", "-N"],
        timeout=30,
    )
    
    if not result.success or not result.stdout.strip():
        logger.warning(f"No api_golfnow user found for {club_id}")
        return None
    
    api_key = result.stdout.strip().split("\n")[0].strip()
    
    # Query 2: Get OAuth client credentials (VisitorsModule)
    oauth_sql = "SELECT id, random_id, secret FROM oauth_client WHERE external_system_name='VisitorsModule' LIMIT 1"
    
    result = await executor.run_command(
        service="teesheet-db",
        argv=["mysql", "-u", "root", database, "-e", oauth_sql, "--batch", "-N"],
        timeout=30,
    )
    
    if not result.success or not result.stdout.strip():
        logger.warning(f"No VisitorsModule OAuth client found for {club_id}")
        return None
    
    parts = result.stdout.strip().split("\t")
    if len(parts) < 3:
        logger.warning(f"Invalid OAuth client data for {club_id}")
        return None
    
    oauth_id = parts[0].strip()
    random_id = parts[1].strip()
    client_secret = parts[2].strip()
    
    # Construct client_id as "{id}_{random_id}"
    client_id = f"{oauth_id}_{random_id}"
    
    logger.info(
        f"Retrieved OAuth credentials for club {club_id} (slug: {club_slug})",
        extra={"correlation_id": correlation_id, "oauth_client_id": oauth_id, "club_slug": club_slug},
    )
    
    return (api_key, client_id, client_secret, club_slug)


async def create_admin_user_handler(
    input: CreateAdminUserInput,
    context: ToolContext,
) -> CreateAdminUserOutput:
    """
    Create an admin user for a club via direct database insert.
    
    BRS admin users are stored in the fe_users table with usergroup=1 (superuser).
    This tool inserts directly into the database since the BRS CLI only syncs
    predefined superusers from config.
    
    Args:
        input: Admin user details (club_id, email, username, role)
        context: Tool context with executor
        
    Returns:
        CreateAdminUserOutput with user details
        
    Raises:
        UpstreamError: If database insert fails
        ToolExecutionError: If validation fails
    """
    executor = await context.get_executor()
    
    # Validate club_id to prevent injection
    club_id = _validate_club_id(str(input.club_id))
    database = f"brsgolf_{club_id}"
    
    # Validate email format
    if not input.email or "@" not in input.email:
        raise ToolExecutionError(
            tool_name="create_admin_user",
            message=f"Invalid email format: {input.email}",
            audit_id=context.audit_id,
        )
    
    # Generate a username from email if not provided
    username = input.username or input.email.split("@")[0]
    
    # Map role to usergroup (BRS convention)
    # 1 = superuser/admin, 2 = staff, 3 = member
    role_to_usergroup = {
        AdminRole.SUPERUSER: 1,
        AdminRole.ADMIN: 1,
        AdminRole.MANAGER: 2,
        AdminRole.STAFF: 2,
    }
    usergroup = role_to_usergroup.get(input.role, 1)
    
    logger.info(
        f"Creating admin user for club {club_id}: {username} ({input.email})",
        extra={
            "correlation_id": context.correlation_id,
            "role": input.role.value,
            "usergroup": usergroup,
        },
    )
    
    # Check if user already exists
    check_sql = f"SELECT uid, username FROM fe_users WHERE email = '{input.email}' LIMIT 1"
    check_result = await executor.run_command(
        service="mysql",
        argv=["mysql", "-u", "root", "-proot", "-N", "-e", check_sql, database],
        timeout=30,
    )
    
    if check_result.success and check_result.stdout and check_result.stdout.strip():
        # User exists
        parts = check_result.stdout.strip().split("\t")
        existing_uid = parts[0] if len(parts) > 0 else "unknown"
        existing_username = parts[1] if len(parts) > 1 else "unknown"
        
        logger.info(
            f"User already exists: uid={existing_uid}, username={existing_username}",
            extra={"correlation_id": context.correlation_id},
        )
        
        return CreateAdminUserOutput(
            user_id=existing_uid,
            club_id=club_id,
            email=input.email,
            role=input.role,
            created_at=datetime.now(timezone.utc),
            already_existed=True,
        )
    
    # Insert new user
    # Note: password is a placeholder - real implementation would hash it
    # The user would need to reset password on first login
    insert_sql = f"""
    INSERT INTO fe_users (username, email, usergroup, disable, name, tstamp, crdate)
    VALUES ('{username}', '{input.email}', {usergroup}, 0, '{username}', UNIX_TIMESTAMP(), UNIX_TIMESTAMP())
    """
    
    insert_result = await executor.run_command(
        service="mysql",
        argv=["mysql", "-u", "root", "-proot", "-e", insert_sql.strip(), database],
        timeout=30,
    )
    
    if not insert_result.success:
        stderr = insert_result.stderr or insert_result.stdout
        logger.error(
            f"Failed to create admin user: {stderr}",
            extra={"correlation_id": context.correlation_id},
        )
        raise UpstreamError(
            service="teesheet",
            detail=f"Failed to create admin user: {stderr[:300]}. The fe_users table may have additional required columns. Use run_sql with DESCRIBE brsgolf_{club_id}.fe_users to see the schema.",
            audit_id=context.audit_id,
        )
    
    # Get the new user's ID
    get_id_sql = f"SELECT uid FROM fe_users WHERE email = '{input.email}' ORDER BY uid DESC LIMIT 1"
    id_result = await executor.run_command(
        service="mysql",
        argv=["mysql", "-u", "root", "-proot", "-N", "-e", get_id_sql, database],
        timeout=30,
    )
    
    user_id = id_result.stdout.strip() if id_result.success and id_result.stdout else "unknown"
    
    logger.info(
        f"Admin user created: uid={user_id}, username={username}",
        extra={"correlation_id": context.correlation_id},
    )
    
    return CreateAdminUserOutput(
        user_id=user_id,
        club_id=club_id,
        email=input.email,
        role=input.role,
        created_at=datetime.now(timezone.utc),
        already_existed=False,
    )


# Tool definition

create_admin_user_tool = Tool(
    name="create_admin_user",
    description="Create an admin or superuser account for a golf club. Inserts into fe_users table with appropriate usergroup. Returns existing user if email already registered.",
    input_schema=CreateAdminUserInput,
    output_schema=CreateAdminUserOutput,
    risk_level=RiskLevel.MEDIUM_WRITE,
    allowed_environments=[Environment.LOCAL, Environment.DEV, Environment.QA],
    requires_approval=False,
    timeout_seconds=60,
    handler=create_admin_user_handler,
    audit_metadata={"category": "brs", "executor": "mysql"},
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
    2. Retrieves OAuth credentials from database (api_key, client_id, client_secret)
    3. Exchanges credentials for OAuth token via BRS OAuth endpoint
    4. Caches token in BRSAuthProvider for automatic use
    
    SECURITY:
    - Credentials are NEVER exposed to agents or logged
    - Only success/failure status is returned
    - Credentials stay entirely within gateway internals
    
    Args:
        input: Club ID to authenticate
        context: Tool context with executor
        
    Returns:
        AuthenticateClubOutput with success status (NO credentials)
        
    Raises:
        UpstreamError: If authentication fails
        ToolExecutionError: If credentials not found or validation fails
    """
    executor = await context.get_executor()
    
    # Validate club_id - prevents SQL/command injection
    club_id = _validate_club_id(str(input.club_id))
    
    logger.info(
        f"Starting club authentication: {club_id}",
        extra={"correlation_id": context.correlation_id},
    )
    
    # Step 1: Retrieve all OAuth credentials from database
    credentials = await _retrieve_oauth_credentials_internal(
        executor=executor,
        club_id=club_id,
        correlation_id=context.correlation_id,
    )
    
    if not credentials:
        logger.warning(
            f"No OAuth credentials found for club: {club_id}",
            extra={"correlation_id": context.correlation_id},
        )
        return AuthenticateClubOutput(
            club_id=club_id,
            authenticated=False,
            message="No OAuth credentials found. Ensure api_golfnow user and VisitorsModule OAuth client exist.",
        )
    
    api_key, client_id, client_secret, club_slug = credentials
    
    # Step 2: Exchange for OAuth token using dynamic credentials
    try:
        auth_provider = BRSAuthProvider.get_instance()
        
        # Check teesheet URL is configured (only env var we still need)
        if not auth_provider.teesheet_url:
            logger.error(
                "BRS teesheet URL not configured",
                extra={"correlation_id": context.correlation_id},
            )
            return AuthenticateClubOutput(
                club_id=club_id,
                authenticated=False,
                message="BRS teesheet URL not configured. Set BRS_TEESHEET_URL environment variable.",
            )
        
        # Exchange credentials for token using DB-sourced credentials
        # Use club_slug for OAuth URL (e.g., brsgolfclubsales, not 7)
        token = await auth_provider.get_token_with_credentials(
            club_id=club_slug,  # Use slug for OAuth URL
            api_key=api_key,
            client_id=client_id,
            client_secret=client_secret,
        )
        
        # Clear credentials from memory after use
        del api_key, client_id, client_secret
        
        logger.info(
            f"Club authenticated successfully: {club_id} (slug: {club_slug})",
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
        # Clear credentials from memory on error
        api_key = client_id = client_secret = None
        
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
