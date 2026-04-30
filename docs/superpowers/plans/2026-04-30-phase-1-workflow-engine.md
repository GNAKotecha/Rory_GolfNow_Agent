# Phase 1: Workflow Engine + Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build workflow orchestration engine with LangGraph, add workflow models with state persistence, and implement comprehensive metrics collection for data-driven optimization.

**Architecture:** LangGraph StateGraph for workflow execution with PostgresCheckpointer for state persistence (reuses existing database). WorkflowOrchestrator service converts JSON templates to executable graphs. MetricsCollector instruments every step execution for performance analysis and prompt optimization.

**Tech Stack:** LangGraph 0.2+, langgraph-checkpoint-postgres, SQLAlchemy, PostgreSQL, pytest

---

## Task Completion Status

**Progress**: 6 of 11 tasks complete (55%)

- [x] **Task 1**: Add LangGraph Dependencies ✅ (Commit: 6c99f0b)
- [x] **Task 2**: Create Workflow Database Models ✅ (Commits: 317b0be, e9f072f)
- [x] **Task 3**: Create Metrics Database Models ✅ (Commits: 573a274, b741e83, be49bf2)
- [x] **Task 4**: Create Database Migration ✅ (Commits: 540aacc, 2905b9e)
- [x] **Task 5**: Create MetricsCollector Service ✅ (Commits: d7839f2, a92af91, 5e95801)
- [x] **Task 6**: Create WorkflowOrchestrator Service (Part 1) ✅ (Commits: 5ad48dc, 3139559)
- [ ] **Task 7**: Implement LangGraph Integration - **NEXT**
- [ ] **Task 8**: Add Workflow Execution with Metrics
- [ ] **Task 9**: Add API Schemas
- [ ] **Task 10**: Integration Test - End-to-End Workflow
- [ ] **Task 11**: Documentation

**See HANDOVER.md for critical context and session handover information.**

---

## File Structure

### New Files
- `backend/app/models/workflow.py` - WorkflowTemplate, WorkflowRun, WorkflowStepExecution models
- `backend/app/models/metrics.py` - StepMetrics, LLMDecisionMetrics models
- `backend/app/services/workflow_orchestrator.py` - LangGraph integration service
- `backend/app/services/metrics_collector.py` - Metrics collection service
- `backend/app/schemas/workflow.py` - Pydantic schemas for API
- `backend/alembic/versions/001_add_workflow_models.py` - Database migration

### Test Files
- `backend/tests/unit/models/test_workflow_models.py`
- `backend/tests/unit/models/test_metrics_models.py`
- `backend/tests/unit/services/test_workflow_orchestrator.py`
- `backend/tests/unit/services/test_metrics_collector.py`
- `backend/tests/fixtures/workflow_fixtures.py`

### Modified Files
- `backend/requirements.txt` - Add LangGraph dependencies
- `backend/app/models/__init__.py` - Export new models

---

## Task 1: Add LangGraph Dependencies

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add LangGraph packages to requirements**

```txt
# Add to requirements.txt after existing dependencies

# Workflow orchestration
langgraph==0.2.16
langgraph-checkpoint-postgres==2.0.2
```

- [ ] **Step 2: Install dependencies**

Run:
```bash
cd backend
pip install -r requirements.txt
```

Expected: Packages install successfully

- [ ] **Step 3: Verify imports work**

Run:
```bash
python -c "from langgraph.graph import StateGraph; from langgraph.checkpoint.postgres import PostgresCheckpointer; print('✓ LangGraph imports successful')"
```

Expected: `✓ LangGraph imports successful`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "build: add langgraph dependencies for workflow orchestration"
```

---

## Task 2: Create Workflow Database Models

**Files:**
- Create: `backend/app/models/workflow.py`
- Create: `backend/tests/unit/models/test_workflow_models.py`

- [ ] **Step 1: Write test for WorkflowTemplate model**

Create `backend/tests/unit/models/test_workflow_models.py`:

```python
import pytest
from datetime import datetime
from app.models.workflow import (
    WorkflowTemplate,
    WorkflowRun,
    WorkflowStepExecution,
    WorkflowRunStatus,
    StepStatus
)
from app.models.models import WorkflowCategory


def test_workflow_template_creation(db_session):
    """Test creating a workflow template."""
    template = WorkflowTemplate(
        name="test_onboarding",
        description="Test onboarding workflow",
        version="1.0.0",
        workflow_category=WorkflowCategory.WORKFLOW,
        definition={
            "steps": [
                {
                    "id": "step1",
                    "name": "Initialize",
                    "type": "tool_call",
                    "config": {"tool": "init_db"}
                }
            ],
            "entry_point": "step1"
        }
    )
    
    db_session.add(template)
    db_session.commit()
    
    assert template.id is not None
    assert template.name == "test_onboarding"
    assert template.workflow_category == WorkflowCategory.WORKFLOW
    assert "steps" in template.definition


def test_workflow_template_unique_name(db_session):
    """Test workflow template name uniqueness constraint."""
    template1 = WorkflowTemplate(
        name="duplicate_name",
        version="1.0.0",
        workflow_category=WorkflowCategory.WORKFLOW,
        definition={"steps": []}
    )
    db_session.add(template1)
    db_session.commit()
    
    template2 = WorkflowTemplate(
        name="duplicate_name",
        version="2.0.0",
        workflow_category=WorkflowCategory.WORKFLOW,
        definition={"steps": []}
    )
    db_session.add(template2)
    
    with pytest.raises(Exception):  # IntegrityError
        db_session.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd backend
pytest tests/unit/models/test_workflow_models.py::test_workflow_template_creation -v
```

Expected: FAIL with "No module named 'backend.app.models.workflow'"

- [ ] **Step 3: Create WorkflowTemplate model**

Create `backend/app/models/workflow.py`:

```python
import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from app.db.session import Base


class WorkflowRunStatus(str, enum.Enum):
    """Workflow run execution status."""
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, enum.Enum):
    """Individual step execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING_APPROVAL = "waiting_approval"


class WorkflowTemplate(Base):
    """
    Reusable workflow definitions.
    
    Each template defines a workflow as a JSON graph of steps,
    dependencies, and configuration.
    """
    __tablename__ = "workflow_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    version = Column(String(50), nullable=False)
    
    # Link to workflow classification
    workflow_category = Column(
        SQLEnum("WORKFLOW", "QUESTION", "BUG_FIX", "FEATURE", "ANALYSIS", "CREATIVE", "ADMIN", "UNKNOWN", name="workflowcategory"),
        nullable=False,
        index=True
    )
    
    # Workflow definition as JSON
    # Structure: {steps: [{id, name, type, config, dependencies}], entry_point: str}
    definition = Column(JSON, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    runs = relationship("WorkflowRun", back_populates="template")


class WorkflowRun(Base):
    """
    Active workflow execution instance.
    
    Tracks a single execution of a workflow template with specific input data.
    """
    __tablename__ = "workflow_runs"
    
    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("workflow_templates.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    
    # Current execution state
    status = Column(SQLEnum(WorkflowRunStatus), default=WorkflowRunStatus.PENDING, nullable=False, index=True)
    current_step_index = Column(Integer, default=0, nullable=False)
    
    # Denormalized category for analytics queries
    workflow_category = Column(
        SQLEnum("WORKFLOW", "QUESTION", "BUG_FIX", "FEATURE", "ANALYSIS", "CREATIVE", "ADMIN", "UNKNOWN", name="workflowcategory"),
        nullable=False,
        index=True
    )
    
    # Input data (e.g., activation form responses)
    input_data = Column(JSON, nullable=False)
    
    # Execution state (which steps completed, results, etc.)
    # Structure: {steps: {step_id: {status, result, started_at, completed_at}}}
    state = Column(JSON, nullable=False, default=dict)
    
    # Output artifacts (e.g., generated configs, club IDs)
    output_data = Column(JSON, nullable=True)
    
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    template = relationship("WorkflowTemplate", back_populates="runs")
    session = relationship("Session")
    steps = relationship("WorkflowStepExecution", back_populates="workflow_run", cascade="all, delete-orphan")


class WorkflowStepExecution(Base):
    """
    Individual step execution within a workflow run.
    
    Tracks execution details, inputs, outputs, and timing for each step.
    """
    __tablename__ = "workflow_step_executions"
    
    id = Column(Integer, primary_key=True, index=True)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=False, index=True)
    
    step_id = Column(String(255), nullable=False, index=True)
    step_name = Column(String(500), nullable=False)
    step_type = Column(String(100), nullable=False)  # "tool_call", "approval_gate", "condition", etc.
    
    status = Column(SQLEnum(StepStatus), default=StepStatus.PENDING, nullable=False, index=True)
    
    # Step inputs/outputs
    inputs = Column(JSON, nullable=True)
    outputs = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    
    # Tool execution details (if step_type == "tool_call")
    tool_name = Column(String(255), nullable=True)
    tool_call_id = Column(Integer, ForeignKey("tool_calls.id"), nullable=True)
    
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    workflow_run = relationship("WorkflowRun", back_populates="steps")
```

- [ ] **Step 4: Export models from __init__.py**

Modify `backend/app/models/__init__.py`:

```python
# Add to existing imports
from app.models.workflow import (
    WorkflowTemplate,
    WorkflowRun,
    WorkflowStepExecution,
    WorkflowRunStatus,
    StepStatus
)
```

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
cd backend
pytest tests/unit/models/test_workflow_models.py::test_workflow_template_creation -v
```

Expected: PASS

- [ ] **Step 6: Run uniqueness constraint test**

Run:
```bash
pytest tests/unit/models/test_workflow_models.py::test_workflow_template_unique_name -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/workflow.py backend/app/models/__init__.py backend/tests/unit/models/test_workflow_models.py
git commit -m "feat: add workflow database models (WorkflowTemplate, WorkflowRun, WorkflowStepExecution)"
```

---

## Task 3: Create Metrics Database Models

**Note on Metrics Architecture**: This task creates custom metrics tables (StepMetrics, LLMDecisionMetrics) for granular step-level analytics and workflow optimization queries. These complement Langfuse (recommended in tool-recommendations.md), which will be integrated in Phase 3 for LLM call tracing, prompt management, and evaluation. Custom metrics provide immediate queryable data for workflow success rates and failure analysis, while Langfuse handles observability of LLM decisions and prompt optimization.

**Files:**
- Create: `backend/app/models/metrics.py`
- Create: `backend/tests/unit/models/test_metrics_models.py`

- [ ] **Step 1: Write test for StepMetrics model**

Create `backend/tests/unit/models/test_metrics_models.py`:

```python
import pytest
from datetime import datetime, timedelta
from app.models.metrics import StepMetrics, LLMDecisionMetrics
from app.models.workflow import (
    WorkflowTemplate,
    WorkflowRun,
    WorkflowStepExecution,
    WorkflowRunStatus,
    StepStatus
)
from app.models.models import WorkflowCategory


def test_step_metrics_creation(db_session, workflow_run_fixture):
    """Test creating step execution metrics."""
    step_exec = WorkflowStepExecution(
        workflow_run_id=workflow_run_fixture.id,
        step_id="test_step",
        step_name="Test Step",
        step_type="tool_call",
        status=StepStatus.COMPLETED
    )
    db_session.add(step_exec)
    db_session.commit()
    
    metrics = StepMetrics(
        workflow_run_id=workflow_run_fixture.id,
        step_execution_id=step_exec.id,
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow() + timedelta(seconds=5),
        duration_ms=5000,
        attempt_number=1,
        success=True,
        tokens_used=150,
        tool_latency_ms=200
    )
    
    db_session.add(metrics)
    db_session.commit()
    
    assert metrics.id is not None
    assert metrics.duration_ms == 5000
    assert metrics.success is True
    assert metrics.tokens_used == 150


def test_step_metrics_calculate_duration(db_session, workflow_run_fixture):
    """Test automatic duration calculation."""
    step_exec = WorkflowStepExecution(
        workflow_run_id=workflow_run_fixture.id,
        step_id="test_step",
        step_name="Test Step",
        step_type="tool_call",
        status=StepStatus.COMPLETED
    )
    db_session.add(step_exec)
    db_session.commit()
    
    start_time = datetime.utcnow()
    end_time = start_time + timedelta(seconds=3.5)
    
    metrics = StepMetrics(
        workflow_run_id=workflow_run_fixture.id,
        step_execution_id=step_exec.id,
        started_at=start_time,
        completed_at=end_time,
        attempt_number=1,
        success=True
    )
    
    # Calculate duration
    metrics.duration_ms = int((metrics.completed_at - metrics.started_at).total_seconds() * 1000)
    
    db_session.add(metrics)
    db_session.commit()
    
    assert metrics.duration_ms == 3500
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd backend
pytest tests/unit/models/test_metrics_models.py::test_step_metrics_creation -v
```

Expected: FAIL with "No module named 'backend.app.models.metrics'"

- [ ] **Step 3: Create StepMetrics and LLMDecisionMetrics models**

Create `backend/app/models/metrics.py`:

```python
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Float
)
from sqlalchemy.orm import relationship
from app.db.session import Base


class StepMetrics(Base):
    """
    Granular metrics per workflow step execution.
    
    Tracks performance, resource usage, and outcomes for each step.
    Used for workflow optimization and failure analysis.
    """
    __tablename__ = "step_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=False, index=True)
    step_execution_id = Column(Integer, ForeignKey("workflow_step_executions.id"), nullable=False, index=True)
    
    # Performance metrics
    started_at = Column(DateTime, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    
    # Execution metrics
    attempt_number = Column(Integer, default=1, nullable=False)
    success = Column(Boolean, nullable=False, index=True)
    error_type = Column(String(255), nullable=True, index=True)
    error_message = Column(Text, nullable=True)
    
    # Resource metrics
    tokens_used = Column(Integer, nullable=True)  # If LLM step
    tool_latency_ms = Column(Integer, nullable=True)  # If tool call
    
    # Context
    input_hash = Column(String(64), nullable=True, index=True)  # Hash of inputs for deduplication
    output_hash = Column(String(64), nullable=True, index=True)
    
    # Relationships
    workflow_run = relationship("WorkflowRun")
    step_execution = relationship("WorkflowStepExecution")


class LLMDecisionMetrics(Base):
    """
    Track LLM decisions and their outcomes.
    
    Used for prompt optimization, A/B testing, and reinforcement learning.
    """
    __tablename__ = "llm_decision_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=False, index=True)
    step_execution_id = Column(Integer, ForeignKey("workflow_step_executions.id"), nullable=False, index=True)
    
    # Decision context
    decision_point = Column(String(255), nullable=False, index=True)  # e.g., "generate_club_config"
    prompt_template_id = Column(String(255), nullable=False, index=True)  # e.g., "config_gen_v1"
    prompt_hash = Column(String(64), nullable=False, index=True)  # Hash of actual prompt text
    
    # LLM execution
    model_used = Column(String(100), nullable=False, index=True)  # e.g., "qwen2.5:32b"
    response_raw = Column(Text, nullable=False)
    decision_parsed = Column(Text, nullable=True)  # JSON string of parsed decision
    
    tokens_used = Column(Integer, nullable=False)
    latency_ms = Column(Integer, nullable=False)
    temperature = Column(Float, nullable=False)
    
    # Outcome tracking (for reinforcement)
    decision_correct = Column(Boolean, nullable=True, index=True)  # Filled by human feedback
    correction_needed = Column(Boolean, default=False, nullable=False)
    correction_data = Column(Text, nullable=True)  # JSON string of what should have been generated
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Relationships
    workflow_run = relationship("WorkflowRun")
    step_execution = relationship("WorkflowStepExecution")
```

- [ ] **Step 4: Export metrics models**

Modify `backend/app/models/__init__.py`:

```python
# Add to existing imports
from app.models.metrics import (
    StepMetrics,
    LLMDecisionMetrics
)
```

- [ ] **Step 5: Create test fixture for workflow_run**

Create `backend/tests/fixtures/workflow_fixtures.py`:

```python
import pytest
from app.models.workflow import WorkflowTemplate, WorkflowRun, WorkflowRunStatus
from app.models.models import WorkflowCategory, Session, User


@pytest.fixture
def workflow_template_fixture(db_session):
    """Create a test workflow template."""
    template = WorkflowTemplate(
        name="test_template",
        version="1.0.0",
        workflow_category=WorkflowCategory.WORKFLOW,
        definition={
            "steps": [{"id": "step1", "name": "Test Step", "type": "tool_call"}],
            "entry_point": "step1"
        }
    )
    db_session.add(template)
    db_session.commit()
    return template


@pytest.fixture
def workflow_run_fixture(db_session, workflow_template_fixture):
    """Create a test workflow run."""
    # Create user and session
    user = User(email="test@example.com", name="Test User", password_hash="hashed_password")
    db_session.add(user)
    db_session.commit()
    
    session = Session(user_id=user.id)
    db_session.add(session)
    db_session.commit()
    
    # Create workflow run
    run = WorkflowRun(
        template_id=workflow_template_fixture.id,
        session_id=session.id,
        status=WorkflowRunStatus.RUNNING,
        workflow_category=WorkflowCategory.WORKFLOW,
        input_data={"test": "data"},
        state={}
    )
    db_session.add(run)
    db_session.commit()
    return run
```

- [ ] **Step 6: Update conftest to load fixtures**

Modify `backend/tests/conftest.py`:

```python
# Add to existing imports
pytest_plugins = [
    "tests.fixtures.workflow_fixtures",
]
```

- [ ] **Step 7: Run tests to verify they pass**

Run:
```bash
cd backend
pytest tests/unit/models/test_metrics_models.py -v
```

Expected: PASS (both tests)

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/metrics.py backend/app/models/__init__.py backend/tests/unit/models/test_metrics_models.py backend/tests/fixtures/workflow_fixtures.py backend/tests/conftest.py
git commit -m "feat: add metrics database models (StepMetrics, LLMDecisionMetrics)"
```

---

## Task 4: Create Database Migration

**Files:**
- Create: `backend/alembic/versions/001_add_workflow_models.py`

- [ ] **Step 1: Generate Alembic migration**

Run:
```bash
cd backend
alembic revision --autogenerate -m "add workflow and metrics models"
```

Expected: Migration file created in `alembic/versions/`

- [ ] **Step 2: Review migration file**

Open the generated migration file and verify it includes:
- `workflow_templates` table with all columns
- `workflow_runs` table with FKs to workflow_templates and sessions
- `workflow_step_executions` table with FK to workflow_runs
- `step_metrics` table with FKs
- `llm_decision_metrics` table with FKs
- All indexes on FK columns and frequently queried columns

- [ ] **Step 3: Apply migration to test database**

Run:
```bash
cd backend
alembic upgrade head
```

Expected: Migration applies successfully

- [ ] **Step 4: Verify tables created**

Run:
```bash
psql $DATABASE_URL -c "\dt" | grep workflow
```

Expected: See workflow_templates, workflow_runs, workflow_step_executions, step_metrics, llm_decision_metrics

- [ ] **Step 5: Run full test suite to verify database schema**

Run:
```bash
cd backend
pytest tests/unit/models/ -v
```

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/
git commit -m "db: add migration for workflow and metrics models"
```

---

## Task 5: Create MetricsCollector Service

**Files:**
- Create: `backend/app/services/metrics_collector.py`
- Create: `backend/tests/unit/services/test_metrics_collector.py`

- [ ] **Step 1: Write test for recording step metrics**

Create `backend/tests/unit/services/test_metrics_collector.py`:

```python
import pytest
from datetime import datetime
from app.services.metrics_collector import MetricsCollector
from app.models.metrics import StepMetrics, LLMDecisionMetrics
from app.models.workflow import WorkflowStepExecution, StepStatus


def test_record_step_start(db_session, workflow_run_fixture):
    """Test recording step execution start."""
    collector = MetricsCollector(db_session)
    
    step_exec = WorkflowStepExecution(
        workflow_run_id=workflow_run_fixture.id,
        step_id="test_step",
        step_name="Test Step",
        step_type="tool_call",
        status=StepStatus.RUNNING
    )
    db_session.add(step_exec)
    db_session.commit()
    
    metrics = collector.record_step_start(
        workflow_run_id=workflow_run_fixture.id,
        step_execution_id=step_exec.id
    )
    
    assert metrics.id is not None
    assert metrics.started_at is not None
    assert metrics.completed_at is None
    assert metrics.success is False  # Not completed yet


def test_record_step_completion_success(db_session, workflow_run_fixture):
    """Test recording successful step completion."""
    collector = MetricsCollector(db_session)
    
    step_exec = WorkflowStepExecution(
        workflow_run_id=workflow_run_fixture.id,
        step_id="test_step",
        step_name="Test Step",
        step_type="tool_call",
        status=StepStatus.RUNNING
    )
    db_session.add(step_exec)
    db_session.commit()
    
    # Start step
    metrics = collector.record_step_start(
        workflow_run_id=workflow_run_fixture.id,
        step_execution_id=step_exec.id
    )
    metrics_id = metrics.id
    
    # Complete step
    collector.record_step_completion(
        metrics_id=metrics_id,
        success=True,
        output_data={"result": "success"}
    )
    
    # Verify
    updated_metrics = db_session.query(StepMetrics).get(metrics_id)
    assert updated_metrics.success is True
    assert updated_metrics.completed_at is not None
    assert updated_metrics.duration_ms > 0
    assert updated_metrics.error_type is None


def test_record_step_completion_failure(db_session, workflow_run_fixture):
    """Test recording failed step completion."""
    collector = MetricsCollector(db_session)
    
    step_exec = WorkflowStepExecution(
        workflow_run_id=workflow_run_fixture.id,
        step_id="test_step",
        step_name="Test Step",
        step_type="tool_call",
        status=StepStatus.RUNNING
    )
    db_session.add(step_exec)
    db_session.commit()
    
    metrics = collector.record_step_start(
        workflow_run_id=workflow_run_fixture.id,
        step_execution_id=step_exec.id
    )
    metrics_id = metrics.id
    
    # Complete with error
    collector.record_step_completion(
        metrics_id=metrics_id,
        success=False,
        error_type="ValueError",
        error_message="Invalid input"
    )
    
    # Verify
    updated_metrics = db_session.query(StepMetrics).get(metrics_id)
    assert updated_metrics.success is False
    assert updated_metrics.error_type == "ValueError"
    assert updated_metrics.error_message == "Invalid input"


def test_record_llm_decision(db_session, workflow_run_fixture):
    """Test recording LLM decision metrics."""
    collector = MetricsCollector(db_session)
    
    step_exec = WorkflowStepExecution(
        workflow_run_id=workflow_run_fixture.id,
        step_id="generate_config",
        step_name="Generate Config",
        step_type="llm_call",
        status=StepStatus.COMPLETED
    )
    db_session.add(step_exec)
    db_session.commit()
    
    decision_metrics = collector.record_llm_decision(
        workflow_run_id=workflow_run_fixture.id,
        step_execution_id=step_exec.id,
        decision_point="generate_club_config",
        prompt_template_id="config_gen_v1",
        prompt_text="Generate config for club...",
        model_used="qwen2.5:32b",
        response="Generated config: {...}",
        decision_parsed='{"club_name": "Test Club"}',
        tokens_used=200,
        latency_ms=1500,
        temperature=0.7
    )
    
    assert decision_metrics.id is not None
    assert decision_metrics.decision_point == "generate_club_config"
    assert decision_metrics.prompt_template_id == "config_gen_v1"
    assert decision_metrics.tokens_used == 200
    assert decision_metrics.decision_correct is None  # Not yet evaluated
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd backend
pytest tests/unit/services/test_metrics_collector.py::test_record_step_start -v
```

Expected: FAIL with "No module named 'backend.app.services.metrics_collector'"

- [ ] **Step 3: Create MetricsCollector service**

Create `backend/app/services/metrics_collector.py`:

```python
import hashlib
import json
from datetime import datetime
from typing import Optional, Any, Dict
from sqlalchemy.orm import Session
from app.models.metrics import StepMetrics, LLMDecisionMetrics


class MetricsCollector:
    """
    Collect and persist workflow execution metrics.
    
    Tracks step-level performance, resource usage, and LLM decisions
    for data-driven optimization.
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def record_step_start(
        self,
        workflow_run_id: int,
        step_execution_id: int,
        attempt_number: int = 1
    ) -> StepMetrics:
        """Record the start of a step execution."""
        metrics = StepMetrics(
            workflow_run_id=workflow_run_id,
            step_execution_id=step_execution_id,
            started_at=datetime.utcnow(),
            attempt_number=attempt_number,
            success=False  # Will be updated on completion
        )
        self.db.add(metrics)
        self.db.commit()
        self.db.refresh(metrics)
        return metrics
    
    def record_step_completion(
        self,
        metrics_id: int,
        success: bool,
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
        output_data: Optional[Any] = None,
        tokens_used: Optional[int] = None,
        tool_latency_ms: Optional[int] = None
    ) -> StepMetrics:
        """Record step execution completion."""
        metrics = self.db.query(StepMetrics).get(metrics_id)
        
        metrics.completed_at = datetime.utcnow()
        metrics.duration_ms = int(
            (metrics.completed_at - metrics.started_at).total_seconds() * 1000
        )
        metrics.success = success
        metrics.error_type = error_type
        metrics.error_message = error_message
        metrics.tokens_used = tokens_used
        metrics.tool_latency_ms = tool_latency_ms
        
        if output_data:
            metrics.output_hash = hashlib.sha256(
                json.dumps(output_data, sort_keys=True).encode()
            ).hexdigest()
        
        self.db.commit()
        self.db.refresh(metrics)
        return metrics
    
    def record_llm_decision(
        self,
        workflow_run_id: int,
        step_execution_id: int,
        decision_point: str,
        prompt_template_id: str,
        prompt_text: str,
        model_used: str,
        response: str,
        decision_parsed: str,
        tokens_used: int,
        latency_ms: int,
        temperature: float
    ) -> LLMDecisionMetrics:
        """Record LLM decision for later analysis and optimization."""
        prompt_hash = hashlib.sha256(prompt_text.encode()).hexdigest()
        
        decision_metrics = LLMDecisionMetrics(
            workflow_run_id=workflow_run_id,
            step_execution_id=step_execution_id,
            decision_point=decision_point,
            prompt_template_id=prompt_template_id,
            prompt_hash=prompt_hash,
            model_used=model_used,
            response_raw=response,
            decision_parsed=decision_parsed,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
            temperature=temperature,
            created_at=datetime.utcnow()
        )
        
        self.db.add(decision_metrics)
        self.db.commit()
        self.db.refresh(decision_metrics)
        return decision_metrics
    
    def get_workflow_success_rate(
        self, 
        template_name: str, 
        days: int = 30
    ) -> float:
        """Calculate workflow success rate over time period."""
        # TODO: Implement in Phase 3
        pass
    
    def get_step_failure_analysis(
        self, 
        template_name: str, 
        step_id: str
    ) -> Dict:
        """Analyze why a specific step fails."""
        # TODO: Implement in Phase 3
        pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd backend
pytest tests/unit/services/test_metrics_collector.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/metrics_collector.py backend/tests/unit/services/test_metrics_collector.py
git commit -m "feat: add MetricsCollector service for workflow instrumentation"
```

---

## Task 6: Create WorkflowOrchestrator Service (Part 1: Basic Structure)

**Files:**
- Create: `backend/app/services/workflow_orchestrator.py`
- Create: `backend/tests/unit/services/test_workflow_orchestrator.py`

- [ ] **Step 1: Write test for loading workflow template**

Create `backend/tests/unit/services/test_workflow_orchestrator.py`:

```python
import pytest
from app.services.workflow_orchestrator import WorkflowOrchestrator
from app.models.workflow import WorkflowTemplate, WorkflowRun, WorkflowRunStatus
from app.models.models import WorkflowCategory


def test_load_workflow_template(db_session, workflow_template_fixture):
    """Test loading workflow template by name."""
    orchestrator = WorkflowOrchestrator(db_session)
    
    template = orchestrator.load_template("test_template")
    
    assert template is not None
    assert template.name == "test_template"
    assert template.workflow_category == WorkflowCategory.WORKFLOW


def test_load_nonexistent_template(db_session):
    """Test loading non-existent template raises error."""
    orchestrator = WorkflowOrchestrator(db_session)
    
    with pytest.raises(ValueError, match="Template not found"):
        orchestrator.load_template("nonexistent")


def test_create_workflow_run(db_session, workflow_template_fixture):
    """Test creating a new workflow run."""
    orchestrator = WorkflowOrchestrator(db_session)
    
    # Create user and session for test
    from app.models.models import User, Session as DBSession
    user = User(email="test@example.com", name="Test User", password_hash="hashed_password")
    db_session.add(user)
    db_session.commit()
    
    session = DBSession(user_id=user.id)
    db_session.add(session)
    db_session.commit()
    
    # Create workflow run
    workflow_run = orchestrator.create_workflow_run(
        template_name="test_template",
        session_id=session.id,
        input_data={"club_name": "Test Club"}
    )
    
    assert workflow_run.id is not None
    assert workflow_run.template_id == workflow_template_fixture.id
    assert workflow_run.session_id == session.id
    assert workflow_run.status == WorkflowRunStatus.PENDING
    assert workflow_run.input_data == {"club_name": "Test Club"}
    assert workflow_run.workflow_category == WorkflowCategory.WORKFLOW
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd backend
pytest tests/unit/services/test_workflow_orchestrator.py::test_load_workflow_template -v
```

Expected: FAIL with "No module named 'backend.app.services.workflow_orchestrator'"

- [ ] **Step 3: Create WorkflowOrchestrator service skeleton**

Create `backend/app/services/workflow_orchestrator.py`:

```python
import os
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresCheckpointer

from app.models.workflow import (
    WorkflowTemplate,
    WorkflowRun,
    WorkflowStepExecution,
    WorkflowRunStatus,
    StepStatus
)
from app.services.metrics_collector import MetricsCollector


class WorkflowState(dict):
    """
    Workflow state for LangGraph.
    
    LangGraph passes this dict between nodes. Each node can read/write to it.
    """
    pass


class WorkflowOrchestrator:
    """
    Orchestrate workflow execution using LangGraph.
    
    Converts workflow templates (JSON) to executable LangGraph StateGraphs,
    manages execution, and collects metrics.
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.metrics = MetricsCollector(db)
        
        # Initialize PostgreSQL checkpointer for state persistence
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            self.checkpointer = PostgresCheckpointer.from_conn_string(database_url)
        else:
            self.checkpointer = None
    
    def load_template(self, template_name: str) -> WorkflowTemplate:
        """Load workflow template by name."""
        template = self.db.query(WorkflowTemplate).filter_by(
            name=template_name
        ).first()
        
        if not template:
            raise ValueError(f"Template not found: {template_name}")
        
        return template
    
    def create_workflow_run(
        self,
        template_name: str,
        session_id: int,
        input_data: Dict[str, Any]
    ) -> WorkflowRun:
        """Create a new workflow run instance."""
        template = self.load_template(template_name)
        
        workflow_run = WorkflowRun(
            template_id=template.id,
            session_id=session_id,
            status=WorkflowRunStatus.PENDING,
            workflow_category=template.workflow_category,
            input_data=input_data,
            state={}
        )
        
        self.db.add(workflow_run)
        self.db.commit()
        self.db.refresh(workflow_run)
        
        return workflow_run
    
    def build_graph_from_template(self, template: WorkflowTemplate) -> StateGraph:
        """
        Convert workflow template JSON to LangGraph StateGraph.
        
        TODO: Implement in next task.
        """
        pass
    
    async def execute_workflow(
        self,
        workflow_run_id: int
    ) -> WorkflowState:
        """
        Execute a workflow run.
        
        TODO: Implement in next task.
        """
        pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd backend
pytest tests/unit/services/test_workflow_orchestrator.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/workflow_orchestrator.py backend/tests/unit/services/test_workflow_orchestrator.py
git commit -m "feat: add WorkflowOrchestrator service skeleton with template loading"
```

---

## Task 7: Implement LangGraph Integration

**Files:**
- Modify: `backend/app/services/workflow_orchestrator.py`
- Modify: `backend/tests/unit/services/test_workflow_orchestrator.py`

- [ ] **Step 1: Write test for building graph from template**

Add to `backend/tests/unit/services/test_workflow_orchestrator.py`:

```python
def test_build_graph_from_simple_template(db_session):
    """Test building LangGraph from simple linear workflow."""
    template = WorkflowTemplate(
        name="simple_workflow",
        version="1.0.0",
        workflow_category=WorkflowCategory.WORKFLOW,
        definition={
            "entry_point": "step1",
            "steps": [
                {
                    "id": "step1",
                    "name": "First Step",
                    "type": "tool_call",
                    "config": {"tool": "test_tool"},
                    "next": ["step2"]
                },
                {
                    "id": "step2",
                    "name": "Second Step",
                    "type": "tool_call",
                    "config": {"tool": "test_tool2"},
                    "next": []
                }
            ]
        }
    )
    db_session.add(template)
    db_session.commit()
    
    orchestrator = WorkflowOrchestrator(db_session)
    graph = orchestrator.build_graph_from_template(template)
    
    # Verify graph is compiled
    assert graph is not None
    assert hasattr(graph, 'invoke')


def test_build_graph_with_dependencies(db_session):
    """Test building graph with step dependencies."""
    template = WorkflowTemplate(
        name="dependency_workflow",
        version="1.0.0",
        workflow_category=WorkflowCategory.WORKFLOW,
        definition={
            "entry_point": "step1",
            "steps": [
                {
                    "id": "step1",
                    "name": "Init",
                    "type": "tool_call",
                    "config": {},
                    "dependencies": [],
                    "next": ["step2", "step3"]
                },
                {
                    "id": "step2",
                    "name": "Branch A",
                    "type": "tool_call",
                    "config": {},
                    "dependencies": ["step1"],
                    "next": []
                },
                {
                    "id": "step3",
                    "name": "Branch B",
                    "type": "tool_call",
                    "config": {},
                    "dependencies": ["step1"],
                    "next": []
                }
            ]
        }
    )
    db_session.add(template)
    db_session.commit()
    
    orchestrator = WorkflowOrchestrator(db_session)
    graph = orchestrator.build_graph_from_template(template)
    
    assert graph is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd backend
pytest tests/unit/services/test_workflow_orchestrator.py::test_build_graph_from_simple_template -v
```

Expected: FAIL (build_graph_from_template returns None)

- [ ] **Step 3: Implement build_graph_from_template**

Modify `backend/app/services/workflow_orchestrator.py`:

```python
# Add to imports
from typing import Callable

# Replace build_graph_from_template method
def build_graph_from_template(self, template: WorkflowTemplate) -> StateGraph:
    """
    Convert workflow template JSON to LangGraph StateGraph.
    
    Creates nodes for each step and wires edges based on dependencies.
    """
    graph = StateGraph(WorkflowState)
    definition = template.definition
    
    # Add node for each step
    for step in definition["steps"]:
        node_func = self._create_step_node(step, template.id)
        graph.add_node(step["id"], node_func)
    
    # Set entry point
    entry_point = definition.get("entry_point", definition["steps"][0]["id"])
    graph.set_entry_point(entry_point)
    
    # Add edges based on dependencies and next steps
    for step in definition["steps"]:
        next_steps = step.get("next", [])
        
        if not next_steps:
            # Terminal node
            graph.add_edge(step["id"], END)
        elif len(next_steps) == 1:
            # Single next step
            graph.add_edge(step["id"], next_steps[0])
        else:
            # Multiple next steps (fan-out)
            for next_step in next_steps:
                graph.add_edge(step["id"], next_step)
    
    # Compile graph with checkpointer
    return graph.compile(checkpointer=self.checkpointer)

def _create_step_node(self, step: Dict[str, Any], template_id: int) -> Callable:
    """
    Create a LangGraph node function for a workflow step.
    
    The node function executes the step and updates state.
    """
    def node_func(state: WorkflowState) -> WorkflowState:
        """Execute workflow step."""
        # For Phase 1, just mark step as completed
        # Real tool execution will be added in Phase 2
        
        state[f"{step['id']}_status"] = "completed"
        state[f"{step['id']}_output"] = {"mock": "result"}
        
        return state
    
    return node_func
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd backend
pytest tests/unit/services/test_workflow_orchestrator.py::test_build_graph_from_simple_template -v
pytest tests/unit/services/test_workflow_orchestrator.py::test_build_graph_with_dependencies -v
```

Expected: Both tests PASS

- [ ] **Step 5: Test graph execution**

Add test to `backend/tests/unit/services/test_workflow_orchestrator.py`:

```python
def test_execute_simple_graph(db_session):
    """Test executing a simple workflow graph."""
    template = WorkflowTemplate(
        name="executable_workflow",
        version="1.0.0",
        workflow_category=WorkflowCategory.WORKFLOW,
        definition={
            "entry_point": "step1",
            "steps": [
                {
                    "id": "step1",
                    "name": "Test Step",
                    "type": "tool_call",
                    "config": {},
                    "next": []
                }
            ]
        }
    )
    db_session.add(template)
    db_session.commit()
    
    orchestrator = WorkflowOrchestrator(db_session)
    graph = orchestrator.build_graph_from_template(template)
    
    # Execute graph
    initial_state = WorkflowState({"workflow_id": 1})
    result = graph.invoke(initial_state)
    
    # Verify execution
    assert result["step1_status"] == "completed"
    assert "step1_output" in result
```

Run:
```bash
cd backend
pytest tests/unit/services/test_workflow_orchestrator.py::test_execute_simple_graph -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/workflow_orchestrator.py backend/tests/unit/services/test_workflow_orchestrator.py
git commit -m "feat: implement LangGraph integration in WorkflowOrchestrator"
```

---

## Task 8: Add Workflow Execution with Metrics

**Files:**
- Modify: `backend/app/services/workflow_orchestrator.py`
- Modify: `backend/tests/unit/services/test_workflow_orchestrator.py`

- [ ] **Step 1: Write test for workflow execution with metrics**

Add to `backend/tests/unit/services/test_workflow_orchestrator.py`:

```python
import asyncio

@pytest.mark.asyncio
async def test_execute_workflow_with_metrics(db_session, workflow_run_fixture):
    """Test executing workflow and collecting metrics."""
    # Update fixture template with valid definition
    template = workflow_run_fixture.template
    template.definition = {
        "entry_point": "step1",
        "steps": [
            {
                "id": "step1",
                "name": "Test Step",
                "type": "tool_call",
                "config": {"tool": "mock_tool"},
                "next": []
            }
        ]
    }
    db_session.commit()
    
    orchestrator = WorkflowOrchestrator(db_session)
    
    # Execute workflow
    result = await orchestrator.execute_workflow(workflow_run_fixture.id)
    
    # Verify workflow run updated
    db_session.refresh(workflow_run_fixture)
    assert workflow_run_fixture.status == WorkflowRunStatus.COMPLETED
    
    # Verify step execution created
    steps = db_session.query(WorkflowStepExecution).filter_by(
        workflow_run_id=workflow_run_fixture.id
    ).all()
    assert len(steps) == 1
    assert steps[0].step_id == "step1"
    assert steps[0].status == StepStatus.COMPLETED
    
    # Verify metrics collected
    from backend.app.models.metrics import StepMetrics
    metrics = db_session.query(StepMetrics).filter_by(
        workflow_run_id=workflow_run_fixture.id
    ).all()
    assert len(metrics) == 1
    assert metrics[0].success is True
    assert metrics[0].duration_ms is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd backend
pytest tests/unit/services/test_workflow_orchestrator.py::test_execute_workflow_with_metrics -v
```

Expected: FAIL (execute_workflow not implemented)

- [ ] **Step 3: Implement execute_workflow method**

Modify `backend/app/services/workflow_orchestrator.py`:

```python
# Update _create_step_node to collect metrics
def _create_step_node(self, step: Dict[str, Any], template_id: int) -> Callable:
    """Create a LangGraph node function for a workflow step."""
    
    async def node_func(state: WorkflowState) -> WorkflowState:
        """Execute workflow step with metrics collection."""
        workflow_run_id = state.get("workflow_run_id")
        
        # Create step execution record
        step_exec = WorkflowStepExecution(
            workflow_run_id=workflow_run_id,
            step_id=step["id"],
            step_name=step["name"],
            step_type=step["type"],
            status=StepStatus.RUNNING,
            inputs=step.get("config", {})
        )
        self.db.add(step_exec)
        self.db.commit()
        self.db.refresh(step_exec)
        
        # Start metrics collection
        metrics = self.metrics.record_step_start(
            workflow_run_id=workflow_run_id,
            step_execution_id=step_exec.id
        )
        
        try:
            # Execute step (mock for Phase 1)
            # Real tool execution will be added in Phase 2
            result = {"mock": "result"}
            
            # Update step execution
            step_exec.status = StepStatus.COMPLETED
            step_exec.outputs = result
            step_exec.completed_at = datetime.utcnow()
            self.db.commit()
            
            # Record metrics
            self.metrics.record_step_completion(
                metrics_id=metrics.id,
                success=True,
                output_data=result
            )
            
            # Update state
            state[f"{step['id']}_status"] = "completed"
            state[f"{step['id']}_output"] = result
            
        except Exception as e:
            # Update step execution
            step_exec.status = StepStatus.FAILED
            step_exec.error = str(e)
            self.db.commit()
            
            # Record metrics
            self.metrics.record_step_completion(
                metrics_id=metrics.id,
                success=False,
                error_type=type(e).__name__,
                error_message=str(e)
            )
            
            # Update state
            state[f"{step['id']}_status"] = "failed"
            state[f"{step['id']}_error"] = str(e)
            
            raise
        
        return state
    
    return node_func

# Add execute_workflow method
async def execute_workflow(self, workflow_run_id: int) -> WorkflowState:
    """
    Execute a workflow run with full metrics collection.
    
    Returns final workflow state.
    """
    # Load workflow run
    workflow_run = self.db.query(WorkflowRun).get(workflow_run_id)
    if not workflow_run:
        raise ValueError(f"Workflow run not found: {workflow_run_id}")
    
    # Update status
    workflow_run.status = WorkflowRunStatus.RUNNING
    self.db.commit()
    
    # Build graph from template
    graph = self.build_graph_from_template(workflow_run.template)
    
    # Prepare initial state
    initial_state = WorkflowState(
        workflow_run_id=workflow_run_id,
        **workflow_run.input_data
    )
    
    try:
        # Execute graph
        result = await graph.ainvoke(
            initial_state,
            config={
                "configurable": {
                    "thread_id": str(workflow_run_id)
                }
            }
        )
        
        # Update workflow run
        workflow_run.status = WorkflowRunStatus.COMPLETED
        workflow_run.state = dict(result)
        workflow_run.completed_at = datetime.utcnow()
        self.db.commit()
        
        return result
        
    except Exception as e:
        # Update workflow run
        workflow_run.status = WorkflowRunStatus.FAILED
        workflow_run.state = {"error": str(e)}
        self.db.commit()
        
        raise
```

- [ ] **Step 4: Add asyncio support to conftest**

Modify `backend/tests/conftest.py`:

```python
# Add pytest-asyncio plugin
pytest_plugins = [
    "tests.fixtures.workflow_fixtures",
]

# Add asyncio fixture
import pytest

@pytest.fixture(scope="session")
def event_loop():
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
```

- [ ] **Step 5: Install pytest-asyncio**

```bash
cd backend
pip install pytest-asyncio
echo "pytest-asyncio==0.23.5" >> requirements.txt
```

- [ ] **Step 6: Run test to verify it passes**

Run:
```bash
cd backend
pytest tests/unit/services/test_workflow_orchestrator.py::test_execute_workflow_with_metrics -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/workflow_orchestrator.py backend/tests/unit/services/test_workflow_orchestrator.py backend/tests/conftest.py backend/requirements.txt
git commit -m "feat: implement workflow execution with metrics collection"
```

---

## Task 9: Add API Schemas

**Files:**
- Create: `backend/app/schemas/workflow.py`
- Create: `backend/tests/unit/schemas/test_workflow_schemas.py`

- [ ] **Step 1: Write test for workflow schemas**

Create `backend/tests/unit/schemas/test_workflow_schemas.py`:

```python
import pytest
from datetime import datetime
from app.schemas.workflow import (
    WorkflowTemplateCreate,
    WorkflowTemplateResponse,
    WorkflowRunCreate,
    WorkflowRunResponse
)
from app.models.models import WorkflowCategory


def test_workflow_template_create_schema():
    """Test creating workflow template schema."""
    data = {
        "name": "test_workflow",
        "description": "Test workflow",
        "version": "1.0.0",
        "workflow_category": "WORKFLOW",
        "definition": {
            "entry_point": "step1",
            "steps": [
                {"id": "step1", "name": "Test", "type": "tool_call", "config": {}, "next": []}
            ]
        }
    }
    
    schema = WorkflowTemplateCreate(**data)
    assert schema.name == "test_workflow"
    assert schema.workflow_category == "WORKFLOW"
    assert "steps" in schema.definition


def test_workflow_run_create_schema():
    """Test creating workflow run schema."""
    data = {
        "template_name": "test_workflow",
        "session_id": 1,
        "input_data": {"club_name": "Test Club"}
    }
    
    schema = WorkflowRunCreate(**data)
    assert schema.template_name == "test_workflow"
    assert schema.input_data["club_name"] == "Test Club"
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd backend
pytest tests/unit/schemas/test_workflow_schemas.py -v
```

Expected: FAIL (schemas module not found)

- [ ] **Step 3: Create workflow schemas**

Create `backend/app/schemas/workflow.py`:

```python
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class WorkflowTemplateCreate(BaseModel):
    """Schema for creating workflow template."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    version: str = Field(..., pattern=r'^\d+\.\d+\.\d+$')
    workflow_category: str = Field(..., pattern=r'^(WORKFLOW|QUESTION|BUG_FIX|FEATURE|ANALYSIS|CREATIVE|ADMIN|UNKNOWN)$')
    definition: Dict[str, Any] = Field(..., description="Workflow definition as JSON")


class WorkflowTemplateResponse(BaseModel):
    """Schema for workflow template response."""
    id: int
    name: str
    description: Optional[str]
    version: str
    workflow_category: str
    definition: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class WorkflowRunCreate(BaseModel):
    """Schema for creating workflow run."""
    template_name: str = Field(..., min_length=1)
    session_id: int = Field(..., gt=0)
    input_data: Dict[str, Any] = Field(default_factory=dict)


class WorkflowRunResponse(BaseModel):
    """Schema for workflow run response."""
    id: int
    template_id: int
    session_id: int
    status: str
    workflow_category: str
    input_data: Dict[str, Any]
    state: Dict[str, Any]
    output_data: Optional[Dict[str, Any]]
    started_at: datetime
    completed_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class WorkflowStepExecutionResponse(BaseModel):
    """Schema for step execution response."""
    id: int
    workflow_run_id: int
    step_id: str
    step_name: str
    step_type: str
    status: str
    inputs: Optional[Dict[str, Any]]
    outputs: Optional[Dict[str, Any]]
    error: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    
    class Config:
        from_attributes = True
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd backend
pytest tests/unit/schemas/test_workflow_schemas.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/workflow.py backend/tests/unit/schemas/test_workflow_schemas.py
git commit -m "feat: add workflow API schemas"
```

---

## Task 10: Integration Test - End-to-End Workflow

**Files:**
- Create: `backend/tests/integration/test_workflow_e2e.py`

- [ ] **Step 1: Write end-to-end integration test**

Create `backend/tests/integration/test_workflow_e2e.py`:

```python
import pytest
import asyncio
from app.models.workflow import (
    WorkflowTemplate,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowStepExecution,
    StepStatus
)
from app.models.metrics import StepMetrics
from app.models.models import User, Session, WorkflowCategory
from app.services.workflow_orchestrator import WorkflowOrchestrator


@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_workflow_execution(db_session):
    """
    Integration test: Create template, run workflow, verify metrics.
    
    Tests the complete flow from template creation through execution
    to metrics collection.
    """
    # 1. Create user and session
    user = User(email="test@example.com", name="Test User", password_hash="hashed_password")
    db_session.add(user)
    db_session.commit()
    
    session = Session(user_id=user.id)
    db_session.add(session)
    db_session.commit()
    
    # 2. Create workflow template
    template = WorkflowTemplate(
        name="integration_test_workflow",
        description="Integration test workflow",
        version="1.0.0",
        workflow_category=WorkflowCategory.WORKFLOW,
        definition={
            "entry_point": "init",
            "steps": [
                {
                    "id": "init",
                    "name": "Initialize Database",
                    "type": "tool_call",
                    "config": {"tool": "mock_init"},
                    "next": ["configure"]
                },
                {
                    "id": "configure",
                    "name": "Configure Settings",
                    "type": "tool_call",
                    "config": {"tool": "mock_configure"},
                    "next": []
                }
            ]
        }
    )
    db_session.add(template)
    db_session.commit()
    
    # 3. Create workflow orchestrator
    orchestrator = WorkflowOrchestrator(db_session)
    
    # 4. Create workflow run
    workflow_run = orchestrator.create_workflow_run(
        template_name="integration_test_workflow",
        session_id=session.id,
        input_data={"club_name": "Integration Test Club"}
    )
    
    assert workflow_run.status == WorkflowRunStatus.PENDING
    
    # 5. Execute workflow
    result = await orchestrator.execute_workflow(workflow_run.id)
    
    # 6. Verify workflow run completed
    db_session.refresh(workflow_run)
    assert workflow_run.status == WorkflowRunStatus.COMPLETED
    assert workflow_run.completed_at is not None
    
    # 7. Verify step executions created
    steps = db_session.query(WorkflowStepExecution).filter_by(
        workflow_run_id=workflow_run.id
    ).order_by(WorkflowStepExecution.id).all()
    
    assert len(steps) == 2
    assert steps[0].step_id == "init"
    assert steps[0].status == StepStatus.COMPLETED
    assert steps[1].step_id == "configure"
    assert steps[1].status == StepStatus.COMPLETED
    
    # 8. Verify metrics collected for all steps
    metrics = db_session.query(StepMetrics).filter_by(
        workflow_run_id=workflow_run.id
    ).all()
    
    assert len(metrics) == 2
    for metric in metrics:
        assert metric.success is True
        assert metric.started_at is not None
        assert metric.completed_at is not None
        assert metric.duration_ms is not None
        assert metric.duration_ms > 0
    
    # 9. Verify final state
    assert "init_status" in result
    assert result["init_status"] == "completed"
    assert "configure_status" in result
    assert result["configure_status"] == "completed"
```

- [ ] **Step 2: Run integration test**

Run:
```bash
cd backend
pytest tests/integration/test_workflow_e2e.py -v -s
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/test_workflow_e2e.py
git commit -m "test: add end-to-end integration test for workflow execution"
```

---

## Task 11: Documentation

**Files:**
- Create: `backend/docs/phase-1-complete.md`

- [ ] **Step 1: Write Phase 1 completion documentation**

Create `backend/docs/phase-1-complete.md`:

```markdown
# Phase 1 Complete: Workflow Engine + Metrics

## What Was Built

### Database Models
- **WorkflowTemplate**: Reusable workflow definitions with JSON graph structure
- **WorkflowRun**: Active workflow execution instances
- **WorkflowStepExecution**: Individual step execution tracking
- **StepMetrics**: Performance and outcome metrics per step
- **LLMDecisionMetrics**: LLM decision tracking for prompt optimization

### Services
- **MetricsCollector**: Collects step-level and LLM decision metrics
- **WorkflowOrchestrator**: LangGraph integration for workflow execution
  - Converts JSON templates to executable StateGraphs
  - Manages workflow lifecycle
  - Integrates with PostgresCheckpointer for state persistence
  - Instruments every step with metrics collection

### Infrastructure
- LangGraph + PostgresCheckpointer for workflow state management
- PostgreSQL schema migration with all workflow tables
- Comprehensive test suite (unit + integration)

## What Works

- ✅ Create workflow templates from JSON definitions
- ✅ Execute workflows with LangGraph state machine
- ✅ Automatic metrics collection on every step
- ✅ State persistence via PostgreSQL checkpointer
- ✅ Support for linear and branching workflows
- ✅ Step-level instrumentation (duration, success, errors)

## What's Not Yet Implemented

- ⏳ Real tool execution (Phase 2: BRS Tools)
- ⏳ Approval gates (Phase 2)
- ⏳ Error recovery strategies (Phase 2)
- ⏳ LLM decision points (Phase 3)
- ⏳ Langfuse integration for LLM observability (Phase 3 - custom metrics built in Phase 1 provide foundation)
- ⏳ Prompt optimization based on metrics (Phase 3)
- ⏳ Analytics dashboard (Phase 4)

## Database Schema

See migration: `backend/alembic/versions/001_add_workflow_models.py`

Tables created:
- workflow_templates
- workflow_runs
- workflow_step_executions
- step_metrics
- llm_decision_metrics

## Running Tests

```bash
# Unit tests
cd backend
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# Full suite
pytest -v
```

## Next Steps

Proceed to **Phase 2: BRS Tools Integration**
- Implement BRS MCP tool server
- Add real tool execution to workflow steps
- Implement approval gates
- Add error recovery patterns
```

- [ ] **Step 2: Commit**

```bash
git add backend/docs/phase-1-complete.md
git commit -m "docs: add Phase 1 completion summary"
```

---

## Phase 1 Complete! ✅

All tasks completed. The workflow engine foundation is built with:
- Full database schema
- LangGraph integration
- Metrics collection
- Comprehensive testing
- State persistence

**Ready for Phase 2: BRS Tools Integration**
