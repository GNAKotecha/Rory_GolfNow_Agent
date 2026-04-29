"""Tests for MCP health checking."""
import pytest
import asyncio
from datetime import datetime, timezone

from app.services.mcp_health import (
    MCPHealthChecker,
    MCPHealthCheckConfig,
    ServerHealthConfig,
    ServerHealthState,
    ServerRequirement,
    HealthStatus,
    get_health_checker,
    reset_health_checker,
)


class TestServerHealthState:
    """Test server health state tracking."""

    def test_initial_state(self):
        """Test initial health state."""
        state = ServerHealthState(server_name="test")
        assert state.status == HealthStatus.UNKNOWN
        assert state.consecutive_failures == 0
        assert state.consecutive_successes == 0

    def test_record_success(self):
        """Test recording successful health checks."""
        config = ServerHealthConfig(
            server_name="test",
            healthy_threshold=2,
        )
        state = ServerHealthState(server_name="test")

        # First success
        state.record_success(config, ["tool1", "tool2"])
        assert state.consecutive_successes == 1
        assert state.status == HealthStatus.UNKNOWN  # Not yet healthy

        # Second success - should transition to healthy
        state.record_success(config, ["tool1", "tool2"])
        assert state.consecutive_successes == 2
        assert state.status == HealthStatus.HEALTHY
        assert state.discovered_tools == ["tool1", "tool2"]

    def test_record_failure(self):
        """Test recording failed health checks."""
        config = ServerHealthConfig(
            server_name="test",
            unhealthy_threshold=2,
        )
        state = ServerHealthState(server_name="test")
        state.status = HealthStatus.HEALTHY

        # First failure
        state.record_failure(config, "Connection refused")
        assert state.consecutive_failures == 1
        assert state.status == HealthStatus.HEALTHY  # Not yet unhealthy

        # Second failure - should transition to unhealthy
        state.record_failure(config, "Connection refused")
        assert state.consecutive_failures == 2
        assert state.status == HealthStatus.UNHEALTHY
        assert state.last_error == "Connection refused"

    def test_success_resets_failure_count(self):
        """Test that success resets failure count."""
        config = ServerHealthConfig(server_name="test")
        state = ServerHealthState(server_name="test")

        state.record_failure(config, "error")
        state.record_failure(config, "error")
        assert state.consecutive_failures == 2

        state.record_success(config, [])
        assert state.consecutive_failures == 0
        assert state.consecutive_successes == 1


class TestMCPHealthChecker:
    """Test MCP health checker."""

    @pytest.fixture(autouse=True)
    def reset(self):
        """Reset global health checker."""
        reset_health_checker()
        yield
        reset_health_checker()

    @pytest.fixture
    def health_checker(self):
        """Create health checker with test config."""
        config = MCPHealthCheckConfig(
            default_healthy_threshold=1,
            default_unhealthy_threshold=1,
            default_timeout_seconds=1,
        )
        return MCPHealthChecker(config)

    def test_register_server(self, health_checker):
        """Test server registration."""
        health_checker.register_server(
            server_name="test-server",
            requirement=ServerRequirement.REQUIRED,
        )

        assert "test-server" in health_checker._server_configs
        assert "test-server" in health_checker._server_states
        assert health_checker.is_server_required("test-server") is True

    @pytest.mark.asyncio
    async def test_check_server_health_success(self, health_checker):
        """Test successful health check."""
        health_checker.register_server("test-server")

        async def probe():
            return True, ["tool1", "tool2"], None

        result = await health_checker.check_server_health("test-server", probe)
        assert result is True
        assert health_checker.is_server_healthy("test-server") is True

    @pytest.mark.asyncio
    async def test_check_server_health_failure(self, health_checker):
        """Test failed health check."""
        health_checker.register_server("test-server")

        async def probe():
            return False, [], "Connection failed"

        result = await health_checker.check_server_health("test-server", probe)
        assert result is False
        assert health_checker.is_server_healthy("test-server") is False

    @pytest.mark.asyncio
    async def test_check_server_health_timeout(self, health_checker):
        """Test health check timeout."""
        health_checker.register_server("test-server")

        async def slow_probe():
            await asyncio.sleep(5)
            return True, [], None

        result = await health_checker.check_server_health("test-server", slow_probe)
        assert result is False

    def test_get_healthy_tools(self, health_checker):
        """Test getting tools from healthy servers only."""
        # Register two servers
        health_checker.register_server("healthy-server")
        health_checker.register_server("unhealthy-server")

        # Make one healthy with tools
        config = health_checker._server_configs["healthy-server"]
        health_checker._server_states["healthy-server"].record_success(
            config, ["tool1", "tool2"]
        )

        # Make one unhealthy
        config = health_checker._server_configs["unhealthy-server"]
        health_checker._server_states["unhealthy-server"].record_failure(
            config, "error"
        )
        health_checker._server_states["unhealthy-server"].discovered_tools = ["tool3"]

        # Should only get tools from healthy server
        healthy_tools = health_checker.get_healthy_tools()
        assert "tool1" in healthy_tools
        assert "tool2" in healthy_tools
        assert "tool3" not in healthy_tools

    def test_is_write_tool(self, health_checker):
        """Test write tool detection."""
        assert health_checker.is_write_tool("create_user") is True
        assert health_checker.is_write_tool("delete_record") is True
        assert health_checker.is_write_tool("update_config") is True
        assert health_checker.is_write_tool("get_users") is False
        assert health_checker.is_write_tool("list_items") is False
        assert health_checker.is_write_tool("search") is False

    def test_can_auto_approve(self, health_checker):
        """Test auto-approve detection."""
        # Read operations can be auto-approved
        assert health_checker.can_auto_approve("get_user") is True
        assert health_checker.can_auto_approve("list_items") is True
        assert health_checker.can_auto_approve("search_records") is True

        # Write operations cannot
        assert health_checker.can_auto_approve("delete_user") is False
        assert health_checker.can_auto_approve("create_record") is False
        assert health_checker.can_auto_approve("update_config") is False

    def test_check_tool_for_execution_healthy(self, health_checker):
        """Test tool availability check for healthy server."""
        health_checker.register_server("server1")

        config = health_checker._server_configs["server1"]
        health_checker._server_states["server1"].record_success(config, ["my_tool"])

        available, reason = health_checker.check_tool_for_execution("my_tool")
        assert available is True
        assert reason == ""

    def test_check_tool_for_execution_unhealthy_write(self, health_checker):
        """Test write tool fails closed on unhealthy server."""
        health_checker.register_server("server1", requirement=ServerRequirement.REQUIRED)

        config = health_checker._server_configs["server1"]
        state = health_checker._server_states["server1"]
        state.discovered_tools = ["delete_item"]
        state.record_failure(config, "error")

        available, reason = health_checker.check_tool_for_execution("delete_item", is_write=True)
        assert available is False
        assert "Write tool unavailable" in reason

    def test_is_degraded(self, health_checker):
        """Test degraded mode detection."""
        health_checker.register_server(
            "optional-server",
            requirement=ServerRequirement.OPTIONAL,
        )

        # Make optional server healthy first
        config = health_checker._server_configs["optional-server"]
        health_checker._server_states["optional-server"].record_success(config, [])
        
        # Now not degraded
        assert health_checker.is_degraded() is False

        # Make optional server unhealthy
        health_checker._server_states["optional-server"].record_failure(config, "error")

        assert health_checker.is_degraded() is True

    def test_check_required_servers(self, health_checker):
        """Test checking required servers."""
        health_checker.register_server("required1", ServerRequirement.REQUIRED)
        health_checker.register_server("required2", ServerRequirement.REQUIRED)
        health_checker.register_server("optional1", ServerRequirement.OPTIONAL)

        # Make required1 healthy
        config = health_checker._server_configs["required1"]
        health_checker._server_states["required1"].record_success(config, [])

        # required2 still unhealthy (unknown)
        all_healthy, unhealthy = health_checker.check_required_servers()
        assert all_healthy is False
        assert "required2" in unhealthy
        assert "optional1" not in unhealthy

    def test_get_server_status(self, health_checker):
        """Test getting server status."""
        health_checker.register_server("test-server", ServerRequirement.REQUIRED)

        config = health_checker._server_configs["test-server"]
        health_checker._server_states["test-server"].record_success(config, ["t1", "t2"])

        status = health_checker.get_server_status("test-server")
        assert status["status"] == "healthy"
        assert status["requirement"] == "required"
        assert status["tools_available"] == 2


class TestGlobalHealthChecker:
    """Test global singleton health checker."""

    def test_singleton_pattern(self):
        """Test singleton creation and reset."""
        reset_health_checker()

        hc1 = get_health_checker()
        hc2 = get_health_checker()
        assert hc1 is hc2

        reset_health_checker()
        hc3 = get_health_checker()
        assert hc3 is not hc1
