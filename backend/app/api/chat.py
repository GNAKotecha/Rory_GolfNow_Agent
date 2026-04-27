"""Chat endpoint for LLM completions."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.db.session import get_db
from app.models.models import (
    Session as SessionModel,
    Message as MessageModel,
    User,
    WorkflowClassification,
    WorkflowOutcome,
)
from app.services.ollama import OllamaClient, OllamaError
from app.api.auth_deps import get_approved_user
from app.services.workflow_classifier import classify_workflow
from app.services.workflow_analytics import log_unknown_workflow

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""
    session_id: int
    message: str
    model: Optional[str] = None


class ChatResponse(BaseModel):
    """Response from chat endpoint."""
    session_id: int
    user_message_id: int
    assistant_message_id: int
    assistant_message: str


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """
    Send a message and get an LLM response.

    Requires: Authenticated and approved user.

    Flow:
    1. Verify session exists and belongs to user
    2. Save user message to DB
    3. Get conversation history
    4. Send to Ollama
    5. Save assistant response to DB
    6. Return response
    """
    # Verify session exists and belongs to current user
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
    db.commit()
    db.refresh(user_message)

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
    db.commit()
    db.refresh(workflow_classification)

    # Log unknown workflows
    log_unknown_workflow(workflow_classification, db)

    try:
        # Get conversation history (for context)
        messages = (
            db.query(MessageModel)
            .filter(MessageModel.session_id == request.session_id)
            .order_by(MessageModel.created_at.asc())
            .all()
        )

        # Format messages for context assembly
        message_dicts = [
            {"role": msg.role, "content": msg.content}
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

        # Call Ollama with keep_alive
        ollama_client = OllamaClient()
        assistant_response = await ollama_client.generate_chat_completion(
            messages=ollama_messages,
            model=request.model,
            keep_alive="5m",  # Keep model warm
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

        # Update workflow outcome to SUCCESS
        workflow_classification.outcome = WorkflowOutcome.SUCCESS
        workflow_classification.completed_at = datetime.utcnow()

        db.commit()
        db.refresh(assistant_message)

        # Log context metadata
        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            f"Chat completed for session {request.session_id}",
            extra={
                "session_id": request.session_id,
                "user_id": current_user.id,
                **context_metadata,
            }
        )

        return ChatResponse(
            session_id=request.session_id,
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
            assistant_message=assistant_response,
        )

    except OllamaError as e:
        # Mark workflow as failed
        from datetime import datetime
        workflow_classification.outcome = WorkflowOutcome.FAILED
        workflow_classification.completed_at = datetime.utcnow()
        db.commit()

        raise HTTPException(
            status_code=503,
            detail=f"Ollama service error: {str(e)}"
        )
    except Exception as e:
        # Mark workflow as failed
        from datetime import datetime
        workflow_classification.outcome = WorkflowOutcome.FAILED
        workflow_classification.completed_at = datetime.utcnow()
        db.commit()

        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {str(e)}"
        )
