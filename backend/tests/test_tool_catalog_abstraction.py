"""Tests for Task D1: Tool Catalog Abstraction.
Tests for Task D2: Workflow-Scoped Tool Exposure Policy.

Tests cover:
- ToolMetadata creation and inference
- EnhancedToolCatalog filtering by workflow, risk, provider
- Catalog conversions (Ollama format, MCPTool)
- Metadata registry enrichment
- ToolExposurePolicy application and configuration
- Policy overrides and custom configs

Regression tests:
- Filter operations return new catalog (immutability)
- Inferred metadata matches naming patterns
- Empty catalogs handled gracefully
- Policy blocklist takes precedence over allowlist
"""
import pytest
from datetime import datetime, timezone

from app.services.tool_catalog import (
    ToolMetadata,
    ToolRiskLevel,
    ToolProvider,
    WorkflowType,
    EnhancedToolCatalog,
    ToolExposurePolicy,
    ToolExposurePolicyConfig,
    DEFAULT_TOOL_METADATA_REGISTRY,
    DEFAULT_WORKFLOW_POLICIES,
    get_default_metadata_registry,
    get_policy_for_workflow,
)
from app.services.mcp_client import MCPTool


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def sample_mcp_tools():
    """Create sample MCP tools for testing."""
    return [
        MCPTool(
            name="create_club",
            description="Create a new golf club",
            input_schema={"type": "object", "properties": {"name": {"type": "string"}}},
            server_name="gateway-mcp",
        ),
        MCPTool(
            name="get_club_by_name",
            description="Get club details by name",
            input_schema={"type": "object", "properties": {"name": {"type": "string"}}},
            server_name="gateway-mcp",
        ),
        MCPTool(
            name="create_ticket",
            description="Create a Jira ticket",
            input_schema={"type": "object", "properties": {"summary": {"type": "string"}}},
            server_name="atlassian-mcp",
        ),
        MCPTool(
            name="get_ticket_status",
            description="Get ticket status",
            input_schema={"type": "object", "properties": {"ticket_id": {"type": "string"}}},
            server_name="atlassian-mcp",
        ),
        MCPTool(
            name="delete_user",
            description="Delete a user account",
            input_schema={"type": "object", "properties": {"user_id": {"type": "string"}}},
            server_name="admin-service",
        ),
    ]


@pytest.fixture
def enhanced_catalog(sample_mcp_tools):
    """Create an enhanced catalog from sample tools."""
    return EnhancedToolCatalog.from_mcp_tools(
        sample_mcp_tools,
        metadata_registry=get_default_metadata_registry(),
    )


# ==============================================================================
# ToolMetadata Tests
# ==============================================================================

class TestToolMetadata:
    """Tests for ToolMetadata creation and inference."""
    
    def test_create_from_mcp_tool_with_registry(self):
        """ToolMetadata created with registry enrichment."""
        tool = MCPTool(
            name="create_club",
            description="Create a club",
            input_schema={"type": "object"},
            server_name="brs",
        )
        
        meta = ToolMetadata.from_mcp_tool(tool, get_default_metadata_registry())
        
        assert meta.name == "create_club"
        assert meta.risk_level == ToolRiskLevel.LOW_WRITE
        assert meta.provider == ToolProvider.BRS
        assert WorkflowType.CLUB_SETUP in meta.workflow_tags
        assert not meta.requires_approval
    
    def test_create_from_mcp_tool_with_inference(self):
        """ToolMetadata created with inference when no registry match."""
        tool = MCPTool(
            name="get_weather",
            description="Get weather data",
            input_schema={"type": "object"},
            server_name="weather-service",
        )
        
        meta = ToolMetadata.from_mcp_tool(tool, {})
        
        assert meta.name == "get_weather"
        assert meta.risk_level == ToolRiskLevel.READ  # Inferred from get_ prefix
        assert WorkflowType.GENERAL in meta.workflow_tags
    
    def test_infer_risk_from_create_prefix(self):
        """create_ prefix infers LOW_WRITE risk."""
        tool = MCPTool(
            name="create_something",
            description="Create something",
            input_schema={},
            server_name="test",
        )
        
        meta = ToolMetadata.from_mcp_tool(tool, {})
        
        assert meta.risk_level == ToolRiskLevel.LOW_WRITE
    
    def test_infer_risk_from_delete_prefix(self):
        """delete_ prefix infers HIGH_WRITE risk with approval."""
        tool = MCPTool(
            name="delete_item",
            description="Delete an item",
            input_schema={},
            server_name="test",
        )
        
        meta = ToolMetadata.from_mcp_tool(tool, {})
        
        assert meta.risk_level == ToolRiskLevel.HIGH_WRITE
        assert meta.requires_approval
    
    def test_infer_provider_from_server_name(self):
        """Provider inferred from server name patterns."""
        # BRS/Gateway server
        tool = MCPTool(name="tool1", description="", input_schema={}, server_name="gateway-mcp")
        meta = ToolMetadata.from_mcp_tool(tool, {})
        assert meta.provider == ToolProvider.BRS
        
        # Atlassian server
        tool2 = MCPTool(name="tool2", description="", input_schema={}, server_name="jira-service")
        meta2 = ToolMetadata.from_mcp_tool(tool2, {})
        assert meta2.provider == ToolProvider.ATLASSIAN
    
    def test_infer_workflow_from_name(self):
        """Workflow tags inferred from tool name patterns."""
        tool = MCPTool(name="setup_club", description="", input_schema={}, server_name="brs")
        meta = ToolMetadata.from_mcp_tool(tool, {})
        assert WorkflowType.CLUB_SETUP in meta.workflow_tags
        
        tool2 = MCPTool(name="create_ticket", description="", input_schema={}, server_name="jira")
        meta2 = ToolMetadata.from_mcp_tool(tool2, {})
        assert WorkflowType.TICKET_MANAGEMENT in meta2.workflow_tags
    
    def test_to_ollama_format(self):
        """ToolMetadata converts to Ollama format correctly."""
        meta = ToolMetadata(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {"x": {"type": "string"}}},
            server_name="test",
        )
        
        result = meta.to_ollama_format()
        
        assert result["type"] == "function"
        assert result["function"]["name"] == "test_tool"
        assert result["function"]["description"] == "A test tool"
        assert result["function"]["parameters"] == meta.input_schema
    
    def test_is_write_operation(self):
        """is_write_operation returns True for non-READ risk levels."""
        read_meta = ToolMetadata(
            name="get_data", description="", input_schema={}, server_name="",
            risk_level=ToolRiskLevel.READ,
        )
        write_meta = ToolMetadata(
            name="create_data", description="", input_schema={}, server_name="",
            risk_level=ToolRiskLevel.LOW_WRITE,
        )
        
        assert not read_meta.is_write_operation()
        assert write_meta.is_write_operation()
    
    def test_is_external(self):
        """is_external returns True when required_scopes is populated."""
        internal = ToolMetadata(
            name="internal", description="", input_schema={}, server_name="",
        )
        external = ToolMetadata(
            name="external", description="", input_schema={}, server_name="",
            required_scopes=["jira:read"],
        )
        
        assert not internal.is_external()
        assert external.is_external()
    
    def test_matches_workflow(self):
        """matches_workflow checks workflow tags."""
        meta = ToolMetadata(
            name="club_tool", description="", input_schema={}, server_name="",
            workflow_tags={WorkflowType.CLUB_SETUP},
        )
        
        assert meta.matches_workflow(WorkflowType.CLUB_SETUP)
        assert not meta.matches_workflow(WorkflowType.TICKET_MANAGEMENT)


# ==============================================================================
# EnhancedToolCatalog Tests
# ==============================================================================

class TestEnhancedToolCatalog:
    """Tests for EnhancedToolCatalog creation and filtering."""
    
    def test_create_from_mcp_tools(self, sample_mcp_tools):
        """Catalog created from MCP tools with metadata enrichment."""
        catalog = EnhancedToolCatalog.from_mcp_tools(
            sample_mcp_tools,
            metadata_registry=get_default_metadata_registry(),
        )
        
        assert catalog.tool_count == 5
        assert catalog.has_tool("create_club")
        assert catalog.has_tool("get_ticket_status")
    
    def test_get_tool(self, enhanced_catalog):
        """get_tool returns correct tool metadata."""
        tool = enhanced_catalog.get_tool("create_club")
        
        assert tool is not None
        assert tool.name == "create_club"
        assert tool.risk_level == ToolRiskLevel.LOW_WRITE
    
    def test_get_tool_not_found(self, enhanced_catalog):
        """get_tool returns None for unknown tool."""
        assert enhanced_catalog.get_tool("nonexistent") is None
    
    def test_tool_names(self, enhanced_catalog):
        """tool_names returns all tool names."""
        names = enhanced_catalog.tool_names
        
        assert "create_club" in names
        assert "get_ticket_status" in names
        assert len(names) == 5
    
    # ==========================================================================
    # Filtering Tests
    # ==========================================================================
    
    def test_filter_by_workflow_club_setup(self, enhanced_catalog):
        """filter_by_workflow returns tools for club setup."""
        filtered = enhanced_catalog.filter_by_workflow(WorkflowType.CLUB_SETUP)
        
        # Should include club tools
        assert filtered.has_tool("create_club")
        assert filtered.has_tool("get_club_by_name")
        
        # Filter description recorded
        assert "club_setup" in filtered.filter_description
    
    def test_filter_by_workflow_ticket_management(self, enhanced_catalog):
        """filter_by_workflow returns tools for ticket management."""
        filtered = enhanced_catalog.filter_by_workflow(WorkflowType.TICKET_MANAGEMENT)
        
        assert filtered.has_tool("create_ticket")
        assert filtered.has_tool("get_ticket_status")
    
    def test_filter_by_workflow_returns_new_catalog(self, enhanced_catalog):
        """Filtering returns a new catalog, not modifying original."""
        original_count = enhanced_catalog.tool_count
        filtered = enhanced_catalog.filter_by_workflow(WorkflowType.CLUB_SETUP)
        
        # Original unchanged
        assert enhanced_catalog.tool_count == original_count
        # Filtered is different
        assert filtered.tool_count <= original_count
    
    def test_filter_by_risk_read_only(self, enhanced_catalog):
        """filter_by_risk with READ returns only read tools."""
        filtered = enhanced_catalog.filter_by_risk(ToolRiskLevel.READ)
        
        for tool in filtered.tools:
            assert tool.risk_level == ToolRiskLevel.READ
    
    def test_filter_by_risk_up_to_low_write(self, enhanced_catalog):
        """filter_by_risk with LOW_WRITE includes READ and LOW_WRITE."""
        filtered = enhanced_catalog.filter_by_risk(ToolRiskLevel.LOW_WRITE)
        
        for tool in filtered.tools:
            assert tool.risk_level in [ToolRiskLevel.READ, ToolRiskLevel.LOW_WRITE]
    
    def test_filter_by_provider(self, enhanced_catalog):
        """filter_by_provider returns tools from specified providers."""
        filtered = enhanced_catalog.filter_by_provider([ToolProvider.BRS])
        
        for tool in filtered.tools:
            assert tool.provider == ToolProvider.BRS
    
    def test_filter_by_multiple_providers(self, enhanced_catalog):
        """filter_by_provider works with multiple providers."""
        filtered = enhanced_catalog.filter_by_provider([ToolProvider.BRS, ToolProvider.ATLASSIAN])
        
        providers = {tool.provider for tool in filtered.tools}
        assert providers <= {ToolProvider.BRS, ToolProvider.ATLASSIAN}
    
    def test_filter_healthy(self):
        """filter_healthy returns only healthy tools."""
        tools = [
            ToolMetadata(name="healthy", description="", input_schema={}, server_name="", is_healthy=True),
            ToolMetadata(name="unhealthy", description="", input_schema={}, server_name="", is_healthy=False),
        ]
        catalog = EnhancedToolCatalog(tools=tools)
        
        filtered = catalog.filter_healthy()
        
        assert filtered.tool_count == 1
        assert filtered.has_tool("healthy")
        assert not filtered.has_tool("unhealthy")
    
    def test_filter_read_only(self, enhanced_catalog):
        """filter_read_only returns only READ risk tools."""
        filtered = enhanced_catalog.filter_read_only()
        
        for tool in filtered.tools:
            assert tool.risk_level == ToolRiskLevel.READ
    
    def test_exclude_tools(self, enhanced_catalog):
        """exclude_tools removes specified tools."""
        filtered = enhanced_catalog.exclude_tools(["create_club", "create_ticket"])
        
        assert not filtered.has_tool("create_club")
        assert not filtered.has_tool("create_ticket")
        assert filtered.has_tool("get_club_by_name")
    
    def test_include_only(self, enhanced_catalog):
        """include_only keeps only specified tools."""
        filtered = enhanced_catalog.include_only(["create_club", "get_ticket_status"])
        
        assert filtered.tool_count == 2
        assert filtered.has_tool("create_club")
        assert filtered.has_tool("get_ticket_status")
    
    def test_chained_filters(self, enhanced_catalog):
        """Multiple filters can be chained."""
        filtered = (
            enhanced_catalog
            .filter_by_provider([ToolProvider.BRS])
            .filter_by_risk(ToolRiskLevel.READ)
        )
        
        for tool in filtered.tools:
            assert tool.provider == ToolProvider.BRS
            assert tool.risk_level == ToolRiskLevel.READ
    
    # ==========================================================================
    # Conversion Tests
    # ==========================================================================
    
    def test_to_ollama_format(self, enhanced_catalog):
        """to_ollama_format converts all tools."""
        definitions = enhanced_catalog.to_ollama_format()
        
        assert len(definitions) == enhanced_catalog.tool_count
        
        for defn in definitions:
            assert defn["type"] == "function"
            assert "name" in defn["function"]
            assert "description" in defn["function"]
    
    def test_to_mcp_tools(self, enhanced_catalog):
        """to_mcp_tools converts back to MCPTool list."""
        mcp_tools = enhanced_catalog.to_mcp_tools()
        
        assert len(mcp_tools) == enhanced_catalog.tool_count
        
        for tool in mcp_tools:
            assert isinstance(tool, MCPTool)
    
    def test_to_summary_dict(self, enhanced_catalog):
        """to_summary_dict provides catalog statistics."""
        summary = enhanced_catalog.to_summary_dict()
        
        assert "total_tools" in summary
        assert "by_provider" in summary
        assert "by_risk" in summary
        assert summary["total_tools"] == enhanced_catalog.tool_count
    
    # ==========================================================================
    # Edge Cases
    # ==========================================================================
    
    def test_empty_catalog(self):
        """Empty catalog handles all operations gracefully."""
        catalog = EnhancedToolCatalog(tools=[])
        
        assert catalog.tool_count == 0
        assert catalog.get_tool("anything") is None
        assert not catalog.has_tool("anything")
        assert catalog.to_ollama_format() == []
        assert catalog.filter_by_workflow(WorkflowType.GENERAL).tool_count == 0
    
    def test_filter_with_no_matches(self, enhanced_catalog):
        """Filter returning no matches produces empty catalog."""
        # Filter for a provider that doesn't exist
        filtered = enhanced_catalog.filter_by_provider([ToolProvider.EXTERNAL])
        
        assert filtered.tool_count == 0
        assert filtered.tool_names == []


# ==============================================================================
# Registry Tests
# ==============================================================================

class TestDefaultMetadataRegistry:
    """Tests for the default metadata registry."""
    
    def test_registry_contains_brs_tools(self):
        """Registry has metadata for BRS tools."""
        registry = get_default_metadata_registry()
        
        assert "create_club" in registry
        assert "get_club_by_name" in registry
        assert "verify_club_setup" in registry
    
    def test_registry_contains_atlassian_tools(self):
        """Registry has metadata for Atlassian tools."""
        registry = get_default_metadata_registry()
        
        assert "create_ticket" in registry
        assert "get_ticket_status" in registry
        assert "add_comment" in registry
    
    def test_registry_returns_copy(self):
        """get_default_metadata_registry returns a copy."""
        registry1 = get_default_metadata_registry()
        registry2 = get_default_metadata_registry()
        
        # Should be equal but not same object
        assert registry1 == registry2
        assert registry1 is not registry2
    
    def test_registry_tool_has_required_fields(self):
        """Each registry entry has required fields."""
        registry = get_default_metadata_registry()
        
        for tool_name, metadata in registry.items():
            assert "risk_level" in metadata, f"{tool_name} missing risk_level"
            assert "provider" in metadata, f"{tool_name} missing provider"


# ==============================================================================
# Task D2: Tool Exposure Policy Tests
# ==============================================================================

class TestToolExposurePolicy:
    """Tests for ToolExposurePolicy (Task D2)."""
    
    @pytest.fixture
    def full_catalog(self, sample_mcp_tools):
        """Create a full catalog with all tools."""
        return EnhancedToolCatalog.from_mcp_tools(
            sample_mcp_tools,
            metadata_registry=get_default_metadata_registry(),
        )
    
    def test_policy_default_for_workflow(self, full_catalog):
        """Policy uses default config for workflow type."""
        policy = ToolExposurePolicy(WorkflowType.CLUB_SETUP)
        
        assert policy.workflow == WorkflowType.CLUB_SETUP
        assert policy.config.max_risk_level == ToolRiskLevel.MEDIUM_WRITE
    
    def test_policy_apply_filters_by_workflow(self, full_catalog):
        """Policy.apply() filters by workflow."""
        policy = ToolExposurePolicy(WorkflowType.CLUB_SETUP)
        filtered = policy.apply(full_catalog)
        
        # Club setup tools should be present
        assert filtered.has_tool("create_club")
        assert filtered.has_tool("get_club_by_name")
    
    def test_policy_apply_filters_by_risk(self, full_catalog):
        """Policy.apply() filters by max risk level."""
        policy = ToolExposurePolicy(
            WorkflowType.GENERAL,
            config_overrides={"max_risk_level": "read"},
        )
        filtered = policy.apply(full_catalog)
        
        # Only read tools should be present
        for tool in filtered.tools:
            assert tool.risk_level == ToolRiskLevel.READ
    
    def test_policy_apply_filters_by_provider(self, full_catalog):
        """Policy.apply() filters by allowed providers."""
        policy = ToolExposurePolicy(WorkflowType.CLUB_SETUP)
        filtered = policy.apply(full_catalog)
        
        # Should only have BRS or BUILTIN providers
        for tool in filtered.tools:
            assert tool.provider in [ToolProvider.BRS, ToolProvider.BUILTIN]
    
    def test_policy_blocklist_excludes_tools(self, full_catalog):
        """Policy blocklist excludes specified tools."""
        policy = ToolExposurePolicy(
            WorkflowType.GENERAL,
            config_overrides={"blocked_tools": ["create_club"]},
        )
        filtered = policy.apply(full_catalog)
        
        assert not filtered.has_tool("create_club")
    
    def test_policy_blocklist_takes_precedence(self, full_catalog):
        """Blocklist takes precedence over other filters."""
        policy = ToolExposurePolicy(
            WorkflowType.CLUB_SETUP,
            config_overrides={
                "allowed_tools": ["create_club", "get_club_by_name"],
                "blocked_tools": ["create_club"],
            },
        )
        filtered = policy.apply(full_catalog)
        
        # create_club should be blocked even though it's in allowlist
        assert not filtered.has_tool("create_club")
    
    def test_policy_is_tool_allowed(self, full_catalog):
        """is_tool_allowed checks policy for individual tool."""
        policy = ToolExposurePolicy(WorkflowType.CLUB_SETUP)
        
        create_club = full_catalog.get_tool("create_club")
        create_ticket = full_catalog.get_tool("create_ticket")
        
        assert policy.is_tool_allowed(create_club)
        # Atlassian tools should not be allowed in club_setup
        assert not policy.is_tool_allowed(create_ticket)
    
    def test_policy_custom_config(self, full_catalog):
        """Policy with custom config ignores defaults."""
        custom = ToolExposurePolicyConfig(
            max_risk_level=ToolRiskLevel.READ,
            allowed_providers=[ToolProvider.ATLASSIAN],
        )
        policy = ToolExposurePolicy(
            WorkflowType.GENERAL,
            custom_config=custom,
        )
        
        assert policy.config.max_risk_level == ToolRiskLevel.READ
        assert policy.config.allowed_providers == [ToolProvider.ATLASSIAN]
    
    def test_policy_to_dict(self, full_catalog):
        """Policy serializes to dict for logging."""
        policy = ToolExposurePolicy(WorkflowType.CLUB_SETUP)
        result = policy.to_dict()
        
        assert result["workflow"] == "club_setup"
        assert "max_risk_level" in result
        assert "allowed_providers" in result
    
    def test_get_policy_for_workflow_convenience(self, full_catalog):
        """get_policy_for_workflow convenience function works."""
        policy = get_policy_for_workflow(WorkflowType.TICKET_MANAGEMENT)
        
        assert policy.workflow == WorkflowType.TICKET_MANAGEMENT
        assert policy.config.allowed_providers == [ToolProvider.ATLASSIAN, ToolProvider.BUILTIN]
    
    def test_get_policy_with_overrides(self, full_catalog):
        """get_policy_for_workflow applies overrides."""
        policy = get_policy_for_workflow(
            WorkflowType.GENERAL,
            overrides={"max_risk_level": "read"},
        )
        
        assert policy.config.max_risk_level == ToolRiskLevel.READ


class TestDefaultWorkflowPolicies:
    """Tests for default workflow policy configurations."""
    
    def test_general_policy_defaults(self):
        """GENERAL workflow has sensible defaults."""
        policy = DEFAULT_WORKFLOW_POLICIES[WorkflowType.GENERAL]
        
        assert policy.max_risk_level == ToolRiskLevel.LOW_WRITE
        assert policy.include_general_tools is True
        assert policy.include_builtin_tools is True
    
    def test_club_setup_policy_allows_brs_tools(self):
        """CLUB_SETUP workflow allows BRS tools."""
        policy = DEFAULT_WORKFLOW_POLICIES[WorkflowType.CLUB_SETUP]
        
        assert ToolProvider.BRS in policy.allowed_providers
        assert policy.max_risk_level == ToolRiskLevel.MEDIUM_WRITE
    
    def test_ticket_management_policy_allows_atlassian_tools(self):
        """TICKET_MANAGEMENT workflow allows Atlassian tools."""
        policy = DEFAULT_WORKFLOW_POLICIES[WorkflowType.TICKET_MANAGEMENT]
        
        assert ToolProvider.ATLASSIAN in policy.allowed_providers
        assert policy.max_risk_level == ToolRiskLevel.LOW_WRITE
    
    def test_admin_policy_allows_high_write(self):
        """ADMIN workflow allows high-risk operations."""
        policy = DEFAULT_WORKFLOW_POLICIES[WorkflowType.ADMIN]
        
        assert policy.max_risk_level == ToolRiskLevel.HIGH_WRITE


class TestToolExposurePolicyIntegration:
    """Integration tests for tool exposure in club-setup workflow."""
    
    @pytest.fixture
    def club_setup_tools(self):
        """Create tools for club-setup integration test."""
        return [
            MCPTool(name="create_club", description="Create club", input_schema={}, server_name="brs"),
            MCPTool(name="get_club_config", description="Get config", input_schema={}, server_name="brs"),
            MCPTool(name="verify_club_setup", description="Verify", input_schema={}, server_name="brs"),
            MCPTool(name="create_ticket", description="Create ticket", input_schema={}, server_name="jira"),
            MCPTool(name="delete_all_data", description="Dangerous", input_schema={}, server_name="admin"),
        ]
    
    def test_club_setup_workflow_reduces_tool_surface(self, club_setup_tools):
        """Club setup workflow exposes only relevant tools."""
        catalog = EnhancedToolCatalog.from_mcp_tools(
            club_setup_tools,
            metadata_registry=get_default_metadata_registry(),
        )
        
        policy = get_policy_for_workflow(WorkflowType.CLUB_SETUP)
        filtered = policy.apply(catalog)
        
        # Should include BRS tools
        assert filtered.has_tool("create_club")
        assert filtered.has_tool("get_club_config")
        assert filtered.has_tool("verify_club_setup")
        
        # Should NOT include Atlassian tools
        assert not filtered.has_tool("create_ticket")
        
        # Should NOT include high-risk tools
        assert not filtered.has_tool("delete_all_data")
        
        # Reduced surface
        assert filtered.tool_count < catalog.tool_count


# ==============================================================================
# Regression Tests for Bug Fixes
# ==============================================================================

class TestToolExposurePolicyRegressions:
    """Regression tests for fixed bugs in tool exposure policy."""
    
    @pytest.fixture
    def tools_with_builtin(self):
        """Create tools including a builtin tool."""
        return [
            MCPTool(name="create_club", description="Create club", input_schema={}, server_name="brs"),
            MCPTool(name="get_current_time", description="Get time", input_schema={}, server_name="builtin"),
            MCPTool(name="calculate", description="Calculate", input_schema={}, server_name="builtin"),
        ]
    
    def test_allowlist_empty_intersection_returns_empty(self, tools_with_builtin):
        """P1 Regression: Allowlist with no matching tools returns empty catalog.
        
        Previously, if allowed_tools was set but intersection was empty,
        the prior result was unchanged, exposing non-allowlisted tools.
        """
        catalog = EnhancedToolCatalog.from_mcp_tools(
            tools_with_builtin,
            metadata_registry=get_default_metadata_registry(),
        )
        
        # Create policy with allowlist that doesn't match any tools
        policy = ToolExposurePolicy(
            WorkflowType.GENERAL,
            config_overrides={
                "allowed_tools": ["nonexistent_tool_1", "nonexistent_tool_2"],
                "include_builtin_tools": False,  # Disable to isolate test
            },
        )
        filtered = policy.apply(catalog)
        
        # Should be empty - allowlist strictly enforced
        assert filtered.tool_count == 0
        assert not filtered.has_tool("create_club")
        assert not filtered.has_tool("get_current_time")
    
    def test_blocklisted_builtins_not_readded(self, tools_with_builtin):
        """P1 Regression: Blocklisted builtin tools are not re-added in step 6.
        
        Previously, blocklist was applied in step 5 but builtins were re-added
        in step 6 from the original catalog without checking blocklist.
        """
        catalog = EnhancedToolCatalog.from_mcp_tools(
            tools_with_builtin,
            metadata_registry=get_default_metadata_registry(),
        )
        
        # Create policy that blocks a builtin tool
        policy = ToolExposurePolicy(
            WorkflowType.GENERAL,
            config_overrides={
                "blocked_tools": ["get_current_time"],
                "include_builtin_tools": True,  # Enable builtin inclusion
            },
        )
        filtered = policy.apply(catalog)
        
        # get_current_time should NOT be present (was blocked)
        assert not filtered.has_tool("get_current_time")
        # Other builtin should still be present
        assert filtered.has_tool("calculate")
    
    def test_allowlisted_builtins_only_readded(self, tools_with_builtin):
        """P1 Regression: When allowlist is set, only allowlisted builtins are re-added.
        
        Step 6 should respect the allowlist when adding builtins back.
        """
        catalog = EnhancedToolCatalog.from_mcp_tools(
            tools_with_builtin,
            metadata_registry=get_default_metadata_registry(),
        )
        
        # Create policy with allowlist that includes only one builtin
        policy = ToolExposurePolicy(
            WorkflowType.GENERAL,
            config_overrides={
                "allowed_tools": ["create_club", "get_current_time"],  # Only these allowed
                "include_builtin_tools": True,
            },
        )
        filtered = policy.apply(catalog)
        
        # get_current_time should be present (in allowlist)
        assert filtered.has_tool("get_current_time")
        # calculate should NOT be present (not in allowlist)
        assert not filtered.has_tool("calculate")


class TestMetadataRegistryRegressions:
    """Regression tests for metadata registry fixes."""
    
    def test_deep_copy_prevents_mutation(self):
        """P2 Regression: Modifying returned registry doesn't affect global.
        
        Previously, get_default_metadata_registry() returned a shallow copy,
        so nested dict mutations affected the global default.
        """
        registry1 = get_default_metadata_registry()
        registry2 = get_default_metadata_registry()
        
        # Mutate a nested dict in registry1
        original_risk = registry2.get("create_club", {}).get("risk_level")
        registry1["create_club"]["risk_level"] = "high_write"
        
        # registry2 should NOT be affected
        assert registry2["create_club"]["risk_level"] == original_risk
        assert registry2["create_club"]["risk_level"] != "high_write"
    
    def test_deep_copy_nested_lists(self):
        """P2 Regression: Nested lists are also deep copied."""
        registry1 = get_default_metadata_registry()
        registry2 = get_default_metadata_registry()
        
        # Mutate workflow_tags list if present
        if "workflow_tags" in registry1.get("create_club", {}):
            original_tags = list(registry2["create_club"]["workflow_tags"])
            registry1["create_club"]["workflow_tags"].append("mutated_tag")
            
            # registry2 should NOT be affected
            assert registry2["create_club"]["workflow_tags"] == original_tags
            assert "mutated_tag" not in registry2["create_club"]["workflow_tags"]
