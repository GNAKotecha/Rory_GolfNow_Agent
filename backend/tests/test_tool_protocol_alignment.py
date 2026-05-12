"""Protocol-alignment tests for tool calling with Ollama/Qwen models."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from unittest.mock import patch

from app.models.models import User, UserRole
from app.services.agentic_service import AgenticConfig, AgenticService
from app.services.mcp_client import MCPToolResult
from app.services.mcp_registry import MCPToolRegistry
from app.services.ollama import OllamaClient


@pytest.fixture
def mock_user():
    user = MagicMock(spec=User)
    user.id = 1
    user.role = UserRole.ADMIN
    return user


@pytest.fixture
def mock_ollama():
    return MagicMock(spec=OllamaClient)


@pytest.fixture
def mock_mcp_registry():
    return MagicMock(spec=MCPToolRegistry)


@pytest.mark.asyncio
async def test_agentic_service_sends_tool_name_on_tool_result_messages(
    mock_user, mock_ollama, mock_mcp_registry
):
    """Tool-result messages should include tool_name for Ollama compatibility."""
    seen_messages = []

    async def mock_generate(messages, tools=None, model=None, keep_alive="5m"):
        seen_messages.append(messages)
        if len(seen_messages) == 1:
            return {
                "type": "tool_calls",
                "tool_calls": [{
                    "id": "call_1",
                    "function": {
                        "name": "create_club",
                        "arguments": '{"name":"Pebble Beach"}',
                    },
                }],
            }
        return {
            "type": "text",
            "content": "Club created successfully.",
        }

    mock_ollama.generate_chat_completion_with_tools = AsyncMock(side_effect=mock_generate)
    mock_mcp_registry.execute_tool = AsyncMock(return_value=MCPToolResult(
        success=True,
        result={"club_id": "club-123", "name": "Pebble Beach"},
    ))

    async def get_tools(user):
        return [{
            "type": "function",
            "function": {
                "name": "create_club",
                "description": "Create a club",
                "parameters": {"type": "object", "properties": {}},
            },
        }]

    service = AgenticService(
        ollama_client=mock_ollama,
        mcp_registry=mock_mcp_registry,
        config=AgenticConfig(max_steps=5),
    )
    service._get_tool_definitions = get_tools

    result = await service.execute(
        messages=[{"role": "user", "content": "Create Pebble Beach club"}],
        user=mock_user,
        session_id=1,
    )

    assert result.stopped_reason == "completed"
    assert len(seen_messages) >= 2

    follow_up_messages = seen_messages[1]
    tool_messages = [m for m in follow_up_messages if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0].get("tool_name") == "create_club"
    assert tool_messages[0].get("tool_call_id") == "call_1"


@pytest.mark.asyncio
async def test_ollama_parses_prefixed_tool_call_text_shape():
    """Qwen-style 'tool_name {json}' text should be converted into tool_calls."""
    ollama = OllamaClient()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock(return_value=None)
    mock_response.json.return_value = {
        "message": {
            "content": (
                'create_club {"name":"Cranevalley27","country":"GB",'
                '"timezone":"Europe/London","currency":"GBP"}'
            )
        }
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("app.services.ollama.httpx.AsyncClient") as mock_async_client_cls:
        mock_async_client_cls.return_value.__aenter__.return_value = mock_client

        result = await ollama.generate_chat_completion_with_tools(
            messages=[{"role": "user", "content": "Create the club"}],
            tools=[{
                "type": "function",
                "function": {
                    "name": "create_club",
                    "description": "Create a club",
                    "parameters": {"type": "object", "properties": {}},
                },
            }],
        )

    assert result["type"] == "tool_calls"
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["function"]["name"] == "create_club"
    assert result["tool_calls"][0]["function"]["arguments"]["country"] == "GB"
