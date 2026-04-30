"""Database models for workflow metrics and LLM decision tracking."""
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.db.session import Base


class StepMetrics(Base):
    """Tracks execution metrics for individual workflow steps."""

    __tablename__ = "step_metrics"

    id = Column(Integer, primary_key=True, index=True)
    workflow_run_id = Column(
        Integer,
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_execution_id = Column(
        Integer,
        ForeignKey("workflow_step_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_name = Column(String(255), nullable=False, index=True)

    # Timing
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Status
    status = Column(
        String(50),
        nullable=False,
        default="running",
        index=True,
    )

    # Resource usage
    tokens_used = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)

    # Metadata
    error_message = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    workflow_run = relationship("WorkflowRun", back_populates="step_metrics")
    step_execution = relationship("WorkflowStepExecution", back_populates="metrics")


class LLMDecisionMetrics(Base):
    """Tracks LLM decision points and outcomes for learning/optimization."""

    __tablename__ = "llm_decision_metrics"

    id = Column(Integer, primary_key=True, index=True)
    workflow_run_id = Column(
        Integer,
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_execution_id = Column(
        Integer,
        ForeignKey("workflow_step_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_name = Column(String(255), nullable=False, index=True)

    # Decision tracking
    decision_point = Column(String(255), nullable=False, index=True)
    prompt_template_id = Column(String(100), nullable=True, index=True)
    prompt_hash = Column(String(64), nullable=True, index=True)
    model_used = Column(String(100), nullable=False)
    response_raw = Column(Text, nullable=True)
    decision_parsed = Column(Text, nullable=True)
    tokens_used = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    temperature = Column(Float, nullable=True)
    llm_reasoning = Column(Text, nullable=True)

    # Outcome tracking
    human_feedback = Column(
        String(50),
        nullable=True,
        index=True,
    )  # "correct", "incorrect", "partially_correct"
    outcome_quality = Column(Float, nullable=True)  # 0.0 to 1.0 score

    # Metadata
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    workflow_run = relationship("WorkflowRun", back_populates="llm_decision_metrics")
    step_execution = relationship("WorkflowStepExecution", back_populates="llm_decisions")
