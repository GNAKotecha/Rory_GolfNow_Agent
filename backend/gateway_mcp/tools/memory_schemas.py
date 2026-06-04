"""
Gateway MCP Schemas for Agent Memory Tools

Pydantic models for agent memory tool inputs and outputs.

Schemas define the contract between the agent and the Gateway for:
- Working memory: Live session facts with 2KB enforcement
- Session summaries: Historical context from past sessions
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ============================================================================
# get_working_memory Schemas
# ============================================================================

class GetWorkingMemoryInput(BaseModel):
    """Input for get_working_memory tool."""

    session_id: int = Field(
        ...,
        description="Session ID to retrieve working memory for",
        gt=0,
    )
    tenant_id: int = Field(
        ...,
        description="Tenant ID (for multi-tenant isolation)",
        gt=0,
    )


class GetWorkingMemoryOutput(BaseModel):
    """Output for get_working_memory tool."""

    session_id: int = Field(..., description="Session ID")
    memory: dict[str, Any] = Field(
        default_factory=dict,
        description="Working memory facts (key-value pairs)",
    )
    size_bytes: int = Field(
        ...,
        description="Size of memory in bytes (max 2048)",
    )


# ============================================================================
# update_working_memory Schemas
# ============================================================================

class UpdateWorkingMemoryInput(BaseModel):
    """Input for update_working_memory tool."""

    session_id: int = Field(
        ...,
        description="Session ID to update",
        gt=0,
    )
    tenant_id: int = Field(
        ...,
        description="Tenant ID (for multi-tenant isolation)",
        gt=0,
    )
    updates: dict[str, Any] = Field(
        ...,
        description="Dictionary of facts to merge into working memory",
        min_length=1,
    )


class UpdateWorkingMemoryOutput(BaseModel):
    """Output for update_working_memory tool."""

    session_id: int = Field(..., description="Session ID")
    memory: dict[str, Any] = Field(
        default_factory=dict,
        description="Updated working memory (may be trimmed if exceeded 2KB)",
    )
    size_bytes: int = Field(
        ...,
        description="Size of updated memory in bytes (max 2048)",
    )
    keys_added: int = Field(
        ...,
        description="Number of keys added/updated",
    )


# ============================================================================
# store_session_summary Schemas
# ============================================================================

class StoreSessionSummaryInput(BaseModel):
    """Input for store_session_summary tool."""

    session_id: int = Field(
        ...,
        description="Session ID to create summary for",
        gt=0,
    )
    tenant_id: int = Field(
        ...,
        description="Tenant ID (for multi-tenant isolation)",
        gt=0,
    )
    content: str = Field(
        ...,
        description="End-of-session summary content (for historical retrieval)",
        min_length=1,
        max_length=32768,  # 32KB
    )


class StoreSessionSummaryOutput(BaseModel):
    """Output for store_session_summary tool."""

    summary_id: int = Field(..., description="Created summary ID")
    session_id: int = Field(..., description="Session ID")
    created_at: datetime = Field(
        ...,
        description="Timestamp when summary was created",
    )


# ============================================================================
# get_historical_context Schemas
# ============================================================================

class HistoricalContextSummary(BaseModel):
    """A single historical context summary result."""

    summary_id: int = Field(..., description="Summary record ID")
    session_id: int = Field(..., description="Session ID")
    content: str = Field(..., description="Summary content")
    created_at: datetime = Field(
        ...,
        description="Timestamp when summary was created",
    )


class GetHistoricalContextInput(BaseModel):
    """Input for get_historical_context tool."""

    tenant_id: int = Field(
        ...,
        description="Tenant ID to search within",
        gt=0,
    )
    query: str = Field(
        ...,
        description="Keyword to search for in historical summaries",
        min_length=1,
        max_length=256,
    )
    limit: int = Field(
        default=5,
        description="Maximum number of results to return",
        ge=1,
        le=50,
    )


class GetHistoricalContextOutput(BaseModel):
    """Output for get_historical_context tool."""

    query: str = Field(..., description="Search query that was used")
    results_count: int = Field(
        ...,
        description="Number of results returned",
    )
    summaries: list[HistoricalContextSummary] = Field(
        default_factory=list,
        description="Matching historical summaries (newest first)",
    )
