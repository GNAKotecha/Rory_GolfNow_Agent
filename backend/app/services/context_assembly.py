"""Context assembly service with caching and compaction.

Assembles conversation context from:
- Session summary (for old messages)
- Recent messages (verbatim)
- Tool state (if relevant)

Caches assembled context to avoid redundant DB fetches.
"""
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass
import hashlib
import logging

from app.services.history import (
    should_compact_history,
    compact_history,
    build_conversation_context,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# Cache Configuration
# ==============================================================================

# In-memory cache for assembled contexts
# Key: cache_key, Value: CachedContext
_context_cache: Dict[str, "CachedContext"] = {}

# Maximum cache size (number of sessions)
MAX_CACHE_SIZE = 1000


@dataclass
class CachedContext:
    """Cached assembled context."""
    messages: List[Dict]
    cache_key: str
    cached_at: datetime
    metadata: Dict
    session_id: int  # Track session ID for invalidation


# ==============================================================================
# Cache Key Generation
# ==============================================================================

def generate_cache_key(
    session_id: int,
    message_count: int,
    summary_hash: Optional[str] = None,
) -> str:
    """
    Generate cache key for assembled context.

    Args:
        session_id: Session ID
        message_count: Current message count
        summary_hash: Hash of session summary (if exists)

    Returns:
        Cache key string
    """
    key_parts = [
        str(session_id),
        str(message_count),
        summary_hash or "no-summary",
    ]

    key_string = ":".join(key_parts)
    return hashlib.md5(key_string.encode()).hexdigest()


def hash_summary(summary_text: Optional[str]) -> Optional[str]:
    """Generate hash of summary text for cache key."""
    if not summary_text:
        return None
    return hashlib.md5(summary_text.encode()).hexdigest()[:16]


# ==============================================================================
# Cache Operations
# ==============================================================================

def get_cached_context(cache_key: str) -> Optional[CachedContext]:
    """
    Get cached context by key.

    Args:
        cache_key: Cache key

    Returns:
        Cached context or None
    """
    return _context_cache.get(cache_key)


def set_cached_context(cache_key: str, context: CachedContext):
    """
    Store context in cache.

    Args:
        cache_key: Cache key
        context: Context to cache
    """
    # Evict oldest entry if cache is full
    if len(_context_cache) >= MAX_CACHE_SIZE:
        oldest_key = min(
            _context_cache.keys(),
            key=lambda k: _context_cache[k].cached_at
        )
        del _context_cache[oldest_key]
        logger.info(f"Evicted cache entry: {oldest_key}")

    _context_cache[cache_key] = context
    logger.debug(f"Cached context: {cache_key}")


def invalidate_cache(session_id: int):
    """
    Invalidate all cache entries for a session.

    Args:
        session_id: Session ID
    """
    keys_to_remove = [
        key for key, cached in _context_cache.items()
        if cached.session_id == session_id
    ]

    for key in keys_to_remove:
        del _context_cache[key]

    if keys_to_remove:
        logger.info(f"Invalidated {len(keys_to_remove)} cache entries for session {session_id}")


def clear_cache():
    """Clear entire cache."""
    _context_cache.clear()
    logger.info("Cache cleared")


# ==============================================================================
# Context Assembly
# ==============================================================================

def assemble_context(
    messages: List[Dict],
    session_id: int,
    session_summary: Optional[str] = None,
    use_cache: bool = True,
    keep_recent: int = 10,
) -> Tuple[List[Dict], Dict]:
    """
    Assemble conversation context with caching and compaction.

    Args:
        messages: Full message history from DB
        session_id: Session ID
        session_summary: Optional pre-generated summary
        use_cache: Whether to use caching
        keep_recent: Number of recent messages to keep verbatim

    Returns:
        Tuple of (assembled_messages, metadata)
    """
    metadata = {
        "session_id": session_id,
        "total_messages": len(messages),
        "cache_used": False,
        "compacted": False,
    }

    # Generate cache key
    summary_hash = hash_summary(session_summary)
    cache_key = generate_cache_key(session_id, len(messages), summary_hash)

    # Check cache
    if use_cache:
        cached = get_cached_context(cache_key)
        if cached is not None:
            logger.info(
                f"Cache hit for session {session_id}",
                extra={
                    "session_id": session_id,
                    "cache_key": cache_key,
                    "message_count": len(messages),
                }
            )
            # Update metadata with cached values, but ensure cache_used is True
            metadata.update(cached.metadata)
            metadata["cache_used"] = True
            return cached.messages, metadata

    # Cache miss - assemble context
    logger.info(
        f"Cache miss for session {session_id}",
        extra={
            "session_id": session_id,
            "cache_key": cache_key,
            "message_count": len(messages),
        }
    )

    # Check if compaction is needed
    if should_compact_history(len(messages)):
        assembled_messages, compact_stats = compact_history(
            messages,
            keep_recent=keep_recent,
            summary_text=session_summary,
        )
        metadata["compacted"] = True
        metadata.update(compact_stats)
    else:
        assembled_messages = messages
        metadata["compacted"] = False

    # Build final context
    final_context = build_conversation_context(assembled_messages)

    # Cache the result
    if use_cache:
        cached_context = CachedContext(
            messages=final_context,
            cache_key=cache_key,
            cached_at=datetime.now(timezone.utc),
            metadata=metadata,
            session_id=session_id,
        )
        set_cached_context(cache_key, cached_context)

    return final_context, metadata


def prepare_context_for_llm(
    messages: List[Dict],
    session_id: int,
    session_summary: Optional[str] = None,
    use_cache: bool = True,
) -> Tuple[List[Dict], Dict]:
    """
    Prepare conversation context for LLM API call.

    High-level function that handles:
    - Caching
    - Compaction
    - Formatting

    Args:
        messages: Full message history
        session_id: Session ID
        session_summary: Optional summary text
        use_cache: Whether to use caching

    Returns:
        Tuple of (prepared_messages, metadata)
    """
    assembled_messages, metadata = assemble_context(
        messages=messages,
        session_id=session_id,
        session_summary=session_summary,
        use_cache=use_cache,
    )

    logger.info(
        f"Context prepared for session {session_id}",
        extra={
            "session_id": session_id,
            "final_message_count": len(assembled_messages),
            **metadata,
        }
    )

    return assembled_messages, metadata


# ==============================================================================
# Cache Statistics
# ==============================================================================

def get_cache_stats() -> Dict:
    """
    Get cache statistics.

    Returns:
        Dictionary with cache stats
    """
    return {
        "cache_size": len(_context_cache),
        "max_cache_size": MAX_CACHE_SIZE,
        "cache_keys": list(_context_cache.keys()),
    }
