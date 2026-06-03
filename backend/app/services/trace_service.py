"""Trace service layer for advanced trace aggregation, filtering, and caching.

This service wraps Langfuse HTTP API interactions and provides:
- Filtered trace fetching by date range, user, status
- Pagination and sorting
- 5-minute TTL caching for frequently accessed traces
- Correlation tracking with workflow events
- Data normalization and formatting
"""
import os
import logging
import time
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from functools import lru_cache
import httpx
from sqlalchemy.orm import Session

from app.models.models import User, WorkflowEvent


logger = logging.getLogger(__name__)


# ============================================================================
# Cache Configuration
# ============================================================================

CACHE_TTL_SECONDS = 300  # 5 minutes
_trace_cache: Dict[str, Tuple[float, Any]] = {}  # {cache_key: (timestamp, data)}
_cache_lock = None  # Thread lock if needed for production


def _get_cache_key(filters: Dict[str, Any]) -> str:
    """Generate cache key from filter parameters."""
    # Sort keys for consistent cache keys
    sorted_items = sorted(filters.items())
    return str(sorted_items)


def _get_cached(cache_key: str) -> Optional[Any]:
    """Get cached data if not expired."""
    if cache_key not in _trace_cache:
        return None

    timestamp, data = _trace_cache[cache_key]
    if time.time() - timestamp > CACHE_TTL_SECONDS:
        # Expired, remove from cache
        del _trace_cache[cache_key]
        return None

    return data


def _set_cache(cache_key: str, data: Any) -> None:
    """Store data in cache with current timestamp."""
    _trace_cache[cache_key] = (time.time(), data)


def clear_trace_cache() -> None:
    """Clear all cached trace data. Useful for testing or forced refresh."""
    _trace_cache.clear()


# ============================================================================
# TraceService - Main Service Class
# ============================================================================


class TraceService:
    """Service for trace fetching, filtering, and caching.

    All methods are static to avoid state management.
    Caching is handled via module-level cache dict.
    """

    @staticmethod
    def get_langfuse_client() -> httpx.Client:
        """Get configured synchronous Langfuse HTTP client.

        Returns:
            httpx.Client configured with Langfuse credentials

        Raises:
            ValueError: If Langfuse credentials not configured
        """
        host = os.getenv("LANGFUSE_HOST", "http://localhost:3001")
        public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
        secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")

        if not public_key or not secret_key:
            raise ValueError("Langfuse credentials not configured (LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY)")

        return httpx.Client(
            base_url=host,
            auth=(public_key, secret_key),
            timeout=10.0
        )

    @staticmethod
    def get_traces(
        filters: Optional[Dict[str, Any]] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """Fetch traces with optional filtering and caching.

        Args:
            filters: Optional dict with filter criteria:
                - trace_id: str
                - user_id: str
                - session_id: str
                - name: str (trace name)
                - status: str (e.g., "success", "error")
                - start_date: datetime (filter by creation date >= start_date)
                - end_date: datetime (filter by creation date <= end_date)
                - limit: int (default 50, max 100)
                - offset: int (default 0)
            use_cache: Whether to use cached results if available

        Returns:
            Dict with keys:
                - data: List[Dict] - trace objects
                - meta: Dict - pagination metadata (totalItems, etc.)
                - cached: bool - whether result came from cache

        Raises:
            httpx.HTTPError: If Langfuse API request fails
        """
        filters = filters or {}

        # Check cache first
        cache_key = _get_cache_key(filters)
        if use_cache:
            cached_data = _get_cached(cache_key)
            if cached_data is not None:
                logger.debug(f"Cache hit for trace query: {cache_key[:50]}...")
                return {**cached_data, "cached": True}

        # Build query parameters
        params: Dict[str, Any] = {
            "limit": filters.get("limit", 50),
            "offset": filters.get("offset", 0),
        }

        if "trace_id" in filters:
            params["traceId"] = filters["trace_id"]
        if "user_id" in filters:
            params["userId"] = filters["user_id"]
        if "session_id" in filters:
            params["sessionId"] = filters["session_id"]
        if "name" in filters:
            params["name"] = filters["name"]
        if "status" in filters:
            params["status"] = filters["status"]
        if "start_date" in filters:
            params["fromTimestamp"] = filters["start_date"].isoformat()
        if "end_date" in filters:
            params["toTimestamp"] = filters["end_date"].isoformat()

        # Query Langfuse API
        with TraceService.get_langfuse_client() as client:
            try:
                response = client.get("/api/public/traces", params=params)
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPError as e:
                logger.error(f"Failed to query Langfuse: {str(e)}")
                raise

        # Normalize data structure
        result = {
            "data": data.get("data", []),
            "meta": data.get("meta", {"totalItems": len(data.get("data", []))}),
            "cached": False
        }

        # Cache the result
        _set_cache(cache_key, result)

        return result

    @staticmethod
    def get_trace_by_id(trace_id: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """Get single trace by ID with caching.

        Args:
            trace_id: Trace ID to fetch
            use_cache: Whether to use cached result if available

        Returns:
            Trace dict or None if not found

        Raises:
            httpx.HTTPError: If Langfuse API request fails (except 404)
        """
        # Check cache first
        cache_key = f"trace_id:{trace_id}"
        if use_cache:
            cached_data = _get_cached(cache_key)
            if cached_data is not None:
                logger.debug(f"Cache hit for trace ID: {trace_id}")
                return cached_data

        # Query Langfuse API
        with TraceService.get_langfuse_client() as client:
            try:
                response = client.get(f"/api/public/traces/{trace_id}")
                response.raise_for_status()
                trace = response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    logger.warning(f"Trace not found: {trace_id}")
                    return None
                logger.error(f"Failed to fetch trace {trace_id}: {str(e)}")
                raise
            except httpx.HTTPError as e:
                logger.error(f"Failed to query Langfuse for trace {trace_id}: {str(e)}")
                raise

        # Normalize trace data
        normalized_trace = TraceService._normalize_trace(trace)

        # Cache the result
        _set_cache(cache_key, normalized_trace)

        return normalized_trace

    @staticmethod
    def get_spans_for_trace(trace_id: str, use_cache: bool = True) -> List[Dict[str, Any]]:
        """Get all spans (observations) within a trace.

        Args:
            trace_id: Trace ID to fetch spans for
            use_cache: Whether to use cached result if available

        Returns:
            List of span dicts with normalized structure

        Raises:
            httpx.HTTPError: If Langfuse API request fails
        """
        # Get full trace (includes observations)
        trace = TraceService.get_trace_by_id(trace_id, use_cache=use_cache)
        if not trace:
            return []

        # Extract and normalize spans
        observations = trace.get("observations", [])
        spans = [TraceService._normalize_span(obs, trace_id) for obs in observations]

        return spans

    @staticmethod
    def search_traces(
        filters: Dict[str, Any],
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """Advanced trace search with multiple filter criteria.

        This is an alias for get_traces() with explicit search intent.
        Supports all filters from get_traces().

        Args:
            filters: Dict with filter criteria (see get_traces())
            use_cache: Whether to use cached results

        Returns:
            Dict with data, meta, and cached keys (see get_traces())
        """
        return TraceService.get_traces(filters=filters, use_cache=use_cache)

    @staticmethod
    def filter_by_tenant(
        traces: List[Dict[str, Any]],
        tenant_id: int,
        db: Session
    ) -> List[Dict[str, Any]]:
        """Filter traces to only include those from specified tenant.

        Args:
            traces: List of trace dicts
            tenant_id: Tenant ID to filter by
            db: SQLAlchemy session for user lookup

        Returns:
            Filtered list of traces
        """
        # Get all user IDs in the tenant
        tenant_user_ids = [
            str(u.id) for u in db.query(User)
            .filter(User.tenant_id == tenant_id)
            .all()
        ]

        # Filter traces
        filtered = []
        for trace in traces:
            trace_user_id = trace.get("userId") or trace.get("user_id")
            if trace_user_id and trace_user_id in tenant_user_ids:
                filtered.append(trace)

        return filtered

    @staticmethod
    def get_correlation_ids_for_trace(
        trace_id: str,
        db: Session
    ) -> List[str]:
        """Get correlation IDs associated with a trace.

        Queries WorkflowEvent table to find related events.

        Args:
            trace_id: Trace ID to find correlations for
            db: SQLAlchemy session

        Returns:
            List of correlation IDs (run_id values)
        """
        try:
            # Query workflow events - fetch all and filter in Python since
            # metadata.contains may not work on all database backends
            all_events = db.query(WorkflowEvent).all()

            # Filter events that have trace_id in their metadata
            correlation_ids = list(set([
                event.run_id for event in all_events
                if event.run_id and event.metadata and event.metadata.get("trace_id") == trace_id
            ]))

            return correlation_ids
        except Exception as e:
            logger.error(f"Failed to get correlation IDs for trace {trace_id}: {str(e)}")
            return []

    @staticmethod
    def get_traces_for_correlation_id(
        correlation_id: str,
        db: Session,
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """Get all traces associated with a correlation ID (run_id).

        Args:
            correlation_id: Correlation ID (run_id) to search for
            db: SQLAlchemy session
            use_cache: Whether to use cached results

        Returns:
            List of trace dicts
        """
        # Query workflow events by run_id
        events = db.query(WorkflowEvent).filter(
            WorkflowEvent.run_id == correlation_id
        ).all()

        # Extract trace IDs from event metadata
        trace_ids = []
        for event in events:
            if event.metadata and "trace_id" in event.metadata:
                trace_ids.append(event.metadata["trace_id"])

        # Fetch traces by ID
        traces = []
        for trace_id in trace_ids:
            trace = TraceService.get_trace_by_id(trace_id, use_cache=use_cache)
            if trace:
                traces.append(trace)

        return traces

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    @staticmethod
    def _normalize_trace(trace: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize trace data to consistent format.

        Handles missing fields, timestamp formatting, etc.

        Args:
            trace: Raw trace dict from Langfuse API

        Returns:
            Normalized trace dict
        """
        # Parse timestamps
        created_at = None
        if "timestamp" in trace:
            created_at = TraceService._parse_timestamp(trace["timestamp"])

        updated_at = None
        if "updatedAt" in trace:
            updated_at = TraceService._parse_timestamp(trace["updatedAt"])

        # Build normalized structure
        normalized = {
            "trace_id": trace.get("id", ""),
            "user_id": trace.get("userId"),
            "session_id": trace.get("sessionId"),
            "name": trace.get("name"),
            "status": trace.get("status"),
            "created_at": created_at,
            "updated_at": updated_at,
            "duration_ms": trace.get("duration"),
            "input": trace.get("input"),
            "output": trace.get("output"),
            "metadata": trace.get("metadata", {}),
            "tags": trace.get("tags", []),
            "observations": trace.get("observations", []),
        }

        return normalized

    @staticmethod
    def _normalize_span(span: Dict[str, Any], trace_id: str) -> Dict[str, Any]:
        """Normalize span/observation data to consistent format.

        Args:
            span: Raw span dict from Langfuse API
            trace_id: Parent trace ID

        Returns:
            Normalized span dict
        """
        # Parse timestamps
        start_time = None
        if "startTime" in span:
            start_time = TraceService._parse_timestamp(span["startTime"])

        end_time = None
        if "endTime" in span:
            end_time = TraceService._parse_timestamp(span["endTime"])

        # Build normalized structure
        normalized = {
            "span_id": span.get("id", ""),
            "trace_id": trace_id,
            "parent_span_id": span.get("parentObservationId"),
            "name": span.get("name", ""),
            "start_time": start_time,
            "end_time": end_time,
            "duration_ms": span.get("duration"),
            "status": span.get("level"),
            "input": span.get("input"),
            "output": span.get("output"),
            "metadata": span.get("metadata", {}),
            "level": span.get("level"),
        }

        return normalized

    @staticmethod
    def _parse_timestamp(timestamp_str: str) -> Optional[datetime]:
        """Parse ISO timestamp string to datetime object.

        Handles both UTC (Z) and timezone-aware formats.

        Args:
            timestamp_str: ISO format timestamp string

        Returns:
            Datetime object or None if parsing fails
        """
        if not timestamp_str:
            return None

        try:
            # Remove 'Z' suffix and replace with +00:00
            clean_str = timestamp_str.replace("Z", "+00:00")
            return datetime.fromisoformat(clean_str)
        except (ValueError, AttributeError) as e:
            logger.warning(f"Failed to parse timestamp '{timestamp_str}': {e}")
            return None
