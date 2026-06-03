"""Database models for E2E test run results persistence."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship

from app.db.session import Base


class TestRun(Base):
    """
    Overall test run metadata and summary statistics.

    Tracks when a test run executed, its environment, pass/fail counts,
    and total execution duration.
    """
    __tablename__ = "test_runs"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(36), unique=True, nullable=False, index=True)  # UUID format
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    environment = Column(String(50), nullable=False, index=True)  # dev, staging, prod

    # Test statistics
    total_scenarios = Column(Integer, nullable=False, default=0)
    passed = Column(Integer, nullable=False, default=0)
    failed = Column(Integer, nullable=False, default=0)

    # Execution metrics
    duration_seconds = Column(Float, nullable=False)

    # Filtering/categorization
    tags = Column(JSON, nullable=True, default=[])  # e.g., ["core", "jira", "infrastructure"]

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="test_runs")
    scenario_results = relationship(
        "TestScenarioResult",
        back_populates="test_run",
        cascade="all, delete-orphan"
    )


class TestScenarioResult(Base):
    """
    Per-scenario test result details.

    Captures whether a specific scenario passed or failed, including
    the number of turns, tool calls, and detailed turn results.
    """
    __tablename__ = "test_scenario_results"

    id = Column(Integer, primary_key=True, index=True)
    test_run_id = Column(Integer, ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    scenario_name = Column(String(255), nullable=False, index=True)

    # Result status
    success = Column(Boolean, nullable=False, index=True)

    # Execution details
    turn_count = Column(Integer, nullable=False, default=0)
    tool_calls_count = Column(Integer, nullable=False, default=0)

    # Error information (if failed)
    error_message = Column(String(1000), nullable=True)

    # Detailed turn-by-turn results (array of turn result objects)
    turn_results = Column(JSON, nullable=True, default=[])

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    test_run = relationship("TestRun", back_populates="scenario_results")
