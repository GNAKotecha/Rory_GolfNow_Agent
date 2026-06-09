"""Pydantic schemas for API request/response validation."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr


# User schemas
class UserBase(BaseModel):
    email: EmailStr
    name: str


class UserCreate(UserBase):
    pass


class UserResponse(UserBase):
    id: int
    role: str
    approval_status: str
    created_at: datetime
    # Phase 6: RBAC authentication fields
    auth_source: Optional[str] = None
    external_id: Optional[str] = None
    sso_claims: Optional[dict] = None
    club_context: Optional[dict] = None
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True


# Session schemas
class SessionCreate(BaseModel):
    title: Optional[str] = None


class SessionResponse(BaseModel):
    id: int
    user_id: int
    title: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Message schemas
class MessageCreate(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class MessageResponse(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


# Session with messages
class SessionWithMessages(SessionResponse):
    messages: List[MessageResponse] = []

    class Config:
        from_attributes = True
