"""Workflow execution tracking models for LangGraph integration."""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.orm import relationship
import enum

from app.db.session import Base
from app.models.models import WorkflowCategory


class WorkflowRunStatus(str, enum.Enum):
    """Status of workflow execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, enum.Enum):
    """Status of individual workflow step."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowTemplate(Base):
    """Workflow template definition."""
    __tablename__ = "workflow_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    version = Column(String(50), nullable=False)
    workflow_category = Column(SQLEnum(WorkflowCategory), nullable=False)
    definition = Column(JSON, nullable=False)  # LangGraph workflow definition
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    workflow_runs = relationship("WorkflowRun", back_populates="template", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('name', name='uq_workflow_template_name'),
    )


class WorkflowRun(Base):
    """Individual workflow execution instance."""
    __tablename__ = "workflow_runs"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("workflow_templates.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    status = Column(SQLEnum(WorkflowRunStatus), default=WorkflowRunStatus.PENDING, nullable=False, index=True)

    # Execution tracking
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)

    # State management
    current_state = Column(JSON, nullable=True)  # LangGraph state snapshot
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    template = relationship("WorkflowTemplate", back_populates="workflow_runs")
    session = relationship("Session")
    step_executions = relationship("WorkflowStepExecution", back_populates="workflow_run", cascade="all, delete-orphan")
    step_metrics = relationship("StepMetrics", back_populates="workflow_run", cascade="all, delete-orphan")
    llm_decision_metrics = relationship("LLMDecisionMetrics", back_populates="workflow_run", cascade="all, delete-orphan")


class WorkflowStepExecution(Base):
    """Individual step execution within a workflow run."""
    __tablename__ = "workflow_step_executions"

    id = Column(Integer, primary_key=True, index=True)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=False, index=True)
    step_id = Column(String(255), nullable=False)  # Identifier from workflow definition
    step_name = Column(String(500), nullable=False)
    step_type = Column(String(100), nullable=False)  # e.g., "tool_call", "llm_call", "decision"
    status = Column(SQLEnum(StepStatus), default=StepStatus.PENDING, nullable=False, index=True)

    # Execution data
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)

    # Timing
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    workflow_run = relationship("WorkflowRun", back_populates="step_executions")
    metrics = relationship("StepMetrics", back_populates="step_execution", cascade="all, delete-orphan")
    llm_decisions = relationship("LLMDecisionMetrics", back_populates="step_execution", cascade="all, delete-orphan")
