"""Tests for conversation history compaction."""
import pytest

from app.services.history import (
    should_compact_history,
    estimate_token_count,
    compact_history,
    extract_recent_messages,
    prepare_messages_for_api,
    filter_system_messages,
    normalize_message_roles,
)


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def sample_messages():
    """Create sample message history."""
    return [
        {"role": "user", "content": f"User message {i}"}
        for i in range(30)
    ]


# ==============================================================================
# Compaction Threshold Tests
# ==============================================================================

def test_should_compact_history_below_threshold():
    """Test compaction not triggered below threshold."""
    assert should_compact_history(10) is False
    assert should_compact_history(20) is False


def test_should_compact_history_above_threshold():
    """Test compaction triggered above threshold."""
    assert should_compact_history(21) is True
    assert should_compact_history(50) is True


# ==============================================================================
# Token Estimation Tests
# ==============================================================================

def test_estimate_token_count():
    """Test token count estimation."""
    messages = [
        {"role": "user", "content": "a" * 100},
        {"role": "assistant", "content": "b" * 200},
    ]

    # Rough estimate: ~75 tokens (300 chars / 4)
    token_count = estimate_token_count(messages)
    assert token_count > 0
    assert token_count == 75


def test_estimate_token_count_empty():
    """Test token estimation for empty messages."""
    assert estimate_token_count([]) == 0


# ==============================================================================
# Compaction Tests
# ==============================================================================

def test_compact_history_basic(sample_messages):
    """Test basic history compaction."""
    compacted, stats = compact_history(sample_messages, keep_recent=10)

    # Should have summary + 10 recent messages
    assert len(compacted) == 11
    assert stats["compacted"] is True
    assert stats["messages_kept"] == 10
    assert stats["messages_summarized"] == 20

    # First message should be summary
    assert compacted[0]["role"] == "system"
    assert "summary" in compacted[0]["content"].lower()


def test_compact_history_with_summary(sample_messages):
    """Test compaction with existing summary."""
    summary_text = "Existing conversation summary"

    compacted, stats = compact_history(
        sample_messages,
        keep_recent=10,
        summary_text=summary_text,
    )

    # Summary should be included
    assert len(compacted) == 11
    assert summary_text in compacted[0]["content"]


def test_compact_history_no_compaction_needed():
    """Test compaction when not enough messages."""
    short_messages = [
        {"role": "user", "content": f"Message {i}"}
        for i in range(5)
    ]

    compacted, stats = compact_history(short_messages, keep_recent=10)

    # No compaction needed
    assert len(compacted) == len(short_messages)
    assert stats["compacted"] is False


def test_extract_recent_messages(sample_messages):
    """Test extracting recent messages."""
    recent = extract_recent_messages(sample_messages, count=10)

    assert len(recent) == 10
    # Should be the last 10 messages
    assert recent[0]["content"] == "User message 20"
    assert recent[-1]["content"] == "User message 29"


def test_extract_recent_messages_short_history():
    """Test extracting from short history."""
    short_messages = [{"role": "user", "content": f"Message {i}"} for i in range(5)]

    recent = extract_recent_messages(short_messages, count=10)

    # Should return all messages if count > length
    assert len(recent) == 5


# ==============================================================================
# Message Preparation Tests
# ==============================================================================

def test_prepare_messages_for_api_no_compaction():
    """Test preparing messages without compaction."""
    messages = [
        {"role": "user", "content": f"Message {i}"}
        for i in range(10)
    ]

    prepared, metadata = prepare_messages_for_api(
        messages,
        use_compaction=True,
    )

    # Below threshold - no compaction
    assert metadata["compacted"] is False
    assert metadata["reason"] == "below_threshold"
    assert len(prepared) == len(messages)


def test_prepare_messages_for_api_with_compaction():
    """Test preparing messages with compaction."""
    messages = [
        {"role": "user", "content": f"Message {i}"}
        for i in range(30)
    ]

    prepared, metadata = prepare_messages_for_api(
        messages,
        use_compaction=True,
    )

    # Above threshold - compaction applied
    assert metadata["compacted"] is True
    assert len(prepared) < len(messages)


def test_prepare_messages_for_api_compaction_disabled():
    """Test preparing messages with compaction disabled."""
    messages = [
        {"role": "user", "content": f"Message {i}"}
        for i in range(30)
    ]

    prepared, metadata = prepare_messages_for_api(
        messages,
        use_compaction=False,
    )

    # Compaction disabled - all messages returned
    assert metadata["compacted"] is False
    assert len(prepared) == len(messages)


# ==============================================================================
# Message Filtering Tests
# ==============================================================================

def test_filter_system_messages():
    """Test filtering system messages."""
    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "User message"},
        {"role": "assistant", "content": "Assistant response"},
        {"role": "system", "content": "Summary", "is_summary": True},
    ]

    filtered = filter_system_messages(messages)

    # Should keep user, assistant, and summary messages
    assert len(filtered) == 3
    assert filtered[0]["role"] == "user"
    assert filtered[1]["role"] == "assistant"
    assert filtered[2]["role"] == "system"  # Summary kept


def test_normalize_message_roles():
    """Test normalizing message roles to alternate."""
    messages = [
        {"role": "user", "content": "User 1"},
        {"role": "user", "content": "User 2"},  # Duplicate role
        {"role": "assistant", "content": "Assistant 1"},
        {"role": "assistant", "content": "Assistant 2"},  # Duplicate role
        {"role": "user", "content": "User 3"},
    ]

    normalized = normalize_message_roles(messages)

    # Should remove consecutive duplicates
    assert len(normalized) == 3
    assert normalized[0]["role"] == "user"
    assert normalized[1]["role"] == "assistant"
    assert normalized[2]["role"] == "user"


def test_normalize_message_roles_keeps_summaries():
    """Test that summaries are not filtered as duplicates."""
    messages = [
        {"role": "system", "content": "Summary", "is_summary": True},
        {"role": "system", "content": "Another system"},  # Should be filtered
        {"role": "user", "content": "User message"},
    ]

    normalized = normalize_message_roles(messages)

    # Summary should be kept even if same role
    assert len(normalized) == 2
    assert normalized[0]["role"] == "system"
    assert normalized[1]["role"] == "user"
