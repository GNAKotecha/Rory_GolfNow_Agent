"""
Integration tests for Atlassian Jira workflow.

Tests the end-to-end flow:
1. create_ticket → Create a new Jira ticket
2. get_ticket_status → Verify ticket was created
3. add_comment → Add a comment to the ticket

Uses mocked upstream MCP responses to simulate Atlassian behavior.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gateway_mcp.core.config import Settings, UpstreamMCPConfig
from gateway_mcp.core.executors.mcp_proxy import MCPProxyBackend, MCPToolCallResult
from gateway_mcp.tools.base import Environment, ToolContext
from gateway_mcp.tools.jira import (
    add_comment_handler,
    create_ticket_handler,
    get_ticket_status_handler,
)
from gateway_mcp.tools.schemas import (
    AddCommentInput,
    CreateTicketInput,
    GetTicketStatusInput,
    IssueType,
)


class MockAtlassianMCP:
    """
    Mock for Atlassian MCP that simulates realistic behavior.
    
    Maintains state across calls to simulate a real Jira instance:
    - Tracks created tickets
    - Returns ticket details for status queries
    - Adds comments with proper IDs
    """
    
    def __init__(self):
        self.tickets: dict[str, dict] = {}
        self.next_ticket_num = 1
        self.next_comment_num = 1
    
    async def handle_tool_call(
        self,
        tool_name: str,
        arguments: dict,
        user_id: int,
    ) -> MCPToolCallResult:
        """Handle a tool call and return appropriate response."""
        
        if tool_name == "create_issue":
            return await self._create_issue(arguments)
        elif tool_name == "get_issue":
            return await self._get_issue(arguments)
        elif tool_name == "add_comment":
            return await self._add_comment(arguments)
        else:
            return MCPToolCallResult(
                success=False,
                error=f"Unknown tool: {tool_name}",
            )
    
    async def _create_issue(self, args: dict) -> MCPToolCallResult:
        """Simulate creating a Jira issue."""
        project_key = args["project"]["key"]
        summary = args["summary"]
        issue_type = args.get("issuetype", {}).get("name", "Task")
        
        ticket_key = f"{project_key}-{self.next_ticket_num}"
        ticket_id = f"1000{self.next_ticket_num}"
        self.next_ticket_num += 1
        
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        ticket = {
            "id": ticket_id,
            "key": ticket_key,
            "self": f"https://golfnow.atlassian.net/rest/api/3/issue/{ticket_id}",
            "fields": {
                "summary": summary,
                "description": args.get("description", ""),
                "issuetype": {"name": issue_type},
                "status": {"name": "To Do"},
                "created": now,
                "updated": now,
                "assignee": None,
                "labels": args.get("labels", []),
            },
            "comments": [],
        }
        
        self.tickets[ticket_key] = ticket
        
        return MCPToolCallResult(
            success=True,
            result={
                "id": ticket_id,
                "key": ticket_key,
                "self": ticket["self"],
                "fields": {
                    "status": {"name": "To Do"},
                    "created": now,
                },
            },
            duration_ms=150,
        )
    
    async def _get_issue(self, args: dict) -> MCPToolCallResult:
        """Simulate getting a Jira issue."""
        issue_key = args["issueIdOrKey"]
        
        if issue_key not in self.tickets:
            return MCPToolCallResult(
                success=False,
                error=f"Issue not found: {issue_key}",
                duration_ms=50,
            )
        
        ticket = self.tickets[issue_key]
        
        return MCPToolCallResult(
            success=True,
            result={
                "id": ticket["id"],
                "key": ticket["key"],
                "self": ticket["self"],
                "fields": ticket["fields"],
            },
            duration_ms=100,
        )
    
    async def _add_comment(self, args: dict) -> MCPToolCallResult:
        """Simulate adding a comment to a Jira issue."""
        issue_key = args["issueIdOrKey"]
        body = args["body"]
        
        if issue_key not in self.tickets:
            return MCPToolCallResult(
                success=False,
                error=f"Issue does not exist: {issue_key}",
                duration_ms=50,
            )
        
        comment_id = f"5000{self.next_comment_num}"
        self.next_comment_num += 1
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        comment = {
            "id": comment_id,
            "body": body,
            "author": {
                "emailAddress": "agent@golfnow.com",
                "displayName": "GolfNow Agent",
            },
            "created": now,
        }
        
        self.tickets[issue_key]["comments"].append(comment)
        
        return MCPToolCallResult(
            success=True,
            result=comment,
            duration_ms=100,
        )


class TestJiraWorkflow:
    """Integration tests for Jira workflow."""
    
    @pytest.fixture
    def mock_atlassian(self):
        """Create mock Atlassian MCP."""
        return MockAtlassianMCP()
    
    @pytest.fixture
    def mcp_proxy(self, mock_atlassian):
        """Create MCPProxyBackend with mocked call_mcp_tool."""
        settings = Settings(
            env="local",
            executor_backend="mock",  # Use valid executor type
            upstream_mcps={
                "atlassian": UpstreamMCPConfig(
                    url="https://mcp.atlassian.com/v1/mcp",
                    auth_mode="oauth",
                    provider="atlassian",
                ),
            },
        )
        
        proxy = MCPProxyBackend(settings)
        
        # Patch call_mcp_tool to use mock Atlassian
        async def mocked_call(
            upstream_name: str,
            tool_name: str,
            arguments: dict,
            timeout: int,
            bearer_token: str = None,
            user_id: int = None,
        ):
            if upstream_name == "atlassian":
                return await mock_atlassian.handle_tool_call(
                    tool_name, arguments, user_id
                )
            # For non-atlassian, return error
            return MCPToolCallResult(
                success=False,
                error=f"Unknown upstream: {upstream_name}",
            )
        
        proxy.call_mcp_tool = mocked_call
        return proxy
    
    @pytest.fixture
    def context(self, mcp_proxy):
        """Create tool context with MCP proxy."""
        return ToolContext(
            user_id=42,
            correlation_id="integration-test-corr",
            audit_id="integration-test-audit",
            environment=Environment.LOCAL,
            _executor=mcp_proxy,
        )
    
    @pytest.mark.asyncio
    async def test_full_jira_workflow(self, context, mock_atlassian):
        """
        Test complete Jira workflow:
        1. create_ticket → Create a new ticket
        2. get_ticket_status → Verify ticket exists with correct data
        3. add_comment → Add a comment to the ticket
        4. get_ticket_status → Verify comment was added
        """
        # Step 1: Create a ticket
        create_input = CreateTicketInput(
            project_key="GOLF",
            summary="Automated onboarding ticket",
            description="This ticket was created by the onboarding workflow.",
            issue_type=IssueType.TASK,
            labels=["onboarding", "automated"],
        )
        
        create_result = await create_ticket_handler(create_input, context)
        
        assert create_result.ticket_key == "GOLF-1"
        assert create_result.ticket_id == "10001"
        assert create_result.status == "To Do"
        assert "golfnow.atlassian.net" in create_result.url
        
        # Step 2: Get ticket status
        status_input = GetTicketStatusInput(ticket_key=create_result.ticket_key)
        
        status_result = await get_ticket_status_handler(status_input, context)
        
        assert status_result.found is True
        assert status_result.ticket_key == "GOLF-1"
        assert status_result.summary == "Automated onboarding ticket"
        assert status_result.status == "To Do"
        assert status_result.assignee is None  # Not assigned yet
        
        # Step 3: Add a comment
        comment_input = AddCommentInput(
            ticket_key=create_result.ticket_key,
            comment_body="Onboarding workflow completed successfully. "
                        "All setup steps have been verified.",
        )
        
        comment_result = await add_comment_handler(comment_input, context)
        
        assert comment_result.ticket_key == "GOLF-1"
        assert comment_result.comment_id == "50001"
        assert comment_result.author == "agent@golfnow.com"
        
        # Step 4: Verify state in mock
        ticket = mock_atlassian.tickets["GOLF-1"]
        assert len(ticket["comments"]) == 1
        assert "workflow completed successfully" in ticket["comments"][0]["body"]
    
    @pytest.mark.asyncio
    async def test_create_multiple_tickets(self, context, mock_atlassian):
        """Test creating multiple tickets in sequence."""
        # Create first ticket
        result1 = await create_ticket_handler(
            CreateTicketInput(project_key="GOLF", summary="First ticket"),
            context,
        )
        
        # Create second ticket
        result2 = await create_ticket_handler(
            CreateTicketInput(project_key="GOLF", summary="Second ticket"),
            context,
        )
        
        # Create ticket in different project
        result3 = await create_ticket_handler(
            CreateTicketInput(project_key="BRS", summary="BRS ticket"),
            context,
        )
        
        assert result1.ticket_key == "GOLF-1"
        assert result2.ticket_key == "GOLF-2"
        assert result3.ticket_key == "BRS-3"
        
        # Verify all tickets exist in mock
        assert len(mock_atlassian.tickets) == 3
    
    @pytest.mark.asyncio
    async def test_add_multiple_comments(self, context, mock_atlassian):
        """Test adding multiple comments to a ticket."""
        # Create a ticket
        create_result = await create_ticket_handler(
            CreateTicketInput(project_key="GOLF", summary="Multi-comment test"),
            context,
        )
        
        # Add first comment
        comment1 = await add_comment_handler(
            AddCommentInput(
                ticket_key=create_result.ticket_key,
                comment_body="First comment",
            ),
            context,
        )
        
        # Add second comment
        comment2 = await add_comment_handler(
            AddCommentInput(
                ticket_key=create_result.ticket_key,
                comment_body="Second comment",
            ),
            context,
        )
        
        assert comment1.comment_id == "50001"
        assert comment2.comment_id == "50002"
        
        # Verify both comments in mock
        ticket = mock_atlassian.tickets["GOLF-1"]
        assert len(ticket["comments"]) == 2
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_ticket(self, context):
        """Test getting status of non-existent ticket."""
        status_result = await get_ticket_status_handler(
            GetTicketStatusInput(ticket_key="GOLF-999"),
            context,
        )
        
        assert status_result.found is False
        assert status_result.ticket_key is None
    
    @pytest.mark.asyncio
    async def test_different_issue_types(self, context, mock_atlassian):
        """Test creating tickets with different issue types."""
        # Task
        task = await create_ticket_handler(
            CreateTicketInput(
                project_key="GOLF",
                summary="Task ticket",
                issue_type=IssueType.TASK,
            ),
            context,
        )
        
        # Bug
        bug = await create_ticket_handler(
            CreateTicketInput(
                project_key="GOLF",
                summary="Bug ticket",
                issue_type=IssueType.BUG,
            ),
            context,
        )
        
        # Story
        story = await create_ticket_handler(
            CreateTicketInput(
                project_key="GOLF",
                summary="Story ticket",
                issue_type=IssueType.STORY,
            ),
            context,
        )
        
        # Verify issue types in mock
        assert mock_atlassian.tickets["GOLF-1"]["fields"]["issuetype"]["name"] == "Task"
        assert mock_atlassian.tickets["GOLF-2"]["fields"]["issuetype"]["name"] == "Bug"
        assert mock_atlassian.tickets["GOLF-3"]["fields"]["issuetype"]["name"] == "Story"


class TestJiraWorkflowErrorHandling:
    """Integration tests for error handling in Jira workflow."""
    
    @pytest.fixture
    def error_mcp_proxy(self):
        """Create MCPProxyBackend that returns errors."""
        settings = Settings(
            env="local",
            executor_backend="mock",  # Use valid executor type
            upstream_mcps={
                "atlassian": UpstreamMCPConfig(
                    url="https://mcp.atlassian.com/v1/mcp",
                    auth_mode="oauth",
                    provider="atlassian",
                ),
            },
        )
        
        proxy = MCPProxyBackend(settings)
        proxy.call_mcp_tool = AsyncMock()
        return proxy
    
    @pytest.fixture
    def context(self, error_mcp_proxy):
        """Create tool context with error MCP proxy."""
        return ToolContext(
            user_id=42,
            correlation_id="error-test-corr",
            audit_id="error-test-audit",
            environment=Environment.LOCAL,
            _executor=error_mcp_proxy,
        )
    
    @pytest.mark.asyncio
    async def test_comment_on_nonexistent_ticket(self, context, error_mcp_proxy):
        """Test adding comment to non-existent ticket fails properly."""
        from gateway_mcp.core.errors import UpstreamError
        
        error_mcp_proxy.call_mcp_tool.return_value = MCPToolCallResult(
            success=False,
            error="Issue does not exist or you do not have permission to see it",
            duration_ms=50,
        )
        
        with pytest.raises(UpstreamError):
            await add_comment_handler(
                AddCommentInput(
                    ticket_key="NONEXISTENT-999",
                    comment_body="Should fail",
                ),
                context,
            )
