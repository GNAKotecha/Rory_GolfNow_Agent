"""Database models for conversation persistence and workflow analytics."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.orm import relationship
import enum

from app.db.session import Base


class UserRole(str, enum.Enum):
    """User role types."""
    ADMIN = "admin"
    USER = "user"


class ApprovalStatus(str, enum.Enum):
    """User approval status."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class MessageRole(str, enum.Enum):
    """Message role in conversation."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class WorkflowEventType(str, enum.Enum):
    """Types of workflow events."""
    TOOL_CALL = "tool_call"
    APPROVAL_REQUEST = "approval_request"
    APPROVAL_RESPONSE = "approval_response"
    ERROR = "error"
    CLASSIFICATION = "classification"


class WorkflowCategory(str, enum.Enum):
    """Workflow classification categories."""
    WORKFLOW = "workflow"  # Multi-step complex task
    QUESTION = "question"  # Simple query
    BUG_FIX = "bug_fix"  # Debugging/troubleshooting
    FEATURE = "feature"  # Building new functionality
    ANALYSIS = "analysis"  # Review/evaluation
    CREATIVE = "creative"  # Generative task
    ADMIN = "admin"  # System/config management
    UNKNOWN = "unknown"  # Uncategorized


class WorkflowOutcome(str, enum.Enum):
    """Workflow outcome status."""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    ESCALATED = "escalated"
    PENDING = "pending"


class User(Base):
    """User accounts."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.USER, nullable=False)
    approval_status = Column(SQLEnum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False)
    approved_at = Column(DateTime, nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Tool approval policy (defaults to not requiring approval unless explicitly enabled)
    require_tool_approval = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    sessions = relationship("Session", back_populates="user")


class Session(Base):
    """Conversation sessions."""
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Compaction fields
    session_summary = Column(Text, nullable=True)
    summary_generated_at = Column(DateTime, nullable=True)
    message_count_at_summary = Column(Integer, default=0, nullable=False)

    # Relationships
    user = relationship("User", back_populates="sessions")
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")
    workflow_events = relationship("WorkflowEvent", back_populates="session", cascade="all, delete-orphan")


class Message(Base):
    """Individual messages in a conversation."""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    role = Column(SQLEnum(MessageRole), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    session = relationship("Session", back_populates="messages")


class WorkflowEvent(Base):
    """Workflow events for analytics and tracking."""
    __tablename__ = "workflow_events"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    event_type = Column(SQLEnum(WorkflowEventType), nullable=False, index=True)
    event_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    session = relationship("Session", back_populates="workflow_events")


class ToolCall(Base):
    """Tool execution records."""
    __tablename__ = "tool_calls"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    tool_name = Column(String(255), nullable=False, index=True)
    parameters = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Approval(Base):
    """User approval records for sensitive operations."""
    __tablename__ = "approvals"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    request_type = Column(String(255), nullable=False)
    request_data = Column(JSON, nullable=True)
    approved = Column(Integer, nullable=True)  # NULL = pending, 1 = approved, 0 = rejected
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    responded_at = Column(DateTime, nullable=True)


class WorkflowClassification(Base):
    """Workflow classification and outcome tracking."""
    __tablename__ = "workflow_classifications"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Classification
    category = Column(SQLEnum(WorkflowCategory), nullable=False, index=True)
    subcategory = Column(String(255), nullable=True)  # Optional fine-grained category
    confidence = Column(Integer, nullable=False)  # 0-100

    # Outcome
    outcome = Column(SQLEnum(WorkflowOutcome), default=WorkflowOutcome.PENDING, nullable=False, index=True)

    # Metadata
    request_text = Column(Text, nullable=False)  # Original user request
    keywords = Column(JSON, nullable=True)  # Extracted keywords for analytics

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)


class UserPreference(Base):
    """User preferences for cross-session personalization."""
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    key = Column(String(255), nullable=False)
    value = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('user_id', 'key', name='uq_user_preferences_user_key'),
    )


class WorkflowMemory(Base):
    """Past workflow outcomes for learning patterns."""
    __tablename__ = "workflow_memory"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    workflow_type = Column(String(100), nullable=False, index=True)
    outcome = Column(String(50), nullable=False)
    context = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class DomainKnowledge(Base):
    """Domain-specific knowledge discovered during execution."""
    __tablename__ = "domain_knowledge"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    domain = Column(String(100), nullable=False, index=True)
    knowledge = Column(Text, nullable=False)
    source = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class FailedRun(Base):
    """Failed run logs for debugging and analytics."""
    __tablename__ = "failed_runs"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True, index=True)
    run_id = Column(String(255), nullable=True, index=True)
    error_type = Column(String(100), nullable=False, index=True)
    error_message = Column(Text, nullable=False)
    original_message_count = Column(Integer, nullable=False)
    context = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
