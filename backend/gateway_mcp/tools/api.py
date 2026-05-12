"""
BRS Internal API Tools

Handlers for internal API operations:
- call_internal_api: Execute internal API operations with enum-controlled operations

BRS Architecture:
- Most APIs live under brs-teesheet: /{clubId}/api/v3/...
- Configuration APIs: /{clubId}/api/v3/ (ClubConfigurationController)
- Features are controlled via configuration table entries
"""

import logging
from typing import Any

from gateway_mcp.core.errors import ToolExecutionError, UpstreamError
from gateway_mcp.tools.base import (
    Environment,
    RiskLevel,
    Tool,
    ToolContext,
)
from gateway_mcp.tools.schemas import (
    CallInternalApiInput,
    CallInternalApiOutput,
    InternalApiOperation,
)

logger = logging.getLogger(__name__)


# Operation to API mapping
# The Gateway owns this mapping - agents use enum values, not raw API calls
# BRS features are controlled via configuration keys, not a dedicated features API
OPERATION_MAPPING: dict[InternalApiOperation, dict[str, Any]] = {
    InternalApiOperation.ENABLE_REQUIRED_FEATURES: {
        # In BRS, features are enabled via configuration table entries
        # For demo purposes, we verify current config and report what's enabled
        "endpoint": "/{club_id}/api/v3/",
        "method": "GET",
        "features_to_check": [
            "member_booking_feature_supported",
            "visitor_booking_feature_supported",
            "facility_booking_feature_supported",
            "mobile_enabled",
        ],
        "description": "Check which standard features are enabled for the club",
    },
}


async def call_internal_api_handler(
    input: CallInternalApiInput,
    context: ToolContext,
) -> CallInternalApiOutput:
    """
    Execute an internal API operation.
    
    This tool provides a controlled interface to internal APIs.
    Operations are enum-controlled - the Gateway owns the mapping
    from operation names to actual API calls.
    
    Currently supported operations:
    - enable_required_features: Check/verify standard features for a club
    
    Args:
        input: Club ID and operation to perform
        context: Tool context with executor
        
    Returns:
        CallInternalApiOutput with operation result
        
    Raises:
        UpstreamError: If internal API fails
        ToolExecutionError: If operation is not supported
    """
    executor = await context.get_executor()
    
    # Get operation config
    op_config = OPERATION_MAPPING.get(input.operation)
    if not op_config:
        raise ToolExecutionError(
            tool_name="call_internal_api",
            message=f"Unsupported operation: {input.operation}",
            audit_id=context.audit_id,
        )
    
    # Build the endpoint URL
    endpoint = op_config["endpoint"].format(club_id=input.club_id)
    method = op_config["method"]
    
    logger.info(
        f"Calling internal API: {method} {endpoint}",
        extra={"correlation_id": context.correlation_id},
    )
    
    # Use the teesheet service (brs-teesheet on localhost:8056)
    try:
        result = await executor.call_http(
            service="teesheet",
            method=method,
            path=endpoint,
            club_id=str(input.club_id),  # Use cached per-club auth token
        )
    except Exception as e:
        logger.error(
            f"Internal API call failed: {e}",
            extra={"correlation_id": context.correlation_id},
        )
        raise UpstreamError(
            service="teesheet",
            detail=f"Internal API failed: {str(e)[:200]}",
            audit_id=context.audit_id,
        )
    
    if result.status_code == 404:
        raise UpstreamError(
            service="teesheet",
            detail=f"Club '{input.club_id}' not found or not configured",
            audit_id=context.audit_id,
        )
    
    if result.status_code != 200:
        raise UpstreamError(
            service="teesheet",
            detail=f"Internal API returned {result.status_code}",
            audit_id=context.audit_id,
        )
    
    # Parse response based on operation type
    if input.operation == InternalApiOperation.ENABLE_REQUIRED_FEATURES:
        enabled_features: list[str] = []
        
        if isinstance(result.body, dict):
            # BRS returns configuration as key-value pairs
            configs = result.body.get("configurations", result.body)
            features_to_check = op_config.get("features_to_check", [])
            
            for feature in features_to_check:
                value = configs.get(feature, "")
                if isinstance(value, str) and value.lower() in ("yes", "true", "1"):
                    enabled_features.append(feature)
                elif value is True:
                    enabled_features.append(feature)
        
        return CallInternalApiOutput(
            club_id=input.club_id,
            enabled_features=enabled_features,
        )
    
    # Default response for unknown operations (shouldn't reach here due to enum)
    return CallInternalApiOutput(
        club_id=input.club_id,
        enabled_features=[],
    )


# Tool definition

call_internal_api_tool = Tool(
    name="call_internal_api",
    description="Execute controlled internal API operations (enum-based, not free-form)",
    input_schema=CallInternalApiInput,
    output_schema=CallInternalApiOutput,
    risk_level=RiskLevel.MEDIUM_WRITE,
    allowed_environments=[Environment.LOCAL, Environment.DEV, Environment.QA],
    requires_approval=False,
    timeout_seconds=60,
    handler=call_internal_api_handler,
    audit_metadata={"category": "brs", "executor": "http_rest"},
)


# List of all API tools for registry
API_TOOLS = [
    call_internal_api_tool,
]
