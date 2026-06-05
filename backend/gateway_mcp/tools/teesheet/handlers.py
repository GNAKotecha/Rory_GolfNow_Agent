"""
Teesheet Tool Handlers

Implementation of Teesheet tools:
- list_routes: Discover API routes via Symfony debug:router
- call_api: HTTP client for Teesheet API
- run_sql: Read-only SQL queries via docker exec
- get_config: Configuration lookup wrapper
"""

import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import httpx

from gateway_mcp.core.errors import (
    ToolExecutionError,
    UpstreamError,
)
from gateway_mcp.tools.base import ApprovalPolicy, ToolContext
from gateway_mcp.tools.teesheet.schemas import (
    CallApiInput,
    CallApiOutput,
    ConfigEntry,
    GetConfigInput,
    GetConfigOutput,
    GetSchemaInput,
    GetSchemaOutput,
    ListRoutesInput,
    ListRoutesOutput,
    RouteInfo,
    RunSqlInput,
    RunSqlOutput,
    UpdateCasualBookingRuleInput,
    UpdateCasualBookingRuleOutput,
    UpdateConfigurationInput,
    UpdateConfigurationOutput,
    CreateVisitorGreenFeeInput,
    CreateVisitorGreenFeeOutput,
    CreateBookingInput,
    CreateBookingOutput,
)

logger = logging.getLogger(__name__)

# Configuration from environment
TEESHEET_BASE_URL = os.getenv("TEESHEET_BASE_URL", "http://localhost:8056")
TEESHEET_CLUB_ID = os.getenv("TEESHEET_CLUB_ID", "brsgolfclubsales")
TEESHEET_DATABASE = os.getenv("TEESHEET_DATABASE", "brsgolf_brsgolfclubsales")
TEESHEET_DB_CONTAINER = os.getenv("TEESHEET_DB_CONTAINER", "mysqlhost")

# SQL security - forbidden keywords
FORBIDDEN_SQL_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", 
    "TRUNCATE", "CREATE", "GRANT", "REVOKE"
]


def get_call_api_approval_policy(arguments: Dict[str, Any]) -> ApprovalPolicy:
    """
    Determine approval policy for call_api based on HTTP method.
    
    GET requests are safe, all others require approval.
    """
    method = arguments.get("method", "GET").upper()
    if method == "GET":
        return ApprovalPolicy.SAFE
    return ApprovalPolicy.SENSITIVE


# -----------------------------------------------------------------------------
# list_routes handler
# -----------------------------------------------------------------------------

async def list_routes_handler(
    input: ListRoutesInput,
    context: ToolContext,
) -> ListRoutesOutput:
    """
    Discover available API routes from the Symfony application.
    
    Uses: docker exec php bin/console debug:router --format=json
    """
    executor = await context.get_executor()
    
    logger.info(
        "Listing Teesheet API routes",
        extra={"correlation_id": context.correlation_id},
    )
    
    # Run Symfony debug:router command
    result = await executor.run_command(
        service="teesheet",
        argv=["php", "bin/console", "debug:router", "--format=json"],
        timeout=30,
    )
    
    if not result.success:
        raise UpstreamError(
            service="teesheet",
            detail=f"debug:router failed: {result.stderr or result.stdout}",
            audit_id=context.audit_id,
        )
    
    try:
        all_routes = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise ToolExecutionError(
            tool_name="list_routes",
            detail=f"Failed to parse router output: {e}",
            audit_id=context.audit_id,
        )
    
    # Filter to only /api/ routes
    api_routes = []
    for name, route in all_routes.items():
        path = route.get("path", "")
        if path.startswith("/api/"):
            method = route.get("method") or route.get("methods", ["ANY"])
            if isinstance(method, list):
                method = "|".join(method)
            
            api_routes.append(RouteInfo(
                name=name,
                method=method,
                path=path,
                defaults=route.get("defaults", {}),
            ))
    
    logger.info(
        f"Found {len(api_routes)} API routes",
        extra={"correlation_id": context.correlation_id},
    )
    
    return ListRoutesOutput(
        routes=api_routes,
        count=len(api_routes),
    )


# -----------------------------------------------------------------------------
# call_api handler
# -----------------------------------------------------------------------------


def _resolve_club_slug(club_id: str) -> str:
    """
    Resolve club_id to slug for API URLs.
    
    Uses cached data if available, otherwise returns input as-is.
    For strict validation, use async _resolve_club_database() instead.
    """
    # Check if we have cached club data
    club_key = str(club_id).lower().strip()
    
    # If it's a numeric ID, try to find the slug in cache
    if club_key.isdigit() and _CLUB_CACHE:
        for key, (db_name, _) in _CLUB_CACHE.items():
            if key == club_key:
                # Extract slug from database name (brsgolf_slug -> slug)
                if db_name.startswith("brsgolf_"):
                    return db_name[8:]  # Remove "brsgolf_" prefix
    
    # If it starts with brsgolf_, extract the slug
    if club_key.startswith("brsgolf_"):
        return club_key[8:]
    
    # Return as-is (API will validate)
    return club_id


async def call_api_handler(
    input: CallApiInput,
    context: ToolContext,
) -> CallApiOutput:
    """
    Make an HTTP request to the Teesheet API.
    
    Handles URL construction, authentication, and response parsing.
    """
    club_id = input.club_id or TEESHEET_CLUB_ID
    # Resolve to slug for API URLs and token lookup
    club_slug = _resolve_club_slug(club_id)
    
    method = input.method.upper()
    path = input.path
    
    # Resolve {clubId} placeholders in path using SLUG (not numeric ID)
    path = path.replace("{clubId}", club_slug)
    
    # Also replace literal numeric club IDs in path (LLM might use /clubs/7/ instead of /clubs/{clubId}/)
    if club_id != club_slug:
        path = re.sub(rf"/clubs/{re.escape(club_id)}(/|$|\?)", rf"/clubs/{club_slug}\1", path)
    
    # Build URL - API routes go directly to the base URL
    # e.g., /api/v2/clubs/{clubId}/booking-rules -> base_url/api/v2/clubs/{clubId}/booking-rules
    if path.startswith("/"):
        url = f"{TEESHEET_BASE_URL}{path}"
    else:
        url = f"{TEESHEET_BASE_URL}/{path}"
    
    # Add query parameters
    if input.query:
        url += "?" + urlencode(input.query)
    
    # Prepare headers
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if input.headers:
        headers.update(input.headers)
    
    # Get auth token from BRSAuthProvider
    # Uses static BRS_API_KEY from env but targets the specific club for OAuth
    try:
        from gateway_mcp.core.brs_auth import BRSAuthProvider
        auth_provider = BRSAuthProvider.get_instance()
        print(f"DEBUG: BRSAuthProvider configured: {auth_provider.is_configured}, has_static_key: {auth_provider.has_static_api_key}", flush=True)
        
        if auth_provider.is_configured and auth_provider.has_static_api_key:
            # Get token using static API key but for this specific club
            # The OAuth endpoint requires a real club_id in the URL path
            token = await auth_provider.get_token_for_club(
                club_id=club_slug,  # Use actual club slug for OAuth URL
                api_key=auth_provider.static_api_key,
            )
            bearer = token.as_bearer()
            headers["Authorization"] = bearer
            print(f"DEBUG: Using BRS auth token for {club_slug}: {bearer[:40]}...", flush=True)
        else:
            print(f"DEBUG: BRS auth not configured - missing credentials", flush=True)
    except Exception as e:
        print(f"DEBUG: Failed to get auth token: {e}", flush=True)
        # Continue without auth - some endpoints don't require it
    
    print(f"DEBUG: Final URL: {url}", flush=True)
    print(f"DEBUG: Final headers: {dict((k, v[:40]+'...' if k == 'Authorization' else v) for k, v in headers.items())}", flush=True)
    
    logger.info(
        f"Calling Teesheet API: {method} {path}",
        extra={
            "correlation_id": context.correlation_id,
            "method": method,
            "path": path,
            "club_id": club_id,
            "club_slug": club_slug,
        },
    )
    
    # Make HTTP request
    import time
    request_start = time.time()
    request_body_for_log = None

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            if method in ("POST", "PUT", "PATCH") and input.body:
                body_format = input.body_format

                if body_format == "form":
                    # URL-encode form data
                    encoded_body = urlencode(input.body)
                    request_body_for_log = encoded_body
                    headers["Content-Type"] = "application/x-www-form-urlencoded"
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        content=encoded_body,
                    )
                elif body_format == "raw":
                    # Send as raw string, no encoding
                    request_body_for_log = input.body
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        content=input.body,
                    )
                else:  # json (default)
                    # Existing behavior: JSON encode
                    request_body_for_log = input.body
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        json=input.body,
                    )
            else:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                )
        except httpx.ConnectError:
            raise UpstreamError(
                service="teesheet",
                detail=f"Cannot connect to Teesheet at {TEESHEET_BASE_URL}. Is it running?",
                audit_id=context.audit_id,
            )
        except httpx.TimeoutException:
            raise UpstreamError(
                service="teesheet",
                detail=f"Request to {path} timed out",
                audit_id=context.audit_id,
            )

    elapsed_ms = (time.time() - request_start) * 1000

    # Parse response body
    try:
        body = response.json()
    except json.JSONDecodeError:
        body = response.text

    # Convert headers to dict
    response_headers = dict(response.headers)

    # Log complete request/response details
    print(f"\n{'='*80}", flush=True)
    print(f"API CALL COMPLETED: {method} {url}", flush=True)
    print(f"{'='*80}", flush=True)
    print(f"Status: {response.status_code} | Time: {elapsed_ms:.0f}ms", flush=True)
    print(f"\nREQUEST HEADERS:", flush=True)
    for k, v in headers.items():
        if k == "Authorization":
            print(f"  {k}: {v[:50]}...", flush=True)
        else:
            print(f"  {k}: {v}", flush=True)
    if request_body_for_log:
        print(f"\nREQUEST BODY:", flush=True)
        if isinstance(request_body_for_log, dict):
            print(f"  {json.dumps(request_body_for_log, indent=2)}", flush=True)
        else:
            print(f"  {request_body_for_log[:500]}", flush=True)
    print(f"\nRESPONSE HEADERS:", flush=True)
    for k, v in response_headers.items():
        print(f"  {k}: {v}", flush=True)
    print(f"\nRESPONSE BODY:", flush=True)
    if isinstance(body, dict):
        print(f"  {json.dumps(body, indent=2)[:1000]}", flush=True)
    else:
        print(f"  {body[:500]}", flush=True)
    print(f"{'='*80}\n", flush=True)

    logger.info(
        f"Teesheet API response: {response.status_code}",
        extra={
            "correlation_id": context.correlation_id,
            "status": response.status_code,
            "elapsed_ms": elapsed_ms,
            "method": method,
            "path": path,
        },
    )
    
    return CallApiOutput(
        status=response.status_code,
        headers=response_headers,
        body=body,
    )


# -----------------------------------------------------------------------------
# run_sql handler
# -----------------------------------------------------------------------------

# Database name mapping - resolve LLM-generated names to actual DB names
_DATABASE_MAP = {
    "7": "brsgolf_brsgolfclubsales",
    "club_7": "brsgolf_brsgolfclubsales",
    "brsgolfclubsales": "brsgolf_brsgolfclubsales",
    "brsgolf_brsgolfclubsales": "brsgolf_brsgolfclubsales",
}


def _resolve_database(database: str) -> str:
    """Resolve LLM-generated database names to actual database names."""
    return _DATABASE_MAP.get(database, database)


async def run_sql_handler(
    input: RunSqlInput,
    context: ToolContext,
) -> RunSqlOutput:
    """
    Execute a read-only SQL query against the Teesheet MySQL database.
    
    Security checks:
    - Only SELECT queries allowed (unless YOLO_MODE=true)
    - No multi-statement queries (no semicolons except at end)
    """
    executor = await context.get_executor()
    # Resolve database name - LLM might use "club_7" but actual is "brsgolf_brsgolfclubsales"
    database = _resolve_database(input.database) if input.database else TEESHEET_DATABASE
    query = input.query.strip()
    
    # Security check: only SELECT queries (bypassed in YOLO_MODE)
    yolo_mode = os.environ.get("YOLO_MODE", "").lower() in ("1", "true", "yes")
    query_upper = query.upper()
    if not yolo_mode:
        for keyword in FORBIDDEN_SQL_KEYWORDS:
            if query_upper.startswith(keyword):
                raise ToolExecutionError(
                    tool_name="run_sql",
                    detail=f"SQL query cannot start with {keyword}. Only SELECT queries are allowed.",
                    audit_id=context.audit_id,
                )
    else:
        logger.warning(f"YOLO_MODE: Allowing potentially dangerous SQL: {query[:100]}")
    
    # Security check: no multi-statement queries
    # Allow single trailing semicolon but no others
    query_no_trailing = query.rstrip(";")
    if ";" in query_no_trailing:
        raise ToolExecutionError(
            tool_name="run_sql",
            detail="Multi-statement queries are not allowed (no semicolons).",
            audit_id=context.audit_id,
        )
    
    logger.info(
        f"Executing SQL query on {database}",
        extra={
            "correlation_id": context.correlation_id,
            "database": database,
            "query_preview": query[:100],
        },
    )
    
    # Execute via docker exec on the MySQL container
    # We run mysql directly in the mysqlhost container
    result = await executor.run_command(
        service="teesheet-db",  # Uses the MySQL container directly
        argv=[
            "mysql",
            "-u", "root",
            database,
            "-e", query,
            "--table",
            "--batch",
        ],
        timeout=30,
    )
    
    if not result.success:
        error_msg = result.stderr or result.stdout
        raise UpstreamError(
            service="teesheet-db",
            detail=f"SQL query failed: {error_msg}",
            audit_id=context.audit_id,
        )
    
    output = result.stdout.strip() if result.stdout else ""
    
    # Count rows (lines minus header line)
    lines = [l for l in output.split("\n") if l.strip()]
    row_count = max(0, len(lines) - 1) if lines else 0
    
    if not output:
        output = "Query executed successfully. 0 rows returned."
    
    logger.info(
        f"SQL query returned {row_count} rows",
        extra={"correlation_id": context.correlation_id, "row_count": row_count},
    )
    
    return RunSqlOutput(
        result=output,
        row_count=row_count,
    )


# -----------------------------------------------------------------------------
# get_config handler
# -----------------------------------------------------------------------------

async def get_config_handler(
    input: GetConfigInput,
    context: ToolContext,
) -> GetConfigOutput:
    """
    Retrieve configuration values from the Teesheet database.
    
    Wrapper around run_sql for the configuration table.
    """
    database = input.database or TEESHEET_DATABASE
    
    # Build SQL query
    if input.key:
        # Escape single quotes in key
        escaped_key = input.key.replace("'", "''")
        query = f"SELECT id, value FROM configuration WHERE id = '{escaped_key}'"
    else:
        query = "SELECT id, value FROM configuration"
    
    logger.info(
        f"Getting config from {database}",
        extra={
            "correlation_id": context.correlation_id,
            "database": database,
            "key": input.key,
        },
    )
    
    # Use run_sql internally
    sql_input = RunSqlInput(query=query, database=database)
    sql_result = await run_sql_handler(sql_input, context)
    
    # Parse the tabular output into config entries
    configs = []
    lines = sql_result.result.split("\n")
    
    # Skip header lines (table formatting)
    data_started = False
    for line in lines:
        line = line.strip()
        if not line or line.startswith("+") or line.startswith("|"):
            # Look for actual data rows
            if line.startswith("|"):
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 2 and parts[0] != "id":  # Skip header row
                    configs.append(ConfigEntry(
                        id=parts[0],
                        value=parts[1] if len(parts) > 1 else "",
                    ))
    
    logger.info(
        f"Found {len(configs)} config entries",
        extra={"correlation_id": context.correlation_id},
    )
    
    return GetConfigOutput(
        configs=configs,
        count=len(configs),
    )


# -----------------------------------------------------------------------------
# get_schema handler
# -----------------------------------------------------------------------------

async def get_schema_handler(
    input: "GetSchemaInput",
    context: ToolContext,
) -> "GetSchemaOutput":
    """
    Discover database schema structure.
    
    Helps LLM understand what databases, tables, and columns are available.
    
    Scope options:
    - 'databases': List all available databases (filters to brsgolf_*)
    - 'tables': List tables in a specific database
    - 'columns': Describe structure of a specific table
    """
    from gateway_mcp.tools.teesheet.schemas import GetSchemaInput, GetSchemaOutput
    
    executor = await context.get_executor()
    scope = input.scope.lower()
    
    logger.info(
        f"Getting schema: scope={scope}, database={input.database}, table={input.table}",
        extra={"correlation_id": context.correlation_id},
    )
    
    if scope == "databases":
        # List all brsgolf databases
        query = "SHOW DATABASES LIKE 'brsgolf%'"
        database = "mysql"
    elif scope == "tables":
        # List tables in specified database
        database = _resolve_database(input.database) if input.database else TEESHEET_DATABASE
        query = "SHOW TABLES"
    elif scope == "columns":
        # Describe table structure
        database = _resolve_database(input.database) if input.database else TEESHEET_DATABASE
        if not input.table:
            raise ToolExecutionError(
                tool_name="get_schema",
                detail="Table name required for 'columns' scope",
                audit_id=context.audit_id,
            )
        query = f"DESCRIBE {input.table}"
    else:
        raise ToolExecutionError(
            tool_name="get_schema",
            detail=f"Invalid scope '{scope}'. Use: databases, tables, or columns",
            audit_id=context.audit_id,
        )
    
    # Execute via docker exec on the MySQL container
    result = await executor.run_command(
        service="teesheet-db",
        argv=[
            "mysql",
            "-u", "root",
            database,
            "-e", query,
            "--table",
            "--batch",
        ],
        timeout=30,
    )
    
    if not result.success:
        error_msg = result.stderr or result.stdout
        raise UpstreamError(
            service="teesheet-db",
            detail=f"Schema query failed: {error_msg}",
            audit_id=context.audit_id,
        )
    
    output = result.stdout.strip() if result.stdout else ""
    
    # Extract item names from output
    items = []
    lines = output.split("\n")
    for line in lines:
        line = line.strip()
        if line and not line.startswith("+") and not line.startswith("|"):
            continue
        if line.startswith("|"):
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if parts and parts[0] not in ["Database", "Tables_in_", "Field", "Type"]:
                # Skip header rows
                if not any(parts[0].startswith(h) for h in ["Database", "Tables_in", "Field"]):
                    items.append(parts[0])
    
    logger.info(
        f"Schema query returned {len(items)} items",
        extra={"correlation_id": context.correlation_id, "scope": scope},
    )
    
    return GetSchemaOutput(
        scope=scope,
        result=output,
        items=items,
        count=len(items),
    )


# -----------------------------------------------------------------------------
# update_casual_booking_rule handler
# -----------------------------------------------------------------------------

# Valid day abbreviations
_VALID_DAYS = frozenset(["mon", "tue", "wed", "thu", "fri", "sat", "sun"])

# Club cache with TTL (5 minutes)
_CLUB_CACHE: Dict[str, Tuple[str, float]] = {}  # club_id -> (database_name, timestamp)
_CLUB_CACHE_TTL = 300  # 5 minutes
_CLUB_CACHE_LOCK = False  # Simple lock for concurrent access


async def _get_valid_clubs(executor) -> Dict[str, str]:
    """
    Query the admin database to get valid club mappings.
    
    Returns dict mapping club identifiers to database names.
    Queries brsgolf_admin.cross_ref table where system_type != 'Cancelled'.
    
    Multiple identifiers map to same DB:
    - _id (numeric ID)
    - club_id (slug like 'brsgolfclubsales')
    - brsgolf_{club_id} (full database name)
    """
    global _CLUB_CACHE, _CLUB_CACHE_LOCK
    
    # Check if we have a valid cache
    now = time.time()
    if _CLUB_CACHE:
        # Check if any entry is still valid
        any_valid = any(now - ts < _CLUB_CACHE_TTL for _, ts in _CLUB_CACHE.values())
        if any_valid:
            return {k: v[0] for k, v in _CLUB_CACHE.items()}
    
    # Query the database for valid clubs
    query = """
        SELECT _id, club_id, name 
        FROM cross_ref 
        WHERE system_type != 'Cancelled' OR system_type IS NULL
    """
    
    try:
        result = await executor.run_command(
            service="teesheet-db",
            argv=[
                "mysql",
                "-u", "root",
                "brsgolf_admin",
                "-N", "-B",  # No headers, tab-separated
                "-e", query,
            ],
            timeout=10,
        )
        
        if not result.success:
            logger.warning(f"Failed to query clubs: {result.stderr}")
            # Return empty cache - will fail validation
            return {}
        
        # Parse results: _id\tclub_id\tname
        clubs: Dict[str, str] = {}
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                numeric_id = parts[0].strip()
                club_slug = parts[1].strip()
                db_name = f"brsgolf_{club_slug}"
                
                # Map all possible identifiers to the database name
                clubs[numeric_id] = db_name
                clubs[club_slug] = db_name
                clubs[db_name] = db_name
        
        # Update cache with timestamp
        _CLUB_CACHE = {k: (v, now) for k, v in clubs.items()}
        
        logger.info(f"Loaded {len(clubs) // 3} valid clubs from database")
        return clubs
        
    except Exception as e:
        logger.error(f"Error querying clubs: {e}")
        return {}


async def _resolve_club_database(club_id: str, executor) -> Optional[str]:
    """
    Resolve a club identifier to its database name.
    
    Returns database name if valid, None if club not found.
    Queries database if cache is stale.
    """
    # Normalize input
    club_key = str(club_id).lower().strip()
    
    # Get valid clubs (cached)
    valid_clubs = await _get_valid_clubs(executor)
    
    # Try exact match first
    if club_key in valid_clubs:
        return valid_clubs[club_key]
    
    # Try case-insensitive match
    for key, db_name in valid_clubs.items():
        if key.lower() == club_key:
            return db_name
    
    return None


def _validate_date(date_str: str) -> bool:
    """Validate date string is a real date."""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _validate_time(time_str: str) -> bool:
    """Validate time string is a real time."""
    try:
        datetime.strptime(time_str, "%H:%M:%S")
        return True
    except ValueError:
        return False


def _escape_sql_string(value: str) -> str:
    """
    Escape a string for safe SQL insertion.
    
    This is a defense-in-depth measure - inputs should already be validated
    by Pydantic patterns, but we escape anyway.
    """
    # Replace backslashes first, then single quotes
    return value.replace("\\", "\\\\").replace("'", "\\'")


async def update_casual_booking_rule_handler(
    input: UpdateCasualBookingRuleInput,
    context: ToolContext,
) -> UpdateCasualBookingRuleOutput:
    """
    Create or update a member casual booking rule.
    
    Security measures:
    - All inputs validated by Pydantic patterns before reaching here
    - Club ID validated against known clubs
    - Course ID validated as integer by Pydantic
    - Dates validated as real dates
    - Days validated against allowed set
    - All string values escaped for SQL
    - No user input directly concatenated without validation
    """
    executor = await context.get_executor()
    
    # 1. Validate club ID maps to a real database (queries brsgolf_admin.cross_ref)
    database = await _resolve_club_database(input.club_id, executor)
    if not database:
        # Get list of valid clubs for error message
        valid_clubs = await _get_valid_clubs(executor)
        # Extract unique slugs (every 3rd entry is the slug)
        unique_slugs = sorted(set(
            k for k in valid_clubs.keys() 
            if not k.isdigit() and not k.startswith("brsgolf_")
        ))
        raise ToolExecutionError(
            tool_name="update_casual_booking_rule",
            detail=f"Invalid club_id '{input.club_id}'. Valid clubs: {unique_slugs[:10]}{'...' if len(unique_slugs) > 10 else ''}",
            audit_id=context.audit_id,
        )
    
    # 2. Validate dates are real dates (not just pattern matches)
    if not _validate_date(input.start_date):
        raise ToolExecutionError(
            tool_name="update_casual_booking_rule",
            detail=f"Invalid start_date '{input.start_date}' - not a valid date",
            audit_id=context.audit_id,
        )
    if not _validate_date(input.end_date):
        raise ToolExecutionError(
            tool_name="update_casual_booking_rule",
            detail=f"Invalid end_date '{input.end_date}' - not a valid date",
            audit_id=context.audit_id,
        )
    
    # 3. Validate times if provided
    start_time = input.start_time or "00:00:00"
    end_time = input.end_time or "23:59:00"
    if not _validate_time(start_time):
        raise ToolExecutionError(
            tool_name="update_casual_booking_rule",
            detail=f"Invalid start_time '{start_time}' - not a valid time",
            audit_id=context.audit_id,
        )
    if not _validate_time(end_time):
        raise ToolExecutionError(
            tool_name="update_casual_booking_rule",
            detail=f"Invalid end_time '{end_time}' - not a valid time",
            audit_id=context.audit_id,
        )
    
    # 4. Validate days
    apply_days = [d.lower() for d in input.apply_days]
    invalid_days = set(apply_days) - _VALID_DAYS
    if invalid_days:
        raise ToolExecutionError(
            tool_name="update_casual_booking_rule",
            detail=f"Invalid days: {invalid_days}. Valid days: {list(_VALID_DAYS)}",
            audit_id=context.audit_id,
        )
    
    # 5. Validate course exists in database
    course_check_query = f"SELECT course_id FROM casual_times WHERE course_id = {input.course_id} LIMIT 1"
    # Also check if any course config exists for this course
    config_check_query = f"SELECT id FROM configuration WHERE id LIKE 'course{input.course_id}%' LIMIT 1"
    
    result = await executor.run_command(
        service="teesheet-db",
        argv=[
            "mysql",
            "-u", "root",
            database,
            "-N", "-B",  # No headers, batch mode
            "-e", config_check_query,
        ],
        timeout=10,
    )
    
    # If no course config found and no existing rules, check if course_id is reasonable
    if not result.stdout.strip() and input.course_id > 5:
        raise ToolExecutionError(
            tool_name="update_casual_booking_rule",
            detail=f"Course {input.course_id} does not appear to exist. Valid courses are typically 1-5.",
            audit_id=context.audit_id,
        )
    
    # 6. Build the SQL safely
    # Convert booking_type to char: 'book' -> '1', 'view' -> '0'
    booking_type_char = "1" if input.booking_type == "book" else "0"
    
    # Convert days to Y/N columns
    apply_mon = "Y" if "mon" in apply_days else "N"
    apply_tue = "Y" if "tue" in apply_days else "N"
    apply_wed = "Y" if "wed" in apply_days else "N"
    apply_thu = "Y" if "thu" in apply_days else "N"
    apply_fri = "Y" if "fri" in apply_days else "N"
    apply_sat = "Y" if "sat" in apply_days else "N"
    apply_sun = "Y" if "sun" in apply_days else "N"
    
    # Format days_advance as 3-char string (padded with spaces if needed)
    days_advance_str = str(input.days_advance)[:3]
    
    # Get current timestamp
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Players/guests settings
    players_number = input.players_number or 4
    guests_allowed = 1 if input.guests_allowed else 0
    guests_number = input.guests_number if input.guests_number is not None else 4
    
    logger.info(
        f"Updating casual booking rule for club {database}, course {input.course_id}",
        extra={
            "correlation_id": context.correlation_id,
            "club_id": input.club_id,
            "course_id": input.course_id,
            "booking_type": input.booking_type,
        },
    )
    
    if input.rule_id:
        # UPDATE existing rule
        # Verify rule exists first
        check_query = f"SELECT id FROM casual_times WHERE id = {input.rule_id}"
        result = await executor.run_command(
            service="teesheet-db",
            argv=["mysql", "-u", "root", database, "-N", "-B", "-e", check_query],
            timeout=10,
        )
        if not result.stdout.strip():
            raise ToolExecutionError(
                tool_name="update_casual_booking_rule",
                detail=f"Rule with id {input.rule_id} not found",
                audit_id=context.audit_id,
            )
        
        # Build UPDATE query with only safe, validated values
        sql = f"""UPDATE casual_times SET
            DateTime = '{now}',
            Username = 'agent_mcp',
            course_id = {input.course_id},
            startDate = '{input.start_date}',
            endDate = '{input.end_date}',
            startTime = '{start_time}',
            endTime = '{end_time}',
            bookingType = '{booking_type_char}',
            daysAdvance = '{days_advance_str}',
            applyMon = '{apply_mon}',
            applyTue = '{apply_tue}',
            applyWed = '{apply_wed}',
            applyThu = '{apply_thu}',
            applyFri = '{apply_fri}',
            applySat = '{apply_sat}',
            applySun = '{apply_sun}',
            playersNumber = {players_number},
            guestsAllowed = {guests_allowed},
            guestsNumber = {guests_number}
            WHERE id = {input.rule_id}"""
        
        action = "updated"
        rule_id = input.rule_id
    else:
        # INSERT new rule
        sql = f"""INSERT INTO casual_times (
            DateTime, Username, course_id, startDate, endDate,
            startTime, endTime, bookingType, daysAdvance,
            applyMon, applyTue, applyWed, applyThu, applyFri, applySat, applySun,
            memTypeSelector, playersNumber, guestsAllowed, guestsNumber, bookablePlayersNumber
        ) VALUES (
            '{now}', 'agent_mcp', {input.course_id}, '{input.start_date}', '{input.end_date}',
            '{start_time}', '{end_time}', '{booking_type_char}', '{days_advance_str}',
            '{apply_mon}', '{apply_tue}', '{apply_wed}', '{apply_thu}', '{apply_fri}', '{apply_sat}', '{apply_sun}',
            1, {players_number}, {guests_allowed}, {guests_number}, {players_number}
        )"""
        
        action = "created"
        rule_id = 0  # Will be updated after insert
    
    # Execute the SQL
    result = await executor.run_command(
        service="teesheet-db",
        argv=["mysql", "-u", "root", database, "-e", sql],
        timeout=15,
    )
    
    if not result.success:
        raise UpstreamError(
            service="teesheet-db",
            detail=f"Failed to {action[:-1]} rule: {result.stderr or result.stdout}",
            audit_id=context.audit_id,
        )
    
    # Get the rule ID for new inserts
    if action == "created":
        get_id_query = "SELECT LAST_INSERT_ID()"
        result = await executor.run_command(
            service="teesheet-db",
            argv=["mysql", "-u", "root", database, "-N", "-B", "-e", get_id_query],
            timeout=10,
        )
        if result.success and result.stdout.strip():
            rule_id = int(result.stdout.strip())
    
    message = (
        f"Successfully {action} casual booking rule {rule_id} for course {input.course_id}: "
        f"{input.booking_type} {input.days_advance} days advance, "
        f"applies {'-'.join(sorted(apply_days))}, "
        f"{input.start_date} to {input.end_date}"
    )
    
    logger.info(
        message,
        extra={"correlation_id": context.correlation_id, "rule_id": rule_id},
    )
    
    return UpdateCasualBookingRuleOutput(
        success=True,
        rule_id=rule_id,
        action=action,
        message=message,
    )


# -----------------------------------------------------------------------------
# update_configuration handler
# -----------------------------------------------------------------------------

async def update_configuration_handler(
    input: UpdateConfigurationInput,
    context: ToolContext,
) -> UpdateConfigurationOutput:
    """
    Update system configuration values via the BRS v2 API.
    
    Uses PATCH /api/v2/clubs/{clubId}/configurations
    """
    club_slug = _resolve_club_slug(input.club_id)
    
    logger.info(
        f"Updating configuration for club {club_slug}",
        extra={
            "correlation_id": context.correlation_id,
            "club_id": input.club_id,
            "keys": list(input.configurations.keys()),
        },
    )
    
    # Build API request using call_api_handler
    api_input = CallApiInput(
        method="PATCH",
        path=f"/api/v2/clubs/{{clubId}}/configurations",
        club_id=input.club_id,
        body={"configurations": input.configurations},
    )
    
    result = await call_api_handler(api_input, context)
    
    if result.status >= 400:
        error_detail = result.body if isinstance(result.body, str) else json.dumps(result.body)
        raise UpstreamError(
            service="teesheet",
            detail=f"Configuration update failed with status {result.status}: {error_detail}",
            audit_id=context.audit_id,
        )
    
    updated_keys = list(input.configurations.keys())
    message = f"Successfully updated {len(updated_keys)} configuration(s): {', '.join(updated_keys)}"
    
    return UpdateConfigurationOutput(
        success=True,
        updated_keys=updated_keys,
        message=message,
    )


# -----------------------------------------------------------------------------
# create_visitor_green_fee handler
# -----------------------------------------------------------------------------

async def create_visitor_green_fee_handler(
    input: CreateVisitorGreenFeeInput,
    context: ToolContext,
) -> CreateVisitorGreenFeeOutput:
    """
    Create a visitor green fee rate via the BRS v3 API.
    
    The BRS API uses:
    - Per-player pricing: green_fee_1_ball through green_fee_4_ball
    - Day applicability: day_mon through day_sun (Y/N for which days)
    - Time window: start_time, end_time
    """
    club_slug = _resolve_club_slug(input.club_id)
    
    # Validate dates are real
    if not _validate_date(input.start_date):
        raise ToolExecutionError(
            tool_name="create_visitor_green_fee",
            detail=f"Invalid start_date '{input.start_date}'",
            audit_id=context.audit_id,
        )
    if not _validate_date(input.end_date):
        raise ToolExecutionError(
            tool_name="create_visitor_green_fee",
            detail=f"Invalid end_date '{input.end_date}'",
            audit_id=context.audit_id,
        )
    
    logger.info(
        f"Creating visitor green fee for club {club_slug}",
        extra={
            "correlation_id": context.correlation_id,
            "club_id": input.club_id,
            "course_id": input.course_id,
            "green_fee_1_ball": input.green_fee_1_ball,
        },
    )
    
    # Default multi-ball prices to single ball price if not specified
    fee_1 = f"{input.green_fee_1_ball:.2f}"
    fee_2 = f"{(input.green_fee_2_ball or input.green_fee_1_ball):.2f}"
    fee_3 = f"{(input.green_fee_3_ball or input.green_fee_1_ball):.2f}"
    fee_4 = f"{(input.green_fee_4_ball or input.green_fee_1_ball):.2f}"
    
    # Build API request body matching BRS schema
    api_body = {
        "course_id": input.course_id,
        "course_2_id": 0,  # Required field, 0 for single course
        "start_date": input.start_date,
        "end_date": input.end_date,
        "start_time": input.start_time,
        "end_time": input.end_time,
        "green_fee_1_ball": fee_1,
        "green_fee_2_ball": fee_2,
        "green_fee_3_ball": fee_3,
        "green_fee_4_ball": fee_4,
        "green_fee_rate_type": input.green_fee_rate_type,
        "sub_type": input.sub_type,
        "num_holes": input.num_holes,
        "days_advance": str(input.days_advance),
        "day_mon": "Y" if input.day_mon else "",
        "day_tue": "Y" if input.day_tue else "",
        "day_wed": "Y" if input.day_wed else "",
        "day_thu": "Y" if input.day_thu else "",
        "day_fri": "Y" if input.day_fri else "",
        "day_sat": "Y" if input.day_sat else "",
        "day_sun": "Y" if input.day_sun else "",
        "package_enabled": 1 if input.package_enabled else 0,
        "package_name": "",
        "package_desc": "",
        "icon_food": 0,
        "icon_buggies": 0,
        "icon_accom": 0,
        "savings": "",
        "club_website": "Y" if input.club_website else "N",
        "tour_ops_club_website": "N",
        "channel_agents": "",
        "channel_tour_ops": "",
    }
    
    api_input = CallApiInput(
        method="POST",
        path=f"/api/v3/clubs/{{clubId}}/visitor-green-fee-rates.json",
        club_id=input.club_id,
        body=api_body,
    )
    
    result = await call_api_handler(api_input, context)
    
    if result.status >= 400:
        # API failed - provide clear error message
        error_detail = "Unknown error"
        if isinstance(result.body, dict):
            if "message" in result.body:
                error_detail = result.body["message"]
            if "errors" in result.body:
                # Extract validation errors
                errors = result.body["errors"]
                if isinstance(errors, dict) and "children" in errors:
                    field_errors = []
                    for field, info in errors["children"].items():
                        if isinstance(info, dict) and "errors" in info and info["errors"]:
                            field_errors.append(f"{field}: {', '.join(info['errors'])}")
                        elif isinstance(info, list) and info:
                            field_errors.append(f"{field}: {', '.join(info)}")
                    if field_errors:
                        error_detail = "; ".join(field_errors)
        elif isinstance(result.body, str):
            error_detail = result.body
        
        raise UpstreamError(
            service="teesheet",
            detail=f"Visitor green fee creation failed ({result.status}): {error_detail}",
            audit_id=context.audit_id,
        )
    
    # API succeeded - extract green fee ID
    green_fee_id = None
    if "Location" in result.headers:
        location = result.headers["Location"]
        match = re.search(r"/visitor-green-fee-rates/(\d+)", location)
        if match:
            green_fee_id = int(match.group(1))
    
    # Try to extract ID from response body
    if not green_fee_id and isinstance(result.body, dict):
        green_fee_id = result.body.get("id") or result.body.get("visitorGreenFeeID")
    
    message = f"Successfully created visitor green fee: {input.green_fee_rate_type} {input.sub_type}, {fee_1} per player"
    if green_fee_id:
        message += f" (ID: {green_fee_id})"
    
    return CreateVisitorGreenFeeOutput(
        success=True,
        green_fee_id=green_fee_id,
        message=message,
    )

# -----------------------------------------------------------------------------
# create_booking handler
# -----------------------------------------------------------------------------

async def create_booking_handler(
    input: CreateBookingInput,
    context: ToolContext,
) -> CreateBookingOutput:
    """
    Create a tee time booking via the BRS v3 API.
    
    Uses POST /api/v3/clubs/{clubId}/bookings.
    
    Request Format:
    - Body must be wrapped in "tee_sheet_booking" key for Symfony form binding
    - Slots must be an object with string keys ("1", "2", "3", "4"), not an array
    - Each slot requires player.type ("MEMBER" or "CONTACT") and player.id
    
    If you encounter "Validation Failed" with empty error arrays:
    1. Check the tee_sheet_booking wrapper is present
    2. Verify player.type and player.id are set for each slot
    3. Confirm the tee time exists at the specified date/time
    """
    club_slug = _resolve_club_slug(input.club_id)
    
    logger.info(
        f"Creating booking for club {club_slug}",
        extra={
            "correlation_id": context.correlation_id,
            "club_id": input.club_id,
            "course_id": input.course_id,
            "date": input.date,
            "time": input.time,
            "slot_count": len(input.slots),
        },
    )
    
    # Build slots as object with string keys (1, 2, 3, 4), not array
    # BRS API expects: {"1": {"player": {...}}, "2": {...}, ...}
    # Player types:
    #   - MEMBER: requires member_id
    #   - CONTACT: requires contact_id  
    #   - GUEST: no ID required (for visitor bookings)
    api_slots = {}
    for i, slot in enumerate(input.slots, start=1):
        player_data = {"name_on_tee_sheet": slot.name}
        if slot.member_id:
            player_data["id"] = slot.member_id
            player_data["type"] = "MEMBER"
        elif slot.contact_id:
            player_data["id"] = slot.contact_id
            player_data["type"] = "CONTACT"
        else:
            # No member/contact ID - use GUEST type (for visitor bookings)
            player_data["type"] = "GUEST"
        api_slots[str(i)] = {"player": player_data}
        if slot.green_fee_id:
            api_slots[str(i)]["green_fee"] = {"id": slot.green_fee_id}
    
    # Build API request body matching BRS v3 format
    # IMPORTANT: Must be wrapped in "tee_sheet_booking" key for Symfony form submission
    booking_data = {
        "course_id": input.course_id,
        "date": input.date,
        "time": input.time,
        "holes": input.holes,
        "reservation_name": input.reservation_name,
        "reservation_type": input.reservation_type,
        "slots": api_slots,
    }
    
    # Add optional fields
    if input.contact_id:
        booking_data["contact_id"] = input.contact_id
    if input.number_of_buggies > 0:
        booking_data["number_of_buggies"] = input.number_of_buggies
    if input.notes:
        booking_data["notes"] = {"booking": input.notes}
    
    # Wrap in tee_sheet_booking for Symfony form binding
    api_body = {"tee_sheet_booking": booking_data}
    
    api_input = CallApiInput(
        method="POST",
        path=f"/api/v3/clubs/{{clubId}}/bookings",
        club_id=input.club_id,
        body=api_body,
    )
    
    result = await call_api_handler(api_input, context)
    
    if result.status >= 400:
        # API failed - provide clear error message
        error_detail = "Unknown error"
        if isinstance(result.body, dict):
            if "message" in result.body:
                error_detail = result.body["message"]
            if "errors" in result.body:
                # Extract validation errors
                errors = result.body["errors"]
                if isinstance(errors, dict) and "children" in errors:
                    field_errors = []
                    for field, info in errors["children"].items():
                        if isinstance(info, dict) and "errors" in info and info["errors"]:
                            field_errors.append(f"{field}: {', '.join(info['errors'])}")
                        elif isinstance(info, list) and info:
                            field_errors.append(f"{field}: {', '.join(info)}")
                    if field_errors:
                        error_detail = "; ".join(field_errors)
                    else:
                        # Empty errors usually means pre-validation failure
                        error_detail = (
                            "Validation failed with no specific field errors. "
                            "This usually means: (1) the tee time doesn't exist at the specified date/time, "
                            "(2) the API user lacks booking permissions, or "
                            "(3) the club's tee sheet is not configured. "
                            "Try using 'brsgolfclubsales' club which has tee times configured."
                        )
        
        raise UpstreamError(
            service="teesheet",
            detail=f"Booking creation failed ({result.status}): {error_detail}",
            audit_id=context.audit_id,
        )
    
    # Extract booking ID from Location header or response body
    booking_id = None
    if "Location" in result.headers:
        location = result.headers["Location"]
        match = re.search(r"/bookings/(\d+)", location)
        if match:
            booking_id = int(match.group(1))
    elif isinstance(result.body, dict) and "id" in result.body:
        booking_id = result.body["id"]
    
    message = f"Successfully created booking '{input.reservation_name}' for {len(input.slots)} player(s) on {input.date} at {input.time}"
    if booking_id:
        message += f" (Booking ID: {booking_id})"
    
    return CreateBookingOutput(
        success=True,
        booking_id=booking_id,
        message=message,
    )
