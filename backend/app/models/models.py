"""Database models for conversation persistence and workflow analytics."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.orm import relationship
import enum

from app.db.session import Base


class Tenant(Base):
    """Tenant/organization for multi-tenancy support."""
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    users = relationship("User", back_populates="tenant")
    sessions = relationship("Session", back_populates="tenant")
    workflow_events = relationship("WorkflowEvent", back_populates="tenant")
    tool_calls = relationship("ToolCall", back_populates="tenant")
    approvals = relationship("Approval", back_populates="tenant")
    session_tool_approvals = relationship("SessionToolApproval", back_populates="tenant")
    workflow_classifications = relationship("WorkflowClassification", back_populates="tenant")
    external_credentials = relationship("ExternalCredential", back_populates="tenant")
    workflow_runs = relationship("WorkflowRun", back_populates="tenant")
    mcp_integrations = relationship("TenantMCPIntegration", back_populates="tenant")
    skills = relationship("TenantSkill", back_populates="tenant")
    workflows = relationship("TenantWorkflow", back_populates="tenant")
    session_memory_summaries = relationship("SessionMemorySummary", back_populates="tenant")
    test_runs = relationship("TestRun", back_populates="tenant")


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
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
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
    tenant = relationship("Tenant", back_populates="users")
    sessions = relationship("Session", back_populates="user")


class Session(Base):
    """Conversation sessions."""
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Compaction fields
    session_summary = Column(Text, nullable=True)
    summary_generated_at = Column(DateTime, nullable=True)
    message_count_at_summary = Column(Integer, default=0, nullable=False)

    # Agent memory
    session_working_memory = Column(JSON, nullable=True, default={})

    # Relationships
    tenant = relationship("Tenant", back_populates="sessions")
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


class SessionMemorySummary(Base):
    """Historical memory summaries for cross-session context retrieval."""
    __tablename__ = "session_memory_summaries"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="session_memory_summaries")


class WorkflowEvent(Base):
    """Workflow events for analytics and tracking."""
    __tablename__ = "workflow_events"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    event_type = Column(SQLEnum(WorkflowEventType), nullable=False, index=True)
    event_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="workflow_events")
    session = relationship("Session", back_populates="workflow_events")


class ToolCall(Base):
    """Tool execution records."""
    __tablename__ = "tool_calls"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    tool_name = Column(String(255), nullable=False, index=True)
    parameters = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="tool_calls")


class Approval(Base):
    """User approval records for sensitive operations."""
    __tablename__ = "approvals"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    request_type = Column(String(255), nullable=False)
    request_data = Column(JSON, nullable=True)
    approved = Column(Integer, nullable=True)  # NULL = pending, 1 = approved, 0 = rejected
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    responded_at = Column(DateTime, nullable=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="approvals")


class SessionToolApproval(Base):
    """
    Session-scoped tool approval cache.

    Once a user approves a tool for a session, subsequent calls
    to the same tool (with matching pattern) skip approval.
    """
    __tablename__ = "session_tool_approvals"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    tool_name = Column(String(255), nullable=False, index=True)
    # Pattern for contextual matching (e.g., {"method": "POST", "path_prefix": "/api/v3/"})
    # NULL means "any arguments" for this tool
    approval_pattern = Column(JSON, nullable=True)
    # Hash of approval_pattern for unique constraint (computed on insert)
    pattern_hash = Column(String(64), nullable=False)
    approved_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="session_tool_approvals")

    __table_args__ = (
        UniqueConstraint('session_id', 'tool_name', 'pattern_hash', name='uq_session_tool_approval'),
    )


class WorkflowClassification(Base):
    """Workflow classification and outcome tracking."""
    __tablename__ = "workflow_classifications"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
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

    # Relationships
    tenant = relationship("Tenant", back_populates="workflow_classifications")


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


class TenantMCPIntegration(Base):
    """
    Tenant-scoped MCP integration registry.

    Each tenant can onboard MCP integrations (GitHub, Jira, etc.) with their own credentials.
    The gateway layer resolves tenant-scoped tools at runtime using this registry.

    Example config schema:
    {
        "api_version": "v3",
        "base_url": "https://api.github.com",
        "timeout": 30,
        "custom_settings": {...}
    }

    Credentials are stored separately in ExternalCredential model (encrypted).
    """
    __tablename__ = "mcp_integrations"
    __table_args__ = (
        UniqueConstraint('tenant_id', 'integration_name', name='uq_tenant_integration_name'),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    integration_name = Column(String(100), nullable=False)  # "github", "jira", "slack", etc.
    auth_type = Column(String(50), nullable=False)  # "oauth", "api_key", "pat"
    config = Column(JSON, nullable=False, default={})  # Non-sensitive configuration
    is_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="mcp_integrations")


class TenantSkill(Base):
    """
    Tenant-scoped custom skills/capabilities.

    Each tenant can define their own skills that extend the agent's capabilities.
    Skills are versioned to support iterative development and rollback.

    Example skill_data structure:
    {
        "type": "workflow",
        "triggers": ["on_chat_message"],
        "steps": [
            {"action": "approve_required", "gates": ["manager_approval"]},
            {"action": "execute_tool", "tool": "github_pr_create"}
        ]
    }

    Version tracking allows multiple versions of the same skill with only one active at a time.
    """
    __tablename__ = "tenant_skills"
    __table_args__ = (
        UniqueConstraint('tenant_id', 'skill_name', 'version', name='uq_tenant_skill_name_version'),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_name = Column(String(255), nullable=False)  # e.g., "club_creation_workflow"
    description = Column(String(500), nullable=True)  # Skill documentation
    skill_data = Column(JSON, nullable=False, default={})  # Skill definition (content, config, etc)
    version = Column(Integer, nullable=False, default=1)  # Version number
    is_active = Column(Boolean, nullable=False, default=False)  # Whether this version is active
    intent_patterns = Column(JSON, nullable=True, default=list)  # Semantic matching patterns for skill invocation
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # Who created this skill

    # Relationships
    tenant = relationship("Tenant", back_populates="skills")


class TenantWorkflow(Base):
    """
    Tenant-scoped workflow definitions.

    Each tenant can define custom workflows with approval gates, tool requirements, and execution policies.
    Workflows are versioned to support iterative refinement.

    Example workflow_definition:
    {
        "name": "club_creation",
        "approval_gates": ["manager"],
        "tools_required": ["github", "jira"],
        "max_retries": 3,
        "timeout_seconds": 300
    }

    active_version tracks which version is currently in use for runtime resolution.
    """
    __tablename__ = "tenant_workflows"
    __table_args__ = (
        UniqueConstraint('tenant_id', 'workflow_name', 'version', name='uq_tenant_workflow_name_version'),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_name = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    workflow_definition = Column(JSON, nullable=False, default={})  # Workflow steps, config
    version = Column(Integer, nullable=False, default=1)  # Version number
    is_active = Column(Boolean, nullable=False, default=False)  # Whether this version is active
    active_version = Column(Integer, nullable=True)  # Pointer to active version
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # Who created this workflow

    # Relationships
    tenant = relationship("Tenant", back_populates="workflows")
