"""Admin endpoints for user management."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from datetime import datetime

from app.db.session import get_db
from app.models.models import User, ApprovalStatus
from app.api.auth_deps import get_admin_user

router = APIRouter(prefix="/admin", tags=["admin"])


class UserListItem(BaseModel):
    id: int
    email: str
    name: str
    role: str
    approval_status: str
    created_at: datetime
    approved_at: datetime | None

    class Config:
        from_attributes = True


class ApproveUserRequest(BaseModel):
    approve: bool  # True to approve, False to reject


@router.get("/users", response_model=List[UserListItem])
def list_users(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """
    List all users (admin only).
    """
    users = db.query(User).order_by(User.created_at.desc()).all()
    return users


@router.post("/users/{user_id}/approve", response_model=UserListItem)
def approve_user(
    user_id: int,
    request: ApproveUserRequest,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """
    Approve or reject a user (admin only).
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if request.approve:
        user.approval_status = ApprovalStatus.APPROVED
        user.approved_at = datetime.utcnow()
        user.approved_by = admin_user.id
    else:
        user.approval_status = ApprovalStatus.REJECTED

    db.commit()
    db.refresh(user)

    return user
