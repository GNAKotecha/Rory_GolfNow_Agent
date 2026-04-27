"""Tests for summarization service."""
import pytest
from unittest.mock import AsyncMock, patch

from app.services.summarization import (
    generate_summary,
    should_regenerate_summary,
)


# ==============================================================================
# Summary Generation Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_generate_summary_basic():
    """Test basic summary generation."""
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
        {"role": "user", "content": "How are you?"},
        {"role": "assistant", "content": "I'm good"},
    ]

    # Mock Ollama client
    with patch("app.services.summarization.OllamaClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.generate_chat_completion = AsyncMock(
            return_value="This is a summary of the conversation"
        )
        mock_client_class.return_value = mock_client

        summary = await generate_summary(messages)

        assert summary == "This is a summary of the conversation"
        mock_client.generate_chat_completion.assert_called_once()


@pytest.mark.asyncio
async def test_generate_summary_with_existing():
    """Test summary generation with existing summary."""
    messages = [
        {"role": "user", "content": "New message"},
        {"role": "assistant", "content": "New response"},
    ]

    existing_summary = "Previous conversation summary"

    with patch("app.services.summarization.OllamaClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.generate_chat_completion = AsyncMock(
            return_value="Updated summary"
        )
        mock_client_class.return_value = mock_client

        summary = await generate_summary(messages, existing_summary=existing_summary)

        assert summary == "Updated summary"

        # Check that existing summary was included in prompt
        call_args = mock_client.generate_chat_completion.call_args
        prompt = call_args[1]["messages"][0]["content"]
        assert existing_summary in prompt


@pytest.mark.asyncio
async def test_generate_summary_empty_messages():
    """Test summary generation with empty messages."""
    summary = await generate_summary([])
    assert summary == ""

    # With existing summary
    existing = "Existing summary"
    summary = await generate_summary([], existing_summary=existing)
    assert summary == existing


# ==============================================================================
# Summary Regeneration Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_should_regenerate_summary_below_threshold():
    """Test that regeneration is not triggered below threshold."""
    should_regen = await should_regenerate_summary(
        current_message_count=25,
        message_count_at_summary=20,
        threshold=20,
    )
    assert should_regen is False


@pytest.mark.asyncio
async def test_should_regenerate_summary_above_threshold():
    """Test that regeneration is triggered above threshold."""
    should_regen = await should_regenerate_summary(
        current_message_count=45,
        message_count_at_summary=20,
        threshold=20,
    )
    assert should_regen is True


@pytest.mark.asyncio
async def test_should_regenerate_summary_at_threshold():
    """Test that regeneration is triggered exactly at threshold."""
    should_regen = await should_regenerate_summary(
        current_message_count=40,
        message_count_at_summary=20,
        threshold=20,
    )
    assert should_regen is True
