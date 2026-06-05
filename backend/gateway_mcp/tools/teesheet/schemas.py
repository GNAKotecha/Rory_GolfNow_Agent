"""
Teesheet Tool Schemas

Pydantic models for input/output validation of Teesheet tools.
"""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


# -----------------------------------------------------------------------------
# list_routes
# -----------------------------------------------------------------------------

class ListRoutesInput(BaseModel):
    """Input for list_routes tool - no parameters required."""
    pass


class RouteInfo(BaseModel):
    """Information about a single API route."""
    name: str = Field(..., description="Route name (e.g., 'api_v3_competitions_list')")
    method: str = Field(..., description="HTTP method(s) (e.g., 'GET', 'POST|PUT')")
    path: str = Field(..., description="URL path (e.g., '/api/v3/competitions')")
    defaults: Dict[str, Any] = Field(default_factory=dict, description="Route defaults")


class ListRoutesOutput(BaseModel):
    """Output from list_routes tool."""
    routes: List[RouteInfo] = Field(..., description="List of available API routes")
    count: int = Field(..., description="Number of routes found")


# -----------------------------------------------------------------------------
# call_api
# -----------------------------------------------------------------------------

class CallApiInput(BaseModel):
    """Input for call_api tool."""
    method: str = Field(
        ...,
        description="HTTP method: GET, POST, PUT, PATCH, or DELETE"
    )
    path: str = Field(
        ...,
        description="API path, e.g., /api/v3/competitions"
    )
    club_id: Optional[str] = Field(
        None,
        description="Club identifier (defaults to environment setting if not provided)"
    )
    body: Optional[Dict[str, Any] | str] = Field(
        None,
        description="Request body for POST/PUT/PATCH (dict for json/form, str for raw)"
    )
    body_format: Literal["json", "form", "raw"] = Field(
        "json",
        description="Body encoding format: 'json' (default), 'form' (application/x-www-form-urlencoded), or 'raw' (as-is string)"
    )
    query: Optional[Dict[str, str]] = Field(
        None,
        description="Query string parameters"
    )
    headers: Optional[Dict[str, str]] = Field(
        None,
        description="Additional HTTP headers"
    )

    @field_validator("body_format")
    @classmethod
    def validate_body_format_consistency(cls, v, info):
        """Ensure body_format is consistent with body type."""
        body = info.data.get("body")
        body_format = v

        if body is not None:
            if body_format == "form":
                if not isinstance(body, dict):
                    raise ValueError("body_format='form' requires body to be a dict (will be URL-encoded)")
            elif body_format == "raw":
                if not isinstance(body, str):
                    raise ValueError("body_format='raw' requires body to be a string")

        return v


class CallApiOutput(BaseModel):
    """Output from call_api tool."""
    status: int = Field(..., description="HTTP status code")
    headers: Dict[str, str] = Field(
        default_factory=dict,
        description="Response headers"
    )
    body: Any = Field(..., description="Response body (parsed JSON or text)")


# -----------------------------------------------------------------------------
# run_sql
# -----------------------------------------------------------------------------

class RunSqlInput(BaseModel):
    """Input for run_sql tool."""
    query: str = Field(
        ...,
        description="SQL query to execute (SELECT only)"
    )
    database: Optional[str] = Field(
        None,
        description="Database name (defaults to environment setting if not provided)"
    )


class RunSqlOutput(BaseModel):
    """Output from run_sql tool."""
    result: str = Field(
        ...,
        description="Query results in tabular format"
    )
    row_count: int = Field(
        0,
        description="Number of rows returned"
    )


# -----------------------------------------------------------------------------
# get_config
# -----------------------------------------------------------------------------

class GetConfigInput(BaseModel):
    """Input for get_config tool."""
    key: Optional[str] = Field(
        None,
        description="Specific config key to look up (omit for all configs)"
    )
    database: Optional[str] = Field(
        None,
        description="Database name (defaults to environment setting if not provided)"
    )


class ConfigEntry(BaseModel):
    """A single configuration entry."""
    id: str = Field(..., description="Configuration key")
    value: Any = Field(..., description="Configuration value")


class GetConfigOutput(BaseModel):
    """Output from get_config tool."""
    configs: List[ConfigEntry] = Field(
        default_factory=list,
        description="List of configuration entries"
    )
    count: int = Field(0, description="Number of configs found")


# -----------------------------------------------------------------------------
# get_schema
# -----------------------------------------------------------------------------

class GetSchemaInput(BaseModel):
    """Input for get_schema tool - discover database structure."""
    scope: str = Field(
        "databases",
        description="What to discover: 'databases' (list all), 'tables' (list tables in database), or 'columns' (describe table structure)"
    )
    database: Optional[str] = Field(
        None,
        description="Database name - required for 'tables' and 'columns' scope"
    )
    table: Optional[str] = Field(
        None,
        description="Table name - required for 'columns' scope"
    )


class GetSchemaOutput(BaseModel):
    """Output from get_schema tool."""
    scope: str = Field(..., description="The scope that was queried")
    result: str = Field(..., description="Schema information in tabular format")
    items: List[str] = Field(default_factory=list, description="List of database/table/column names found")
    count: int = Field(0, description="Number of items found")


# -----------------------------------------------------------------------------
# update_casual_booking_rule
# -----------------------------------------------------------------------------

class UpdateCasualBookingRuleInput(BaseModel):
    """
    Input for update_casual_booking_rule tool.
    
    Updates member casual booking rules in the database.
    All inputs are heavily validated to prevent SQL injection.
    """
    club_id: str = Field(
        ...,
        description="Club identifier (e.g., '7' or 'brsgolfclubsales')",
        min_length=1,
        max_length=64,
    )
    course_id: int = Field(
        ...,
        description="Course identifier (typically 1-5)",
        ge=1,
        le=99,
    )
    start_date: str = Field(
        ...,
        description="Start date for the rule in YYYY-MM-DD format",
        pattern=r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$",
    )
    end_date: str = Field(
        ...,
        description="End date for the rule in YYYY-MM-DD format",
        pattern=r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$",
    )
    start_time: Optional[str] = Field(
        "00:00:00",
        description="Start time for the rule in HH:MM:SS format",
        pattern=r"^([01]\d|2[0-3]):[0-5]\d:[0-5]\d$",
    )
    end_time: Optional[str] = Field(
        "23:59:00",
        description="End time for the rule in HH:MM:SS format",
        pattern=r"^([01]\d|2[0-3]):[0-5]\d:[0-5]\d$",
    )
    booking_type: str = Field(
        ...,
        description="Booking type: 'view' (members can view but not book) or 'book' (members can book)",
        pattern=r"^(view|book)$",
    )
    days_advance: int = Field(
        ...,
        description="Number of days in advance members can book (0-999)",
        ge=0,
        le=999,
    )
    apply_days: List[str] = Field(
        ...,
        description="Days the rule applies to: list of 'mon','tue','wed','thu','fri','sat','sun'",
        min_length=1,
    )
    players_number: Optional[int] = Field(
        4,
        description="Maximum players per booking (1-8)",
        ge=1,
        le=8,
    )
    guests_allowed: Optional[bool] = Field(
        True,
        description="Whether guests are allowed",
    )
    guests_number: Optional[int] = Field(
        4,
        description="Maximum guests allowed (0-8)",
        ge=0,
        le=8,
    )
    rule_id: Optional[int] = Field(
        None,
        description="Existing rule ID to update. If not provided, creates a new rule.",
        ge=1,
    )


class UpdateCasualBookingRuleOutput(BaseModel):
    """Output from update_casual_booking_rule tool."""
    success: bool = Field(..., description="Whether the operation succeeded")
    rule_id: int = Field(..., description="ID of the created/updated rule")
    action: str = Field(..., description="Action performed: 'created' or 'updated'")
    message: str = Field(..., description="Description of what was done")


# -----------------------------------------------------------------------------
# update_configuration
# -----------------------------------------------------------------------------

class UpdateConfigurationInput(BaseModel):
    """
    Input for update_configuration tool.
    
    Updates system configuration values via the BRS API.
    """
    club_id: str = Field(
        ...,
        description="Club identifier (e.g., '7' or 'brsgolfclubsales')",
        min_length=1,
        max_length=64,
    )
    configurations: Dict[str, Any] = Field(
        ...,
        description="Dictionary of configuration key-value pairs to update",
    )


class UpdateConfigurationOutput(BaseModel):
    """Output from update_configuration tool."""
    success: bool = Field(..., description="Whether the operation succeeded")
    updated_keys: List[str] = Field(default_factory=list, description="Keys that were updated")
    message: str = Field(..., description="Description of what was done")


# -----------------------------------------------------------------------------
# create_visitor_green_fee
# -----------------------------------------------------------------------------

class CreateVisitorGreenFeeInput(BaseModel):
    """
    Input for create_visitor_green_fee tool.
    
    Creates a visitor green fee rate via the BRS API.
    
    BRS visitor_green_fees table uses:
    - course_id: Which course this rate applies to
    - Date range: start_date, end_date
    - Time range: start_time, end_time (when this rate is available)
    - Per-player pricing: green_fee_1_ball through green_fee_4_ball
    - Day applicability: day_mon through day_sun (true/false for which days)
    - green_fee_rate_type: e.g., 'Standard', 'Special'
    - sub_type: e.g., 'visitor', 'twilight'
    - num_holes: '9' or '18'
    """
    club_id: str = Field(
        ...,
        description="Club identifier",
        min_length=1,
        max_length=64,
    )
    course_id: int = Field(
        1,
        description="Course ID (usually 1 for single-course clubs)",
        ge=1,
    )
    # Per-player pricing (BRS model: price varies by group size)
    green_fee_1_ball: float = Field(
        ...,
        description="Price for 1 player (solo)",
        ge=0,
    )
    green_fee_2_ball: Optional[float] = Field(
        None,
        description="Price for 2-ball (per player). Defaults to 1-ball price.",
        ge=0,
    )
    green_fee_3_ball: Optional[float] = Field(
        None,
        description="Price for 3-ball (per player). Defaults to 1-ball price.",
        ge=0,
    )
    green_fee_4_ball: Optional[float] = Field(
        None,
        description="Price for 4-ball (per player). Defaults to 1-ball price.",
        ge=0,
    )
    start_date: str = Field(
        ...,
        description="Start date in YYYY-MM-DD format",
        pattern=r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$",
    )
    end_date: str = Field(
        ...,
        description="End date in YYYY-MM-DD format",
        pattern=r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$",
    )
    num_holes: str = Field(
        "18",
        description="Number of holes: '9' or '18'",
        pattern=r"^(9|18)$",
    )
    start_time: str = Field(
        "08:00:00",
        description="Start time in HH:MM:SS format (when rate becomes available)",
        pattern=r"^\d{2}:\d{2}:\d{2}$",
    )
    end_time: str = Field(
        "20:00:00",
        description="End time in HH:MM:SS format (when rate expires for the day)",
        pattern=r"^\d{2}:\d{2}:\d{2}$",
    )
    green_fee_rate_type: str = Field(
        "Standard",
        description="Rate type: 'Standard', 'Special', 'Early Bird', etc.",
    )
    sub_type: str = Field(
        "visitor",
        description="Sub type: 'visitor', 'twilight', 'member', etc.",
    )
    # Day applicability
    day_mon: bool = Field(True, description="Rate available on Monday")
    day_tue: bool = Field(True, description="Rate available on Tuesday")
    day_wed: bool = Field(True, description="Rate available on Wednesday")
    day_thu: bool = Field(True, description="Rate available on Thursday")
    day_fri: bool = Field(True, description="Rate available on Friday")
    day_sat: bool = Field(True, description="Rate available on Saturday")
    day_sun: bool = Field(True, description="Rate available on Sunday")
    # Optional package features
    days_advance: int = Field(0, description="Days in advance booking required", ge=0)
    package_enabled: bool = Field(False, description="Whether this is a package deal")
    club_website: bool = Field(True, description="Show on club website")


class CreateVisitorGreenFeeOutput(BaseModel):
    """Output from create_visitor_green_fee tool."""
    success: bool = Field(..., description="Whether the operation succeeded")
    green_fee_id: Optional[int] = Field(None, description="ID of the created green fee rate")
    message: str = Field(..., description="Description of what was done")


# -----------------------------------------------------------------------------
# create_booking
# -----------------------------------------------------------------------------

class BookingSlot(BaseModel):
    """
    A slot/player in a booking.
    
    Player types supported:
    - GUEST: No ID required (for visitor bookings) - default if no ID provided
    - MEMBER: Requires member_id
    - CONTACT: Requires contact_id
    """
    name: str = Field(..., description="Player name to show on tee sheet")
    member_id: Optional[int] = Field(None, description="Member ID (for MEMBER type players)")
    contact_id: Optional[int] = Field(None, description="Contact ID (for CONTACT type players)")
    green_fee_id: Optional[int] = Field(None, description="Green fee product ID")


class CreateBookingInput(BaseModel):
    """
    Input for create_booking tool.
    
    Creates a tee time booking via the BRS API.
    Uses separate date/time fields to match API format.
    """
    club_id: str = Field(
        ...,
        description="Club identifier",
        min_length=1,
        max_length=64,
    )
    course_id: int = Field(
        ...,
        description="Course identifier",
        ge=1,
    )
    date: str = Field(
        ...,
        description="Booking date in YYYY-MM-DD format",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    time: str = Field(
        ...,
        description="Tee time in HH:MM format (e.g., '09:00')",
        pattern=r"^\d{2}:\d{2}$",
    )
    holes: int = Field(
        18,
        description="Number of holes: 9 or 18",
        ge=9,
        le=18,
    )
    reservation_name: str = Field(
        ...,
        description="Name for the booking/reservation",
    )
    reservation_type: str = Field(
        "Visitor",
        description="Reservation type (e.g., 'Visitor', 'Member', 'Competition')",
    )
    slots: List[BookingSlot] = Field(
        ...,
        description="List of players/slots for this booking",
        min_length=1,
    )
    contact_id: Optional[int] = Field(
        None,
        description="Main contact ID for the booking",
    )
    number_of_buggies: int = Field(
        0,
        description="Number of buggies required",
    )
    notes: Optional[str] = Field(
        None,
        description="Booking notes",
    )


class CreateBookingOutput(BaseModel):
    """Output from create_booking tool."""
    success: bool = Field(..., description="Whether the operation succeeded")
    booking_id: Optional[int] = Field(None, description="ID of the created booking")
    message: str = Field(..., description="Description of what was done")
