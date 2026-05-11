"""
Unit tests for Atlassian Jira tool handlers.

Tests each Jira tool with mocked MCP proxy:
- create_ticket
- get_ticket_status
- add_comment
"""

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gateway_mcp.core.errors import (
    CredentialMissingError,
    ToolExecutionError,
    UpstreamError,
)
from gateway_mcp.core.executors.mcp_proxy import MCPProxyBackend, MCPToolCallResult
from gateway_mcp.tools.base import Environment, ToolContext
from gateway_mcp.tools.jira import (
    add_comment_handler,
    create_ticket_handler,
    get_ticket_status_handler,
    UPSTREAM_ADD_COMMENT,
    UPSTREAM_CREATE_ISSUE,
    UPSTREAM_GET_ISSUE,
)
from gateway_mcp.tools.schemas import (
    AddCommentInput,
    CreateTicketInput,
    GetTicketStatusInput,
    IssueType,
)


# --------------------
# Fixtures
# --------------------


@pytest.fixture
def mock_mcp_proxy():
    """Mock MCPProxyBackend for testing."""
    mock = MagicMock(spec=MCPProxyBackend)
    mock.call_mcp_tool = AsyncMock()
    return mock


@pytest.fixture
def context(mock_mcp_proxy):
    """Tool context with mock MCP proxy."""
    return ToolContext(
        user_id=42,
        correlation_id="test-corr-jira-123",
        audit_id="test-audit-jira-123",
        environment=Environment.LOCAL,
        _executor=mock_mcp_proxy,
    )


# --------------------
# create_ticket tests
# --------------------


class TestCreateTicket:
    """Tests for create_ticket handler."""

    @pytest.mark.asyncio
    async def test_create_ticket_success(self, context, mock_mcp_proxy):
        """Test successful ticket creation."""
        mock_mcp_proxy.call_mcp_tool.return_value = MCPToolCallResult(
            success=True,
            result={
                "id": "10001",
                "key": "GOLF-123",
                "self": "https://golfnow.atlassian.net/rest/api/3/issue/10001",
                "fields": {
                    "status": {"name": "To Do"},
                    "created": "2026-05-10T10:30:00Z",
                },
            },
            duration_ms=150,
        )

        input = CreateTicketInput(
            project_key="GOLF",
            summary="New onboarding issue",
            description="Details about the issue",
            issue_type=IssueType.TASK,
            labels=["onboarding", "automated"],
        )

        result = await create_ticket_handler(input, context)

        assert result.ticket_id == "10001"
        assert result.ticket_key == "GOLF-123"
        assert "golfnow.atlassian.net" in result.url
        assert result.status == "To Do"

        # Verify MCP proxy was called correctly
        mock_mcp_proxy.call_mcp_tool.assert_called_once()
        call_args = mock_mcp_proxy.call_mcp_tool.call_args
        assert call_args.kwargs["upstream_name"] == "atlassian"
        assert call_args.kwargs["tool_name"] == UPSTREAM_CREATE_ISSUE
        assert call_args.kwargs["arguments"]["project"]["key"] == "GOLF"
        assert call_args.kwargs["arguments"]["summary"] == "New onboarding issue"
        assert call_args.kwargs["user_id"] == 42

    @pytest.mark.asyncio
    async def test_create_ticket_minimal_input(self, context, mock_mcp_proxy):
        """Test ticket creation with minimal input (no description/labels)."""
        mock_mcp_proxy.call_mcp_tool.return_value = MCPToolCallResult(
            success=True,
            result={
                "id": "10002",
                "key": "GOLF-124",
            },
            duration_ms=100,
        )

        input = CreateTicketInput(
            project_key="golf",  # Should be uppercased
            summary="Minimal ticket",
        )

        result = await create_ticket_handler(input, context)

        assert result.ticket_id == "10002"
        assert result.ticket_key == "GOLF-124"
        # URL should be constructed from key when not in response
        assert "GOLF-124" in result.url

        # Verify description and labels were not sent
        call_args = mock_mcp_proxy.call_mcp_tool.call_args
        args = call_args.kwargs["arguments"]
        assert "description" not in args
        assert "labels" not in args

    @pytest.mark.asyncio
    async def test_create_ticket_upstream_error(self, context, mock_mcp_proxy):
        """Test ticket creation failure from upstream MCP."""
        mock_mcp_proxy.call_mcp_tool.return_value = MCPToolCallResult(
            success=False,
            error="Project not found: INVALID",
            duration_ms=50,
        )

        input = CreateTicketInput(
            project_key="INVALID",
            summary="Should fail",
        )

        with pytest.raises(UpstreamError) as exc_info:
            await create_ticket_handler(input, context)

        assert "atlassian" in str(exc_info.value).lower()
        assert "Project not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_ticket_parses_string_result(self, context, mock_mcp_proxy):
        """Test ticket creation with JSON string response."""
        mock_mcp_proxy.call_mcp_tool.return_value = MCPToolCallResult(
            success=True,
            result=json.dumps({
                "id": "10003",
                "key": "GOLF-125",
            }),
            duration_ms=100,
        )

        input = CreateTicketInput(
            project_key="GOLF",
            summary="String result test",
        )

        result = await create_ticket_handler(input, context)

        assert result.ticket_id == "10003"
        assert result.ticket_key == "GOLF-125"

    @pytest.mark.asyncio
    async def test_create_ticket_with_bug_type(self, context, mock_mcp_proxy):
        """Test ticket creation with Bug issue type."""
        mock_mcp_proxy.call_mcp_tool.return_value = MCPToolCallResult(
            success=True,
            result={
                "id": "10004",
                "key": "GOLF-126",
            },
            duration_ms=100,
        )

        input = CreateTicketInput(
            project_key="GOLF",
            summary="Bug report",
            issue_type=IssueType.BUG,
        )

        await create_ticket_handler(input, context)

        call_args = mock_mcp_proxy.call_mcp_tool.call_args
        args = call_args.kwargs["arguments"]
        assert args["issuetype"]["name"] == "Bug"


# --------------------
# get_ticket_status tests
# --------------------


class TestGetTicketStatus:
    """Tests for get_ticket_status handler."""

    @pytest.mark.asyncio
    async def test_get_ticket_status_success(self, context, mock_mcp_proxy):
        """Test successful ticket status retrieval."""
        mock_mcp_proxy.call_mcp_tool.return_value = MCPToolCallResult(
            success=True,
            result={
                "key": "GOLF-123",
                "fields": {
                    "summary": "Onboarding issue",
                    "status": {"name": "In Progress"},
                    "assignee": {
                        "emailAddress": "dev@golfnow.com",
                        "displayName": "Dev User",
                    },
                    "updated": "2026-05-10T14:30:00Z",
                },
            },
            duration_ms=100,
        )

        input = GetTicketStatusInput(ticket_key="GOLF-123")

        result = await get_ticket_status_handler(input, context)

        assert result.found is True
        assert result.ticket_key == "GOLF-123"
        assert result.summary == "Onboarding issue"
        assert result.status == "In Progress"
        assert result.assignee == "dev@golfnow.com"
        assert result.updated_at is not None

        # Verify MCP proxy was called correctly
        call_args = mock_mcp_proxy.call_mcp_tool.call_args
        assert call_args.kwargs["upstream_name"] == "atlassian"
        assert call_args.kwargs["tool_name"] == UPSTREAM_GET_ISSUE
        assert call_args.kwargs["arguments"]["issueIdOrKey"] == "GOLF-123"

    @pytest.mark.asyncio
    async def test_get_ticket_status_not_found(self, context, mock_mcp_proxy):
        """Test ticket not found returns found=False."""
        mock_mcp_proxy.call_mcp_tool.return_value = MCPToolCallResult(
            success=False,
            error="Issue not found: GOLF-999",
            duration_ms=50,
        )

        input = GetTicketStatusInput(ticket_key="GOLF-999")

        result = await get_ticket_status_handler(input, context)

        assert result.found is False
        assert result.ticket_key is None
        assert result.status is None

    @pytest.mark.asyncio
    async def test_get_ticket_status_upstream_error(self, context, mock_mcp_proxy):
        """Test non-404 error raises UpstreamError."""
        mock_mcp_proxy.call_mcp_tool.return_value = MCPToolCallResult(
            success=False,
            error="Internal server error",
            duration_ms=50,
        )

        input = GetTicketStatusInput(ticket_key="GOLF-123")

        with pytest.raises(UpstreamError) as exc_info:
            await get_ticket_status_handler(input, context)

        assert "atlassian" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_get_ticket_status_no_assignee(self, context, mock_mcp_proxy):
        """Test ticket with no assignee."""
        mock_mcp_proxy.call_mcp_tool.return_value = MCPToolCallResult(
            success=True,
            result={
                "key": "GOLF-100",
                "fields": {
                    "summary": "Unassigned ticket",
                    "status": {"name": "Open"},
                    "assignee": None,
                },
            },
            duration_ms=100,
        )

        input = GetTicketStatusInput(ticket_key="GOLF-100")

        result = await get_ticket_status_handler(input, context)

        assert result.found is True
        assert result.assignee is None

    @pytest.mark.asyncio
    async def test_get_ticket_status_uses_display_name(self, context, mock_mcp_proxy):
        """Test assignee falls back to displayName when no email."""
        mock_mcp_proxy.call_mcp_tool.return_value = MCPToolCallResult(
            success=True,
            result={
                "key": "GOLF-101",
                "fields": {
                    "summary": "Display name test",
                    "status": {"name": "Open"},
                    "assignee": {
                        "displayName": "John Doe",
                    },
                },
            },
            duration_ms=100,
        )

        input = GetTicketStatusInput(ticket_key="GOLF-101")

        result = await get_ticket_status_handler(input, context)

        assert result.assignee == "John Doe"


# --------------------
# add_comment tests
# --------------------


class TestAddComment:
    """Tests for add_comment handler."""

    @pytest.mark.asyncio
    async def test_add_comment_success(self, context, mock_mcp_proxy):
        """Test successful comment addition."""
        mock_mcp_proxy.call_mcp_tool.return_value = MCPToolCallResult(
            success=True,
            result={
                "id": "50001",
                "author": {
                    "emailAddress": "agent@golfnow.com",
                    "displayName": "Agent Bot",
                },
                "created": "2026-05-10T15:00:00Z",
            },
            duration_ms=100,
        )

        input = AddCommentInput(
            ticket_key="GOLF-123",
            comment_body="This is an automated comment from the agent.",
        )

        result = await add_comment_handler(input, context)

        assert result.ticket_key == "GOLF-123"
        assert result.comment_id == "50001"
        assert result.author == "agent@golfnow.com"
        assert result.created_at is not None

        # Verify MCP proxy was called correctly
        call_args = mock_mcp_proxy.call_mcp_tool.call_args
        assert call_args.kwargs["upstream_name"] == "atlassian"
        assert call_args.kwargs["tool_name"] == UPSTREAM_ADD_COMMENT
        assert call_args.kwargs["arguments"]["issueIdOrKey"] == "GOLF-123"
        assert call_args.kwargs["arguments"]["body"] == "This is an automated comment from the agent."

    @pytest.mark.asyncio
    async def test_add_comment_upstream_error(self, context, mock_mcp_proxy):
        """Test comment addition failure."""
        mock_mcp_proxy.call_mcp_tool.return_value = MCPToolCallResult(
            success=False,
            error="Issue does not exist or you do not have permission",
            duration_ms=50,
        )

        input = AddCommentInput(
            ticket_key="GOLF-999",
            comment_body="Should fail",
        )

        with pytest.raises(UpstreamError) as exc_info:
            await add_comment_handler(input, context)

        assert "atlassian" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_add_comment_parses_string_result(self, context, mock_mcp_proxy):
        """Test comment with JSON string response."""
        mock_mcp_proxy.call_mcp_tool.return_value = MCPToolCallResult(
            success=True,
            result=json.dumps({
                "id": "50002",
                "author": {
                    "displayName": "Test User",
                },
            }),
            duration_ms=100,
        )

        input = AddCommentInput(
            ticket_key="GOLF-123",
            comment_body="String result test",
        )

        result = await add_comment_handler(input, context)

        assert result.comment_id == "50002"
        assert result.author == "Test User"

    @pytest.mark.asyncio
    async def test_add_comment_uses_display_name(self, context, mock_mcp_proxy):
        """Test author falls back to displayName when no email."""
        mock_mcp_proxy.call_mcp_tool.return_value = MCPToolCallResult(
            success=True,
            result={
                "id": "50003",
                "author": {
                    "displayName": "Jane Smith",
                },
                "created": "2026-05-10T16:00:00Z",
            },
            duration_ms=100,
        )

        input = AddCommentInput(
            ticket_key="GOLF-100",
            comment_body="Fallback test",
        )

        result = await add_comment_handler(input, context)

        assert result.author == "Jane Smith"

    @pytest.mark.asyncio
    async def test_add_comment_unknown_author(self, context, mock_mcp_proxy):
        """Test comment with no author information."""
        mock_mcp_proxy.call_mcp_tool.return_value = MCPToolCallResult(
            success=True,
            result={
                "id": "50004",
            },
            duration_ms=100,
        )

        input = AddCommentInput(
            ticket_key="GOLF-100",
            comment_body="No author test",
        )

        result = await add_comment_handler(input, context)

        assert result.author == "unknown"


# --------------------
# Error handling tests
# --------------------


class TestJiraToolErrors:
    """Tests for error handling across all Jira tools."""

    @pytest.mark.asyncio
    async def test_non_mcp_proxy_executor_raises(self, mock_mcp_proxy):
        """Test that non-MCPProxyBackend executor raises error."""
        # Create context with wrong executor type
        context = ToolContext(
            user_id=42,
            correlation_id="test-corr",
            audit_id="test-audit",
            environment=Environment.LOCAL,
            _executor=MagicMock(),  # Not an MCPProxyBackend
        )

        input = CreateTicketInput(
            project_key="GOLF",
            summary="Should fail",
        )

        with pytest.raises(RuntimeError) as exc_info:
            await create_ticket_handler(input, context)

        assert "MCPProxyBackend" in str(exc_info.value)


# --------------------
# Tool registration tests
# --------------------


class TestJiraToolRegistration:
    """Tests for Jira tool definitions."""

    def test_create_ticket_tool_definition(self):
        """Test create_ticket tool is properly configured."""
        from gateway_mcp.tools.jira import create_ticket_tool

        assert create_ticket_tool.name == "create_ticket"
        assert create_ticket_tool.handler is not None
        assert "read:jira-work" in create_ticket_tool.required_scopes
        assert "write:jira-work" in create_ticket_tool.required_scopes

    def test_get_ticket_status_tool_definition(self):
        """Test get_ticket_status tool is properly configured."""
        from gateway_mcp.tools.jira import get_ticket_status_tool
        from gateway_mcp.tools.base import RiskLevel

        assert get_ticket_status_tool.name == "get_ticket_status"
        assert get_ticket_status_tool.risk_level == RiskLevel.READ
        assert get_ticket_status_tool.handler is not None

    def test_add_comment_tool_definition(self):
        """Test add_comment tool is properly configured."""
        from gateway_mcp.tools.jira import add_comment_tool

        assert add_comment_tool.name == "add_comment"
        assert add_comment_tool.handler is not None

    def test_jira_tools_list(self):
        """Test JIRA_TOOLS contains all 3 tools."""
        from gateway_mcp.tools.jira import JIRA_TOOLS

        assert len(JIRA_TOOLS) == 3
        tool_names = {t.name for t in JIRA_TOOLS}
        assert tool_names == {"create_ticket", "get_ticket_status", "add_comment"}

    def test_jira_tools_registered_in_full_registry(self):
        """Test Jira tools are in the full registry."""
        from gateway_mcp.tools import create_full_registry

        registry = create_full_registry()

        assert registry.get("create_ticket") is not None
        assert registry.get("get_ticket_status") is not None
        assert registry.get("add_comment") is not None
        assert len(registry) == 9  # 6 BRS + 3 Jira
