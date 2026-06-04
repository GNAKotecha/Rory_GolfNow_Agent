"""
Agent Memory Tools

Handlers for agent memory operations:
- get_working_memory: Retrieve session working memory
- update_working_memory: Update session working memory with new facts
- store_session_summary: Store end-of-session memory summary
- get_historical_context: Retrieve historical context via keyword search

Agent memory services provide critical memory management for agent execution:
- Working memory: Live session facts, enforced 2KB limit
- Session summaries: Historical context from past sessions
- Workflow outcomes: Tracking of workflow execution history
"""

import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from gateway_mcp.core.errors import ToolExecutionError
from gateway_mcp.tools.base import (
    Environment,
    RiskLevel,
    Tool,
    ToolContext,
)
from gateway_mcp.tools.memory_schemas import (
    GetWorkingMemoryInput,
    GetWorkingMemoryOutput,
    UpdateWorkingMemoryInput,
    UpdateWorkingMemoryOutput,
    StoreSessionSummaryInput,
    StoreSessionSummaryOutput,
    GetHistoricalContextInput,
    GetHistoricalContextOutput,
)

logger = logging.getLogger(__name__)


async def get_working_memory_handler(
    input: GetWorkingMemoryInput,
    context: ToolContext,
) -> GetWorkingMemoryOutput:
    """
    Retrieve session working memory.

    Returns the live session memory facts (limited to 2KB).

    Args:
        input: Session ID and tenant ID
        context: Tool context with database session

    Returns:
        GetWorkingMemoryOutput with memory facts or empty dict if not found

    Raises:
        ToolExecutionError: If session not found (cross-tenant access attempted)
    """
    db = await context.get_executor()  # ExecutorBackend provides db session

    try:
        from app.services.agent_memory import AgentMemoryService

        memory = AgentMemoryService.get_working_memory(
            session_id=input.session_id,
            tenant_id=input.tenant_id,
            db=db
        )

        if memory is None:
            raise ToolExecutionError(
                tool_name="get_working_memory",
                message=f"Session {input.session_id} not found or cross-tenant access attempted",
                audit_id=context.audit_id,
            )

        logger.info(
            f"Retrieved working memory for session {input.session_id}",
            extra={"correlation_id": context.correlation_id},
        )

        return GetWorkingMemoryOutput(
            session_id=input.session_id,
            memory=memory,
            size_bytes=len(str(memory).encode('utf-8')),
        )
    except ToolExecutionError:
        raise
    except Exception as e:
        logger.error(
            f"Failed to get working memory: {e}",
            extra={"correlation_id": context.correlation_id},
        )
        raise ToolExecutionError(
            tool_name="get_working_memory",
            message=f"Failed to retrieve working memory: {str(e)[:200]}",
            audit_id=context.audit_id,
        )


async def update_working_memory_handler(
    input: UpdateWorkingMemoryInput,
    context: ToolContext,
) -> UpdateWorkingMemoryOutput:
    """
    Update session working memory with new facts.

    Merges updates into existing memory, enforcing 2KB limit.
    Auto-trims oldest keys if exceeded.

    Args:
        input: Session ID, tenant ID, and updates dictionary
        context: Tool context with database session

    Returns:
        UpdateWorkingMemoryOutput with updated memory

    Raises:
        ToolExecutionError: If update fails or cross-tenant access attempted
    """
    db = await context.get_executor()

    try:
        from app.services.agent_memory import AgentMemoryService

        updated_memory = AgentMemoryService.update_working_memory(
            session_id=input.session_id,
            tenant_id=input.tenant_id,
            updates=input.updates,
            db=db
        )

        if updated_memory is None:
            raise ToolExecutionError(
                tool_name="update_working_memory",
                message=f"Session {input.session_id} not found or cross-tenant access attempted",
                audit_id=context.audit_id,
            )

        logger.info(
            f"Updated working memory for session {input.session_id} with {len(input.updates)} keys",
            extra={"correlation_id": context.correlation_id},
        )

        return UpdateWorkingMemoryOutput(
            session_id=input.session_id,
            memory=updated_memory,
            size_bytes=len(str(updated_memory).encode('utf-8')),
            keys_added=len(input.updates),
        )
    except ToolExecutionError:
        raise
    except Exception as e:
        logger.error(
            f"Failed to update working memory: {e}",
            extra={"correlation_id": context.correlation_id},
        )
        raise ToolExecutionError(
            tool_name="update_working_memory",
            message=f"Failed to update working memory: {str(e)[:200]}",
            audit_id=context.audit_id,
        )


async def store_session_summary_handler(
    input: StoreSessionSummaryInput,
    context: ToolContext,
) -> StoreSessionSummaryOutput:
    """
    Store end-of-session memory summary for historical retrieval.

    Summaries are used to reconstruct historical context for future sessions.

    Args:
        input: Session ID, tenant ID, and summary content
        context: Tool context with database session

    Returns:
        StoreSessionSummaryOutput with summary ID and creation timestamp

    Raises:
        ToolExecutionError: If storage fails
    """
    db = await context.get_executor()

    try:
        from app.services.agent_memory import AgentMemoryService

        summary = AgentMemoryService.store_session_summary(
            session_id=input.session_id,
            tenant_id=input.tenant_id,
            content=input.content,
            db=db
        )

        logger.info(
            f"Stored session summary for session {input.session_id}",
            extra={"correlation_id": context.correlation_id},
        )

        return StoreSessionSummaryOutput(
            summary_id=summary.id,
            session_id=input.session_id,
            created_at=summary.created_at,
        )
    except Exception as e:
        logger.error(
            f"Failed to store session summary: {e}",
            extra={"correlation_id": context.correlation_id},
        )
        raise ToolExecutionError(
            tool_name="store_session_summary",
            message=f"Failed to store session summary: {str(e)[:200]}",
            audit_id=context.audit_id,
        )


async def get_historical_context_handler(
    input: GetHistoricalContextInput,
    context: ToolContext,
) -> GetHistoricalContextOutput:
    """
    Retrieve historical context via keyword search across session summaries.

    Performs case-insensitive substring matching on summary content.
    Results ordered newest first.

    Args:
        input: Tenant ID, search query, and limit
        context: Tool context with database session

    Returns:
        GetHistoricalContextOutput with matching summaries

    Raises:
        ToolExecutionError: If retrieval fails
    """
    db = await context.get_executor()

    try:
        from app.services.agent_memory import AgentMemoryService

        results = AgentMemoryService.retrieve_historical_context(
            tenant_id=input.tenant_id,
            query_text=input.query,
            db=db,
            limit=input.limit,
        )

        logger.info(
            f"Retrieved {len(results)} historical contexts for tenant {input.tenant_id} matching '{input.query}'",
            extra={"correlation_id": context.correlation_id},
        )

        summaries = [
            {
                "summary_id": r.id,
                "session_id": r.session_id,
                "content": r.content,
                "created_at": r.created_at,
            }
            for r in results
        ]

        return GetHistoricalContextOutput(
            query=input.query,
            results_count=len(summaries),
            summaries=summaries,
        )
    except Exception as e:
        logger.error(
            f"Failed to retrieve historical context: {e}",
            extra={"correlation_id": context.correlation_id},
        )
        raise ToolExecutionError(
            tool_name="get_historical_context",
            message=f"Failed to retrieve historical context: {str(e)[:200]}",
            audit_id=context.audit_id,
        )


# Tool definitions

get_working_memory_tool = Tool(
    name="get_working_memory",
    description="Retrieve session working memory (live facts, 2KB limit)",
    input_schema=GetWorkingMemoryInput,
    output_schema=GetWorkingMemoryOutput,
    risk_level=RiskLevel.READ,
    allowed_environments=[Environment.LOCAL, Environment.DEV, Environment.QA, Environment.PROD],
    requires_approval=False,
    timeout_seconds=30,
    handler=get_working_memory_handler,
    audit_metadata={"category": "memory", "executor": "agent_memory_service"},
)

update_working_memory_tool = Tool(
    name="update_working_memory",
    description="Update session working memory with new facts (auto-enforces 2KB limit)",
    input_schema=UpdateWorkingMemoryInput,
    output_schema=UpdateWorkingMemoryOutput,
    risk_level=RiskLevel.LOW_WRITE,
    allowed_environments=[Environment.LOCAL, Environment.DEV, Environment.QA, Environment.PROD],
    requires_approval=False,
    timeout_seconds=30,
    handler=update_working_memory_handler,
    audit_metadata={"category": "memory", "executor": "agent_memory_service"},
)

store_session_summary_tool = Tool(
    name="store_session_summary",
    description="Store end-of-session memory summary for historical retrieval",
    input_schema=StoreSessionSummaryInput,
    output_schema=StoreSessionSummaryOutput,
    risk_level=RiskLevel.LOW_WRITE,
    allowed_environments=[Environment.LOCAL, Environment.DEV, Environment.QA, Environment.PROD],
    requires_approval=False,
    timeout_seconds=30,
    handler=store_session_summary_handler,
    audit_metadata={"category": "memory", "executor": "agent_memory_service"},
)

get_historical_context_tool = Tool(
    name="get_historical_context",
    description="Retrieve historical context via keyword search across past sessions",
    input_schema=GetHistoricalContextInput,
    output_schema=GetHistoricalContextOutput,
    risk_level=RiskLevel.READ,
    allowed_environments=[Environment.LOCAL, Environment.DEV, Environment.QA, Environment.PROD],
    requires_approval=False,
    timeout_seconds=30,
    handler=get_historical_context_handler,
    audit_metadata={"category": "memory", "executor": "agent_memory_service"},
)


# List of all memory tools for registry
MEMORY_TOOLS = [
    get_working_memory_tool,
    update_working_memory_tool,
    store_session_summary_tool,
    get_historical_context_tool,
]
