"""Tests for tool-call protocol normalizer hardening (Task C3)."""

import pytest
from unittest.mock import AsyncMock, MagicMock
import httpx

from app.services.ollama import (
    OllamaClient,
    ToolCallParserMetrics,
    get_parser_metrics,
    reset_parser_metrics,
)


@pytest.fixture(autouse=True)
def reset_metrics():
    """Reset parser metrics before each test."""
    reset_parser_metrics()
    yield
    reset_parser_metrics()


class TestToolCallParserMetrics:
    """Tests for ToolCallParserMetrics telemetry."""

    def test_default_metrics_are_zero(self):
        """All metrics should start at zero."""
        metrics = ToolCallParserMetrics()
        d = metrics.to_dict()
        
        assert d["native_tool_calls"] == 0
        assert d["tagged_xml_parsed"] == 0
        assert d["prefixed_json_parsed"] == 0
        assert d["raw_json_object_parsed"] == 0
        assert d["text_responses"] == 0

    def test_to_dict_includes_all_fields(self):
        """to_dict should include all counter fields."""
        metrics = ToolCallParserMetrics()
        metrics.native_tool_calls = 5
        metrics.prefixed_json_parsed = 2
        metrics.schema_validation_rejected = 1
        
        d = metrics.to_dict()
        
        assert d["native_tool_calls"] == 5
        assert d["prefixed_json_parsed"] == 2
        assert d["schema_validation_rejected"] == 1

    def test_get_parser_metrics_returns_singleton(self):
        """get_parser_metrics should return the global instance."""
        metrics1 = get_parser_metrics()
        metrics2 = get_parser_metrics()
        
        assert metrics1 is metrics2

    def test_reset_parser_metrics(self):
        """reset_parser_metrics should create fresh metrics."""
        metrics1 = get_parser_metrics()
        metrics1.native_tool_calls = 10
        
        reset_parser_metrics()
        metrics2 = get_parser_metrics()
        
        assert metrics2.native_tool_calls == 0


class TestNativeToolCallsPriority:
    """Tests for native tool_calls field priority."""

    @pytest.mark.asyncio
    async def test_native_tool_calls_increments_counter(self):
        """Native tool_calls should increment the native counter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "message": {
                "tool_calls": [{
                    "id": "call_1",
                    "function": {"name": "create_club", "arguments": "{}"},
                }]
            }
        }

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.is_closed = False

        client = OllamaClient(http_client=mock_http_client)
        result = await client.generate_chat_completion_with_tools(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"type": "function", "function": {"name": "create_club", "parameters": {}}}],
        )

        assert result["type"] == "tool_calls"
        metrics = get_parser_metrics()
        assert metrics.native_tool_calls == 1
        assert metrics.prefixed_json_parsed == 0

    @pytest.mark.asyncio
    async def test_native_tool_calls_rejected_for_unknown_tool(self):
        """Native tool_calls with unknown tool name should be rejected (P2 fix)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "message": {
                "content": "I will create the club for you.",
                "tool_calls": [{
                    "id": "call_1",
                    "function": {"name": "hallucinated_tool", "arguments": "{}"},
                }]
            }
        }

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.is_closed = False

        client = OllamaClient(http_client=mock_http_client)
        result = await client.generate_chat_completion_with_tools(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"type": "function", "function": {"name": "create_club", "parameters": {}}}],
        )

        # Unknown tool_call should be rejected, falling through to text response
        assert result["type"] == "text"
        metrics = get_parser_metrics()
        assert metrics.schema_validation_rejected == 1
        # native_tool_calls NOT incremented because validation failed
        assert metrics.native_tool_calls == 0

    @pytest.mark.asyncio
    async def test_native_tool_calls_partial_validation(self):
        """Native tool_calls with mixed valid/invalid tools should keep only valid ones."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "message": {
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "create_club", "arguments": "{}"}},
                    {"id": "call_2", "function": {"name": "unknown_tool", "arguments": "{}"}},
                ]
            }
        }

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.is_closed = False

        client = OllamaClient(http_client=mock_http_client)
        result = await client.generate_chat_completion_with_tools(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"type": "function", "function": {"name": "create_club", "parameters": {}}}],
        )

        # Should return only the valid tool call
        assert result["type"] == "tool_calls"
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["function"]["name"] == "create_club"
        metrics = get_parser_metrics()
        assert metrics.schema_validation_rejected == 1  # unknown_tool rejected
        assert metrics.native_tool_calls == 1  # Still counted as native path

    @pytest.mark.asyncio
    async def test_native_tool_calls_malformed_entries_skipped(self):
        """Native tool_calls with non-dict entries (string/null) should be skipped gracefully."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "message": {
                "content": "Fallback text",
                "tool_calls": [
                    "malformed_string_entry",  # String instead of dict
                    None,  # Null entry
                    {"function": {"name": "create_club", "arguments": "{}"}},  # Valid entry
                ]
            }
        }

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.is_closed = False

        client = OllamaClient(http_client=mock_http_client)
        result = await client.generate_chat_completion_with_tools(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"type": "function", "function": {"name": "create_club", "parameters": {}}}],
        )

        # Should return only the valid tool call, skipping malformed entries
        assert result["type"] == "tool_calls"
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["function"]["name"] == "create_club"
        metrics = get_parser_metrics()
        assert metrics.native_tool_calls == 1

    @pytest.mark.asyncio
    async def test_native_tool_calls_malformed_function_field_skipped(self):
        """Native tool_calls where function is not a dict should be skipped."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "message": {
                "content": "Fallback text",
                "tool_calls": [
                    {"function": "not_a_dict"},  # function is string instead of dict
                    {"function": {"name": "create_club", "arguments": "{}"}},  # Valid entry
                ]
            }
        }

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.is_closed = False

        client = OllamaClient(http_client=mock_http_client)
        result = await client.generate_chat_completion_with_tools(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"type": "function", "function": {"name": "create_club", "parameters": {}}}],
        )

        # Should return only the valid tool call
        assert result["type"] == "tool_calls"
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["function"]["name"] == "create_club"


class TestPrefixedJsonParsing:
    """Tests for prefixed JSON parsing (tool_name {...})."""

    @pytest.mark.asyncio
    async def test_prefixed_json_increments_counter(self):
        """Prefixed JSON should increment the prefixed counter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "message": {
                "content": 'create_club {"name":"TestClub","country":"GB"}'
            }
        }

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.is_closed = False

        client = OllamaClient(http_client=mock_http_client)
        result = await client.generate_chat_completion_with_tools(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"type": "function", "function": {"name": "create_club", "parameters": {}}}],
        )

        assert result["type"] == "tool_calls"
        assert result["tool_calls"][0]["function"]["name"] == "create_club"
        
        metrics = get_parser_metrics()
        assert metrics.prefixed_json_parsed == 1
        assert metrics.native_tool_calls == 0


class TestSchemaValidation:
    """Tests for strict schema validation (Task C3)."""

    @pytest.mark.asyncio
    async def test_unknown_tool_name_rejected(self):
        """Tool name not in provided tools should be rejected."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "message": {
                "content": 'unknown_tool {"arg":"value"}'
            }
        }

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.is_closed = False

        client = OllamaClient(http_client=mock_http_client)
        result = await client.generate_chat_completion_with_tools(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"type": "function", "function": {"name": "create_club", "parameters": {}}}],
        )

        # Should fall through to text response since tool name doesn't match
        assert result["type"] == "text"
        
        metrics = get_parser_metrics()
        assert metrics.schema_validation_rejected >= 1

    @pytest.mark.asyncio
    async def test_valid_tool_name_accepted(self):
        """Tool name in provided tools should be accepted."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "message": {
                "content": '{"name":"create_club","arguments":{"name":"Test"}}'
            }
        }

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.is_closed = False

        client = OllamaClient(http_client=mock_http_client)
        result = await client.generate_chat_completion_with_tools(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"type": "function", "function": {"name": "create_club", "parameters": {}}}],
        )

        assert result["type"] == "tool_calls"
        assert result["tool_calls"][0]["function"]["name"] == "create_club"


class TestTextResponseTracking:
    """Tests for text response telemetry."""

    @pytest.mark.asyncio
    async def test_text_response_increments_counter(self):
        """Text response (no tool call) should increment text counter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "message": {
                "content": "This is just a text response without any tool calls."
            }
        }

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.is_closed = False

        client = OllamaClient(http_client=mock_http_client)
        result = await client.generate_chat_completion_with_tools(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"type": "function", "function": {"name": "create_club", "parameters": {}}}],
        )

        assert result["type"] == "text"
        
        metrics = get_parser_metrics()
        assert metrics.text_responses == 1


class TestTaggedXmlParsing:
    """Tests for tagged XML tool call parsing."""

    @pytest.mark.asyncio
    async def test_tagged_xml_increments_counter(self):
        """Tagged XML tool calls should increment the tagged counter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "message": {
                "content": '<tool_call>{"name":"create_club","arguments":{"name":"Test"}}</tool_call>'
            }
        }

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.is_closed = False

        client = OllamaClient(http_client=mock_http_client)
        result = await client.generate_chat_completion_with_tools(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"type": "function", "function": {"name": "create_club", "parameters": {}}}],
        )

        assert result["type"] == "tool_calls"
        
        metrics = get_parser_metrics()
        assert metrics.tagged_xml_parsed == 1


class TestRawJsonParsing:
    """Tests for raw JSON tool call parsing."""

    @pytest.mark.asyncio
    async def test_raw_json_object_increments_counter(self):
        """Raw JSON object should increment the raw_json_object counter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "message": {
                "content": '{"name":"create_club","arguments":{"name":"Test"}}'
            }
        }

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.is_closed = False

        client = OllamaClient(http_client=mock_http_client)
        result = await client.generate_chat_completion_with_tools(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"type": "function", "function": {"name": "create_club", "parameters": {}}}],
        )

        assert result["type"] == "tool_calls"
        
        metrics = get_parser_metrics()
        assert metrics.raw_json_object_parsed == 1

    @pytest.mark.asyncio
    async def test_raw_json_tool_calls_array_increments_counter(self):
        """Raw JSON tool_calls array should increment the array counter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "message": {
                "content": '{"tool_calls":[{"name":"create_club","arguments":{"name":"Test"}}]}'
            }
        }

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.is_closed = False

        client = OllamaClient(http_client=mock_http_client)
        result = await client.generate_chat_completion_with_tools(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"type": "function", "function": {"name": "create_club", "parameters": {}}}],
        )

        assert result["type"] == "tool_calls"
        
        metrics = get_parser_metrics()
        assert metrics.raw_json_tool_calls_array == 1
