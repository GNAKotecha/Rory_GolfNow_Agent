"""API endpoints for session and message management."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import Session as SessionModel, Message as MessageModel, User as UserModel
from app.api.schemas import (
    SessionCreate,
    SessionResponse,
    SessionWithMessages,
    MessageCreate,
    MessageResponse,
)
from app.api.auth_deps import get_approved_user

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse)
def create_session(
    session_data: SessionCreate,
    current_user: UserModel = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """Create a new conversation session for the authenticated user."""
    session = SessionModel(
        user_id=current_user.id,
        title=session_data.title,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/{session_id}", response_model=SessionWithMessages)
def get_session(
    session_id: int,
    current_user: UserModel = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """Get session with all messages (must belong to current user)."""
    session = db.query(SessionModel).filter(
        SessionModel.id == session_id,
        SessionModel.user_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("", response_model=List[SessionResponse])
def list_sessions(
    current_user: UserModel = Depends(get_approved_user),
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """List authenticated user's sessions."""
    sessions = (
        db.query(SessionModel)
        .filter(SessionModel.user_id == current_user.id)
        .order_by(SessionModel.updated_at.desc())
        .limit(limit)
        .all()
    )
    return sessions


@router.post("/{session_id}/messages", response_model=MessageResponse)
def add_message(
    session_id: int,
    message_data: MessageCreate,
    current_user: UserModel = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """Add a message to a session (must belong to current user)."""
    # Verify session exists and belongs to current user
    session = db.query(SessionModel).filter(
        SessionModel.id == session_id,
        SessionModel.user_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    message = MessageModel(
        session_id=session_id,
        role=message_data.role,
        content=message_data.content,
    )
    db.add(message)

    # Update session timestamp
    from datetime import datetime
    session.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(message)
    return message


@router.get("/{session_id}/messages", response_model=List[MessageResponse])
def get_messages(
    session_id: int,
    current_user: UserModel = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """Get all messages for a session (must belong to current user)."""
    session = db.query(SessionModel).filter(
        SessionModel.id == session_id,
        SessionModel.user_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = (
        db.query(MessageModel)
        .filter(MessageModel.session_id == session_id)
        .order_by(MessageModel.created_at.asc())
        .all()
    )
    return messages
