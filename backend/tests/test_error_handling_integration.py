"""Integration tests for hardened error handling.

Tests for:
- MCP 401 returns immediate terminal/ASK_USER behavior
- Repeated tool failure does not loop indefinitely
- Combined retry budget is bounded
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.services.agentic_service import AgenticService, AgenticConfig, AgenticResult
from app.services.agent_state import AgentState, ActionOutcome
from app.services.mcp_client import MCPToolResult
from app.services.ollama import OllamaClient
from app.services.mcp_registry import MCPToolRegistry
from app.models.models import User, UserRole


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
    user = MagicMock(spec=User)
    user.id = 1
    user.role = UserRole.ADMIN
    return user


@pytest.fixture
def mock_ollama():
    """Create a mock Ollama client."""
    client = MagicMock(spec=OllamaClient)
    return client


@pytest.fixture
def mock_mcp_registry():
    """Create a mock MCP registry."""
    registry = MagicMock(spec=MCPToolRegistry)
    return registry


@pytest.fixture
def agentic_config():
    """Create agentic config for testing.
    
    Note: use_tool_catalog=False to test legacy execute_tool path.
    Catalog-specific tests are in test_tool_catalog.py.
    """
    return AgenticConfig(
        max_steps=10,
        timeout_seconds=60,
        enable_loop_detection=True,
        loop_window_size=3,
        use_tool_catalog=False,  # Use legacy path for these error handling tests
    )


class TestMCP401HandlingIntegration:
    """Integration tests for 401/403 error handling."""
    
    @pytest.mark.asyncio
    async def test_mcp_401_stops_immediately(self, mock_user, mock_ollama, mock_mcp_registry, agentic_config):
        """MCP returning 401 should stop execution immediately without exhausting retry budget."""
        # Setup mock to return tool call
        mock_ollama.generate_chat_completion_with_tools = AsyncMock(return_value={
            "type": "tool_calls",
            "tool_calls": [{
                "id": "call_1",
                "function": {
                    "name": "test_tool",
                    "arguments": {"param": "value"},
                },
            }],
        })
        
        # Setup MCP to return 401 error
        mock_mcp_registry.execute_tool = AsyncMock(return_value=MCPToolResult(
            success=False,
            error="401 Unauthorized: Invalid API key",
            result=None,
        ))
        
        # Setup tool definitions
        async def get_tools(user):
            return [{
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "Test tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }]
        
        service = AgenticService(
            ollama_client=mock_ollama,
            mcp_registry=mock_mcp_registry,
            config=agentic_config,
        )
        service._get_tool_definitions = get_tools
        
        # Create stream events collector
        events = []
        async def collect_events(event):
            events.append(event)
        agentic_config.stream_callback = collect_events
        
        # Execute
        result = await service.execute(
            messages=[{"role": "user", "content": "Call test_tool"}],
            user=mock_user,
            session_id=1,
        )
        
        # Verify: Should stop with ask_user (auth failures ask user)
        assert result.stopped_reason == "ask_user"
        assert "auth" in result.error.lower() or "unauthorized" in result.error.lower()
        
        # Should only have called the tool ONCE (no retries for auth errors)
        assert mock_mcp_registry.execute_tool.call_count == 1
        
        # Should have emitted an ask_user event
        ask_user_events = [e for e in events if e.get("type") == "ask_user"]
        assert len(ask_user_events) == 1
        assert ask_user_events[0].get("error_type") == "auth_failure"
    
    @pytest.mark.asyncio
    async def test_mcp_403_stops_immediately(self, mock_user, mock_ollama, mock_mcp_registry, agentic_config):
        """MCP returning 403 should stop execution immediately."""
        mock_ollama.generate_chat_completion_with_tools = AsyncMock(return_value={
            "type": "tool_calls",
            "tool_calls": [{
                "id": "call_1",
                "function": {
                    "name": "test_tool",
                    "arguments": {},
                },
            }],
        })
        
        mock_mcp_registry.execute_tool = AsyncMock(return_value=MCPToolResult(
            success=False,
            error="403 Forbidden: Insufficient permissions",
            result=None,
        ))
        
        async def get_tools(user):
            return [{
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "Test tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }]
        
        service = AgenticService(
            ollama_client=mock_ollama,
            mcp_registry=mock_mcp_registry,
            config=agentic_config,
        )
        service._get_tool_definitions = get_tools
        
        result = await service.execute(
            messages=[{"role": "user", "content": "Call test_tool"}],
            user=mock_user,
            session_id=1,
        )
        
        # Should stop immediately
        assert result.stopped_reason == "ask_user"
        assert mock_mcp_registry.execute_tool.call_count == 1


class TestRepeatedToolFailureIntegration:
    """Integration tests for repeated tool failure handling."""
    
    @pytest.mark.asyncio
    async def test_repeated_failure_does_not_loop_indefinitely(
        self, mock_user, mock_ollama, mock_mcp_registry, agentic_config
    ):
        """Repeated tool failure should not create an infinite loop."""
        call_count = 0
        
        # Mock Ollama to keep requesting the same tool
        async def mock_generate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return {
                "type": "tool_calls",
                "tool_calls": [{
                    "id": f"call_{call_count}",
                    "function": {
                        "name": "failing_tool",
                        "arguments": {"x": 1},
                    },
                }],
            }
        
        mock_ollama.generate_chat_completion_with_tools = AsyncMock(side_effect=mock_generate)
        
        # Mock MCP to always fail with transient error
        mock_mcp_registry.execute_tool = AsyncMock(return_value=MCPToolResult(
            success=False,
            error="500 Internal Server Error",
            result=None,
        ))
        
        async def get_tools(user):
            return [{
                "type": "function",
                "function": {
                    "name": "failing_tool",
                    "description": "A tool that always fails",
                    "parameters": {"type": "object", "properties": {}},
                },
            }]
        
        service = AgenticService(
            ollama_client=mock_ollama,
            mcp_registry=mock_mcp_registry,
            config=agentic_config,
        )
        service._get_tool_definitions = get_tools
        
        result = await service.execute(
            messages=[{"role": "user", "content": "Call failing_tool"}],
            user=mock_user,
            session_id=1,
        )
        
        # Should stop with error OR loop_detected (both are valid terminal states)
        assert result.stopped_reason in ("error", "loop_detected")
        
        # Should have bounded number of calls (retry budget)
        # With AGENT_RETRY_BUDGET=3 and max_retries=3, should be <= 4 calls per step
        # Given max_steps=10, absolute max would be 40, but error should stop earlier
        assert mock_mcp_registry.execute_tool.call_count <= 10
    
    @pytest.mark.asyncio
    async def test_validation_error_stops_without_retry(
        self, mock_user, mock_ollama, mock_mcp_registry, agentic_config
    ):
        """400 validation error should stop immediately without retry."""
        mock_ollama.generate_chat_completion_with_tools = AsyncMock(return_value={
            "type": "tool_calls",
            "tool_calls": [{
                "id": "call_1",
                "function": {
                    "name": "test_tool",
                    "arguments": {"invalid_param": "value"},
                },
            }],
        })
        
        mock_mcp_registry.execute_tool = AsyncMock(return_value=MCPToolResult(
            success=False,
            error="400 Bad Request: Validation error - 'invalid_param' is not a valid parameter",
            result=None,
        ))
        
        async def get_tools(user):
            return [{
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "Test tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }]
        
        service = AgenticService(
            ollama_client=mock_ollama,
            mcp_registry=mock_mcp_registry,
            config=agentic_config,
        )
        service._get_tool_definitions = get_tools
        
        result = await service.execute(
            messages=[{"role": "user", "content": "Call test_tool"}],
            user=mock_user,
            session_id=1,
        )
        
        # Should ask user after reflection turn fails
        assert result.stopped_reason == "ask_user"
        assert result.final_response
        assert "validation" in result.final_response.lower()
        # Task A3: Validation errors now get one reflection turn before escalating
        # With same fingerprint, we get: 1 initial + 1 reflection = 2 calls max
        assert mock_mcp_registry.execute_tool.call_count == 2


class TestRetryBudgetIntegration:
    """Integration tests for retry budget enforcement."""
    
    @pytest.mark.asyncio
    async def test_retry_budget_is_bounded(
        self, mock_user, mock_ollama, mock_mcp_registry, agentic_config
    ):
        """Combined retry attempts should be bounded by budget."""
        attempt_count = 0
        
        async def count_attempts(*args, **kwargs):
            nonlocal attempt_count
            attempt_count += 1
            return MCPToolResult(
                success=False,
                error="Connection timeout",
                result=None,
            )
        
        mock_ollama.generate_chat_completion_with_tools = AsyncMock(return_value={
            "type": "tool_calls",
            "tool_calls": [{
                "id": "call_1",
                "function": {
                    "name": "timeout_tool",
                    "arguments": {},
                },
            }],
        })
        
        mock_mcp_registry.execute_tool = AsyncMock(side_effect=count_attempts)
        
        async def get_tools(user):
            return [{
                "type": "function",
                "function": {
                    "name": "timeout_tool",
                    "description": "A tool that times out",
                    "parameters": {"type": "object", "properties": {}},
                },
            }]
        
        service = AgenticService(
            ollama_client=mock_ollama,
            mcp_registry=mock_mcp_registry,
            config=agentic_config,
        )
        service._get_tool_definitions = get_tools
        
        result = await service.execute(
            messages=[{"role": "user", "content": "Call timeout_tool"}],
            user=mock_user,
            session_id=1,
        )
        
        # Should have stopped
        assert result.stopped_reason == "error"
        
        # Attempts should be bounded (AGENT_RETRY_BUDGET + 1 initial)
        # Default budget is 3, so max 4 attempts before abort
        assert attempt_count <= 4


class TestTelemetryIntegration:
    """Integration tests for telemetry emission."""
    
    @pytest.mark.asyncio
    async def test_tool_error_event_has_required_fields(
        self, mock_user, mock_ollama, mock_mcp_registry, agentic_config
    ):
        """Tool error events should have all required telemetry fields."""
        events = []
        
        async def collect_events(event):
            events.append(event)
        
        agentic_config.stream_callback = collect_events
        
        mock_ollama.generate_chat_completion_with_tools = AsyncMock(return_value={
            "type": "tool_calls",
            "tool_calls": [{
                "id": "call_1",
                "function": {
                    "name": "test_tool",
                    "arguments": {},
                },
            }],
        })
        
        mock_mcp_registry.execute_tool = AsyncMock(return_value=MCPToolResult(
            success=False,
            error="500 Internal Server Error",
            result=None,
        ))
        
        async def get_tools(user):
            return [{
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "Test tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }]
        
        service = AgenticService(
            ollama_client=mock_ollama,
            mcp_registry=mock_mcp_registry,
            config=agentic_config,
        )
        service._get_tool_definitions = get_tools
        
        await service.execute(
            messages=[{"role": "user", "content": "Call test_tool"}],
            user=mock_user,
            session_id=1,
        )
        
        # Find tool_error events
        error_events = [e for e in events if e.get("type") == "tool_error"]
        assert len(error_events) > 0
        
        # Check required fields
        error_event = error_events[0]
        assert "tool_name" in error_event
        assert "error" in error_event
        assert "error_type" in error_event
        assert "retryable" in error_event
        assert "attempt_index" in error_event
        assert "attempt_budget" in error_event
        assert "recovery_strategy" in error_event
        assert "terminal" in error_event
        assert "duration_ms" in error_event


class TestRetryOwnershipIntegration:
    """Task A2: Integration tests for retry ownership policy."""
    
    @pytest.mark.asyncio
    async def test_transport_retries_exhausted_stops_agent_retry(
        self, mock_user, mock_ollama, mock_mcp_registry, agentic_config
    ):
        """When MCP client exhausts transport retries, agent should NOT retry."""
        agent_retry_attempts = 0
        
        async def track_attempts(*args, **kwargs):
            nonlocal agent_retry_attempts
            agent_retry_attempts += 1
            # Return with transport_retries_exhausted=True
            return MCPToolResult(
                success=False,
                error="Server error: HTTP 500",
                http_status=500,
                retry_count=3,  # MCP client already retried 3 times
                transport_retries_exhausted=True,  # A2: Signal to agent
            )
        
        mock_ollama.generate_chat_completion_with_tools = AsyncMock(return_value={
            "type": "tool_calls",
            "tool_calls": [{
                "id": "call_1",
                "function": {
                    "name": "test_tool",
                    "arguments": {},
                },
            }],
        })
        
        mock_mcp_registry.execute_tool = AsyncMock(side_effect=track_attempts)
        
        async def get_tools(user):
            return [{
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "Test tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }]
        
        service = AgenticService(
            ollama_client=mock_ollama,
            mcp_registry=mock_mcp_registry,
            config=agentic_config,
        )
        service._get_tool_definitions = get_tools
        
        result = await service.execute(
            messages=[{"role": "user", "content": "Call test_tool"}],
            user=mock_user,
            session_id=1,
        )
        
        # Should stop without agent-level retry
        assert agent_retry_attempts == 1, "Agent should NOT retry when transport retries exhausted"
        assert result.stopped_reason == "ask_user"
        assert "exhausted" in result.error.lower() or "transport" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_semantic_error_handled_by_agent_no_transport_retry(
        self, mock_user, mock_ollama, mock_mcp_registry, agentic_config
    ):
        """Semantic errors (isError) should be handled by agent, not transport-retried."""
        mock_ollama.generate_chat_completion_with_tools = AsyncMock(return_value={
            "type": "tool_calls",
            "tool_calls": [{
                "id": "call_1",
                "function": {
                    "name": "test_tool",
                    "arguments": {"param": "bad_value"},
                },
            }],
        })
        
        # Return semantic error with is_semantic_error=True
        mock_mcp_registry.execute_tool = AsyncMock(return_value=MCPToolResult(
            success=False,
            error="Validation error: 'bad_value' is not valid",
            retry_count=0,  # MCP client did NOT retry (semantic error)
            is_semantic_error=True,  # A2: Agent handles recovery
        ))
        
        async def get_tools(user):
            return [{
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "Test tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }]
        
        service = AgenticService(
            ollama_client=mock_ollama,
            mcp_registry=mock_mcp_registry,
            config=agentic_config,
        )
        service._get_tool_definitions = get_tools
        
        result = await service.execute(
            messages=[{"role": "user", "content": "Call test_tool"}],
            user=mock_user,
            session_id=1,
        )
        
        # Should ask user (agent handles semantic errors)
        assert result.stopped_reason == "ask_user"
        # Task A3: Validation errors get one reflection turn before escalating
        # With same fingerprint: 1 initial + 1 reflection = 2 calls max
        assert mock_mcp_registry.execute_tool.call_count == 2

    @pytest.mark.asyncio
    async def test_semantic_tool_failure_not_retried_as_transient(
        self, mock_user, mock_ollama, mock_mcp_registry, agentic_config
    ):
        """Generic semantic errors should escalate, not enter transient RETRY loops."""
        mock_ollama.generate_chat_completion_with_tools = AsyncMock(return_value={
            "type": "tool_calls",
            "tool_calls": [{
                "id": "call_1",
                "function": {
                    "name": "test_tool",
                    "arguments": {"param": "value"},
                },
            }],
        })

        # Semantic error text that does not match validation/auth regexes.
        # Without semantic ownership guard this would fall into TOOL_FAILURE -> RETRY.
        mock_mcp_registry.execute_tool = AsyncMock(return_value=MCPToolResult(
            success=False,
            error="Business rule violation: operation cannot be completed in current state",
            retry_count=0,
            is_semantic_error=True,
        ))

        async def get_tools(user):
            return [{
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "Test tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }]

        service = AgenticService(
            ollama_client=mock_ollama,
            mcp_registry=mock_mcp_registry,
            config=agentic_config,
        )
        service._get_tool_definitions = get_tools

        result = await service.execute(
            messages=[{"role": "user", "content": "Call test_tool"}],
            user=mock_user,
            session_id=1,
        )

        assert result.stopped_reason == "ask_user"
        assert mock_mcp_registry.execute_tool.call_count == 1
        assert result.error
        assert "semantic error" in result.error.lower()


class TestReflectionTurnIntegration:
    """Task A3: Integration tests for error reflection turn behavior."""
    
    @pytest.mark.asyncio
    async def test_validation_error_allows_one_reflection_turn(
        self, mock_user, mock_ollama, mock_mcp_registry, agentic_config
    ):
        """Validation errors should allow model one reflection turn before escalating."""
        call_count = 0
        reflection_message_validated = False
        
        async def model_response(*args, **kwargs):
            nonlocal call_count, reflection_message_validated
            call_count += 1
            if call_count == 2:
                messages = kwargs.get("messages", [])
                # Ensure reflection injection uses Ollama-compatible message shape
                last_assistant = next(
                    (m for m in reversed(messages) if m.get("role") == "assistant" and m.get("tool_calls")),
                    None,
                )
                last_tool = next(
                    (m for m in reversed(messages) if m.get("role") == "tool"),
                    None,
                )
                if last_assistant and last_tool:
                    reflection_message_validated = (
                        last_assistant.get("content") == ""
                        and "tool_name" in last_tool
                        and "name" not in last_tool
                    )
            if call_count <= 2:
                # Model keeps trying same bad params (same fingerprint)
                return {
                    "type": "tool_calls",
                    "tool_calls": [{
                        "id": f"call_{call_count}",
                        "function": {
                            "name": "test_tool",
                            "arguments": {"param": "bad_value"},  # Same args = same fingerprint
                        },
                    }],
                }
            else:
                # Should not reach here
                return {"type": "text", "content": "Done"}
        
        mock_ollama.generate_chat_completion_with_tools = AsyncMock(side_effect=model_response)
        
        # Tool always returns validation error
        mock_mcp_registry.execute_tool = AsyncMock(return_value=MCPToolResult(
            success=False,
            error="Validation error: invalid parameter value",
            is_semantic_error=True,
        ))
        
        async def get_tools(user):
            return [{
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "Test tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }]
        
        events = []
        async def collect_events(event):
            events.append(event)
        agentic_config.stream_callback = collect_events
        
        service = AgenticService(
            ollama_client=mock_ollama,
            mcp_registry=mock_mcp_registry,
            config=agentic_config,
        )
        service._get_tool_definitions = get_tools
        
        result = await service.execute(
            messages=[{"role": "user", "content": "Call test_tool"}],
            user=mock_user,
            session_id=1,
        )
        
        # Should have called model twice (initial + reflection)
        # Note: same fingerprint gets one reflection, then escalates
        assert call_count == 2, f"Expected 2 model calls, got {call_count}"
        
        # Should emit reflection_turn event
        reflection_events = [e for e in events if e.get("type") == "reflection_turn"]
        assert len(reflection_events) == 1, "Should emit one reflection_turn event"
        assert reflection_message_validated, "Reflection tool-result message shape should be Ollama-compatible"
        
        # After reflection fails (same fingerprint), should escalate to ask_user
        assert result.stopped_reason == "ask_user"
    
    @pytest.mark.asyncio
    async def test_reflection_turn_success_after_correction(
        self, mock_user, mock_ollama, mock_mcp_registry, agentic_config
    ):
        """Model should be able to succeed after correcting in reflection turn."""
        call_count = 0
        tool_call_count = 0
        
        async def model_response(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: model calls tool with bad params
                return {
                    "type": "tool_calls",
                    "tool_calls": [{
                        "id": f"call_{call_count}",
                        "function": {
                            "name": "test_tool",
                            "arguments": {"param": "bad_value"},
                        },
                    }],
                }
            elif call_count == 2:
                # Second call (reflection): model corrects params
                return {
                    "type": "tool_calls",
                    "tool_calls": [{
                        "id": f"call_{call_count}",
                        "function": {
                            "name": "test_tool",
                            "arguments": {"param": "good_value"},  # Correct value
                        },
                    }],
                }
            else:
                return {"type": "text", "content": "Success!"}
        
        async def tool_response(*args, **kwargs):
            nonlocal tool_call_count
            tool_call_count += 1
            arguments = kwargs.get("arguments", {})
            if arguments.get("param") == "good_value":
                return MCPToolResult(success=True, result="Tool succeeded")
            return MCPToolResult(
                success=False,
                error="Validation error: invalid parameter value",
                is_semantic_error=True,
            )
        
        mock_ollama.generate_chat_completion_with_tools = AsyncMock(side_effect=model_response)
        mock_mcp_registry.execute_tool = AsyncMock(side_effect=tool_response)
        
        async def get_tools(user):
            return [{
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "Test tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }]
        
        service = AgenticService(
            ollama_client=mock_ollama,
            mcp_registry=mock_mcp_registry,
            config=agentic_config,
        )
        service._get_tool_definitions = get_tools
        
        result = await service.execute(
            messages=[{"role": "user", "content": "Call test_tool"}],
            user=mock_user,
            session_id=1,
        )
        
        # Model should have been called 3 times (initial, reflection, final)
        assert call_count == 3, f"Expected 3 model calls, got {call_count}"
        
        # Tool should have been called twice (bad, then good)
        assert tool_call_count == 2, f"Expected 2 tool calls, got {tool_call_count}"
        
        # Should complete successfully
        assert result.stopped_reason == "completed"
        assert "Success" in result.final_response
