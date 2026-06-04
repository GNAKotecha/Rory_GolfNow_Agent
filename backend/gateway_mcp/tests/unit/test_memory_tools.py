"""
Unit tests for Agent Memory tools in Gateway MCP.

Tests tool registration, schema validation, and handler behavior.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from gateway_mcp.tools.memory import (
    MEMORY_TOOLS,
    get_working_memory_handler,
    update_working_memory_handler,
    store_session_summary_handler,
    get_historical_context_handler,
)
from gateway_mcp.tools.memory_schemas import (
    GetWorkingMemoryInput,
    GetWorkingMemoryOutput,
    UpdateWorkingMemoryInput,
    UpdateWorkingMemoryOutput,
    StoreSessionSummaryInput,
    StoreSessionSummaryOutput,
    GetHistoricalContextInput,
    GetHistoricalContextOutput,
)
from gateway_mcp.tools.base import RiskLevel, Environment


class TestMemoryToolRegistration:
    """Test that memory tools are correctly registered."""

    def test_memory_tools_exported(self):
        """Test that MEMORY_TOOLS list exists and contains 4 tools."""
        assert MEMORY_TOOLS is not None
        assert len(MEMORY_TOOLS) == 4

    def test_tool_names(self):
        """Test that all expected tools are present."""
        tool_names = {tool.name for tool in MEMORY_TOOLS}
        expected = {
            "get_working_memory",
            "update_working_memory",
            "store_session_summary",
            "get_historical_context",
        }
        assert tool_names == expected

    def test_tool_descriptions(self):
        """Test that all tools have descriptions."""
        for tool in MEMORY_TOOLS:
            assert tool.description
            assert len(tool.description) > 0

    def test_read_tool_risk_levels(self):
        """Test that read tools have READ risk level."""
        read_tools = [t for t in MEMORY_TOOLS if t.name in [
            "get_working_memory",
            "get_historical_context",
        ]]
        for tool in read_tools:
            assert tool.risk_level == RiskLevel.READ

    def test_write_tool_risk_levels(self):
        """Test that write tools have LOW_WRITE risk level."""
        write_tools = [t for t in MEMORY_TOOLS if t.name in [
            "update_working_memory",
            "store_session_summary",
        ]]
        for tool in write_tools:
            assert tool.risk_level == RiskLevel.LOW_WRITE

    def test_all_tools_allow_production(self):
        """Test that all memory tools are allowed in PROD."""
        for tool in MEMORY_TOOLS:
            assert Environment.PROD in tool.allowed_environments

    def test_tools_no_approval_required(self):
        """Test that memory tools don't require approval."""
        for tool in MEMORY_TOOLS:
            assert tool.requires_approval is False

    def test_tool_timeout_values(self):
        """Test that all tools have reasonable timeout values."""
        for tool in MEMORY_TOOLS:
            assert 0 < tool.timeout_seconds <= 60

    def test_tool_schemas_valid(self):
        """Test that all tools have valid input/output schemas."""
        for tool in MEMORY_TOOLS:
            assert tool.input_schema is not None
            assert tool.output_schema is not None
            # Schema should have model_validate
            assert hasattr(tool.input_schema, 'model_validate')


class TestMemoryToolSchemas:
    """Test input/output schema validation."""

    def test_get_working_memory_input(self):
        """Test GetWorkingMemoryInput validation."""
        # Valid input
        valid = GetWorkingMemoryInput(session_id=1, tenant_id=1)
        assert valid.session_id == 1
        assert valid.tenant_id == 1

        # Invalid: zero session_id
        with pytest.raises(ValueError):
            GetWorkingMemoryInput(session_id=0, tenant_id=1)

        # Invalid: negative tenant_id
        with pytest.raises(ValueError):
            GetWorkingMemoryInput(session_id=1, tenant_id=-1)

    def test_get_working_memory_output(self):
        """Test GetWorkingMemoryOutput validation."""
        output = GetWorkingMemoryOutput(
            session_id=1,
            memory={"key": "value"},
            size_bytes=100,
        )
        assert output.session_id == 1
        assert output.memory == {"key": "value"}
        assert output.size_bytes == 100

    def test_update_working_memory_input(self):
        """Test UpdateWorkingMemoryInput validation."""
        # Valid input
        valid = UpdateWorkingMemoryInput(
            session_id=1,
            tenant_id=1,
            updates={"fact": "value"},
        )
        assert valid.updates == {"fact": "value"}

        # Invalid: empty updates
        with pytest.raises(ValueError):
            UpdateWorkingMemoryInput(
                session_id=1,
                tenant_id=1,
                updates={},
            )

    def test_store_session_summary_input(self):
        """Test StoreSessionSummaryInput validation."""
        # Valid input
        valid = StoreSessionSummaryInput(
            session_id=1,
            tenant_id=1,
            content="Session summary",
        )
        assert valid.content == "Session summary"

        # Invalid: empty content
        with pytest.raises(ValueError):
            StoreSessionSummaryInput(
                session_id=1,
                tenant_id=1,
                content="",
            )

    def test_get_historical_context_input(self):
        """Test GetHistoricalContextInput validation."""
        # Valid with defaults
        valid = GetHistoricalContextInput(
            tenant_id=1,
            query="test",
        )
        assert valid.limit == 5

        # Valid with custom limit
        valid2 = GetHistoricalContextInput(
            tenant_id=1,
            query="test",
            limit=10,
        )
        assert valid2.limit == 10

        # Invalid: limit too high
        with pytest.raises(ValueError):
            GetHistoricalContextInput(
                tenant_id=1,
                query="test",
                limit=51,
            )

    def test_get_historical_context_output(self):
        """Test GetHistoricalContextOutput validation."""
        output = GetHistoricalContextOutput(
            query="test",
            results_count=0,
            summaries=[],
        )
        assert output.query == "test"
        assert output.results_count == 0
        assert output.summaries == []


class TestMemoryToolHandlers:
    """Test tool handler functions."""

    @pytest.mark.asyncio
    async def test_get_working_memory_handler_success(self):
        """Test successful working memory retrieval."""
        # Mock executor and AgentMemoryService
        mock_executor = AsyncMock()
        mock_context = MagicMock()
        mock_context.get_executor = AsyncMock(return_value=mock_executor)
        mock_context.correlation_id = "corr-123"
        mock_context.audit_id = "audit-123"

        input_data = GetWorkingMemoryInput(session_id=1, tenant_id=1)

        with patch('app.services.agent_memory.AgentMemoryService') as mock_service:
            mock_service.get_working_memory.return_value = {"fact": "value"}

            result = await get_working_memory_handler(input_data, mock_context)

            assert isinstance(result, GetWorkingMemoryOutput)
            assert result.session_id == 1
            assert result.memory == {"fact": "value"}

    @pytest.mark.asyncio
    async def test_get_working_memory_handler_not_found(self):
        """Test working memory retrieval when session not found."""
        mock_executor = AsyncMock()
        mock_context = MagicMock()
        mock_context.get_executor = AsyncMock(return_value=mock_executor)
        mock_context.correlation_id = "corr-123"
        mock_context.audit_id = "audit-123"

        input_data = GetWorkingMemoryInput(session_id=999, tenant_id=1)

        with patch('app.services.agent_memory.AgentMemoryService') as mock_service:
            mock_service.get_working_memory.return_value = None

            with pytest.raises(Exception):  # ToolExecutionError
                await get_working_memory_handler(input_data, mock_context)

    @pytest.mark.asyncio
    async def test_update_working_memory_handler_success(self):
        """Test successful working memory update."""
        mock_executor = AsyncMock()
        mock_context = MagicMock()
        mock_context.get_executor = AsyncMock(return_value=mock_executor)
        mock_context.correlation_id = "corr-123"
        mock_context.audit_id = "audit-123"

        input_data = UpdateWorkingMemoryInput(
            session_id=1,
            tenant_id=1,
            updates={"new_fact": "new_value"},
        )

        with patch('app.services.agent_memory.AgentMemoryService') as mock_service:
            mock_service.update_working_memory.return_value = {
                "old_fact": "old_value",
                "new_fact": "new_value",
            }

            result = await update_working_memory_handler(input_data, mock_context)

            assert isinstance(result, UpdateWorkingMemoryOutput)
            assert result.session_id == 1
            assert result.keys_added == 1

    @pytest.mark.asyncio
    async def test_store_session_summary_handler_success(self):
        """Test successful session summary storage."""
        mock_executor = AsyncMock()
        mock_context = MagicMock()
        mock_context.get_executor = AsyncMock(return_value=mock_executor)
        mock_context.correlation_id = "corr-123"
        mock_context.audit_id = "audit-123"

        input_data = StoreSessionSummaryInput(
            session_id=1,
            tenant_id=1,
            content="Session summary content",
        )

        # Mock summary object
        mock_summary = MagicMock()
        mock_summary.id = 100
        mock_summary.created_at = datetime.now(timezone.utc)

        with patch('app.services.agent_memory.AgentMemoryService') as mock_service:
            mock_service.store_session_summary.return_value = mock_summary

            result = await store_session_summary_handler(input_data, mock_context)

            assert isinstance(result, StoreSessionSummaryOutput)
            assert result.summary_id == 100
            assert result.session_id == 1

    @pytest.mark.asyncio
    async def test_get_historical_context_handler_success(self):
        """Test successful historical context retrieval."""
        mock_executor = AsyncMock()
        mock_context = MagicMock()
        mock_context.get_executor = AsyncMock(return_value=mock_executor)
        mock_context.correlation_id = "corr-123"
        mock_context.audit_id = "audit-123"

        input_data = GetHistoricalContextInput(
            tenant_id=1,
            query="booking",
            limit=5,
        )

        # Mock results
        mock_result1 = MagicMock()
        mock_result1.id = 1
        mock_result1.session_id = 10
        mock_result1.content = "Previous booking session"
        mock_result1.created_at = datetime.now(timezone.utc)

        with patch('app.services.agent_memory.AgentMemoryService') as mock_service:
            mock_service.retrieve_historical_context.return_value = [mock_result1]

            result = await get_historical_context_handler(input_data, mock_context)

            assert isinstance(result, GetHistoricalContextOutput)
            assert result.query == "booking"
            assert result.results_count == 1
            assert len(result.summaries) == 1


class TestMemoryToolsIntegration:
    """Test memory tools in the registry."""

    def test_tools_in_registry(self):
        """Test that memory tools can be added to the registry."""
        from gateway_mcp.tools import ToolRegistry

        registry = ToolRegistry()
        registry.register_all(MEMORY_TOOLS)

        assert len(registry) == 4
        assert "get_working_memory" in registry
        assert "update_working_memory" in registry
        assert "store_session_summary" in registry
        assert "get_historical_context" in registry

    def test_full_registry_includes_memory_tools(self):
        """Test that full registry includes memory tools."""
        from gateway_mcp.tools import create_full_registry

        registry = create_full_registry()

        # Check memory tools are present
        assert registry.get("get_working_memory") is not None
        assert registry.get("update_working_memory") is not None
        assert registry.get("store_session_summary") is not None
        assert registry.get("get_historical_context") is not None

    def test_memory_tools_mcp_schema(self):
        """Test that memory tools can be converted to MCP schema."""
        from gateway_mcp.tools import create_full_registry

        registry = create_full_registry()
        schemas = registry.to_mcp_list()

        # Extract memory tool schemas
        memory_tool_names = {tool.name for tool in MEMORY_TOOLS}
        memory_schemas = [s for s in schemas if s['name'] in memory_tool_names]

        assert len(memory_schemas) == 4
        for schema in memory_schemas:
            assert 'name' in schema
            assert 'description' in schema
            assert 'inputSchema' in schema
