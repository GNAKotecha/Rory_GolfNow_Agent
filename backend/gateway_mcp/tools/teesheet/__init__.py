"""
Teesheet Tools

Tools for interacting with the BRS Teesheet system:
- list_routes: Discover available API routes from Symfony router
- call_api: Generic HTTP client for Teesheet API endpoints
- run_sql: Execute read-only SQL queries against the club database
- get_config: Retrieve configuration values from the database
- get_schema: Discover database structure (databases, tables, columns)
- update_casual_booking_rule: Create/update member casual booking rules (SQL-based)
- update_configuration: Update system configuration via API
- create_visitor_green_fee: Create visitor green fee rates via API
- create_booking: Create tee time bookings via API

These tools provide low-level access to the Teesheet system for
debugging, analysis, and operations not covered by higher-level tools.
"""

from gateway_mcp.tools.base import (
    ApprovalPolicy,
    Environment,
    RiskLevel,
    Tool,
)
from gateway_mcp.tools.teesheet.handlers import (
    list_routes_handler,
    call_api_handler,
    run_sql_handler,
    get_config_handler,
    get_schema_handler,
    get_call_api_approval_policy,
    update_casual_booking_rule_handler,
    update_configuration_handler,
    create_visitor_green_fee_handler,
    create_booking_handler,
)
from gateway_mcp.tools.teesheet.schemas import (
    ListRoutesInput,
    ListRoutesOutput,
    CallApiInput,
    CallApiOutput,
    RunSqlInput,
    RunSqlOutput,
    GetConfigInput,
    GetConfigOutput,
    GetSchemaInput,
    GetSchemaOutput,
    UpdateCasualBookingRuleInput,
    UpdateCasualBookingRuleOutput,
    UpdateConfigurationInput,
    UpdateConfigurationOutput,
    CreateVisitorGreenFeeInput,
    CreateVisitorGreenFeeOutput,
    CreateBookingInput,
    CreateBookingOutput,
)

# List Routes Tool - Safe, read-only discovery
list_routes_tool = Tool(
    name="list_routes",
    description=(
        "Discover available API routes from the Teesheet Symfony application. "
        "Returns routes starting with /api/ including their name, HTTP method, path, and defaults. "
        "Useful for understanding which endpoints are available before calling them."
    ),
    input_schema=ListRoutesInput,
    output_schema=ListRoutesOutput,
    risk_level=RiskLevel.READ,
    allowed_environments=[Environment.LOCAL, Environment.DEV, Environment.QA],
    requires_approval=False,
    approval_policy=ApprovalPolicy.SAFE,
    timeout_seconds=30,
    handler=list_routes_handler,
    audit_metadata={"category": "teesheet", "executor": "docker_exec"},
)

# Call API Tool - Contextual approval based on HTTP method
call_api_tool = Tool(
    name="call_api",
    description=(
        "Make an HTTP request to the Teesheet API. "
        "Supports GET, POST, PUT, PATCH, DELETE methods. "
        "Automatically adds authentication if available. "
        "Returns the response status, headers, and body."
    ),
    input_schema=CallApiInput,
    output_schema=CallApiOutput,
    risk_level=RiskLevel.LOW_WRITE,  # Can do writes
    allowed_environments=[Environment.LOCAL, Environment.DEV, Environment.QA],
    requires_approval=False,  # Handled by approval_policy
    approval_policy=ApprovalPolicy.CONTEXTUAL,
    approval_evaluator=get_call_api_approval_policy,
    timeout_seconds=60,
    handler=call_api_handler,
    audit_metadata={"category": "teesheet", "executor": "http"},
)

# Run SQL Tool - Sensitive, requires first-use approval
run_sql_tool = Tool(
    name="run_sql",
    description=(
        "Execute a SQL query against the Teesheet MySQL database. "
        "Only SELECT queries are allowed for safety. "
        "Returns the query results in tabular format. "
        "Useful for investigating data, checking configurations, and debugging."
    ),
    input_schema=RunSqlInput,
    output_schema=RunSqlOutput,
    risk_level=RiskLevel.READ,
    allowed_environments=[Environment.LOCAL, Environment.DEV],  # More restricted
    requires_approval=False,  # Handled by approval_policy
    approval_policy=ApprovalPolicy.SENSITIVE,
    timeout_seconds=30,
    handler=run_sql_handler,
    audit_metadata={"category": "teesheet", "executor": "docker_exec"},
)

# Get Config Tool - Safe, read-only
get_config_tool = Tool(
    name="get_config",
    description=(
        "Retrieve configuration settings from the Teesheet database. "
        "Can fetch a specific config key or all configurations. "
        "Reads from the 'configuration' table in the club database."
    ),
    input_schema=GetConfigInput,
    output_schema=GetConfigOutput,
    risk_level=RiskLevel.READ,
    allowed_environments=[Environment.LOCAL, Environment.DEV, Environment.QA],
    requires_approval=False,
    approval_policy=ApprovalPolicy.SAFE,
    timeout_seconds=15,
    handler=get_config_handler,
    audit_metadata={"category": "teesheet", "executor": "docker_exec"},
)

# Get Schema Tool - Safe, read-only database structure discovery
get_schema_tool = Tool(
    name="get_schema",
    description=(
        "Discover database structure. Use this FIRST before run_sql to understand what's available. "
        "Scope options: 'databases' (list all brsgolf_* databases), "
        "'tables' (list tables in a database), or 'columns' (describe table structure). "
        "Example: get_schema(scope='databases') -> shows available databases. "
        "Then: get_schema(scope='tables', database='brsgolf_brsgolfclubsales') -> shows tables."
    ),
    input_schema=GetSchemaInput,
    output_schema=GetSchemaOutput,
    risk_level=RiskLevel.READ,
    allowed_environments=[Environment.LOCAL, Environment.DEV, Environment.QA],
    requires_approval=False,
    approval_policy=ApprovalPolicy.SAFE,
    timeout_seconds=15,
    handler=get_schema_handler,
    audit_metadata={"category": "teesheet", "executor": "docker_exec"},
)

# Update Casual Booking Rule Tool - SENSITIVE, write operation via SQL
update_casual_booking_rule_tool = Tool(
    name="update_casual_booking_rule",
    description=(
        "Create or update member casual booking rules. "
        "Controls when members can view or book tee times. "
        "Parameters: club_id, course_id (1-5), start_date/end_date (YYYY-MM-DD), "
        "booking_type ('view' or 'book'), days_advance (0-999), "
        "apply_days (list of 'mon','tue','wed','thu','fri','sat','sun'). "
        "Optional: rule_id to update existing rule. "
        "All inputs are heavily validated to prevent SQL injection."
    ),
    input_schema=UpdateCasualBookingRuleInput,
    output_schema=UpdateCasualBookingRuleOutput,
    risk_level=RiskLevel.MEDIUM_WRITE,
    allowed_environments=[Environment.LOCAL, Environment.DEV],  # Restricted
    requires_approval=False,  # Approval disabled for LOCAL testing; enable in production
    approval_policy=ApprovalPolicy.CONTEXTUAL,  # Will be SENSITIVE in production
    timeout_seconds=30,
    handler=update_casual_booking_rule_handler,
    audit_metadata={"category": "teesheet", "executor": "docker_exec", "write": True},
)

# Update Configuration Tool - Writes via API
update_configuration_tool = Tool(
    name="update_configuration",
    description=(
        "Update system configuration settings via the BRS API. "
        "Uses PATCH /api/v2/clubs/{clubId}/configurations. "
        "Takes a club_id and dictionary of key-value pairs to update."
    ),
    input_schema=UpdateConfigurationInput,
    output_schema=UpdateConfigurationOutput,
    risk_level=RiskLevel.MEDIUM_WRITE,
    allowed_environments=[Environment.LOCAL, Environment.DEV, Environment.QA],
    requires_approval=True,
    approval_policy=ApprovalPolicy.SENSITIVE,
    timeout_seconds=30,
    handler=update_configuration_handler,
    audit_metadata={"category": "teesheet", "executor": "http", "write": True},
)

# Create Visitor Green Fee Tool - Writes via API
create_visitor_green_fee_tool = Tool(
    name="create_visitor_green_fee",
    description=(
        "Create a visitor green fee rate for a golf club via the BRS v3 API. "
        "Uses per-player pricing model (1-ball to 4-ball rates). "
        "Required: club_id, green_fee_1_ball (price per player), start_date, end_date. "
        "Optional: green_fee_2/3/4_ball (defaults to 1_ball), course_id (default 1), "
        "num_holes ('9' or '18'), start_time, end_time, green_fee_rate_type ('Standard'), "
        "sub_type ('visitor'), day_mon/tue/wed/thu/fri/sat/sun (true/false for which days)."
    ),
    input_schema=CreateVisitorGreenFeeInput,
    output_schema=CreateVisitorGreenFeeOutput,
    risk_level=RiskLevel.LOW_WRITE,
    allowed_environments=[Environment.LOCAL, Environment.DEV, Environment.QA],
    requires_approval=False,
    approval_policy=ApprovalPolicy.CONTEXTUAL,
    timeout_seconds=30,
    handler=create_visitor_green_fee_handler,
    audit_metadata={"category": "teesheet", "executor": "http", "write": True},
)

# Create Booking Tool - Writes via API
create_booking_tool = Tool(
    name="create_booking",
    description=(
        "Create a tee time booking via the BRS API. "
        "Uses POST /api/v3/clubs/{clubId}/bookings. "
        "Parameters: club_id, course_id, date (YYYY-MM-DD), time (HH:MM:SS), "
        "reservation_name, reservation_type, slots (list of players with name field)."
    ),
    input_schema=CreateBookingInput,
    output_schema=CreateBookingOutput,
    risk_level=RiskLevel.LOW_WRITE,
    allowed_environments=[Environment.LOCAL, Environment.DEV, Environment.QA],
    requires_approval=False,
    approval_policy=ApprovalPolicy.CONTEXTUAL,
    timeout_seconds=30,
    handler=create_booking_handler,
    audit_metadata={"category": "teesheet", "executor": "http", "write": True},
)

# Export list for registry
TEESHEET_TOOLS = [
    list_routes_tool,
    call_api_tool,
    run_sql_tool,
    get_config_tool,
    get_schema_tool,
    update_casual_booking_rule_tool,
    update_configuration_tool,
    create_visitor_green_fee_tool,
    create_booking_tool,
]
