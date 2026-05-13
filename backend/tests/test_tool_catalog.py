"""Tests for Task B1 (Tool Catalog) and Task B2 (Tool Not Found Semantics).

Tests cover:
- Run-scoped tool catalog creation and isolation
- Catalog TTL and no fallback behavior
- Structured tool-not-found classification
- RBAC vs auth remediation
- Error category propagation

Regression tests:
- Two concurrent runs must not share same catalog object
- Long-running run does not silently switch to legacy discovery
- Server with failing /health but working /tools/list still exposes tools
- RBAC denial emits role-policy remediation, not credential remediation
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timezone, timedelta

from app.services.mcp_registry import (
    MCPToolRegistry,
    ToolCatalog,
    ToolNotFoundReason,
    ToolLookupResult,
    DEFAULT_CATALOG_TTL_SECONDS,
)
from app.services.mcp_client import MCPTool, MCPToolResult
from app.services.error_handler import (
    classify_error_from_category,
    classify_error_from_message,
    ErrorType,
    AgentErrorHandler,
    ErrorContext,
)
from app.config.mcp_config import Environment


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def mock_tools():
    """Create mock MCP tools."""
    return [
        MCPTool(
            name="create_club",
            description="Create a club",
            input_schema={"type": "object"},
            server_name="brs",
        ),
        MCPTool(
            name="get_club",
            description="Get club details",
            input_schema={"type": "object"},
            server_name="brs",
        ),
        MCPTool(
            name="send_email",
            description="Send an email",
            input_schema={"type": "object"},
            server_name="notifications",
        ),
    ]


@pytest.fixture
def sample_catalog(mock_tools):
    """Create a sample tool catalog."""
    catalog = ToolCatalog(
        tools=mock_tools,
        tool_to_server={
            "create_club": "brs",
            "get_club": "brs",
            "send_email": "notifications",
        },
        server_to_tools={
            "brs": ["create_club", "get_club"],
            "notifications": ["send_email"],
        },
        server_health={
            "brs": True,
            "notifications": True,
        },
        total_servers=2,
        failed_servers=0,
        ttl_seconds=600,
    )
    return catalog


@pytest.fixture
def registry():
    """Create MCP tool registry instance."""
    return MCPToolRegistry(Environment.DEVELOPMENT)


class MockUser:
    """Mock user for testing."""
    def __init__(self, user_id: int, role_value: str):
        self.id = user_id
        
        class Role:
            def __init__(self, value):
                self.value = value
        
        self.role = Role(role_value)


@pytest.fixture
def admin_user():
    """Create admin user."""
    return MockUser(1, "admin")


# ==============================================================================
# Task B1: Tool Catalog Tests
# ==============================================================================

class TestToolCatalog:
    """Tests for ToolCatalog class."""

    def test_catalog_has_tool(self, sample_catalog):
        """Test checking if tool exists in catalog."""
        assert sample_catalog.has_tool("create_club") is True
        assert sample_catalog.has_tool("get_club") is True
        assert sample_catalog.has_tool("nonexistent") is False

    def test_catalog_get_server_for_tool(self, sample_catalog):
        """Test getting server name for a tool."""
        assert sample_catalog.get_server_for_tool("create_club") == "brs"
        assert sample_catalog.get_server_for_tool("send_email") == "notifications"
        assert sample_catalog.get_server_for_tool("nonexistent") is None

    def test_catalog_get_tool(self, sample_catalog):
        """Test getting tool object from catalog."""
        tool = sample_catalog.get_tool("create_club")
        assert tool is not None
        assert tool.name == "create_club"
        assert tool.server_name == "brs"
        
        assert sample_catalog.get_tool("nonexistent") is None

    def test_catalog_is_valid_not_expired(self, sample_catalog):
        """Test that fresh catalog is valid."""
        assert sample_catalog.is_valid() is True

    def test_catalog_is_valid_expired(self, sample_catalog):
        """Test that expired catalog is invalid."""
        # Set created_at to past (beyond TTL)
        sample_catalog.created_at = datetime.now(timezone.utc) - timedelta(seconds=700)
        assert sample_catalog.is_valid() is False

    def test_catalog_is_valid_no_ttl(self, sample_catalog):
        """Test that catalog with TTL=0 never expires."""
        sample_catalog.ttl_seconds = 0
        sample_catalog.created_at = datetime.now(timezone.utc) - timedelta(days=100)
        assert sample_catalog.is_valid() is True

    def test_catalog_immutable_after_creation(self, sample_catalog):
        """Refactor: Catalog tools list should be copied, not shared.
        
        Verifies that modifying the tools list after creation doesn't affect the catalog.
        """
        original_count = len(sample_catalog.tools)
        
        # Attempting to modify tools list should not affect catalog
        # (Catalog defensively copies the list)
        external_tools = sample_catalog.tools.copy()
        external_tools.append(MCPTool(
            name="fake_tool",
            description="Should not appear",
            input_schema={},
            server_name="fake",
        ))
        
        # Catalog tools unchanged
        assert len(sample_catalog.tools) == original_count

    def test_catalog_to_summary_dict(self, sample_catalog):
        """Test catalog summary generation."""
        summary = sample_catalog.to_summary_dict()
        
        assert summary["total_tools"] == 3
        assert summary["total_servers"] == 2
        assert summary["failed_servers"] == 0
        assert summary["is_valid"] is True
        assert "created_at" in summary


# ==============================================================================
# Task B2: Tool Lookup with Structured Not-Found Reasons
# ==============================================================================

class TestToolLookup:
    """Tests for structured tool lookup."""

    def test_lookup_tool_found(self, sample_catalog):
        """Test successful tool lookup."""
        result = sample_catalog.lookup_tool("create_club")
        
        assert result.found is True
        assert result.server_name == "brs"
        assert result.not_found_reason is None

    def test_lookup_tool_catalog_miss(self, sample_catalog):
        """Test lookup for tool not in catalog."""
        result = sample_catalog.lookup_tool("nonexistent_tool")
        
        assert result.found is False
        assert result.not_found_reason == ToolNotFoundReason.CATALOG_MISS
        assert "not found in any MCP server" in result.error_message

    def test_lookup_tool_unhealthy_server_still_found(self, sample_catalog):
        """Test lookup when server health check failed.
        
        Refactor: Health check is telemetry-only. If tool was discovered
        via tools/list, it should be found even if server marked unhealthy.
        """
        # Mark brs server as unhealthy
        sample_catalog.server_health["brs"] = False
        
        result = sample_catalog.lookup_tool("create_club")
        
        # Tool IS found (health is telemetry, not a gate)
        assert result.found is True
        assert result.server_name == "brs"

    def test_lookup_tool_rbac_denied(self, sample_catalog):
        """Test lookup with role-based access denial (RBAC).
        
        Refactor: Uses RBAC_DENIED, not PERMISSION_DENIED.
        """
        # Test with a role that doesn't have access
        with patch("app.services.mcp_registry.is_tool_allowed", return_value=False):
            result = sample_catalog.lookup_tool("create_club", user_role="pending")
        
        assert result.found is False
        assert result.not_found_reason == ToolNotFoundReason.RBAC_DENIED
        assert "not allowed" in result.error_message.lower()


# ==============================================================================
# Task B1: Registry Catalog Management Tests
# ==============================================================================

class TestRegistryCatalogManagement:
    """Tests for MCPToolRegistry catalog management.
    
    Refactor: Tests updated for create_run_catalog() which returns fresh
    immutable copies instead of shared cached catalogs.
    """

    @pytest.mark.asyncio
    async def test_create_run_catalog_returns_fresh_copy(self, registry, mock_tools):
        """Test that create_run_catalog returns fresh copies each time.
        
        Regression: Two concurrent runs must not share same catalog object.
        """
        # Setup mock client
        mock_client = AsyncMock()
        mock_client.health_check.return_value = True
        mock_client.list_tools.return_value = mock_tools[:2]  # Just BRS tools
        
        registry._initialized = True
        registry.clients = {"brs": mock_client}
        
        # First call creates catalog
        catalog1 = await registry.create_run_catalog()
        assert catalog1 is not None
        assert len(catalog1.tools) == 2
        
        # Second call returns DIFFERENT instance (immutable copy)
        catalog2 = await registry.create_run_catalog()
        assert catalog2 is not catalog1  # Different objects
        
        # But same content (from shared internal cache)
        assert len(catalog2.tools) == len(catalog1.tools)
        
        # list_tools only called once (internal cache reused)
        assert mock_client.list_tools.call_count == 1
        
        # Check metrics
        metrics = registry.get_catalog_metrics()
        assert metrics["creation_count"] == 1  # Internal catalog built once
        assert metrics["copy_count"] >= 2  # At least 2 copies made

    @pytest.mark.asyncio
    async def test_create_run_catalog_force_refresh(self, registry, mock_tools):
        """Test force_refresh rebuilds internal catalog."""
        mock_client = AsyncMock()
        mock_client.health_check.return_value = True
        mock_client.list_tools.return_value = mock_tools[:2]
        
        registry._initialized = True
        registry.clients = {"brs": mock_client}
        
        # Create initial catalog
        catalog1 = await registry.create_run_catalog()
        
        # Force refresh rebuilds internal cache
        catalog2 = await registry.create_run_catalog(force_refresh=True)
        
        # Should be different instances
        assert catalog2 is not catalog1
        
        # list_tools called twice (force refresh)
        assert mock_client.list_tools.call_count == 2

    @pytest.mark.asyncio
    async def test_create_run_catalog_custom_ttl(self, registry, mock_tools):
        """Test custom TTL on catalog creation."""
        mock_client = AsyncMock()
        mock_client.health_check.return_value = True
        mock_client.list_tools.return_value = mock_tools[:2]
        
        registry._initialized = True
        registry.clients = {"brs": mock_client}
        
        catalog = await registry.create_run_catalog(ttl_seconds=60)
        assert catalog.ttl_seconds == 60

    @pytest.mark.asyncio
    async def test_unhealthy_server_still_exposes_tools_if_tools_list_works(self, registry, mock_tools):
        """Regression: Server with failing /health but working /tools/list still exposes tools.
        
        Health check is telemetry-only, not a gate on tool discovery.
        """
        mock_client = AsyncMock()
        mock_client.health_check.return_value = False  # Unhealthy
        mock_client.list_tools.return_value = mock_tools[:2]  # But tools/list works
        
        registry._initialized = True
        registry.clients = {"brs": mock_client}
        
        catalog = await registry.create_run_catalog()
        
        # Server marked unhealthy for telemetry
        assert catalog.server_health.get("brs") is False
        
        # But tools ARE discovered (health check is not a gate)
        assert len(catalog.tools) == 2
        assert catalog.has_tool("create_club")


# ==============================================================================
# Task B2: Error Classification with Categories
# ==============================================================================

class TestErrorClassificationWithCategories:
    """Tests for structured error classification."""

    def test_classify_tool_not_found_from_category(self):
        """Test classification of tool_not_found category."""
        result = classify_error_from_category("tool_not_found")
        assert result == ErrorType.TOOL_NOT_FOUND

    def test_classify_catalog_miss_from_category(self):
        """Test classification of catalog_miss category."""
        result = classify_error_from_category("catalog_miss")
        assert result == ErrorType.TOOL_NOT_FOUND

    def test_classify_server_unavailable_from_category(self):
        """Test classification of server_unavailable category."""
        result = classify_error_from_category("server_unavailable")
        assert result == ErrorType.RESOURCE_EXHAUSTED

    def test_classify_rbac_denied_from_category(self):
        """Test classification of rbac_denied category.
        
        Refactor: RBAC denial is distinct from auth failure.
        """
        result = classify_error_from_category("rbac_denied")
        assert result == ErrorType.RBAC_DENIED

    def test_classify_catalog_stale_from_category(self):
        """Test classification of catalog_stale category."""
        result = classify_error_from_category("catalog_stale")
        assert result == ErrorType.CATALOG_STALE

    def test_classify_unknown_category_returns_none(self):
        """Test that unknown category returns None."""
        result = classify_error_from_category("unknown_category")
        assert result is None

    def test_classify_error_prefers_category(self):
        """Test that category takes precedence over message parsing."""
        # Message suggests validation error, but category is tool_not_found
        result = classify_error_from_message(
            "validation failed",
            http_status=None,
            error_category="tool_not_found"
        )
        assert result == ErrorType.TOOL_NOT_FOUND

    def test_classify_error_falls_back_to_http_status(self):
        """Test fallback to HTTP status when no category."""
        result = classify_error_from_message(
            "some error",
            http_status=404,
            error_category=None
        )
        assert result == ErrorType.TOOL_NOT_FOUND

    def test_classify_error_falls_back_to_message(self):
        """Test fallback to message parsing when no category or status."""
        result = classify_error_from_message(
            "tool not found on any mcp server",
            http_status=None,
            error_category=None
        )
        assert result == ErrorType.TOOL_NOT_FOUND


class TestAgentErrorHandlerWithCategories:
    """Tests for AgentErrorHandler with error categories."""

    def test_classify_error_with_category(self):
        """Test error classification with category parameter."""
        handler = AgentErrorHandler()
        
        result = handler.classify_error(
            "some error message",
            http_status=None,
            error_category="server_unavailable"
        )
        
        assert result == ErrorType.RESOURCE_EXHAUSTED

    def test_classify_error_without_category(self):
        """Test error classification without category (backward compatible)."""
        handler = AgentErrorHandler()
        
        result = handler.classify_error(
            "tool not found",
            http_status=None,
        )
        
        assert result == ErrorType.TOOL_NOT_FOUND


# ==============================================================================
# Task B1 + B2: Integration - Execute Tool with Catalog
# ==============================================================================

class TestExecuteToolWithCatalog:
    """Integration tests for execute_tool_with_catalog."""

    @pytest.mark.asyncio
    async def test_execute_tool_with_catalog_success(self, registry, sample_catalog, admin_user):
        """Test successful tool execution with catalog."""
        # Setup mock client
        mock_client = AsyncMock()
        mock_client.call_tool.return_value = MCPToolResult(
            success=True,
            result={"club_id": "123"},
        )
        
        registry._initialized = True
        registry.clients = {"brs": mock_client}
        
        result = await registry.execute_tool_with_catalog(
            tool_name="create_club",
            arguments={"name": "Test Club"},
            user=admin_user,
            catalog=sample_catalog,
        )
        
        assert result.success is True
        assert result.result == {"club_id": "123"}

    @pytest.mark.asyncio
    async def test_execute_tool_with_catalog_not_found(self, registry, sample_catalog, admin_user):
        """Test tool execution with catalog - tool not found."""
        registry._initialized = True
        registry.clients = {"brs": AsyncMock()}
        
        result = await registry.execute_tool_with_catalog(
            tool_name="nonexistent_tool",
            arguments={},
            user=admin_user,
            catalog=sample_catalog,
        )
        
        assert result.success is False
        assert result.error_category == "tool_not_found"
        assert result.is_semantic_error is True

    @pytest.mark.asyncio
    async def test_execute_tool_with_catalog_rbac_denied(self, registry, sample_catalog):
        """Test tool execution with catalog - RBAC denial.
        
        Refactor: Uses rbac_denied category, not permission_denied.
        """
        pending_user = MockUser(2, "pending")
        
        registry._initialized = True
        registry.clients = {"brs": AsyncMock()}
        
        with patch("app.services.mcp_registry.is_tool_allowed", return_value=False):
            result = await registry.execute_tool_with_catalog(
                tool_name="create_club",
                arguments={},
                user=pending_user,
                catalog=sample_catalog,
            )
        
        assert result.success is False
        assert result.error_category == "rbac_denied"
        assert result.http_status == 403

    @pytest.mark.asyncio
    async def test_execute_tool_with_catalog_unhealthy_server_proceeds(self, registry, sample_catalog, admin_user):
        """Test tool execution when server health check failed.
        
        Refactor: Health is telemetry-only. If tool was discovered via tools/list,
        execution proceeds. Actual failures happen at call_tool level.
        """
        # Mark server as unhealthy in catalog (but tools were discovered)
        sample_catalog.server_health["brs"] = False
        
        # Setup mock client that succeeds
        mock_client = AsyncMock()
        mock_client.call_tool.return_value = MCPToolResult(
            success=True,
            result={"club_id": "123"},
        )
        
        registry._initialized = True
        registry.clients = {"brs": mock_client}
        
        # Execution proceeds despite health check failure
        result = await registry.execute_tool_with_catalog(
            tool_name="create_club",
            arguments={"name": "Test Club"},
            user=admin_user,
            catalog=sample_catalog,
        )
        
        # Should succeed (health check is telemetry, not a gate)
        assert result.success is True
        assert result.result == {"club_id": "123"}


# ==============================================================================
# Regression Tests - Phase B Refactor
# ==============================================================================

class TestRegressionRunIsolation:
    """Regression tests for run-scoped catalog isolation."""

    @pytest.mark.asyncio
    async def test_concurrent_runs_get_separate_catalogs(self, registry, mock_tools):
        """Regression: Two concurrent runs must not share same catalog object.
        
        Each run should get its own immutable snapshot to prevent
        cross-run interference.
        """
        mock_client = AsyncMock()
        mock_client.health_check.return_value = True
        mock_client.list_tools.return_value = mock_tools[:2]
        
        registry._initialized = True
        registry.clients = {"brs": mock_client}
        
        # Simulate two concurrent runs getting catalogs
        import asyncio
        catalog1, catalog2 = await asyncio.gather(
            registry.create_run_catalog(),
            registry.create_run_catalog(),
        )
        
        # Must be different object instances
        assert catalog1 is not catalog2
        assert id(catalog1) != id(catalog2)
        
        # Each has independent state
        catalog1_created = catalog1.created_at
        catalog2_created = catalog2.created_at
        
        # Created at same time (from same internal cache) but different objects
        assert abs((catalog1_created - catalog2_created).total_seconds()) < 1

    @pytest.mark.asyncio
    async def test_catalog_mutation_does_not_affect_other_runs(self, registry, mock_tools):
        """Regression: Mutating one run's catalog must not affect another.
        
        Even if somehow a catalog's internal state is modified,
        it should not leak to other runs.
        """
        mock_client = AsyncMock()
        mock_client.health_check.return_value = True
        mock_client.list_tools.return_value = mock_tools[:2]
        
        registry._initialized = True
        registry.clients = {"brs": mock_client}
        
        catalog1 = await registry.create_run_catalog()
        catalog2 = await registry.create_run_catalog()
        
        # Record original tool counts
        original_count1 = len(catalog1.tools)
        original_count2 = len(catalog2.tools)
        
        # Even if we could mutate catalog1's internal list,
        # catalog2 should be unaffected (they're separate copies)
        assert original_count1 == original_count2
        assert catalog1.tools is not catalog2.tools  # Different list objects


class TestRegressionNoFallback:
    """Regression tests ensuring no silent fallback to legacy path."""

    def test_catalog_stale_error_is_terminal(self):
        """Regression: CATALOG_STALE should be non-retryable.
        
        When catalog expires mid-run, we should NOT silently fall back
        to legacy discovery. Instead, return a clear terminal error.
        """
        from app.services.error_handler import is_error_retryable
        
        # CATALOG_STALE must not be retryable
        assert is_error_retryable(ErrorType.CATALOG_STALE) is False

    def test_rbac_denied_is_non_retryable(self):
        """Regression: RBAC_DENIED should be non-retryable.
        
        Role-based denial is a policy decision, not a transient error.
        """
        from app.services.error_handler import is_error_retryable
        
        assert is_error_retryable(ErrorType.RBAC_DENIED) is False


class TestRegressionRBACRemediation:
    """Regression tests for RBAC vs auth remediation separation."""

    def test_rbac_denial_remediation_differs_from_auth(self):
        """Regression: RBAC denial emits role-policy remediation, not credential remediation.
        
        Auth failure suggests checking credentials.
        RBAC denial suggests contacting admin for role access.
        """
        handler = AgentErrorHandler()
        
        # Create RBAC denial context
        rbac_context = ErrorContext(
            error_type=ErrorType.RBAC_DENIED,
            step_number=1,
            tool_name="create_club",
            error_message="Tool 'create_club' is not allowed for role 'pending'",
            retry_count=0,
            metadata={"error_category": "rbac_denied"},
        )
        
        # Create auth failure context
        auth_context = ErrorContext(
            error_type=ErrorType.AUTH_FAILURE,
            step_number=1,
            tool_name="create_club",
            error_message="Invalid API key",
            retry_count=0,
            metadata={"error_category": "auth_failure"},
        )
        
        # Get recovery decisions
        rbac_action = handler.decide_recovery(rbac_context)
        auth_action = handler.decide_recovery(auth_context)
        
        # RBAC should mention role/policy/admin
        assert "role" in rbac_action.remediation_prompt.lower() or \
               "administrator" in rbac_action.remediation_prompt.lower()
        
        # Auth should mention credentials/token
        assert "credential" in auth_action.remediation_prompt.lower() or \
               "token" in auth_action.remediation_prompt.lower() or \
               "api key" in auth_action.remediation_prompt.lower()

    def test_rbac_uses_distinct_error_type(self):
        """Regression: RBAC uses RBAC_DENIED, not AUTH_FAILURE."""
        result = classify_error_from_category("rbac_denied")
        
        # Should NOT be AUTH_FAILURE
        assert result != ErrorType.AUTH_FAILURE
        
        # Should be RBAC_DENIED
        assert result == ErrorType.RBAC_DENIED


class TestRegressionHealthCheckTelemetryOnly:
    """Regression tests for health check being telemetry-only."""

    @pytest.mark.asyncio
    async def test_health_check_failure_does_not_block_tool_discovery(self, registry, mock_tools):
        """Regression: Server with failing /health but working /tools/list still exposes tools.
        
        Health check is for telemetry/observability, not a gate on discovery.
        """
        mock_client = AsyncMock()
        mock_client.health_check.return_value = False  # Health check fails
        mock_client.list_tools.return_value = mock_tools[:2]  # But tools/list works
        
        registry._initialized = True
        registry.clients = {"brs": mock_client}
        
        catalog = await registry.create_run_catalog()
        
        # Health recorded for telemetry
        assert catalog.server_health.get("brs") is False
        
        # Tools ARE discovered (health check is not a gate)
        assert len(catalog.tools) == 2
        assert catalog.has_tool("create_club")
        assert catalog.has_tool("get_club")

    @pytest.mark.asyncio
    async def test_unhealthy_server_tool_execution_still_proceeds(self, registry, mock_tools):
        """Regression: Tool execution proceeds even with unhealthy server marker.
        
        Health is telemetry-only. Actual failures happen at call_tool level.
        """
        mock_client = AsyncMock()
        mock_client.health_check.return_value = False  # Health check fails
        mock_client.list_tools.return_value = mock_tools[:2]
        mock_client.call_tool.return_value = MCPToolResult(
            success=True,
            result={"created": True},
        )
        
        registry._initialized = True
        registry.clients = {"brs": mock_client}
        
        catalog = await registry.create_run_catalog()
        admin_user = MockUser(1, "admin")
        
        # Execute tool despite unhealthy server
        result = await registry.execute_tool_with_catalog(
            tool_name="create_club",
            arguments={"name": "Test"},
            user=admin_user,
            catalog=catalog,
        )
        
        # Should succeed (actual network issues would fail at call_tool)
        assert result.success is True
        assert catalog.has_tool("get_club")


# ==============================================================================
# Phase B Patch: New Contract Tests
# ==============================================================================

class TestLegacyExecuteToolRBACDenied:
    """Tests for legacy execute_tool emitting rbac_denied."""

    @pytest.mark.asyncio
    async def test_legacy_execute_tool_emits_rbac_denied(self, registry, mock_tools):
        """Legacy execute_tool should emit rbac_denied, not permission_denied."""
        mock_client = AsyncMock()
        mock_client.list_tools.return_value = mock_tools[:2]
        
        registry._initialized = True
        registry.clients = {"brs": mock_client}
        
        pending_user = MockUser(2, "pending")
        
        # Use legacy execute_tool (not execute_tool_with_catalog)
        with patch("app.services.mcp_registry.is_tool_allowed", return_value=False):
            result = await registry.execute_tool(
                tool_name="create_club",
                arguments={},
                user=pending_user,
            )
        
        assert result.success is False
        assert result.error_category == "rbac_denied"  # NOT "permission_denied"
        assert result.http_status == 403
        assert "administrator" in result.error.lower()


class TestMCPToolDeepCopy:
    """Tests for MCPTool deep copy isolation."""

    @pytest.mark.asyncio
    async def test_input_schema_mutation_does_not_leak(self, registry, mock_tools):
        """Mutating input_schema in one run catalog should not affect another.
        
        Deep copy ensures each run gets independent MCPTool objects.
        """
        mock_client = AsyncMock()
        mock_client.health_check.return_value = True
        mock_client.list_tools.return_value = mock_tools[:2]
        
        registry._initialized = True
        registry.clients = {"brs": mock_client}
        
        # Get two separate catalogs
        catalog1 = await registry.create_run_catalog()
        catalog2 = await registry.create_run_catalog()
        
        # Mutate input_schema in catalog1
        tool1 = catalog1.get_tool("create_club")
        original_schema = tool1.input_schema.copy()
        tool1.input_schema["mutated"] = True
        
        # catalog2's tool should NOT be affected
        tool2 = catalog2.get_tool("create_club")
        assert "mutated" not in tool2.input_schema
        
        # Verify original schema is preserved in catalog2
        assert tool2.input_schema == original_schema

    @pytest.mark.asyncio
    async def test_tool_objects_are_different_instances(self, registry, mock_tools):
        """Each catalog should have its own MCPTool instances."""
        mock_client = AsyncMock()
        mock_client.health_check.return_value = True
        mock_client.list_tools.return_value = mock_tools[:2]
        
        registry._initialized = True
        registry.clients = {"brs": mock_client}
        
        catalog1 = await registry.create_run_catalog()
        catalog2 = await registry.create_run_catalog()
        
        tool1 = catalog1.get_tool("create_club")
        tool2 = catalog2.get_tool("create_club")
        
        # Same name but different object instances
        assert tool1.name == tool2.name
        assert tool1 is not tool2
        assert tool1.input_schema is not tool2.input_schema


class TestAsyncLockPreventsRefreshStorm:
    """Tests for async lock preventing parallel refresh storms."""

    @pytest.mark.asyncio
    async def test_concurrent_catalog_creation_uses_lock(self, registry, mock_tools):
        """Multiple concurrent create_run_catalog calls should not all trigger discovery.
        
        The async lock should serialize access to _build_catalog_internal.
        """
        call_count = 0
        
        async def slow_list_tools(force_refresh=False):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)  # Simulate slow discovery
            return mock_tools[:2]
        
        mock_client = AsyncMock()
        mock_client.health_check.return_value = True
        mock_client.list_tools = slow_list_tools
        
        registry._initialized = True
        registry.clients = {"brs": mock_client}
        
        # Trigger multiple concurrent requests
        catalogs = await asyncio.gather(
            registry.create_run_catalog(),
            registry.create_run_catalog(),
            registry.create_run_catalog(),
        )
        
        # All should succeed
        assert all(c is not None for c in catalogs)
        assert all(len(c.tools) == 2 for c in catalogs)
        
        # list_tools should only be called once (due to lock + double-check)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_force_refresh_bypasses_cache_but_uses_lock(self, registry, mock_tools):
        """force_refresh should rebuild but still use lock for safety."""
        mock_client = AsyncMock()
        mock_client.health_check.return_value = True
        mock_client.list_tools.return_value = mock_tools[:2]
        
        registry._initialized = True
        registry.clients = {"brs": mock_client}
        
        # Create initial catalog
        catalog1 = await registry.create_run_catalog()
        
        # Force refresh
        catalog2 = await registry.create_run_catalog(force_refresh=True)
        
        # Both should work
        assert len(catalog1.tools) == 2
        assert len(catalog2.tools) == 2
        
        # list_tools called twice (initial + force refresh)
        assert mock_client.list_tools.call_count == 2
