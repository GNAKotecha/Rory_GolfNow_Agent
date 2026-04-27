"""Tests for context assembly and caching."""
import pytest
from datetime import datetime, timezone

from app.services.context_assembly import (
    generate_cache_key,
    hash_summary,
    assemble_context,
    get_cached_context,
    set_cached_context,
    invalidate_cache,
    clear_cache,
    CachedContext,
)


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture(autouse=True)
def clear_cache_before_test():
    """Clear cache before each test."""
    clear_cache()
    yield
    clear_cache()


@pytest.fixture
def sample_messages():
    """Create sample messages."""
    return [
        {"role": "user", "content": f"Message {i}"}
        for i in range(25)
    ]


# ==============================================================================
# Cache Key Tests
# ==============================================================================

def test_generate_cache_key():
    """Test cache key generation."""
    key1 = generate_cache_key(1, 10, "abc123")
    key2 = generate_cache_key(1, 10, "abc123")
    key3 = generate_cache_key(1, 11, "abc123")

    # Same inputs = same key
    assert key1 == key2

    # Different inputs = different key
    assert key1 != key3


def test_hash_summary():
    """Test summary hashing."""
    hash1 = hash_summary("This is a summary")
    hash2 = hash_summary("This is a summary")
    hash3 = hash_summary("Different summary")

    assert hash1 == hash2
    assert hash1 != hash3


def test_hash_summary_none():
    """Test hashing None summary."""
    assert hash_summary(None) is None


# ==============================================================================
# Cache Operations Tests
# ==============================================================================

def test_set_and_get_cached_context():
    """Test setting and getting cached context."""
    cache_key = "test-key"
    cached_context = CachedContext(
        messages=[{"role": "user", "content": "test"}],
        cache_key=cache_key,
        cached_at=datetime.now(timezone.utc),
        metadata={"test": True},
        session_id=1,
    )

    set_cached_context(cache_key, cached_context)
    retrieved = get_cached_context(cache_key)

    assert retrieved is not None
    assert retrieved.cache_key == cache_key
    assert len(retrieved.messages) == 1
    assert retrieved.session_id == 1


def test_get_nonexistent_cache():
    """Test getting nonexistent cache entry."""
    result = get_cached_context("nonexistent")
    assert result is None


def test_invalidate_cache_by_session():
    """Test invalidating cache for specific session."""
    # Create cache entries for different sessions
    set_cached_context("key1", CachedContext(
        messages=[],
        cache_key="key1",
        cached_at=datetime.now(timezone.utc),
        metadata={},
        session_id=1,
    ))
    set_cached_context("key2", CachedContext(
        messages=[],
        cache_key="key2",
        cached_at=datetime.now(timezone.utc),
        metadata={},
        session_id=1,
    ))
    set_cached_context("key3", CachedContext(
        messages=[],
        cache_key="key3",
        cached_at=datetime.now(timezone.utc),
        metadata={},
        session_id=2,
    ))

    # Invalidate session 1
    invalidate_cache(1)

    # Session 1 entries should be gone
    assert get_cached_context("key1") is None
    assert get_cached_context("key2") is None

    # Session 2 entry should remain
    assert get_cached_context("key3") is not None


# ==============================================================================
# Context Assembly Tests
# ==============================================================================

def test_assemble_context_no_compaction(sample_messages):
    """Test context assembly without compaction (few messages)."""
    short_messages = sample_messages[:10]

    assembled, metadata = assemble_context(
        messages=short_messages,
        session_id=1,
        use_cache=False,
    )

    assert metadata["compacted"] is False
    # Messages are filtered/normalized by build_conversation_context
    assert len(assembled) <= len(short_messages)


def test_assemble_context_with_compaction(sample_messages):
    """Test context assembly with compaction (many messages)."""
    assembled, metadata = assemble_context(
        messages=sample_messages,
        session_id=1,
        use_cache=False,
    )

    assert metadata["compacted"] is True
    assert len(assembled) < len(sample_messages)
    # Should have summary + recent messages
    assert metadata["messages_kept"] == 10


def test_assemble_context_with_summary(sample_messages):
    """Test context assembly with existing summary."""
    summary = "This is a conversation summary"

    assembled, metadata = assemble_context(
        messages=sample_messages,
        session_id=1,
        session_summary=summary,
        use_cache=False,
    )

    # Should include summary in compacted context
    assert metadata["compacted"] is True

    # First message should be the summary
    assert assembled[0]["role"] == "system"
    assert "summary" in assembled[0]["content"].lower()


def test_assemble_context_caching():
    """Test that context is cached and reused."""
    messages = [
        {"role": "user", "content": f"Message {i}"}
        for i in range(25)
    ]

    # First call - cache miss
    assembled1, metadata1 = assemble_context(
        messages=messages,
        session_id=1,
        use_cache=True,
    )

    assert metadata1["cache_used"] is False

    # Second call with same data - cache hit
    assembled2, metadata2 = assemble_context(
        messages=messages,
        session_id=1,
        use_cache=True,
    )

    assert metadata2["cache_used"] is True
    assert assembled1 == assembled2


def test_cache_invalidation_on_new_message():
    """Test that cache is invalidated when new message is added."""
    messages = [
        {"role": "user", "content": f"Message {i}"}
        for i in range(25)
    ]

    # First call
    assembled1, metadata1 = assemble_context(
        messages=messages,
        session_id=1,
        use_cache=True,
    )

    assert metadata1["cache_used"] is False

    # Add new message
    messages.append({"role": "assistant", "content": "New message"})

    # Second call with new message - cache miss (different message count)
    assembled2, metadata2 = assemble_context(
        messages=messages,
        session_id=1,
        use_cache=True,
    )

    assert metadata2["cache_used"] is False
    assert len(assembled2) != len(assembled1)


def test_cache_invalidation_on_summary_change():
    """Test that cache is invalidated when summary changes."""
    messages = [
        {"role": "user", "content": f"Message {i}"}
        for i in range(25)
    ]

    # First call with no summary
    assembled1, metadata1 = assemble_context(
        messages=messages,
        session_id=1,
        session_summary=None,
        use_cache=True,
    )

    assert metadata1["cache_used"] is False

    # Second call with summary - cache miss (different summary hash)
    assembled2, metadata2 = assemble_context(
        messages=messages,
        session_id=1,
        session_summary="New summary",
        use_cache=True,
    )

    assert metadata2["cache_used"] is False


def test_assemble_context_no_cache():
    """Test context assembly with caching disabled."""
    messages = [
        {"role": "user", "content": f"Message {i}"}
        for i in range(25)
    ]

    # First call
    assembled1, metadata1 = assemble_context(
        messages=messages,
        session_id=1,
        use_cache=False,
    )

    # Second call - should not use cache
    assembled2, metadata2 = assemble_context(
        messages=messages,
        session_id=1,
        use_cache=False,
    )

    assert metadata1["cache_used"] is False
    assert metadata2["cache_used"] is False
