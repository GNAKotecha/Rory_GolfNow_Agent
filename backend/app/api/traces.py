"""Admin trace exploration API for debugging workflows and tool executions."""
import os
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
import httpx

from app.db.session import get_db
from app.models.models import User, UserRole
from app.api.auth_deps import get_approved_user


router = APIRouter(prefix="/admin/traces", tags=["admin"])


# ============================================================================
# Response Models
# ============================================================================


class TracePreview(BaseModel):
    """Trace preview for list view."""
    trace_id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    name: Optional[str] = None
    status: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    input_preview: Optional[str] = Field(None, max_length=200)
    output_preview: Optional[str] = Field(None, max_length=200)
    tags: Optional[List[str]] = []


class TraceListResponse(BaseModel):
    """Paginated trace list response."""
    traces: List[TracePreview]
    total: int
    limit: int
    offset: int
    has_more: bool = False


class SpanDetail(BaseModel):
    """Detailed span information."""
    span_id: str
    trace_id: str
    parent_span_id: Optional[str] = None
    name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    status: Optional[str] = None
    input: Optional[Dict[str, Any]] = None
    output: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    level: Optional[str] = None


class TraceDetail(BaseModel):
    """Full trace details."""
    trace_id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    name: Optional[str] = None
    status: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    input: Optional[Dict[str, Any]] = None
    output: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = []
    observations: Optional[List[SpanDetail]] = []


class TraceSearchRequest(BaseModel):
    """Search request with filters."""
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    name: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    tags: Optional[List[str]] = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


# ============================================================================
# Helper Functions
# ============================================================================


def verify_admin(current_user: User):
    """Verify user has admin role."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Admin access required"
        )


def get_langfuse_client() -> httpx.Client:
    """Get configured Langfuse HTTP client (synchronous)."""
    host = os.getenv("LANGFUSE_HOST", "http://localhost:3001")
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")

    if not public_key or not secret_key:
        raise HTTPException(
            status_code=500,
            detail="Langfuse credentials not configured"
        )

    return httpx.Client(
        base_url=host,
        auth=(public_key, secret_key),
        timeout=10.0
    )


def sanitize_preview(data: Any, max_length: int = 200) -> Optional[str]:
    """Sanitize and truncate data for preview."""
    if data is None:
        return None

    # Convert to string
    text = str(data)

    # Remove PII patterns (basic email/phone scrubbing)
    # TODO: Add more sophisticated PII detection
    import re
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', text)
    text = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[PHONE]', text)

    # Truncate
    if len(text) > max_length:
        return text[:max_length] + "..."

    return text


def filter_by_tenant(traces: List[Dict], user: User, db: Session) -> List[Dict]:
    """Filter traces to only include those from user's tenant."""
    if not user.tenant_id:
        return traces

    # Get all user IDs in the tenant
    from app.models.models import User as UserModel
    tenant_user_ids = [
        str(u.id) for u in db.query(UserModel)
        .filter(UserModel.tenant_id == user.tenant_id)
        .all()
    ]

    # Filter traces
    filtered = []
    for trace in traces:
        trace_user_id = trace.get("userId") or trace.get("user_id")
        if trace_user_id and trace_user_id in tenant_user_ids:
            filtered.append(trace)

    return filtered


# ============================================================================
# API Endpoints
# ============================================================================


@router.get("", response_model=TraceListResponse)
async def list_traces(
    trace_id: Optional[str] = Query(None, description="Filter by trace ID"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    session_id: Optional[str] = Query(None, description="Filter by session ID"),
    name: Optional[str] = Query(None, description="Filter by trace name"),
    status: Optional[str] = Query(None, description="Filter by status"),
    start_date: Optional[datetime] = Query(None, description="Start date for date range"),
    end_date: Optional[datetime] = Query(None, description="End date for date range"),
    limit: int = Query(50, ge=1, le=100, description="Max traces to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """
    List traces with filtering and pagination.

    Requires: Admin role.

    Returns paginated list of traces with preview data only.
    Full trace details available via GET /traces/{trace_id}.
    """
    verify_admin(current_user)

    # Build query parameters
    params: Dict[str, Any] = {
        "limit": limit,
        "offset": offset,
    }

    if trace_id:
        params["traceId"] = trace_id
    if user_id:
        params["userId"] = user_id
    if session_id:
        params["sessionId"] = session_id
    if name:
        params["name"] = name
    if status:
        params["status"] = status
    if start_date:
        params["fromTimestamp"] = start_date.isoformat()
    if end_date:
        params["toTimestamp"] = end_date.isoformat()

    # Query Langfuse API
    with get_langfuse_client() as client:
        try:
            response = client.get("/api/public/traces", params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to query Langfuse: {str(e)}"
            )

    # Extract traces and track original total before filtering
    traces_data = data.get("data", [])
    total_before_filter = data.get("meta", {}).get("totalItems", len(traces_data))

    # Filter by tenant
    traces_data = filter_by_tenant(traces_data, current_user, db)

    # Convert to preview format
    traces = []
    for trace in traces_data:
        traces.append(TracePreview(
            trace_id=trace.get("id", ""),
            user_id=trace.get("userId"),
            session_id=trace.get("sessionId"),
            name=trace.get("name"),
            status=trace.get("status"),
            created_at=datetime.fromisoformat(trace["timestamp"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(trace["updatedAt"].replace("Z", "+00:00")) if trace.get("updatedAt") else None,
            duration_ms=trace.get("duration"),
            input_preview=sanitize_preview(trace.get("input")),
            output_preview=sanitize_preview(trace.get("output")),
            tags=trace.get("tags", []),
        ))

    # Calculate has_more based on whether we could fetch more if we tried
    has_more = (offset + len(traces)) < total_before_filter

    return TraceListResponse(
        traces=traces,
        total=len(traces),  # Number of traces returned in this batch
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


@router.get("/{trace_id}", response_model=TraceDetail)
async def get_trace(
    trace_id: str,
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """
    Get full details for a single trace.

    Requires: Admin role.

    Returns complete trace data including all observations/spans.
    """
    verify_admin(current_user)

    # Query Langfuse API
    with get_langfuse_client() as client:
        try:
            response = client.get(f"/api/public/traces/{trace_id}")
            response.raise_for_status()
            trace = response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise HTTPException(status_code=404, detail="Trace not found")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch trace: {str(e)}"
            )
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to query Langfuse: {str(e)}"
            )

    # Verify tenant access
    filtered = filter_by_tenant([trace], current_user, db)
    if not filtered:
        raise HTTPException(
            status_code=403,
            detail="Trace not found or access denied"
        )

    # Convert observations to spans
    observations = trace.get("observations", [])
    spans = []
    for obs in observations:
        spans.append(SpanDetail(
            span_id=obs.get("id", ""),
            trace_id=trace_id,
            parent_span_id=obs.get("parentObservationId"),
            name=obs.get("name", ""),
            start_time=datetime.fromisoformat(obs["startTime"].replace("Z", "+00:00")),
            end_time=datetime.fromisoformat(obs["endTime"].replace("Z", "+00:00")) if obs.get("endTime") else None,
            duration_ms=obs.get("duration"),
            status=obs.get("level"),
            input=obs.get("input"),
            output=obs.get("output"),
            metadata=obs.get("metadata"),
            level=obs.get("level"),
        ))

    return TraceDetail(
        trace_id=trace.get("id", ""),
        user_id=trace.get("userId"),
        session_id=trace.get("sessionId"),
        name=trace.get("name"),
        status=trace.get("status"),
        created_at=datetime.fromisoformat(trace["timestamp"].replace("Z", "+00:00")),
        updated_at=datetime.fromisoformat(trace["updatedAt"].replace("Z", "+00:00")) if trace.get("updatedAt") else None,
        duration_ms=trace.get("duration"),
        input=trace.get("input"),
        output=trace.get("output"),
        metadata=trace.get("metadata"),
        tags=trace.get("tags", []),
        observations=spans,
    )


@router.get("/{trace_id}/spans", response_model=List[SpanDetail])
async def get_trace_spans(
    trace_id: str,
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """
    Get all spans/observations within a trace.

    Requires: Admin role.

    Returns array of spans with timing, status, and I/O data.
    """
    verify_admin(current_user)

    # Get full trace (includes observations)
    trace_detail = await get_trace(trace_id, current_user, db)

    return trace_detail.observations or []


@router.post("/search", response_model=TraceListResponse)
async def search_traces(
    search_request: TraceSearchRequest,
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """
    Advanced trace search with filters.

    Requires: Admin role.

    Accepts JSON body with multiple filter criteria.
    Returns matching traces with pagination.
    """
    verify_admin(current_user)

    # Build query parameters from request body
    params: Dict[str, Any] = {
        "limit": search_request.limit,
        "offset": search_request.offset,
    }

    if search_request.user_id:
        params["userId"] = search_request.user_id
    if search_request.session_id:
        params["sessionId"] = search_request.session_id
    if search_request.name:
        params["name"] = search_request.name
    if search_request.status:
        params["status"] = search_request.status
    if search_request.start_date:
        params["fromTimestamp"] = search_request.start_date.isoformat()
    if search_request.end_date:
        params["toTimestamp"] = search_request.end_date.isoformat()
    if search_request.tags:
        # Tags filter (Langfuse API may support this differently)
        params["tags"] = ",".join(search_request.tags)

    # Query Langfuse API
    with get_langfuse_client() as client:
        try:
            response = client.get("/api/public/traces", params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to query Langfuse: {str(e)}"
            )

    # Extract traces and track original total
    traces_data = data.get("data", [])
    total_before_filter = data.get("meta", {}).get("totalItems", len(traces_data))

    # Filter by tenant
    traces_data = filter_by_tenant(traces_data, current_user, db)

    # Apply tag filtering if needed (client-side)
    if search_request.tags:
        traces_data = [
            t for t in traces_data
            if any(tag in t.get("tags", []) for tag in search_request.tags)
        ]

    # Convert to preview format
    traces = []
    for trace in traces_data:
        traces.append(TracePreview(
            trace_id=trace.get("id", ""),
            user_id=trace.get("userId"),
            session_id=trace.get("sessionId"),
            name=trace.get("name"),
            status=trace.get("status"),
            created_at=datetime.fromisoformat(trace["timestamp"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(trace["updatedAt"].replace("Z", "+00:00")) if trace.get("updatedAt") else None,
            duration_ms=trace.get("duration"),
            input_preview=sanitize_preview(trace.get("input")),
            output_preview=sanitize_preview(trace.get("output")),
            tags=trace.get("tags", []),
        ))

    # Calculate has_more
    has_more = (search_request.offset + len(traces)) < total_before_filter

    return TraceListResponse(
        traces=traces,
        total=len(traces),
        limit=search_request.limit,
        offset=search_request.offset,
        has_more=has_more,
    )
