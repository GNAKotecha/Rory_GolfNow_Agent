"""
Atlassian Jira Tools

Handlers for Jira operations via upstream Atlassian MCP:
- create_ticket: Create a new Jira ticket
- get_ticket_status: Get current status of a ticket
- add_comment: Add a comment to a ticket

These tools proxy to the upstream Atlassian MCP server, translating between
Gateway's business schema and Atlassian's MCP protocol. User credentials
(OAuth tokens) are transparently injected by the middleware layer.
"""

import logging
from datetime import datetime, timezone

from gateway_mcp.core.errors import (
    CredentialMissingError,
    ToolExecutionError,
    UpstreamError,
)
from gateway_mcp.core.executors.mcp_proxy import MCPProxyBackend, MCPToolCallResult
from gateway_mcp.tools.base import (
    Environment,
    RiskLevel,
    Tool,
    ToolContext,
)
from gateway_mcp.tools.schemas import (
    AddCommentInput,
    AddCommentOutput,
    CreateTicketInput,
    CreateTicketOutput,
    GetTicketStatusInput,
    GetTicketStatusOutput,
)

logger = logging.getLogger(__name__)

# Upstream Atlassian MCP tool names
UPSTREAM_CREATE_ISSUE = "create_issue"
UPSTREAM_GET_ISSUE = "get_issue"
UPSTREAM_ADD_COMMENT = "add_comment"


async def _get_mcp_proxy(context: ToolContext) -> MCPProxyBackend:
    """
    Get MCP proxy backend from context.
    
    For Jira tools, the executor should be an MCPProxyBackend configured
    with the Atlassian upstream MCP.
    
    Raises:
        RuntimeError: If executor is not an MCPProxyBackend.
    """
    executor = await context.get_executor()
    if not isinstance(executor, MCPProxyBackend):
        raise RuntimeError(
            f"Jira tools require MCPProxyBackend, got {type(executor).__name__}"
        )
    return executor


# -----------------------------------------------------------------------------
# create_ticket handler
# -----------------------------------------------------------------------------

async def create_ticket_handler(
    input: CreateTicketInput,
    context: ToolContext,
) -> CreateTicketOutput:
    """
    Create a new Jira ticket.
    
    Translates Gateway's create_ticket schema to Atlassian MCP's create_issue
    tool, handling the response transformation.
    
    Args:
        input: Ticket details (project_key, summary, description, issue_type, labels)
        context: Tool context with MCP proxy and user credentials
        
    Returns:
        CreateTicketOutput with ticket_id, ticket_key, url, status, created_at
        
    Raises:
        CredentialMissingError: User hasn't connected Atlassian OAuth
        UpstreamError: Atlassian MCP returned an error
        ToolExecutionError: Response cannot be parsed
    """
    mcp_proxy = await _get_mcp_proxy(context)
    
    logger.info(
        f"Creating Jira ticket: project={input.project_key}, "
        f"type={input.issue_type.value}, summary={input.summary[:50]}...",
        extra={"correlation_id": context.correlation_id},
    )
    
    # Build upstream MCP arguments
    # Atlassian MCP expects fields in Jira API format
    upstream_args = {
        "project": {"key": input.project_key},
        "summary": input.summary,
        "issuetype": {"name": input.issue_type.value},
    }
    
    if input.description:
        upstream_args["description"] = input.description
    
    if input.labels:
        upstream_args["labels"] = input.labels
    
    # Call upstream Atlassian MCP
    result = await mcp_proxy.call_mcp_tool(
        upstream_name="atlassian",
        tool_name=UPSTREAM_CREATE_ISSUE,
        arguments=upstream_args,
        timeout=60,
        user_id=context.user_id,
    )
    
    if not result.success:
        logger.error(
            f"Failed to create Jira ticket: {result.error}",
            extra={"correlation_id": context.correlation_id},
        )
        raise UpstreamError(
            service="atlassian",
            detail=f"Atlassian MCP error: {result.error}",
            audit_id=context.audit_id,
        )
    
    # Parse upstream response
    try:
        data = result.result
        if isinstance(data, str):
            import json
            data = json.loads(data)
        
        # Extract fields from Jira API response format
        ticket_id = data.get("id", "")
        ticket_key = data.get("key", "")
        
        # Build ticket URL from self link or construct from key
        url = data.get("self", "")
        if not url and ticket_key:
            # Fallback URL construction
            url = f"https://golfnow.atlassian.net/browse/{ticket_key}"
        
        # Initial status is typically "To Do" or "Open"
        status = "To Do"
        if "fields" in data and "status" in data["fields"]:
            status = data["fields"]["status"].get("name", status)
        
        # Parse created timestamp or use now
        created_at = datetime.now(timezone.utc)
        if "fields" in data and "created" in data["fields"]:
            try:
                created_at = datetime.fromisoformat(
                    data["fields"]["created"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass
        
        return CreateTicketOutput(
            ticket_id=ticket_id,
            ticket_key=ticket_key,
            url=url,
            status=status,
            created_at=created_at,
        )
        
    except (KeyError, TypeError, AttributeError) as e:
        raise ToolExecutionError(
            tool_name="create_ticket",
            message=f"Cannot parse Atlassian response: {e}",
            audit_id=context.audit_id,
        )


# -----------------------------------------------------------------------------
# get_ticket_status handler
# -----------------------------------------------------------------------------

async def get_ticket_status_handler(
    input: GetTicketStatusInput,
    context: ToolContext,
) -> GetTicketStatusOutput:
    """
    Get the current status of a Jira ticket.
    
    Translates Gateway's get_ticket_status schema to Atlassian MCP's get_issue
    tool, extracting relevant status fields from the response.
    
    Args:
        input: Ticket key to look up (e.g., "GOLF-123")
        context: Tool context with MCP proxy and user credentials
        
    Returns:
        GetTicketStatusOutput with status, assignee, updated_at, etc.
        Returns found=False if ticket doesn't exist.
        
    Raises:
        CredentialMissingError: User hasn't connected Atlassian OAuth
        UpstreamError: Atlassian MCP returned an error (non-404)
    """
    mcp_proxy = await _get_mcp_proxy(context)
    
    logger.info(
        f"Getting Jira ticket status: {input.ticket_key}",
        extra={"correlation_id": context.correlation_id},
    )
    
    # Call upstream Atlassian MCP
    result = await mcp_proxy.call_mcp_tool(
        upstream_name="atlassian",
        tool_name=UPSTREAM_GET_ISSUE,
        arguments={"issueIdOrKey": input.ticket_key},
        timeout=30,
        user_id=context.user_id,
    )
    
    # Handle not found case
    if not result.success:
        if "not found" in (result.error or "").lower():
            return GetTicketStatusOutput(found=False)
        
        logger.error(
            f"Failed to get Jira ticket: {result.error}",
            extra={"correlation_id": context.correlation_id},
        )
        raise UpstreamError(
            service="atlassian",
            detail=f"Atlassian MCP error: {result.error}",
            audit_id=context.audit_id,
        )
    
    # Parse upstream response
    data = result.result
    if isinstance(data, str):
        import json
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            raise UpstreamError(
                service="atlassian",
                detail=f"Invalid JSON from Atlassian: {data[:200]}",
                audit_id=context.audit_id,
            )
    
    fields = data.get("fields", {})
    
    # Extract status name
    status = None
    if "status" in fields:
        status = fields["status"].get("name")
    
    # Extract assignee email or display name
    assignee = None
    if "assignee" in fields and fields["assignee"]:
        assignee = fields["assignee"].get(
            "emailAddress",
            fields["assignee"].get("displayName"),
        )
    
    # Parse updated timestamp
    updated_at = None
    if "updated" in fields:
        try:
            updated_at = datetime.fromisoformat(
                fields["updated"].replace("Z", "+00:00")
            )
        except (ValueError, TypeError):
            pass
    
    # Build URL
    url = data.get("self", "")
    ticket_key = data.get("key", input.ticket_key)
    if not url:
        url = f"https://golfnow.atlassian.net/browse/{ticket_key}"
    
    return GetTicketStatusOutput(
        ticket_key=ticket_key,
        summary=fields.get("summary"),
        status=status,
        assignee=assignee,
        updated_at=updated_at,
        url=url,
        found=True,
    )


# -----------------------------------------------------------------------------
# add_comment handler
# -----------------------------------------------------------------------------

async def add_comment_handler(
    input: AddCommentInput,
    context: ToolContext,
) -> AddCommentOutput:
    """
    Add a comment to a Jira ticket.
    
    Translates Gateway's add_comment schema to Atlassian MCP's add_comment
    tool, handling the response transformation.
    
    Args:
        input: Comment details (ticket_key, comment_body)
        context: Tool context with MCP proxy and user credentials
        
    Returns:
        AddCommentOutput with comment_id, author, created_at
        
    Raises:
        CredentialMissingError: User hasn't connected Atlassian OAuth
        UpstreamError: Atlassian MCP returned an error
        ToolExecutionError: Response cannot be parsed
    """
    mcp_proxy = await _get_mcp_proxy(context)
    
    logger.info(
        f"Adding comment to Jira ticket: {input.ticket_key}",
        extra={"correlation_id": context.correlation_id},
    )
    
    # Call upstream Atlassian MCP
    result = await mcp_proxy.call_mcp_tool(
        upstream_name="atlassian",
        tool_name=UPSTREAM_ADD_COMMENT,
        arguments={
            "issueIdOrKey": input.ticket_key,
            "body": input.comment_body,
        },
        timeout=30,
        user_id=context.user_id,
    )
    
    if not result.success:
        logger.error(
            f"Failed to add comment: {result.error}",
            extra={"correlation_id": context.correlation_id},
        )
        raise UpstreamError(
            service="atlassian",
            detail=f"Atlassian MCP error: {result.error}",
            audit_id=context.audit_id,
        )
    
    # Parse upstream response
    try:
        data = result.result
        if isinstance(data, str):
            import json
            data = json.loads(data)
        
        comment_id = data.get("id", "")
        
        # Extract author
        author = "unknown"
        if "author" in data:
            author = data["author"].get(
                "emailAddress",
                data["author"].get("displayName", "unknown"),
            )
        
        # Parse created timestamp
        created_at = datetime.now(timezone.utc)
        if "created" in data:
            try:
                created_at = datetime.fromisoformat(
                    data["created"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass
        
        return AddCommentOutput(
            ticket_key=input.ticket_key,
            comment_id=comment_id,
            author=author,
            created_at=created_at,
        )
        
    except (KeyError, TypeError, AttributeError) as e:
        raise ToolExecutionError(
            tool_name="add_comment",
            message=f"Cannot parse Atlassian response: {e}",
            audit_id=context.audit_id,
        )


# -----------------------------------------------------------------------------
# Tool definitions
# -----------------------------------------------------------------------------

create_ticket_tool = Tool(
    name="create_ticket",
    description="Create a new Jira ticket in a project",
    input_schema=CreateTicketInput,
    output_schema=CreateTicketOutput,
    risk_level=RiskLevel.LOW_WRITE,
    allowed_environments=[Environment.LOCAL, Environment.DEV, Environment.QA, Environment.PROD],
    requires_approval=False,
    timeout_seconds=60,
    handler=create_ticket_handler,
    required_scopes=["read:jira-work", "write:jira-work"],
    audit_metadata={"category": "atlassian", "executor": "mcp_proxy"},
)

get_ticket_status_tool = Tool(
    name="get_ticket_status",
    description="Get the current status of a Jira ticket",
    input_schema=GetTicketStatusInput,
    output_schema=GetTicketStatusOutput,
    risk_level=RiskLevel.READ,
    allowed_environments=[Environment.LOCAL, Environment.DEV, Environment.QA, Environment.PROD],
    requires_approval=False,
    timeout_seconds=30,
    handler=get_ticket_status_handler,
    required_scopes=["read:jira-work"],
    audit_metadata={"category": "atlassian", "executor": "mcp_proxy"},
)

add_comment_tool = Tool(
    name="add_comment",
    description="Add a comment to an existing Jira ticket",
    input_schema=AddCommentInput,
    output_schema=AddCommentOutput,
    risk_level=RiskLevel.LOW_WRITE,
    allowed_environments=[Environment.LOCAL, Environment.DEV, Environment.QA, Environment.PROD],
    requires_approval=False,
    timeout_seconds=30,
    handler=add_comment_handler,
    required_scopes=["read:jira-work", "write:jira-work"],
    audit_metadata={"category": "atlassian", "executor": "mcp_proxy"},
)


# List of all Jira tools for registry
JIRA_TOOLS = [
    create_ticket_tool,
    get_ticket_status_tool,
    add_comment_tool,
]
