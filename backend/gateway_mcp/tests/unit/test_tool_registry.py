"""
Unit tests for Gateway MCP ToolRegistry and Tool dataclass.

Tests cover:
- Tool creation and validation
- ToolRegistry registration and lookup
- Environment filtering
- Risk level filtering
- MCP schema generation
"""

import pytest
from pydantic import BaseModel

from gateway_mcp.tools import (
    EmptyInput,
    EmptyOutput,
    Environment,
    RiskLevel,
    Tool,
    ToolContext,
    ToolRegistry,
)


# ============================================================================
# Test Fixtures
# ============================================================================

class SampleInput(BaseModel):
    """Sample input schema for tests."""
    name: str
    value: int = 0


class SampleOutput(BaseModel):
    """Sample output schema for tests."""
    result: str
    success: bool = True


async def sample_handler(input_data: SampleInput, ctx: ToolContext) -> SampleOutput:
    """Sample handler for tests."""
    return SampleOutput(result=f"processed:{input_data.name}")


@pytest.fixture
def read_tool() -> Tool:
    """Create a read-level tool."""
    return Tool(
        name="get_data",
        description="Get some data",
        input_schema=SampleInput,
        output_schema=SampleOutput,
        risk_level=RiskLevel.READ,
        allowed_environments=[Environment.LOCAL, Environment.DEV, Environment.QA, Environment.PROD],
        timeout_seconds=15,
        handler=sample_handler,
    )


@pytest.fixture
def write_tool() -> Tool:
    """Create a low-write tool."""
    return Tool(
        name="create_data",
        description="Create some data",
        input_schema=SampleInput,
        output_schema=SampleOutput,
        risk_level=RiskLevel.LOW_WRITE,
        allowed_environments=[Environment.LOCAL, Environment.DEV],
        timeout_seconds=60,
        handler=sample_handler,
    )


@pytest.fixture
def external_tool() -> Tool:
    """Create an external tool with required scopes."""
    return Tool(
        name="create_ticket",
        description="Create a Jira ticket",
        input_schema=SampleInput,
        output_schema=SampleOutput,
        risk_level=RiskLevel.LOW_WRITE,
        allowed_environments=[Environment.LOCAL, Environment.DEV, Environment.QA, Environment.PROD],
        timeout_seconds=30,
        required_scopes=["write:jira-work"],
        handler=sample_handler,
    )


@pytest.fixture
def approval_tool() -> Tool:
    """Create a tool that requires approval."""
    return Tool(
        name="delete_data",
        description="Delete some data",
        input_schema=SampleInput,
        output_schema=SampleOutput,
        risk_level=RiskLevel.HIGH_WRITE,
        allowed_environments=[Environment.LOCAL],
        requires_approval=True,
        timeout_seconds=30,
        handler=sample_handler,
    )


@pytest.fixture
def empty_registry() -> ToolRegistry:
    """Create an empty tool registry."""
    return ToolRegistry()


@pytest.fixture
def populated_registry(
    read_tool: Tool,
    write_tool: Tool,
    external_tool: Tool,
    approval_tool: Tool,
) -> ToolRegistry:
    """Create a registry with tools."""
    registry = ToolRegistry()
    registry.register(read_tool)
    registry.register(write_tool)
    registry.register(external_tool)
    registry.register(approval_tool)
    return registry


# ============================================================================
# Tool Dataclass Tests
# ============================================================================

class TestTool:
    """Tests for Tool dataclass."""
    
    def test_create_minimal_tool(self):
        """Test creating a tool with minimal required fields."""
        tool = Tool(
            name="minimal_tool",
            description="A minimal tool",
            input_schema=EmptyInput,
            output_schema=EmptyOutput,
        )
        
        assert tool.name == "minimal_tool"
        assert tool.description == "A minimal tool"
        assert tool.input_schema == EmptyInput
        assert tool.output_schema == EmptyOutput
        assert tool.risk_level == RiskLevel.READ  # default
        assert tool.requires_approval is False  # default
        assert tool.timeout_seconds == 30  # default
        assert tool.required_scopes == []  # default
    
    def test_create_full_tool(self, read_tool: Tool):
        """Test creating a tool with all fields."""
        assert read_tool.name == "get_data"
        assert read_tool.description == "Get some data"
        assert read_tool.risk_level == RiskLevel.READ
        assert Environment.LOCAL in read_tool.allowed_environments
        assert read_tool.timeout_seconds == 15
        assert read_tool.handler is not None
    
    def test_tool_name_required(self):
        """Test that tool name is required."""
        with pytest.raises(ValueError, match="Tool name is required"):
            Tool(
                name="",
                description="Test",
                input_schema=EmptyInput,
                output_schema=EmptyOutput,
            )
    
    def test_tool_description_required(self):
        """Test that tool description is required."""
        with pytest.raises(ValueError, match="Tool description is required"):
            Tool(
                name="test",
                description="",
                input_schema=EmptyInput,
                output_schema=EmptyOutput,
            )
    
    def test_tool_timeout_must_be_positive(self):
        """Test that timeout must be positive."""
        with pytest.raises(ValueError, match="timeout_seconds must be positive"):
            Tool(
                name="test",
                description="Test",
                input_schema=EmptyInput,
                output_schema=EmptyOutput,
                timeout_seconds=0,
            )
    
    def test_is_allowed_in_environment(self, write_tool: Tool):
        """Test environment checking."""
        assert write_tool.is_allowed_in(Environment.LOCAL) is True
        assert write_tool.is_allowed_in(Environment.DEV) is True
        assert write_tool.is_allowed_in(Environment.QA) is False
        assert write_tool.is_allowed_in(Environment.PROD) is False
    
    def test_is_external_tool(self, read_tool: Tool, external_tool: Tool):
        """Test external tool detection."""
        assert read_tool.is_external() is False
        assert external_tool.is_external() is True
    
    def test_to_mcp_schema(self, read_tool: Tool):
        """Test MCP schema generation."""
        schema = read_tool.to_mcp_schema()
        
        assert schema["name"] == "get_data"
        assert schema["description"] == "Get some data"
        assert "inputSchema" in schema
        assert schema["inputSchema"]["type"] == "object"
        assert "properties" in schema["inputSchema"]
        assert "name" in schema["inputSchema"]["properties"]


# ============================================================================
# ToolRegistry Tests
# ============================================================================

class TestToolRegistry:
    """Tests for ToolRegistry."""
    
    def test_empty_registry(self, empty_registry: ToolRegistry):
        """Test empty registry behavior."""
        assert len(empty_registry) == 0
        assert empty_registry.get("nonexistent") is None
        assert empty_registry.list_names() == []
        assert empty_registry.get_all() == []
    
    def test_register_tool(self, empty_registry: ToolRegistry, read_tool: Tool):
        """Test registering a single tool."""
        empty_registry.register(read_tool)
        
        assert len(empty_registry) == 1
        assert "get_data" in empty_registry
        assert empty_registry.get("get_data") == read_tool
    
    def test_register_duplicate_raises(self, empty_registry: ToolRegistry, read_tool: Tool):
        """Test that registering duplicate name raises."""
        empty_registry.register(read_tool)
        
        with pytest.raises(ValueError, match="already registered"):
            empty_registry.register(read_tool)
    
    def test_register_all(self, empty_registry: ToolRegistry, read_tool: Tool, write_tool: Tool):
        """Test registering multiple tools."""
        empty_registry.register_all([read_tool, write_tool])
        
        assert len(empty_registry) == 2
        assert "get_data" in empty_registry
        assert "create_data" in empty_registry
    
    def test_get_tool(self, populated_registry: ToolRegistry):
        """Test getting a tool by name."""
        tool = populated_registry.get("get_data")
        
        assert tool is not None
        assert tool.name == "get_data"
    
    def test_get_nonexistent_tool(self, populated_registry: ToolRegistry):
        """Test getting a nonexistent tool returns None."""
        assert populated_registry.get("nonexistent") is None
    
    def test_get_all(self, populated_registry: ToolRegistry):
        """Test getting all tools."""
        tools = populated_registry.get_all()
        
        assert len(tools) == 4
        names = {t.name for t in tools}
        assert names == {"get_data", "create_data", "create_ticket", "delete_data"}
    
    def test_list_names(self, populated_registry: ToolRegistry):
        """Test listing tool names."""
        names = populated_registry.list_names()
        
        assert len(names) == 4
        assert set(names) == {"get_data", "create_data", "create_ticket", "delete_data"}
    
    def test_get_by_risk_level(self, populated_registry: ToolRegistry):
        """Test filtering by risk level."""
        read_tools = populated_registry.get_by_risk_level(RiskLevel.READ)
        write_tools = populated_registry.get_by_risk_level(RiskLevel.LOW_WRITE)
        high_write_tools = populated_registry.get_by_risk_level(RiskLevel.HIGH_WRITE)
        
        assert len(read_tools) == 1
        assert read_tools[0].name == "get_data"
        
        assert len(write_tools) == 2
        assert {t.name for t in write_tools} == {"create_data", "create_ticket"}
        
        assert len(high_write_tools) == 1
        assert high_write_tools[0].name == "delete_data"
    
    def test_get_for_environment(self, populated_registry: ToolRegistry):
        """Test filtering by environment."""
        local_tools = populated_registry.get_for_environment(Environment.LOCAL)
        prod_tools = populated_registry.get_for_environment(Environment.PROD)
        
        # All 4 tools allow LOCAL
        assert len(local_tools) == 4
        
        # Only get_data and create_ticket allow PROD
        assert len(prod_tools) == 2
        assert {t.name for t in prod_tools} == {"get_data", "create_ticket"}
    
    def test_get_external_tools(self, populated_registry: ToolRegistry):
        """Test getting external tools."""
        external = populated_registry.get_external_tools()
        
        assert len(external) == 1
        assert external[0].name == "create_ticket"
        assert "write:jira-work" in external[0].required_scopes
    
    def test_to_mcp_list(self, populated_registry: ToolRegistry):
        """Test converting to MCP format."""
        mcp_list = populated_registry.to_mcp_list()
        
        assert len(mcp_list) == 4
        assert all("name" in item for item in mcp_list)
        assert all("description" in item for item in mcp_list)
        assert all("inputSchema" in item for item in mcp_list)
    
    def test_contains(self, populated_registry: ToolRegistry):
        """Test __contains__ method."""
        assert "get_data" in populated_registry
        assert "nonexistent" not in populated_registry
    
    def test_iter(self, populated_registry: ToolRegistry):
        """Test iterating over registry."""
        tools = list(populated_registry)
        
        assert len(tools) == 4
        assert all(isinstance(t, Tool) for t in tools)


# ============================================================================
# ToolContext Tests
# ============================================================================

class TestToolContext:
    """Tests for ToolContext."""
    
    def test_create_context(self):
        """Test creating a tool context."""
        ctx = ToolContext(
            user_id=42,
            correlation_id="corr-123",
            audit_id="audit-456",
            environment=Environment.LOCAL,
        )
        
        assert ctx.user_id == 42
        assert ctx.correlation_id == "corr-123"
        assert ctx.audit_id == "audit-456"
        assert ctx.environment == Environment.LOCAL
    
    @pytest.mark.asyncio
    async def test_get_executor_not_set(self):
        """Test that get_executor raises when not set."""
        ctx = ToolContext(
            user_id=1,
            correlation_id="test",
            audit_id="test",
            environment=Environment.LOCAL,
        )
        
        with pytest.raises(RuntimeError, match="Executor not set"):
            await ctx.get_executor()
    
    @pytest.mark.asyncio
    async def test_get_credential_not_set(self):
        """Test that get_credential raises when fetcher not set."""
        ctx = ToolContext(
            user_id=1,
            correlation_id="test",
            audit_id="test",
            environment=Environment.LOCAL,
        )
        
        with pytest.raises(RuntimeError, match="Credential fetcher not set"):
            await ctx.get_credential("atlassian")


# ============================================================================
# Risk Level and Environment Tests
# ============================================================================

class TestEnums:
    """Tests for RiskLevel and Environment enums."""
    
    def test_risk_levels(self):
        """Test risk level enum values."""
        assert RiskLevel.READ.value == "read"
        assert RiskLevel.LOW_WRITE.value == "low_write"
        assert RiskLevel.MEDIUM_WRITE.value == "medium_write"
        assert RiskLevel.HIGH_WRITE.value == "high_write"
    
    def test_environments(self):
        """Test environment enum values."""
        assert Environment.LOCAL.value == "local"
        assert Environment.DEV.value == "dev"
        assert Environment.QA.value == "qa"
        assert Environment.PROD.value == "prod"
