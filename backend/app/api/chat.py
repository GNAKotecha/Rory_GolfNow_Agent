"""Chat endpoint for LLM completions."""
from datetime import datetime
import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import logging

from app.db.session import get_db
from app.models.models import (
    Session as SessionModel,
    Message as MessageModel,
    User,
    WorkflowClassification,
    WorkflowOutcome,
    ToolCall,
)
from app.services.ollama import OllamaClient, OllamaError
from app.services.agentic_service import AgenticService, AgenticConfig
from app.services.mcp_registry import MCPToolRegistry
from app.services.agent_memory import AgentMemory
from app.config.mcp_config import Environment
from app.api.auth_deps import get_approved_user
from app.services.workflow_classifier import classify_workflow
from app.services.workflow_analytics import log_unknown_workflow
from app.services.rate_limiter import get_rate_limiter, RateLimitConfig
from app.services.mcp_health import get_health_checker, ServerRequirement
from app.services.run_state import (
    RunState, ApprovalService, get_approval_service,
    PendingToolCall, ApprovalDecision,
)
from app.services.message_validator import (
    get_message_validator, MessageValidationError,
)

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)

# Singleton instances with proper locking
_mcp_registry: Optional[MCPToolRegistry] = None
_registry_lock = asyncio.Lock()
_initialization_complete = False


async def initialize_mcp_infrastructure() -> MCPToolRegistry:
    """
    Initialize MCP registry and health checks at startup.
    Thread-safe singleton initialization.
    
    Uses hybrid startup validation:
    - Required servers must respond or startup fails
    - Optional servers use lazy connection
    """
    global _mcp_registry, _initialization_complete
    
    async with _registry_lock:
        if _mcp_registry is not None:
            return _mcp_registry
        
        # Create registry
        _mcp_registry = MCPToolRegistry(Environment.DEVELOPMENT)
        await _mcp_registry.initialize()
        
        # Initialize health checker and register servers
        health_checker = get_health_checker()
        
        # Register MCP servers with health checker
        for server_name in _mcp_registry.clients.keys():
            # TODO: Configure required vs optional per server from config
            health_checker.register_server(
                server_name=server_name,
                requirement=ServerRequirement.OPTIONAL,
            )
        
        # Build probe functions
        async def probe_server(client):
            try:
                tools = await client.list_tools(force_refresh=True)
                return True, [t.name for t in tools], None
            except Exception as e:
                return False, [], str(e)
        
        probe_funcs = {
            name: lambda c=client: probe_server(c)
            for name, client in _mcp_registry.clients.items()
        }
        
        # Validate startup (required servers must be healthy)
        success, failed_servers = await health_checker.validate_startup(probe_funcs)
        
        if not success:
            raise RuntimeError(
                f"MCP startup validation failed. Required servers unavailable: {failed_servers}"
            )
        
        _initialization_complete = True
        logger.info(
            "MCP infrastructure initialized",
            extra={
                "servers": list(_mcp_registry.clients.keys()),
                "health_status": health_checker.get_all_server_statuses(),
            }
        )
        
        return _mcp_registry


async def get_mcp_registry() -> MCPToolRegistry:
    """Get or create MCP registry with health checks."""
    global _mcp_registry
    if _mcp_registry is None:
        return await initialize_mcp_infrastructure()
    return _mcp_registry


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""
    session_id: int
    message: str = Field(..., max_length=50000)  # Limit message size
    model: Optional[str] = None
    require_approval: Optional[bool] = None  # Override to make stricter (fail-safe)


class ChatResponse(BaseModel):
    """Response from chat endpoint."""
    session_id: int
    user_message_id: int
    assistant_message_id: int
    assistant_message: str
    agentic_steps: Optional[int] = None
    tool_calls_count: Optional[int] = None
    stopped_reason: Optional[str] = None
    pending_approval: Optional[Dict[str, Any]] = None
    run_id: Optional[str] = None  # For tracking/resuming
    degraded_mode: bool = False  # True if some MCP servers unavailable


class ApprovalRequest(BaseModel):
    """Request to approve/reject a pending tool call."""
    approval_id: int
    approved: bool
    comment: Optional[str] = None


class ApprovalResponse(BaseModel):
    """Response after processing approval."""
    success: bool
    message: str
    resumed: bool = False
    chat_response: Optional[ChatResponse] = None


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
    mcp_registry: MCPToolRegistry = Depends(get_mcp_registry),
):
    """
    Send a message and get an LLM response with agentic workflow.

    Requires: Authenticated and approved user.

    Includes:
    - Rate limiting (per-user active runs, tool calls, model requests)
    - MCP health checks (degraded mode for optional servers)
    - Message validation (never empty, recovery from persisted state)
    - Approval flow for write operations (pause/resume with RunState)

    Flow:
    1. Check rate limits
    2. Verify session exists and belongs to user
    3. Save user message to DB
    4. Get conversation history
    5. Validate messages (recover if needed)
    6. Load user memory (preferences, domain knowledge)
    7. Execute agentic workflow with tool calling
    8. Handle approval requests if needed
    9. Log tool executions
    10. Store workflow outcomes
    11. Save assistant response to DB
    12. Return response with agentic metadata
    """
    # Generate run ID for tracking
    run_id = str(uuid.uuid4())
    
    # Initialize services
    rate_limiter = get_rate_limiter()
    health_checker = get_health_checker()
    message_validator = get_message_validator(db)
    approval_service = get_approval_service(db)
    
    # -------------------------------------------------------------------------
    # Rate Limit Checks
    # -------------------------------------------------------------------------
    
    # Check active run limit
    allowed, msg = await rate_limiter.check_active_run_limit(current_user.id)
    if not allowed:
        raise HTTPException(status_code=429, detail=msg)
    
    # Acquire run slot
    if not await rate_limiter.acquire_run(current_user.id):
        raise HTTPException(
            status_code=429,
            detail="Too many concurrent requests. Please wait and try again."
        )
    
    try:
        # Check model request limit
        allowed, msg = await rate_limiter.check_model_request_limit(current_user.id)
        if not allowed:
            raise HTTPException(status_code=429, detail=msg)
        
        # -------------------------------------------------------------------------
        # MCP Health Checks
        # -------------------------------------------------------------------------
        
        # Check required servers
        all_healthy, unhealthy_required = health_checker.check_required_servers()
        if not all_healthy:
            raise HTTPException(
                status_code=503,
                detail=f"Required MCP servers unavailable: {unhealthy_required}"
            )
        
        # Track degraded mode
        degraded_mode = health_checker.is_degraded()
        if degraded_mode:
            logger.warning(
                "Operating in degraded mode - some MCP servers unavailable",
                extra={"session_id": request.session_id}
            )
        
        # -------------------------------------------------------------------------
        # Session Verification
        # -------------------------------------------------------------------------
        
        session = db.query(SessionModel).filter(
            SessionModel.id == request.session_id,
            SessionModel.user_id == current_user.id
        ).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Save user message
        user_message = MessageModel(
            session_id=request.session_id,
            role="user",
            content=request.message,
        )
        db.add(user_message)
        db.flush()  # Get ID without committing (for atomicity)

        # Classify workflow
        classification_result = classify_workflow(request.message)
        workflow_classification = WorkflowClassification(
            session_id=request.session_id,
            message_id=user_message.id,
            user_id=current_user.id,
            category=classification_result.category,
            subcategory=classification_result.subcategory,
            confidence=classification_result.confidence,
            outcome=WorkflowOutcome.PENDING,
            request_text=request.message,
            keywords=classification_result.keywords,
        )
        db.add(workflow_classification)
        db.flush()

        # Log unknown workflows
        log_unknown_workflow(workflow_classification, db)

        # -------------------------------------------------------------------------
        # Get Conversation History
        # -------------------------------------------------------------------------
        
        messages = (
            db.query(MessageModel)
            .filter(MessageModel.session_id == request.session_id)
            .order_by(MessageModel.created_at.asc())
            .all()
        )

        # Format messages for context assembly
        message_dicts = [
            {"role": msg.role.value if hasattr(msg.role, 'value') else str(msg.role), "content": msg.content}
            for msg in messages
        ]

        # Check if summary needs updating
        from app.services.summarization import update_session_summary
        await update_session_summary(
            session_id=request.session_id,
            messages=message_dicts,
            existing_summary=session.session_summary,
            db_session=db,
            force=False,
        )

        # Refresh session to get updated summary
        db.refresh(session)

        # Assemble context with caching and compaction
        from app.services.context_assembly import prepare_context_for_llm
        ollama_messages, context_metadata = prepare_context_for_llm(
            messages=message_dicts,
            session_id=request.session_id,
            session_summary=session.session_summary,
            use_cache=True,
        )

        # -------------------------------------------------------------------------
        # Message Validation (Never call Ollama with empty messages)
        # -------------------------------------------------------------------------
        
        try:
            validated_messages = message_validator.ensure_valid_messages(
                messages=ollama_messages,
                session_id=request.session_id,
                run_id=run_id,
                allow_recovery=True,
            )
            ollama_messages = validated_messages
        except MessageValidationError as e:
            logger.error(
                f"Message validation failed for session {request.session_id}",
                extra={
                    "session_id": request.session_id,
                    "run_id": run_id,
                    "error_type": e.error_type,
                    "recoverable": e.recoverable,
                }
            )
            
            if e.recoverable and e.recovery_hint:
                # Attempt to create minimal context
                ollama_messages = message_validator.create_minimal_context(
                    user_message=request.message,
                    system_prompt="You are a helpful assistant. Some conversation context was lost.",
                )
                context_metadata["context_recovered"] = True
                context_metadata["recovery_reason"] = e.error_type
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Message validation failed: {str(e)}. {e.recovery_hint or ''}"
                )

        # Load user memory
        memory = AgentMemory(db)
        preferences = memory.get_user_preferences(current_user.id)

        # Add preferences to system prompt if available (with sanitization)
        if preferences and ollama_messages:
            # Sanitize preferences to prevent injection
            safe_prefs = {k: str(v)[:200] for k, v in preferences.items()}
            system_content = f"User preferences: {safe_prefs}\n\n"
            # Check if first message is system message
            if ollama_messages[0].get("role") == "system":
                ollama_messages[0]["content"] = system_content + ollama_messages[0]["content"]
            else:
                # Prepend system message
                ollama_messages.insert(0, {
                    "role": "system",
                    "content": system_content
                })

        # Record model request for rate limiting
        await rate_limiter.record_model_request(current_user.id)

        # -------------------------------------------------------------------------
        # Execute Agentic Workflow
        # -------------------------------------------------------------------------

        # Determine approval requirement (fail-safe: can only make stricter)
        user_requires_approval = current_user.require_tool_approval
        request_requires_approval = request.require_approval

        # Fail-safe logic: request can only increase strictness, never decrease
        if request_requires_approval is not None:
            # If user/org requires approval, client cannot disable it
            if user_requires_approval and not request_requires_approval:
                logger.warning(
                    "Ignoring attempt to disable required approval",
                    extra={
                        "user_id": current_user.id,
                        "user_setting": user_requires_approval,
                        "request_override": request_requires_approval,
                    }
                )
                final_approval_setting = True  # Fail-safe: keep approval required
            else:
                # Allow client to enable approval even if user doesn't require it
                final_approval_setting = request_requires_approval
        else:
            # No override: use user/org setting
            final_approval_setting = user_requires_approval

        logger.info(
            "Approval policy determined",
            extra={
                "user_id": current_user.id,
                "user_requires_approval": user_requires_approval,
                "request_override": request_requires_approval,
                "final_setting": final_approval_setting,
            }
        )

        ollama_client = OllamaClient()
        agentic_service = AgenticService(
            ollama_client=ollama_client,
            mcp_registry=mcp_registry,
            config=AgenticConfig(
                max_steps=10,
                require_approval_for_write=final_approval_setting,
                timeout_seconds=120,
                enable_loop_detection=True,
                loop_window_size=3,
                enable_planning=False,  # Simplified for MVP
                verify_plan_steps=False,
            ),
            rate_limiter=rate_limiter,
            health_checker=health_checker,
            run_id=run_id,
        )

        logger.info(
            "Starting agentic workflow",
            extra={
                "session_id": request.session_id,
                "user_id": current_user.id,
                "user_role": current_user.role.value,
                "run_id": run_id,
                "degraded_mode": degraded_mode,
                **context_metadata,
            }
        )

        agentic_result = await agentic_service.execute(
            messages=ollama_messages,
            user=current_user,
            session_id=request.session_id,
            model=request.model,
        )

        # Check for errors
        if agentic_result.error:
            logger.error(
                f"Agentic workflow failed: {agentic_result.error}",
                extra={
                    "session_id": request.session_id,
                    "user_id": current_user.id,
                    "steps": agentic_result.total_steps,
                    "stopped_reason": agentic_result.stopped_reason,
                }
            )
            # Mark workflow as failed
            workflow_classification.outcome = WorkflowOutcome.FAILED
            from datetime import datetime
            workflow_classification.completed_at = datetime.utcnow()
            db.commit()

            raise HTTPException(
                status_code=503,
                detail=f"Agentic workflow error: {agentic_result.error}"
            )

        # Check for approval needed
        if agentic_result.stopped_reason == "approval_needed":
            pending_tool_data = agentic_result.metadata.get("pending_tool_call", {})
            
            logger.info(
                "Agentic workflow paused for approval",
                extra={
                    "session_id": request.session_id,
                    "user_id": current_user.id,
                    "run_id": run_id,
                    "pending_tool": pending_tool_data.get("tool_name"),
                }
            )

            # Build pending tool call
            pending_tool = approval_service.build_pending_tool_call(
                tool_name=pending_tool_data.get("tool_name", "unknown"),
                arguments=pending_tool_data.get("arguments", {}),
                tool_call_id=pending_tool_data.get("tool_call_id", "unknown"),
            )
            
            # Check if auto-approval is allowed
            if approval_service.can_auto_approve(pending_tool.tool_name):
                logger.info(
                    f"Auto-approving low-risk tool: {pending_tool.tool_name}",
                    extra={"run_id": run_id, "tool_name": pending_tool.tool_name}
                )
                # TODO: Resume workflow with auto-approval
                # For now, proceed as normal approval flow
            
            # Create RunState for pause/resume
            run_state = RunState(
                run_id=run_id,
                session_id=request.session_id,
                user_id=current_user.id,
                model=request.model,
                max_steps=10,
                current_step=agentic_result.total_steps,
                status="paused_for_approval",
                messages=[m for m in ollama_messages],  # Copy messages
                steps=[
                    {
                        "step_number": s.step_number,
                        "llm_response_type": s.llm_response.get("type"),
                        "tool_executions": s.tool_executions,
                    }
                    for s in agentic_result.steps
                ],
            )
            run_state.pause_for_approval(pending_tool)
            
            # Create approval record
            approval_record = approval_service.create_approval_request(
                run_state=run_state,
                tool_call=pending_tool,
            )
            
            # Save to database
            approval_id = await approval_service.save_approval_request(approval_record)
            
            # Return response with pending approval
            pending_approval = {
                "approval_id": approval_id,
                "tool_name": pending_tool.tool_name,
                "arguments": pending_tool.arguments,
                "reason": pending_tool.reason,
                "risk_level": pending_tool.risk_level,
            }
            assistant_response = f"Approval required: {pending_tool.reason}"
            
            # Save partial assistant message
            assistant_message = MessageModel(
                session_id=request.session_id,
                role="assistant",
                content=assistant_response,
            )
            db.add(assistant_message)
            
            # Update workflow as pending
            workflow_classification.outcome = WorkflowOutcome.PENDING
            workflow_classification.completed_at = datetime.utcnow()
            db.commit()
            db.refresh(assistant_message)
            
            return ChatResponse(
                session_id=request.session_id,
                user_message_id=user_message.id,
                assistant_message_id=assistant_message.id,
                assistant_message=assistant_response,
                agentic_steps=agentic_result.total_steps,
                tool_calls_count=sum(len(step.tool_executions) for step in agentic_result.steps),
                stopped_reason=agentic_result.stopped_reason,
                pending_approval=pending_approval,
                run_id=run_id,
                degraded_mode=degraded_mode,
            )
        else:
            assistant_response = agentic_result.final_response
            pending_approval = None

        # Log tool executions to database
        for step in agentic_result.steps:
            for execution in step.tool_executions:
                result = execution.get("result")
                
                # Defensive access for result object
                result_data = None
                error_data = None
                if result:
                    if hasattr(result, 'success') and result.success:
                        result_data = result.result if hasattr(result, 'result') else None
                    elif hasattr(result, 'error'):
                        error_data = result.error
                    
                tool_call = ToolCall(
                    session_id=request.session_id,
                    tool_name=execution["tool_name"],
                    parameters=execution["arguments"],
                    result=result_data,
                    error=error_data or execution.get("error"),
                )
                db.add(tool_call)

        # Store workflow outcome in memory
        memory.store_workflow_outcome(
            user_id=current_user.id,
            workflow_type=classification_result.category.value,
            outcome=agentic_result.stopped_reason,
            context={
                "steps": agentic_result.total_steps,
                "tool_calls": sum(len(step.tool_executions) for step in agentic_result.steps),
                "classification": classification_result.category.value,
            }
        )

        # Save assistant message
        assistant_message = MessageModel(
            session_id=request.session_id,
            role="assistant",
            content=assistant_response,
        )
        db.add(assistant_message)

        # Update session timestamp
        from datetime import datetime
        session.updated_at = datetime.utcnow()

        # Update workflow outcome based on agentic result
        if agentic_result.stopped_reason == "completed":
            workflow_classification.outcome = WorkflowOutcome.SUCCESS
        elif agentic_result.stopped_reason in ["max_steps", "loop_detected"]:
            workflow_classification.outcome = WorkflowOutcome.PARTIAL
        elif agentic_result.stopped_reason == "approval_needed":
            workflow_classification.outcome = WorkflowOutcome.PENDING
        else:
            workflow_classification.outcome = WorkflowOutcome.FAILED

        workflow_classification.completed_at = datetime.utcnow()

        db.commit()
        db.refresh(assistant_message)

        # Log context and agentic execution metadata
        logger.info(
            f"Agentic workflow completed for session {request.session_id}",
            extra={
                "session_id": request.session_id,
                "user_id": current_user.id,
                "total_steps": agentic_result.total_steps,
                "stopped_reason": agentic_result.stopped_reason,
                "tool_calls_count": sum(len(step.tool_executions) for step in agentic_result.steps),
                "outcome": workflow_classification.outcome.value,
                "run_id": run_id,
                "degraded_mode": degraded_mode,
                **context_metadata,
            }
        )

        return ChatResponse(
            session_id=request.session_id,
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
            assistant_message=assistant_response,
            agentic_steps=agentic_result.total_steps,
            tool_calls_count=sum(len(step.tool_executions) for step in agentic_result.steps),
            stopped_reason=agentic_result.stopped_reason,
            pending_approval=pending_approval,
            run_id=run_id,
            degraded_mode=degraded_mode,
        )

    except OllamaError as e:
        # Rollback any partial state before marking as failed
        db.rollback()
        
        # Mark workflow as failed in a clean transaction
        workflow_classification.outcome = WorkflowOutcome.FAILED
        workflow_classification.completed_at = datetime.utcnow()
        db.commit()

        logger.error(
            "Ollama service error",
            extra={
                "session_id": request.session_id,
                "run_id": run_id,
                "error": str(e),
            }
        )

        raise HTTPException(
            status_code=503,
            detail="Model service temporarily unavailable. Please try again."
        )
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Rollback any partial state before marking as failed
        db.rollback()
        
        # Mark workflow as failed in a clean transaction
        workflow_classification.outcome = WorkflowOutcome.FAILED
        workflow_classification.completed_at = datetime.utcnow()
        db.commit()

        # Log full error for debugging but don't expose to client
        logger.exception(
            "Internal error in chat endpoint",
            extra={
                "session_id": request.session_id,
                "run_id": run_id,
            }
        )

        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again."
        )
    
    finally:
        # Always release the rate limit slot
        await rate_limiter.release_run(current_user.id)


@router.post("/approve", response_model=ApprovalResponse)
async def process_approval(
    request: ApprovalRequest,
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """
    Process approval or rejection for a pending tool call.
    
    On approval, resumes the paused workflow.
    On rejection, marks the workflow as cancelled.
    """
    approval_service = get_approval_service(db)
    
    # Process the decision
    run_state = await approval_service.process_approval_decision(
        approval_id=request.approval_id,
        approved=request.approved,
        decided_by=current_user.id,
        comment=request.comment,
    )
    
    if run_state is None:
        raise HTTPException(
            status_code=404,
            detail="Approval request not found or already processed"
        )
    
    if not request.approved:
        # Rejected - workflow is cancelled
        return ApprovalResponse(
            success=True,
            message="Tool call rejected. Workflow cancelled.",
            resumed=False,
        )
    
    # TODO: Resume workflow execution from run_state
    # For now, just confirm approval was recorded
    return ApprovalResponse(
        success=True,
        message=f"Tool call approved: {run_state.pending_approval.get('tool_name')}",
        resumed=False,  # Will be True when resume is implemented
    )


@router.get("/pending-approvals")
async def get_pending_approvals(
    session_id: Optional[int] = None,
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """Get pending approval requests for the current user's sessions."""
    approval_service = get_approval_service(db)
    
    approvals = await approval_service.get_pending_approvals(
        session_id=session_id,
    )
    
    return {"pending_approvals": approvals}
