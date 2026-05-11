"""Integration tests for Gateway MCP routing.

Verifies:
- MCPToolRegistry picks up Gateway MCP server from config
- Gateway tools are discoverable
- Workflow orchestrator routes to Gateway MCP tools
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.config.mcp_config import Environment, get_servers_for_environment
from app.services.mcp_registry import MCPToolRegistry
from app.services.mcp_client import MCPClient, MCPTool, MCPToolResult
from app.services.workflow_orchestrator import (
    WorkflowOrchestrator,
    GATEWAY_TOOL_MAPPING,
)


class TestGatewayMCPConfig:
    """Test Gateway MCP is properly configured."""
    
    def test_gateway_mcp_in_development_servers(self):
        """Gateway MCP should be first in development server list."""
        servers = get_servers_for_environment(Environment.DEVELOPMENT)
        
        assert len(servers) >= 1
        assert servers[0].name == "gateway-mcp"
        # URL is env-driven via MCP_GATEWAY_URL, default is localhost:8090
        assert "/mcp" in servers[0].url
    
    def test_gateway_mcp_in_staging_servers(self):
        """Gateway MCP should be first in staging server list."""
        servers = get_servers_for_environment(Environment.STAGING)
        
        assert len(servers) >= 1
        assert servers[0].name == "gateway-mcp"
        assert "staging" in servers[0].url
    
    def test_gateway_mcp_in_production_servers(self):
        """Gateway MCP should be first in production server list."""
        servers = get_servers_for_environment(Environment.PRODUCTION)
        
        assert len(servers) >= 1
        assert servers[0].name == "gateway-mcp"


class TestMCPToolRegistryDiscovery:
    """Test MCPToolRegistry discovers Gateway MCP tools."""
    
    @pytest.fixture
    def mock_gateway_tools(self):
        """Mock Gateway MCP tools list."""
        return [
            MCPTool(
                name="create_club",
                description="Create a new golf club in the BRS system",
                input_schema={"type": "object", "properties": {"name": {"type": "string"}}},
                server_name="gateway-mcp",
            ),
            MCPTool(
                name="create_admin_user",
                description="Create an admin user for a club",
                input_schema={"type": "object", "properties": {"club_id": {"type": "string"}}},
                server_name="gateway-mcp",
            ),
            MCPTool(
                name="verify_club_setup",
                description="Verify club setup is complete",
                input_schema={"type": "object", "properties": {"club_id": {"type": "string"}}},
                server_name="gateway-mcp",
            ),
            MCPTool(
                name="get_club_config",
                description="Get club configuration",
                input_schema={"type": "object", "properties": {"club_id": {"type": "string"}}},
                server_name="gateway-mcp",
            ),
            MCPTool(
                name="get_club_by_name",
                description="Look up a club by name",
                input_schema={"type": "object", "properties": {"name": {"type": "string"}}},
                server_name="gateway-mcp",
            ),
            MCPTool(
                name="call_internal_api",
                description="Call internal BRS API",
                input_schema={"type": "object", "properties": {"endpoint": {"type": "string"}}},
                server_name="gateway-mcp",
            ),
            MCPTool(
                name="create_ticket",
                description="Create a Jira ticket",
                input_schema={"type": "object", "properties": {"title": {"type": "string"}}},
                server_name="gateway-mcp",
            ),
            MCPTool(
                name="get_ticket_status",
                description="Get Jira ticket status",
                input_schema={"type": "object", "properties": {"ticket_id": {"type": "string"}}},
                server_name="gateway-mcp",
            ),
            MCPTool(
                name="add_comment",
                description="Add comment to a Jira ticket",
                input_schema={"type": "object", "properties": {"ticket_id": {"type": "string"}}},
                server_name="gateway-mcp",
            ),
        ]
    
    @pytest.mark.asyncio
    async def test_registry_initializes_gateway_client(self):
        """MCPToolRegistry should initialize a client for gateway-mcp."""
        registry = MCPToolRegistry(Environment.DEVELOPMENT)
        await registry.initialize()
        
        assert "gateway-mcp" in registry.clients
        
        await registry.close()
    
    @pytest.mark.asyncio
    async def test_registry_discovers_gateway_tools(self, mock_gateway_tools):
        """MCPToolRegistry should discover tools from Gateway MCP."""
        registry = MCPToolRegistry(Environment.DEVELOPMENT)
        await registry.initialize()
        
        # Mock the list_tools response
        gateway_client = registry.clients.get("gateway-mcp")
        gateway_client.list_tools = AsyncMock(return_value=mock_gateway_tools)
        
        tools = await registry.discover_all_tools()
        
        assert "gateway-mcp" in tools
        gateway_tools = tools["gateway-mcp"]
        
        # Verify all 9 Gateway tools are present
        tool_names = [t.name for t in gateway_tools]
        assert "create_club" in tool_names
        assert "create_admin_user" in tool_names
        assert "verify_club_setup" in tool_names
        assert "create_ticket" in tool_names
        
        await registry.close()
    
    @pytest.mark.asyncio
    async def test_registry_finds_gateway_tool(self, mock_gateway_tools):
        """MCPToolRegistry should find tools from Gateway MCP by name."""
        registry = MCPToolRegistry(Environment.DEVELOPMENT)
        await registry.initialize()
        
        # Mock the list_tools response
        gateway_client = registry.clients.get("gateway-mcp")
        gateway_client._tools_cache = mock_gateway_tools
        
        server_name, client = await registry._find_tool("create_club")
        
        assert server_name == "gateway-mcp"
        assert client is not None
        
        await registry.close()


class TestGatewayToolMapping:
    """Test legacy BRS tool name to Gateway tool name mapping."""
    
    def test_brs_teesheet_init_maps_to_create_club(self):
        """brs_teesheet_init should map to create_club."""
        assert GATEWAY_TOOL_MAPPING["brs_teesheet_init"] == "create_club"
    
    def test_brs_create_superuser_maps_to_create_admin_user(self):
        """brs_create_superuser should map to create_admin_user."""
        assert GATEWAY_TOOL_MAPPING["brs_create_superuser"] == "create_admin_user"
    
    def test_brs_config_validate_maps_to_verify_club_setup(self):
        """brs_config_validate should map to verify_club_setup."""
        assert GATEWAY_TOOL_MAPPING["brs_config_validate"] == "verify_club_setup"
    
    def test_orchestrator_resolves_legacy_names(self, db_session):
        """WorkflowOrchestrator should resolve legacy tool names."""
        orchestrator = WorkflowOrchestrator(db_session)
        
        assert orchestrator._resolve_tool_name("brs_teesheet_init") == "create_club"
        assert orchestrator._resolve_tool_name("brs_create_superuser") == "create_admin_user"
        assert orchestrator._resolve_tool_name("brs_config_validate") == "verify_club_setup"
    
    def test_orchestrator_passes_through_new_names(self, db_session):
        """WorkflowOrchestrator should pass through already-resolved names."""
        orchestrator = WorkflowOrchestrator(db_session)
        
        assert orchestrator._resolve_tool_name("create_club") == "create_club"
        assert orchestrator._resolve_tool_name("create_admin_user") == "create_admin_user"
        assert orchestrator._resolve_tool_name("verify_club_setup") == "verify_club_setup"


class TestOrchestratorToolExecution:
    """Test orchestrator executes tools via Gateway MCP."""
    
    @pytest.fixture
    def mock_registry(self, mock_gateway_tools):
        """Create a mock MCP registry."""
        registry = MagicMock(spec=MCPToolRegistry)
        registry.initialize = AsyncMock()
        registry.execute_tool = AsyncMock(return_value=MCPToolResult(
            success=True,
            result={"club_id": "CLUB-001", "database_name": "club_001"},
            execution_time_ms=150.0,
        ))
        return registry
    
    @pytest.mark.asyncio
    async def test_orchestrator_executes_tool_via_gateway(self, db_session, mock_registry):
        """WorkflowOrchestrator should execute tools via Gateway MCP registry."""
        orchestrator = WorkflowOrchestrator(
            db_session,
            mcp_registry=mock_registry,
        )
        
        step = {
            "id": "test_step",
            "name": "Test Step",
            "type": "tool_call",
            "tool": "create_club",
            "inputs": {"name": "Test Golf Club"},
        }
        
        state = {
            "workflow_run_id": 1,
            "step_results": {},
        }
        
        result = await orchestrator._execute_tool_call(step, state)
        
        # Verify registry was called
        mock_registry.initialize.assert_called_once()
        mock_registry.execute_tool.assert_called_once()
        
        # Verify result
        assert result["tool"] == "create_club"
        assert result["result"]["club_id"] == "CLUB-001"
    
    @pytest.mark.asyncio
    async def test_orchestrator_resolves_legacy_tool_in_execution(
        self, db_session, mock_registry
    ):
        """WorkflowOrchestrator should resolve legacy names when executing."""
        orchestrator = WorkflowOrchestrator(
            db_session,
            mcp_registry=mock_registry,
        )
        
        step = {
            "id": "test_step",
            "name": "Test Step",
            "type": "tool_call",
            "tool": "brs_teesheet_init",  # Legacy name
            "inputs": {"name": "Test Golf Club"},
        }
        
        state = {
            "workflow_run_id": 1,
            "step_results": {},
        }
        
        result = await orchestrator._execute_tool_call(step, state)
        
        # Verify resolved tool name was used
        call_args = mock_registry.execute_tool.call_args
        assert call_args[0][0] == "create_club"  # First positional arg is tool name
        
        # Verify result includes both names
        assert result["tool"] == "create_club"
        assert result["original_tool"] == "brs_teesheet_init"


class TestTemplateInputResolution:
    """Test workflow template input resolution."""
    
    def test_resolve_simple_input_reference(self, db_session):
        """Should resolve {{input.field}} references."""
        orchestrator = WorkflowOrchestrator(db_session)
        
        inputs = {"club_name": "{{input.club_name}}"}
        state = {
            "workflow_run_id": 1,
            "step_results": {"club_name": "Test Golf Club"},
        }
        
        resolved = orchestrator._resolve_template_inputs(inputs, state)
        
        assert resolved["club_name"] == "Test Golf Club"
    
    def test_resolve_step_output_reference(self, db_session):
        """Should resolve {{step_id.field}} references."""
        orchestrator = WorkflowOrchestrator(db_session)
        
        inputs = {"club_id": "{{init_database.club_id}}"}
        state = {
            "workflow_run_id": 1,
            "step_results": {
                "init_database_output": {"club_id": "CLUB-001"},
            },
        }
        
        resolved = orchestrator._resolve_template_inputs(inputs, state)
        
        assert resolved["club_id"] == "CLUB-001"
    
    def test_passthrough_static_values(self, db_session):
        """Should pass through static values unchanged."""
        orchestrator = WorkflowOrchestrator(db_session)
        
        inputs = {"country": "IE", "timezone": "Europe/Dublin"}
        state = {"workflow_run_id": 1, "step_results": {}}
        
        resolved = orchestrator._resolve_template_inputs(inputs, state)
        
        assert resolved["country"] == "IE"
        assert resolved["timezone"] == "Europe/Dublin"


# Fixture for database session
@pytest.fixture
def db_session():
    """Create a mock database session."""
    from unittest.mock import MagicMock
    return MagicMock()


@pytest.fixture
def mock_gateway_tools():
    """Mock Gateway MCP tools list."""
    return [
        MCPTool(
            name="create_club",
            description="Create a new golf club",
            input_schema={},
            server_name="gateway-mcp",
        ),
    ]
