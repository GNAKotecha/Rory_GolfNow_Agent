"""Ollama-compatible API endpoints for Open WebUI integration."""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session as DBSession
from typing import List, Dict, Any, Optional
import json
from datetime import datetime

from app.db.session import SessionLocal
from app.models.models import Session as SessionModel, Message as MessageModel, User as UserModel
from app.services.ollama import OllamaClient, OllamaError

router = APIRouter(prefix="/ollama", tags=["ollama-compat"])


def get_or_create_session_for_user(db: DBSession, user_id: int = 1) -> SessionModel:
    """
    Get the most recent session for a user, or create a new one.
    For MVP, we use a simple strategy: reuse the most recent session.
    """
    session = (
        db.query(SessionModel)
        .filter(SessionModel.user_id == user_id)
        .order_by(SessionModel.updated_at.desc())
        .first()
    )

    if not session:
        # Create user if doesn't exist
        user = db.query(UserModel).filter(UserModel.id == user_id).first()
        if not user:
            user = UserModel(
                id=user_id,
                email="default@example.com",
                name="Default User",
                role="user"
            )
            db.add(user)
            db.commit()

        # Create new session
        session = SessionModel(
            user_id=user_id,
            title="Open WebUI Chat"
        )
        db.add(session)
        db.commit()
        db.refresh(session)

    return session


@router.post("/api/chat")
async def ollama_chat_endpoint(request: Request):
    """
    Ollama-compatible chat endpoint for Open WebUI.

    Open WebUI sends requests in Ollama's format:
    {
      "model": "qwen2.5-coder:32b",
      "messages": [
        {"role": "user", "content": "Hello"}
      ],
      "stream": false
    }

    This endpoint:
    1. Extracts the latest user message
    2. Saves it to our database
    3. Calls Ollama via our client
    4. Saves the response
    5. Returns in Ollama's format
    """
    try:
        body = await request.json()
        model = body.get("model", "qwen2.5-coder:32b")
        messages = body.get("messages", [])
        stream = body.get("stream", False)

        if not messages:
            raise HTTPException(status_code=400, detail="No messages provided")

        # Get the latest user message
        latest_message = messages[-1]
        user_content = latest_message.get("content", "")

        if not user_content:
            raise HTTPException(status_code=400, detail="Empty message")

        # Get or create session
        db = SessionLocal()
        try:
            session = get_or_create_session_for_user(db)

            # Save user message
            user_message = MessageModel(
                session_id=session.id,
                role="user",
                content=user_content,
            )
            db.add(user_message)
            db.commit()
            db.refresh(user_message)

            # Get full conversation history for context
            all_messages = (
                db.query(MessageModel)
                .filter(MessageModel.session_id == session.id)
                .order_by(MessageModel.created_at.asc())
                .all()
            )

            # Format for Ollama
            ollama_messages = [
                {"role": msg.role, "content": msg.content}
                for msg in all_messages
            ]

            # Call Ollama
            ollama_client = OllamaClient()
            assistant_response = await ollama_client.generate_chat_completion(
                messages=ollama_messages,
                model=model,
                stream=False
            )

            # Save assistant message
            assistant_message = MessageModel(
                session_id=session.id,
                role="assistant",
                content=assistant_response,
            )
            db.add(assistant_message)

            # Update session timestamp
            session.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(assistant_message)

            # Return in Ollama's format
            return JSONResponse({
                "model": model,
                "created_at": datetime.utcnow().isoformat(),
                "message": {
                    "role": "assistant",
                    "content": assistant_response
                },
                "done": True
            })

        except OllamaError as e:
            db.rollback()
            raise HTTPException(status_code=503, detail=str(e))
        finally:
            db.close()

    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get("/api/tags")
async def ollama_tags_endpoint():
    """
    Ollama-compatible tags endpoint.
    Proxies directly to Ollama to get full model details.
    """
    try:
        import httpx
        from app.core.config import settings

        # Proxy directly to Ollama for full model details
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{settings.ollama_url}/api/tags")
            response.raise_for_status()
            return response.json()

    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to list models: {str(e)}")


@router.get("/api/version")
async def ollama_version_endpoint():
    """Ollama-compatible version endpoint."""
    return {"version": "0.1.0-backend-proxy"}
