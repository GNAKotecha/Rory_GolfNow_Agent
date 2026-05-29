"""Tests for USE_API_KEY-based LLM backend switching."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.ollama import OllamaClient
from app.services import ollama as ollama_module


@pytest.fixture
def api_mode(monkeypatch):
    """Force OllamaClient into API-key backend mode."""
    monkeypatch.setattr(ollama_module.settings, "use_api_key", True, raising=False)
    monkeypatch.setattr(
        ollama_module.settings,
        "anthropic_base_url",
        "https://golfnow-keystone.vdpv.ai",
        raising=False,
    )
    monkeypatch.setattr(
        ollama_module.settings,
        "anthropic_auth_token",
        "test-token",
        raising=False,
    )


@pytest.mark.asyncio
async def test_api_key_mode_check_connection_uses_models_endpoint(api_mode):
    """check_connection should probe /v1/models when USE_API_KEY=true."""
    mock_http_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_http_client.get = AsyncMock(return_value=mock_response)

    client = OllamaClient(http_client=mock_http_client)
    ok = await client.check_connection()

    assert ok is True
    mock_http_client.get.assert_awaited_once()
    called_url = mock_http_client.get.call_args.args[0]
    assert called_url.endswith("/v1/models")

    headers = mock_http_client.get.call_args.kwargs.get("headers", {})
    assert headers.get("Authorization") == "Bearer test-token"


@pytest.mark.asyncio
async def test_api_key_mode_generate_chat_completion_text(api_mode):
    """Text response should be parsed from OpenAI-compatible choices/message."""
    mock_http_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Created club successfully",
                }
            }
        ]
    }
    mock_http_client.post = AsyncMock(return_value=mock_response)

    client = OllamaClient(http_client=mock_http_client)
    result = await client.generate_chat_completion(
        messages=[{"role": "user", "content": "Create club"}],
        model="claude-sonnet-4-20250514",
    )

    assert result == "Created club successfully"
    called_url = mock_http_client.post.call_args.args[0]
    assert called_url.endswith("/v1/chat/completions")


@pytest.mark.asyncio
async def test_api_key_mode_generate_chat_completion_with_tools(api_mode):
    """Tool calls should be passed through from OpenAI-compatible response shape."""
    mock_http_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "create_club",
                                "arguments": {"name": "Crane Valley"},
                            },
                        }
                    ]
                }
            }
        ]
    }
    mock_http_client.post = AsyncMock(return_value=mock_response)

    client = OllamaClient(http_client=mock_http_client)
    result = await client.generate_chat_completion_with_tools(
        messages=[{"role": "user", "content": "Create club"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "create_club",
                    "description": "Create a club",
                    "parameters": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                        "required": ["name"],
                    },
                },
            }
        ],
        model="claude-sonnet-4-20250514",
    )

    assert result["type"] == "tool_calls"
    assert result["tool_calls"][0]["function"]["name"] == "create_club"
