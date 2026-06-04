"""WebSocket endpoint for real-time chat with streaming updates."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
import json
import logging
import asyncio
import uuid
from typing import Dict, Any

from app.db.session import get_db
from app.models.models import User, ApprovalStatus, Session as SessionModel, Message as MessageModel, MessageRole
from app.services.auth import decode_access_token
from app.services.ollama import OllamaClient
from app.services.mcp_registry import MCPToolRegistry
from app.services.agentic_service import AgenticService, AgenticConfig
from app.services.agent_memory import AgentMemory
from app.config.mcp_config import Environment
from app.api.chat import get_mcp_registry
from app.services.tool_catalog import WorkflowType
from app.services.model_selector import AUTO_MODEL_ID, is_manual_model_request, resolve_model_selection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["websocket"])

# WebSocket configuration
WEBSOCKET_PING_INTERVAL = 30  # seconds
WEBSOCKET_PING_TIMEOUT = 10  # seconds


async def get_user_from_token(token: str, db: Session) -> User:
    """
    Get user from JWT token for WebSocket authentication.

    Args:
        token: JWT access token
        db: Database session

    Returns:
        Authenticated user

    Raises:
        ValueError: If token invalid or user not approved
    """
    payload = decode_access_token(token)

    if payload is None:
        raise ValueError("Invalid authentication token")

    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise ValueError("Invalid token payload")

    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        raise ValueError("Invalid user ID in token")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise ValueError("User not found")

    if user.approval_status != ApprovalStatus.APPROVED:
        raise ValueError("User not approved")

    return user


@router.websocket("/chat")
async def chat_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for chat with streaming agentic updates.

    SECURITY: Authentication happens once at connection time, not per-message.
    User is stored in connection state to prevent:
    - Database contention under load
    - Timing attack vectors
    - Resource waste from repeated auth checks

    Client sends initial auth message:
    {
        "type": "auth",
        "token": "jwt_token"
    }

    Then sends regular messages:
    {
        "type": "message",
        "session_id": 1,
        "message": "user message",
        "require_approval": true  // Optional: override to require approval (fail-safe)
    }

    APPROVAL POLICY (fail-safe):
    - User/org setting determines default approval requirement
    - Client can ONLY increase strictness (enable approval), never decrease
    - If user requires approval, client cannot disable it

    Server sends various event types during workflow execution.
    """
    await websocket.accept()

    # Connection state
    authenticated_user: User = None
    db: Session = None
    mcp_registry: MCPToolRegistry = None
    ollama_client: OllamaClient = None  # Reuse client for all messages

    try:
        # Get database session - ensure cleanup on exit
        from app.db.session import SessionLocal
        db = SessionLocal()

        # Get MCP registry
        mcp_registry = await get_mcp_registry()

        # Create Ollama client once for this connection (prevents resource leak)
        # NOTE: OllamaClient creates new httpx.AsyncClient per request (not ideal),
        # but reusing OllamaClient instance avoids repeated object creation.
        # Future: Make OllamaClient maintain persistent httpx.AsyncClient.
        ollama_client = OllamaClient()

        # Wait for authentication message (first message must be auth)
        auth_data = await websocket.receive_json()

        if auth_data.get("type") != "auth":
            await websocket.send_json({
                "type": "error",
                "error": "First message must be authentication"
            })
            return

        token = auth_data.get("token")
        if not token:
            await websocket.send_json({
                "type": "error",
                "error": "Missing authentication token"
            })
            return

        # Authenticate once at connection time
        try:
            authenticated_user = await get_user_from_token(token, db)
            logger.info(
                f"WebSocket authenticated",
                extra={"user_id": authenticated_user.id, "user_email": authenticated_user.email}
            )

            await websocket.send_json({
                "type": "authenticated",
                "user_id": authenticated_user.id
            })
        except ValueError as e:
            await websocket.send_json({
                "type": "error",
                "error": f"Authentication failed: {str(e)}"
            })
            return

        # Import token store and validation utilities
        from app.services.headless_events import (
            get_default_token_store,
            validate_user_response,
            UserResponse,
        )
        token_store = get_default_token_store()

        # Main message loop - user is already authenticated
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            # Validate message type
            if msg_type not in ("message", "user_response"):
                await websocket.send_json({
                    "type": "error",
                    "error": f"Invalid message type: expected 'message' or 'user_response', got '{msg_type}'"
                })
                continue

            # Refresh authenticated user from DB (prevents stale user properties)
            db.refresh(authenticated_user)

            # Get or validate session (re-queried per message to prevent staleness)
            session_id = data.get("session_id")
            if not session_id:
                await websocket.send_json({
                    "type": "error",
                    "error": "Missing session_id"
                })
                continue

            session = db.query(SessionModel).filter(
                SessionModel.id == session_id,
                SessionModel.tenant_id == authenticated_user.tenant_id,
                SessionModel.user_id == authenticated_user.id
            ).first()

            if not session:
                await websocket.send_json({
                    "type": "error",
                    "error": "Session not found"
                })
                continue

            # Refresh session to get latest state (e.g., updated summary, title)
            db.refresh(session)

            # =====================================================================
            # BRANCH: Handle user_response (HITL resume flow)
            # =====================================================================
            if msg_type == "user_response":
                # Validate the user_response payload
                validation_result = await validate_user_response(data, token_store)
                
                if not validation_result.valid:
                    # Return structured error with remediation options
                    await websocket.send_json({
                        "type": "user_response_error",
                        "error": validation_result.error,
                        "error_type": validation_result.error_type,
                        "remediation_options": [
                            opt.to_dict() for opt in (validation_result.remediation_options or [])
                        ],
                    })
                    continue
                
                # Token is valid - extract context
                token_context = validation_result.token_context
                resume_token = data.get("resume_token")
                
                # Get run_id from token context (preserve run continuity)
                run_id = token_context.get("run_id")
                
                # Check if incoming run_id matches (already validated, but log for debugging)
                request_run_id = data.get("run_id")
                if request_run_id and request_run_id != run_id:
                    logger.warning(
                        f"run_id mismatch in user_response (using token's run_id)",
                        extra={
                            "request_run_id": request_run_id,
                            "token_run_id": run_id,
                            "session_id": session_id,
                        }
                    )
                
                # Consume the token (one-time use)
                await token_store.consume(resume_token)
                
                # Parse the user response payload
                user_response = UserResponse(
                    resume_token=resume_token,
                    selected_option_id=data.get("selected_option_id"),
                    input_values=data.get("input_values", {}),
                    freeform_text=data.get("freeform_text"),
                )
                
                logger.info(
                    f"Processing user_response for resumed workflow",
                    extra={
                        "run_id": run_id,
                        "user_id": authenticated_user.id,
                        "session_id": session_id,
                        "selected_option": user_response.selected_option_id,
                        "has_input_values": bool(user_response.input_values),
                        "has_freeform": bool(user_response.freeform_text),
                    }
                )
                
                # Build the resume message for the agent
                # This is NOT persisted as a user chat message
                resume_context = token_context.get("context", {})
                original_reason = token_context.get("reason", "unknown")
                step_number = token_context.get("step_number")
                
                # Construct a synthetic continuation message for the agent
                resume_message_parts = []
                if user_response.selected_option_id:
                    resume_message_parts.append(f"User selected option: {user_response.selected_option_id}")
                if user_response.input_values:
                    resume_message_parts.append(f"User provided values: {json.dumps(user_response.input_values)}")
                if user_response.freeform_text:
                    resume_message_parts.append(f"User response: {user_response.freeform_text}")
                
                resume_message = "\n".join(resume_message_parts) or "User confirmed to continue"
                
                # Get conversation history (do NOT add a new user message)
                messages = db.query(MessageModel).filter(
                    MessageModel.session_id == session_id
                ).order_by(MessageModel.created_at).all()
                
                # Convert to Ollama format and append continuation context
                ollama_messages = [
                    {"role": msg.role.value, "content": msg.content}
                    for msg in messages
                ]
                
                # Add system context about the resumption
                ollama_messages.append({
                    "role": "system",
                    "content": f"[WORKFLOW RESUMED] User responded to {original_reason} prompt: {resume_message}"
                })
                
                # Create streaming callback with preserved run_id
                async def stream_callback(event: Dict[str, Any]):
                    """Send event to WebSocket client with run_id preservation."""
                    logger.debug(
                        f"Streaming event to client: {event.get('type')}",
                        extra={"event_type": event.get("type"), "session_id": session_id, "run_id": run_id}
                    )
                    await websocket.send_json(event)
                
                # Determine approval setting (same fail-safe logic)
                user_requires_approval = authenticated_user.require_tool_approval
                request_requires_approval = data.get("require_approval")
                if request_requires_approval is not None:
                    if user_requires_approval and not request_requires_approval:
                        final_approval_setting = True
                    else:
                        final_approval_setting = request_requires_approval
                else:
                    final_approval_setting = user_requires_approval
                
                # Parse workflow type
                workflow_type_enum = None
                workflow_type_raw = data.get("workflow_type")
                if workflow_type_raw:
                    try:
                        workflow_type_enum = WorkflowType(workflow_type_raw.lower())
                    except ValueError:
                        pass

                requested_model = data.get("model")
                allow_opus = bool(data.get("allow_opus", False))
                opus_justification = data.get("opus_justification")
                model_selection = await resolve_model_selection(
                    requested_model=requested_model,
                    messages=ollama_messages,
                    client=ollama_client,
                    allow_opus=allow_opus,
                    opus_justification=opus_justification,
                )
                resolved_model = model_selection.resolved_model

                if is_manual_model_request(requested_model) and resolved_model != requested_model:
                    await websocket.send_json({
                        "type": "error",
                        "error": model_selection.reason,
                        "run_id": run_id,
                    })
                    continue
                
                # Execute agentic workflow with PRESERVED run_id
                try:
                    agentic_service = AgenticService(
                        ollama_client=ollama_client,
                        mcp_registry=mcp_registry,
                        config=AgenticConfig(
                            max_steps=10,
                            require_approval_for_write=final_approval_setting,
                            timeout_seconds=120,
                            enable_loop_detection=True,
                            loop_window_size=3,
                            enable_planning=False,
                            verify_plan_steps=False,
                            stream_callback=stream_callback,
                            workflow_type=workflow_type_enum,
                        ),
                        run_id=run_id,  # PRESERVED run_id from token
                    )
                    
                    result = await agentic_service.execute(
                        messages=ollama_messages,
                        user=authenticated_user,
                        session_id=session_id,
                        model=resolved_model,
                    )
                    
                    logger.info(
                        f"Resumed agentic workflow completed",
                        extra={
                            "run_id": run_id,
                            "user_id": authenticated_user.id,
                            "session_id": session_id,
                            "requested_model": requested_model or AUTO_MODEL_ID,
                            "resolved_model": resolved_model,
                            "model_strategy": model_selection.strategy,
                            "model_complexity_tier": model_selection.complexity_tier,
                            "coding_request": model_selection.coding_request,
                            "allow_opus": allow_opus,
                            "total_steps": result.total_steps,
                            "stopped_reason": result.stopped_reason,
                        }
                    )
                    
                    # Save assistant response (but NOT the user_response as a chat message)
                    if result.final_response:
                        assistant_message = MessageModel(
                            session_id=session_id,
                            role=MessageRole.ASSISTANT,
                            content=result.final_response,
                        )
                        db.add(assistant_message)
                        db.commit()
                    
                    # Send final response with preserved run_id
                    await websocket.send_json({
                        "type": "final_response",
                        "message": result.final_response,
                        "total_steps": result.total_steps,
                        "stopped_reason": result.stopped_reason,
                        "run_id": run_id,  # Preserved run_id
                    })
                    
                except Exception as e:
                    try:
                        db.rollback()
                    except Exception:
                        pass
                    
                    logger.error(
                        f"Resumed workflow error",
                        extra={
                            "run_id": run_id,
                            "user_id": authenticated_user.id,
                            "session_id": session_id,
                            "error": str(e),
                        },
                        exc_info=True
                    )
                    await websocket.send_json({
                        "type": "error",
                        "error": f"Workflow error: {str(e)}",
                        "run_id": run_id,  # Preserved run_id
                    })
                
                continue  # Back to main loop
            
            # =====================================================================
            # BRANCH: Handle regular message (new request flow)
            # =====================================================================
            # Get message text (required for regular messages)
            message_text = data.get("message")
            if not message_text or not message_text.strip():
                await websocket.send_json({
                    "type": "error",
                    "error": "Empty message"
                })
                continue

            # Save user message to database
            user_message = MessageModel(
                session_id=session_id,
                role=MessageRole.USER,
                content=message_text.strip(),
            )
            db.add(user_message)
            db.commit()
            db.refresh(user_message)

            # Get conversation history
            messages = db.query(MessageModel).filter(
                MessageModel.session_id == session_id
            ).order_by(MessageModel.created_at).all()

            # Convert to Ollama format
            ollama_messages = [
                {"role": msg.role.value, "content": msg.content}
                for msg in messages
            ]

            # Load user preferences
            memory = AgentMemory(db, tenant_id=authenticated_user.tenant_id)
            preferences = memory.get_user_preferences(authenticated_user.id)

            if preferences and ollama_messages:
                # Sanitize preferences to prevent injection
                safe_prefs = {k: str(v)[:200] for k, v in preferences.items()}
                system_content = f"User preferences: {safe_prefs}\n\n"
                if ollama_messages[0].get("role") == "system":
                    ollama_messages[0]["content"] = system_content + ollama_messages[0]["content"]
                else:
                    ollama_messages.insert(0, {
                        "role": "system",
                        "content": system_content
                    })

            # Create streaming callback
            async def stream_callback(event: Dict[str, Any]):
                """Send event to WebSocket client."""
                logger.debug(
                    f"Streaming event to client: {event.get('type')}",
                    extra={"event_type": event.get("type"), "session_id": session_id}
                )
                await websocket.send_json(event)

            # Determine approval requirement (fail-safe: can only make stricter)
            user_requires_approval = authenticated_user.require_tool_approval
            request_requires_approval = data.get("require_approval")  # Optional override

            # Fail-safe logic: request can only increase strictness, never decrease
            if request_requires_approval is not None:
                if user_requires_approval and not request_requires_approval:
                    logger.warning(
                        "WebSocket: ignoring attempt to disable required approval",
                        extra={
                            "user_id": authenticated_user.id,
                            "user_setting": user_requires_approval,
                            "request_override": request_requires_approval,
                        }
                    )
                    final_approval_setting = True  # Fail-safe
                else:
                    final_approval_setting = request_requires_approval
            else:
                final_approval_setting = user_requires_approval

            # Generate NEW run ID for fresh request
            run_id = str(uuid.uuid4())

            logger.info(
                f"Starting agentic workflow",
                extra={
                    "run_id": run_id,
                    "user_id": authenticated_user.id,
                    "session_id": session_id,
                    "message_length": len(message_text),
                    "require_approval": final_approval_setting,
                }
            )

            # Parse workflow type if provided (Task D2)
            workflow_type_enum = None
            workflow_type_raw = data.get("workflow_type")
            if workflow_type_raw:
                try:
                    workflow_type_enum = WorkflowType(workflow_type_raw.lower())
                except ValueError:
                    logger.warning(
                        f"Invalid workflow_type '{workflow_type_raw}', using default GENERAL",
                        extra={"requested_workflow": workflow_type_raw, "session_id": session_id}
                    )

            requested_model = data.get("model")
            allow_opus = bool(data.get("allow_opus", False))
            opus_justification = data.get("opus_justification")
            model_selection = await resolve_model_selection(
                requested_model=requested_model,
                messages=ollama_messages,
                client=ollama_client,
                allow_opus=allow_opus,
                opus_justification=opus_justification,
            )
            resolved_model = model_selection.resolved_model

            if is_manual_model_request(requested_model) and resolved_model != requested_model:
                await websocket.send_json({
                    "type": "error",
                    "error": model_selection.reason,
                    "run_id": run_id,
                })
                continue
            
            # Execute agentic workflow with streaming
            try:
                agentic_service = AgenticService(
                    ollama_client=ollama_client,  # Reuse connection-level client
                    mcp_registry=mcp_registry,
                    config=AgenticConfig(
                        max_steps=10,
                        require_approval_for_write=final_approval_setting,
                        timeout_seconds=120,
                        enable_loop_detection=True,
                        loop_window_size=3,
                        enable_planning=False,
                        verify_plan_steps=False,
                        stream_callback=stream_callback,
                        workflow_type=workflow_type_enum,  # Task D2: Workflow-scoped exposure
                    ),
                    run_id=run_id,  # Pass run_id for workspace isolation
                )

                result = await agentic_service.execute(
                    messages=ollama_messages,
                    user=authenticated_user,
                    session_id=session_id,
                    model=resolved_model,
                )

                logger.info(
                    f"Agentic workflow completed",
                    extra={
                        "run_id": run_id,
                        "user_id": authenticated_user.id,
                        "session_id": session_id,
                        "requested_model": requested_model or AUTO_MODEL_ID,
                        "resolved_model": resolved_model,
                        "model_strategy": model_selection.strategy,
                        "model_complexity_tier": model_selection.complexity_tier,
                        "coding_request": model_selection.coding_request,
                        "allow_opus": allow_opus,
                        "total_steps": result.total_steps,
                        "stopped_reason": result.stopped_reason,
                        "response_length": len(result.final_response) if result.final_response else 0,
                    }
                )

                # Save assistant message
                assistant_message = MessageModel(
                    session_id=session_id,
                    role=MessageRole.ASSISTANT,
                    content=result.final_response,
                )
                db.add(assistant_message)
                db.commit()

                # P1 Fix: Include run_id in final_response for correlation
                # Extract run_id from result metadata if available
                result_run_id = result.metadata.get("run_id") if result.metadata else run_id

                # Send final response
                await websocket.send_json({
                    "type": "final_response",
                    "message": result.final_response,
                    "total_steps": result.total_steps,
                    "stopped_reason": result.stopped_reason,
                    "run_id": result_run_id,
                })

            except Exception as e:
                # Rollback any partial state to prevent broken transaction
                try:
                    db.rollback()
                except Exception as rollback_error:
                    logger.error(f"Failed to rollback transaction: {rollback_error}")

                logger.error(
                    f"Agentic workflow error",
                    extra={
                        "run_id": run_id,
                        "user_id": authenticated_user.id,
                        "session_id": session_id,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    exc_info=True
                )
                await websocket.send_json({
                    "type": "error",
                    "error": f"Workflow error: {str(e)}",
                    "run_id": run_id,
                })

    except WebSocketDisconnect:
        logger.info(
            "WebSocket disconnected",
            extra={"user_id": authenticated_user.id if authenticated_user else None}
        )
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "error": f"Server error: {str(e)}"
            })
        except:
            pass
    finally:
        # CRITICAL: Always cleanup resources to prevent leaks
        # Note: OllamaClient uses httpx.AsyncClient context managers internally,
        # so no explicit cleanup needed. Each request creates and closes its own client.

        # Close database session
        if db:
            try:
                db.close()
                logger.debug("WebSocket DB session closed")
            except Exception as e:
                logger.error(f"Error closing DB session: {e}")
