# Phase 3: Onboarding Workflow + Testing + Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build complete teesheet onboarding workflow template with approval gates, integrate DeepEval for workflow testing, create analytics dashboard on Langfuse traces, and add prompt versioning for optimization.

**Architecture:** Teesheet onboarding workflow orchestrates BRS tools (init → superuser → config) with human approval gates at business decision points. DeepEval tests real workflow executions against success criteria. Analytics dashboard queries Langfuse PostgreSQL for workflow metrics (success rate, duration, step failures). Prompt templates stored in database with versioning for A/B testing.

**Analytics Strategy:**
- **Primary (Langfuse Built-in):** Use Langfuse's built-in dashboard for trace visualization, LLM call analysis, and token usage tracking at http://localhost:3000
- **Custom (This Phase):** Build custom analytics API + React dashboard for:
  - Workflow success rates (Langfuse doesn't understand workflow semantics)
  - Step-level failure analysis (aggregated from WorkflowStepExecution table)
  - Prompt version comparison (A/B metrics from PromptTemplateVersion table)
  - Business-specific dashboards (onboarding completion rates, avg setup time)

**Tech Stack:** LangGraph (workflow), BRS Tool Gateway (Phase 2), DeepEval, Langfuse API, SQLAlchemy (prompt versioning), pytest

---

## Task Completion Status

**Progress**: 0 of 8 tasks complete (0%)

- [ ] **Task 1**: Teesheet Onboarding Workflow Template
- [ ] **Task 2**: Approval Gate Implementation
- [ ] **Task 3**: DeepEval Integration
- [ ] **Task 4**: Workflow Test Suite with DeepEval
- [ ] **Task 5**: Prompt Template Versioning
- [ ] **Task 6**: Analytics Dashboard (Backend API)
- [ ] **Task 7**: Analytics Dashboard (Frontend Components)
- [ ] **Task 8**: Documentation

---

## File Structure

### New Files

```
backend/
├── app/
│   ├── models/
│   │   └── prompt_template.py          # Prompt versioning models
│   ├── services/
│   │   ├── analytics_service.py        # Langfuse query service
│   │   └── approval_service.py         # Approval gate orchestration
│   ├── workflows/
│   │   ├── __init__.py
│   │   └── teesheet_onboarding.py      # Complete onboarding workflow
│   └── api/
│       └── analytics.py                # Analytics API endpoints
├── alembic/versions/
│   └── xxxx_add_prompt_templates.py    # Migration for prompt versioning
└── tests/
    ├── unit/
    │   ├── services/
    │   │   ├── test_analytics_service.py
    │   │   └── test_approval_service.py
    │   └── models/
    │       └── test_prompt_template.py
    ├── integration/
    │   └── test_teesheet_onboarding_e2e.py
    └── deepeval/
        ├── __init__.py
        ├── test_workflow_correctness.py
        ├── test_workflow_hallucination.py
        └── test_workflow_toxicity.py
frontend/
├── src/
│   ├── components/
│   │   └── analytics/
│   │       ├── WorkflowSuccessRate.tsx
│   │       ├── WorkflowDurationChart.tsx
│   │       ├── StepFailureAnalysis.tsx
│   │       └── PromptVersionComparison.tsx
│   └── pages/
│       └── analytics/
│           └── dashboard.tsx           # Analytics dashboard page
```

### Modified Files

```
backend/
├── app/models/workflow.py              # Add approval fields
├── app/services/workflow_orchestrator.py  # Add approval gate support
├── tests/fixtures/workflow_fixtures.py  # Add workflow_run_factory
├── requirements.txt                    # Add deepeval
└── .env.example                        # Add DeepEval API key
```

---

## Prerequisites: Add Test Fixtures

> **Note:** These fixtures are required by Task 2 tests. Add them before starting Task 2.

**Files:**
- Modify: `backend/tests/fixtures/workflow_fixtures.py`

Add the `workflow_run_factory` fixture:

```python
# Add to backend/tests/fixtures/workflow_fixtures.py

@pytest.fixture
def workflow_run_factory(db_session, workflow_template_fixture):
    """Factory for creating workflow runs with configurable status.
    
    Usage:
        run = workflow_run_factory(status=WorkflowRunStatus.RUNNING)
    """
    from datetime import datetime, timezone
    from app.models.workflow import WorkflowRun, WorkflowRunStatus
    
    created_runs = []
    
    def _create_workflow_run(
        status: WorkflowRunStatus = WorkflowRunStatus.PENDING,
        input_data: dict = None,
        session_id: int = None
    ) -> WorkflowRun:
        workflow_run = WorkflowRun(
            template_id=workflow_template_fixture.id,
            session_id=session_id or 1,
            user_id=1,
            status=status,
            input_data=input_data or {"club_name": "Test Club"},
            created_at=datetime.now(timezone.utc)
        )
        db_session.add(workflow_run)
        db_session.commit()
        db_session.refresh(workflow_run)
        created_runs.append(workflow_run)
        return workflow_run
    
    yield _create_workflow_run
    
    # Cleanup
    for run in created_runs:
        db_session.delete(run)
    db_session.commit()
```

---

## BRS Tool Integration Note

> **Important:** Phase 3 workflows use BRS tools defined in Phase 2. During development:
> - **Mock mode (default)**: Workflows execute with mock BRS tool responses
> - **Real CLI mode**: Set `BRS_MOCK_MODE=false` and configure `BRS_TEESHEET_PATH`
> 
> The transition to real CLI happens in production deployment, not in this phase.

---

## Task 1: Teesheet Onboarding Workflow Template

**Files:**
- Create: `backend/app/workflows/__init__.py`
- Create: `backend/app/workflows/teesheet_onboarding.py`
- Create: `backend/tests/integration/test_teesheet_onboarding_e2e.py`

- [ ] **Step 1: Write test for onboarding workflow execution**

Create `backend/tests/integration/test_teesheet_onboarding_e2e.py`:

```python
import pytest
from app.workflows.teesheet_onboarding import create_teesheet_onboarding_template
from app.services.workflow_orchestrator import WorkflowOrchestrator
from app.models.workflow import WorkflowRun, WorkflowRunStatus


@pytest.mark.asyncio
async def test_teesheet_onboarding_workflow_e2e(db_session, session):
    """Test complete teesheet onboarding workflow."""
    # Create workflow template
    template = create_teesheet_onboarding_template(db_session)
    
    assert template.name == "Teesheet Onboarding"
    assert len(template.definition["steps"]) >= 4  # At least 4 main steps
    
    # Create orchestrator
    orchestrator = WorkflowOrchestrator(db_session, None)
    
    # Create workflow run with club data
    workflow_run = orchestrator.create_workflow_run(
        template=template,
        session_id=session.id,
        input_data={
            "club_name": "Pebble Beach Golf Links",
            "club_id": "PB001",
            "contact_email": "admin@pebblebeach.com",
            "contact_name": "John Smith",
            "facility_type": "golf_course",
            "modules": ["member", "sms"]
        },
        user_id=1
    )
    
    # Execute workflow (mock mode)
    result = await orchestrator.execute_workflow(workflow_run.id)
    
    # Verify completion
    db_session.refresh(workflow_run)
    assert workflow_run.status == WorkflowRunStatus.COMPLETED
    
    # Verify all steps executed
    step_executions = workflow_run.step_executions
    assert len(step_executions) >= 4
    
    # Verify step sequence
    step_names = [step.step_name for step in sorted(step_executions, key=lambda x: x.started_at)]
    assert "init_database" in step_names[0]
    assert "create_superuser" in step_names[1]
    assert "config_setup" in step_names[2]


@pytest.mark.asyncio
async def test_teesheet_onboarding_workflow_validates_input(db_session, session):
    """Test workflow validates required input data."""
    template = create_teesheet_onboarding_template(db_session)
    orchestrator = WorkflowOrchestrator(db_session, None)
    
    # Missing required fields
    with pytest.raises(ValueError) as exc_info:
        orchestrator.create_workflow_run(
            template=template,
            session_id=session.id,
            input_data={"club_name": "Test"},  # Missing club_id, contact_email
            user_id=1
        )
    
    assert "required" in str(exc_info.value).lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd backend
pytest tests/integration/test_teesheet_onboarding_e2e.py -v
```

Expected: FAIL with "No module named 'app.workflows.teesheet_onboarding'"

- [ ] **Step 3: Create workflow template module**

Create `backend/app/workflows/__init__.py`:

```python
"""Workflow templates for common business processes."""
```

Create `backend/app/workflows/teesheet_onboarding.py`:

```python
from typing import Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from app.models.workflow import WorkflowTemplate, WorkflowCategory


def create_teesheet_onboarding_template(db: Session) -> WorkflowTemplate:
    """Create teesheet onboarding workflow template.
    
    Workflow Steps:
    1. Init Database - Create club-specific database (./bin/teesheet init)
    2. Create Superuser - Setup admin account (./bin/teesheet update-superusers)
    3. Config Setup - Add club config to MongoDB (brs-config-api)
    4. Validate Config - Verify setup is correct
    
    Approval Gates:
    - After config setup (before validation) - human reviews generated config
    
    Args:
        db: Database session
        
    Returns:
        WorkflowTemplate for teesheet onboarding
    """
    
    # Define workflow steps
    workflow_definition = {
        "steps": [
            {
                "id": "init_database",
                "type": "tool_call",
                "tool": "brs_teesheet_init",
                "description": "Initialize club database",
                "inputs": {
                    "club_name": "{{input.club_name}}",
                    "club_id": "{{input.club_id}}"
                },
                "next": "create_superuser",
                "timeout_seconds": 120
            },
            {
                "id": "create_superuser",
                "type": "tool_call",
                "tool": "brs_create_superuser",
                "description": "Create admin account",
                "inputs": {
                    "club_name": "{{input.club_name}}",
                    "email": "{{input.contact_email}}",
                    "name": "{{input.contact_name}}"
                },
                "next": "config_setup",
                "timeout_seconds": 60,
                "depends_on": ["init_database"]
            },
            {
                "id": "config_setup",
                "type": "llm_decision",
                "description": "Generate club configuration",
                "prompt_template": "teesheet_config_generation",
                "inputs": {
                    "club_name": "{{input.club_name}}",
                    "club_id": "{{input.club_id}}",
                    "facility_type": "{{input.facility_type}}",
                    "modules": "{{input.modules}}"
                },
                "next": "approval_gate_config",
                "depends_on": ["create_superuser"]
            },
            {
                "id": "approval_gate_config",
                "type": "approval_gate",
                "description": "Review generated configuration",
                "approval_data_key": "config_setup.output",
                "next": "validate_config",
                "depends_on": ["config_setup"]
            },
            {
                "id": "validate_config",
                "type": "tool_call",
                "tool": "brs_config_validate",
                "description": "Validate configuration",
                "inputs": {
                    "club_id": "{{input.club_id}}"
                },
                "next": "END",
                "depends_on": ["approval_gate_config"]
            }
        ],
        "input_schema": {
            "type": "object",
            "required": ["club_name", "club_id", "contact_email", "contact_name"],
            "properties": {
                "club_name": {"type": "string"},
                "club_id": {"type": "string"},
                "contact_email": {"type": "string", "format": "email"},
                "contact_name": {"type": "string"},
                "facility_type": {"type": "string", "enum": ["golf_course", "driving_range", "simulator"]},
                "modules": {"type": "array", "items": {"type": "string"}}
            }
        }
    }
    
    # Create template
    template = WorkflowTemplate(
        name="Teesheet Onboarding",
        version="1.0.0",
        description="Complete teesheet onboarding workflow with database init, superuser creation, and config setup",
        definition=workflow_definition,
        workflow_category=WorkflowCategory.WORKFLOW,
        max_retries=2,
        retry_delay_seconds=30,
        created_at=datetime.now(timezone.utc)
    )
    
    db.add(template)
    db.commit()
    db.refresh(template)
    
    return template


def validate_onboarding_input(input_data: Dict[str, Any]) -> bool:
    """Validate onboarding workflow input data.
    
    Args:
        input_data: Input data to validate
        
    Returns:
        True if valid
        
    Raises:
        ValueError: If validation fails
    """
    required_fields = ["club_name", "club_id", "contact_email", "contact_name"]
    
    for field in required_fields:
        if field not in input_data or not input_data[field]:
            raise ValueError(f"Required field missing: {field}")
    
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
cd backend
pytest tests/integration/test_teesheet_onboarding_e2e.py::test_teesheet_onboarding_workflow_e2e -v
```

Expected: 1 test PASS

- [ ] **Step 5: Run all onboarding tests**

Run:
```bash
cd backend
pytest tests/integration/test_teesheet_onboarding_e2e.py -v
```

Expected: 2 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/workflows/ backend/tests/integration/test_teesheet_onboarding_e2e.py
git commit -m "feat: add teesheet onboarding workflow template

- Create complete onboarding workflow with 5 steps:
  1. Init database (brs_teesheet_init)
  2. Create superuser (brs_create_superuser)
  3. Generate config (LLM decision)
  4. Approval gate (human review)
  5. Validate config (brs_config_validate)
- Define input schema with required fields
- Add input validation function
- All tests passing (2/2)

Workflow orchestrates:
- BRS Tool Gateway (Phase 2)
- Approval gates (human-in-loop)
- Config generation with LLM
- Dependency management between steps"
```

---

## Task 2: Approval Gate Implementation

**Files:**
- Create: `backend/app/services/approval_service.py`
- Create: `backend/tests/unit/services/test_approval_service.py`
- Modify: `backend/app/models/workflow.py`
- Modify: `backend/app/services/workflow_orchestrator.py`

- [ ] **Step 1: Write test for approval service**

Create `backend/tests/unit/services/test_approval_service.py`:

```python
import pytest
from datetime import datetime, timezone
from app.services.approval_service import ApprovalService, ApprovalStatus
from app.models.workflow import WorkflowRun, WorkflowRunStatus


def test_request_approval_updates_workflow_run(db_session, workflow_run_factory):
    """Should update workflow run to WAITING_APPROVAL status."""
    workflow_run = workflow_run_factory(status=WorkflowRunStatus.RUNNING)
    service = ApprovalService(db_session)
    
    approval_data = {"config": {"club_name": "Test Club"}}
    
    service.request_approval(
        workflow_run_id=workflow_run.id,
        approval_data=approval_data,
        approval_prompt="Please review the generated configuration"
    )
    
    db_session.refresh(workflow_run)
    assert workflow_run.status == WorkflowRunStatus.WAITING_APPROVAL
    assert workflow_run.approval_data == approval_data
    assert "review" in workflow_run.approval_prompt.lower()


def test_approve_workflow_run_updates_status(db_session, workflow_run_factory):
    """Should approve workflow and update status to RUNNING."""
    workflow_run = workflow_run_factory(status=WorkflowRunStatus.WAITING_APPROVAL)
    service = ApprovalService(db_session)
    
    service.process_approval(
        workflow_run_id=workflow_run.id,
        approved=True,
        user_id=1,
        notes="Looks good"
    )
    
    db_session.refresh(workflow_run)
    assert workflow_run.status == WorkflowRunStatus.RUNNING
    assert workflow_run.approved_by == 1
    assert workflow_run.approved_at is not None
    assert workflow_run.approval_notes == "Looks good"


def test_reject_workflow_run_updates_status(db_session, workflow_run_factory):
    """Should reject workflow and update status to FAILED."""
    workflow_run = workflow_run_factory(status=WorkflowRunStatus.WAITING_APPROVAL)
    service = ApprovalService(db_session)
    
    service.process_approval(
        workflow_run_id=workflow_run.id,
        approved=False,
        user_id=1,
        notes="Config is incorrect"
    )
    
    db_session.refresh(workflow_run)
    assert workflow_run.status == WorkflowRunStatus.FAILED
    assert workflow_run.approved_by == 1
    assert workflow_run.approved_at is not None
    assert workflow_run.approval_notes == "Config is incorrect"


def test_get_pending_approvals_returns_waiting_workflows(db_session, workflow_run_factory):
    """Should return all workflows waiting for approval."""
    # Create workflows in different states
    waiting1 = workflow_run_factory(status=WorkflowRunStatus.WAITING_APPROVAL)
    waiting2 = workflow_run_factory(status=WorkflowRunStatus.WAITING_APPROVAL)
    running = workflow_run_factory(status=WorkflowRunStatus.RUNNING)
    completed = workflow_run_factory(status=WorkflowRunStatus.COMPLETED)
    
    service = ApprovalService(db_session)
    pending = service.get_pending_approvals()
    
    pending_ids = [w.id for w in pending]
    assert waiting1.id in pending_ids
    assert waiting2.id in pending_ids
    assert running.id not in pending_ids
    assert completed.id not in pending_ids
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd backend
pytest tests/unit/services/test_approval_service.py -v
```

Expected: FAIL with "No module named 'app.services.approval_service'"

- [ ] **Step 3: Add approval fields to WorkflowRun model**

Modify `backend/app/models/workflow.py`:

```python
# Add to WorkflowRunStatus enum
class WorkflowRunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    WAITING_APPROVAL = "WAITING_APPROVAL"  # New status


# Add to WorkflowRun model
class WorkflowRun(Base):
    # ... existing fields ...
    
    # Approval fields
    approval_data: Optional[Dict] = Column(JSON, nullable=True)
    approval_prompt: Optional[str] = Column(Text, nullable=True)
    approved_by: Optional[int] = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at: Optional[datetime] = Column(DateTime, nullable=True)
    approval_notes: Optional[str] = Column(Text, nullable=True)
```

- [ ] **Step 4: Create database migration**

Run:
```bash
cd backend
alembic revision -m "add approval fields to workflow runs"
```

Edit migration file:

```python
def upgrade():
    op.add_column('workflow_runs', sa.Column('approval_data', sa.JSON(), nullable=True))
    op.add_column('workflow_runs', sa.Column('approval_prompt', sa.Text(), nullable=True))
    op.add_column('workflow_runs', sa.Column('approved_by', sa.Integer(), nullable=True))
    op.add_column('workflow_runs', sa.Column('approved_at', sa.DateTime(), nullable=True))
    op.add_column('workflow_runs', sa.Column('approval_notes', sa.Text(), nullable=True))
    
    op.create_foreign_key(
        'fk_workflow_runs_approved_by_users',
        'workflow_runs', 'users',
        ['approved_by'], ['id']
    )


def downgrade():
    op.drop_constraint('fk_workflow_runs_approved_by_users', 'workflow_runs', type_='foreignkey')
    op.drop_column('workflow_runs', 'approval_notes')
    op.drop_column('workflow_runs', 'approved_at')
    op.drop_column('workflow_runs', 'approved_by')
    op.drop_column('workflow_runs', 'approval_prompt')
    op.drop_column('workflow_runs', 'approval_data')
```

Run migration:
```bash
alembic upgrade head
```

- [ ] **Step 5: Create approval service**

Create `backend/app/services/approval_service.py`:

```python
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.workflow import WorkflowRun, WorkflowRunStatus


class ApprovalStatus:
    """Approval status constants."""
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING = "pending"


class ApprovalService:
    """Service for managing workflow approval gates.
    
    Usage:
        service = ApprovalService(db_session)
        
        # Request approval
        service.request_approval(
            workflow_run_id=123,
            approval_data={"config": {...}},
            approval_prompt="Please review this configuration"
        )
        
        # Process approval
        service.process_approval(
            workflow_run_id=123,
            approved=True,
            user_id=1,
            notes="Looks good"
        )
    """
    
    def __init__(self, db: Session):
        """Initialize approval service.
        
        Args:
            db: Database session
        """
        self.db = db
    
    def request_approval(
        self,
        workflow_run_id: int,
        approval_data: Dict[str, Any],
        approval_prompt: str
    ):
        """Request approval for a workflow run.
        
        Args:
            workflow_run_id: Workflow run ID
            approval_data: Data to be approved (e.g., generated config)
            approval_prompt: Human-readable prompt for approver
        """
        workflow_run = self.db.query(WorkflowRun).filter(
            WorkflowRun.id == workflow_run_id
        ).first()
        
        if not workflow_run:
            raise ValueError(f"Workflow run not found: {workflow_run_id}")
        
        # Update workflow to waiting state
        workflow_run.status = WorkflowRunStatus.WAITING_APPROVAL
        workflow_run.approval_data = approval_data
        workflow_run.approval_prompt = approval_prompt
        
        self.db.commit()
    
    def process_approval(
        self,
        workflow_run_id: int,
        approved: bool,
        user_id: int,
        notes: Optional[str] = None
    ):
        """Process approval decision.
        
        Args:
            workflow_run_id: Workflow run ID
            approved: True if approved, False if rejected
            user_id: ID of user who approved/rejected
            notes: Optional notes from approver
        """
        workflow_run = self.db.query(WorkflowRun).filter(
            WorkflowRun.id == workflow_run_id
        ).first()
        
        if not workflow_run:
            raise ValueError(f"Workflow run not found: {workflow_run_id}")
        
        if workflow_run.status != WorkflowRunStatus.WAITING_APPROVAL:
            raise ValueError(
                f"Workflow run {workflow_run_id} is not waiting for approval "
                f"(current status: {workflow_run.status})"
            )
        
        # Record approval decision
        workflow_run.approved_by = user_id
        workflow_run.approved_at = datetime.now(timezone.utc)
        workflow_run.approval_notes = notes
        
        # Update status based on decision
        if approved:
            workflow_run.status = WorkflowRunStatus.RUNNING
        else:
            workflow_run.status = WorkflowRunStatus.FAILED
            workflow_run.error_message = f"Rejected by user {user_id}: {notes}"
        
        self.db.commit()
    
    def get_pending_approvals(self, user_id: Optional[int] = None) -> List[WorkflowRun]:
        """Get all workflows waiting for approval.
        
        Args:
            user_id: Optional user ID to filter by assigned approver
            
        Returns:
            List of workflow runs waiting for approval
        """
        query = self.db.query(WorkflowRun).filter(
            WorkflowRun.status == WorkflowRunStatus.WAITING_APPROVAL
        )
        
        if user_id:
            # If user_id provided, filter by assigned approver
            # (would need to add approver assignment logic)
            pass
        
        return query.order_by(WorkflowRun.created_at).all()
    
    def get_approval_history(
        self,
        workflow_run_id: int
    ) -> Dict[str, Any]:
        """Get approval history for a workflow run.
        
        Args:
            workflow_run_id: Workflow run ID
            
        Returns:
            Approval history dict
        """
        workflow_run = self.db.query(WorkflowRun).filter(
            WorkflowRun.id == workflow_run_id
        ).first()
        
        if not workflow_run:
            raise ValueError(f"Workflow run not found: {workflow_run_id}")
        
        return {
            "workflow_run_id": workflow_run.id,
            "approval_data": workflow_run.approval_data,
            "approval_prompt": workflow_run.approval_prompt,
            "approved_by": workflow_run.approved_by,
            "approved_at": workflow_run.approved_at.isoformat() if workflow_run.approved_at else None,
            "approval_notes": workflow_run.approval_notes,
            "status": workflow_run.status.value
        }
```

- [ ] **Step 6: Run tests to verify they pass**

Run:
```bash
cd backend
pytest tests/unit/services/test_approval_service.py -v
```

Expected: 4 tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/workflow.py backend/app/services/approval_service.py backend/tests/unit/services/test_approval_service.py backend/alembic/versions/
git commit -m "feat: add approval gate implementation for workflows

- Add WAITING_APPROVAL status to WorkflowRunStatus enum
- Add approval fields to WorkflowRun model:
  - approval_data (JSON data to approve)
  - approval_prompt (human-readable instructions)
  - approved_by, approved_at, approval_notes
- Create ApprovalService for managing approval gates:
  - request_approval() - pause workflow for human review
  - process_approval() - approve/reject and continue/fail workflow
  - get_pending_approvals() - query waiting workflows
  - get_approval_history() - audit trail
- Create database migration for approval fields
- All tests passing (4/4)

Enables human-in-the-loop workflows:
- Green fee rate configuration review
- Booking rule validation
- Config approval before deployment"
```

---

## Task 3: DeepEval Integration

**Files:**
- Create: `backend/tests/deepeval/__init__.py`
- Create: `backend/tests/deepeval/conftest.py`
- Modify: `backend/requirements.txt`
- Modify: `backend/.env.example`

- [ ] **Step 1: Add DeepEval dependency**

Modify `backend/requirements.txt`:

```txt
# Add to existing dependencies
deepeval==1.5.0
```

Install:
```bash
cd backend
pip install deepeval==1.5.0
```

- [ ] **Step 2: Add DeepEval API key to environment**

Modify `backend/.env.example`:

```bash
# Add DeepEval configuration
DEEPEVAL_API_KEY=your_api_key_here
```

- [ ] **Step 3: Create DeepEval test configuration**

Create `backend/tests/deepeval/__init__.py`:

```python
"""DeepEval-based workflow tests for correctness, hallucination, and toxicity."""
```

Create `backend/tests/deepeval/conftest.py`:

```python
import pytest
import os
from deepeval import assert_test
from deepeval.test_case import LLMTestCase


@pytest.fixture(scope="session")
def deepeval_enabled():
    """Check if DeepEval is enabled."""
    return os.getenv("DEEPEVAL_API_KEY") is not None


@pytest.fixture
def skip_if_no_deepeval_key(deepeval_enabled):
    """Skip test if DeepEval API key not configured."""
    if not deepeval_enabled:
        pytest.skip("DeepEval API key not configured")
```

- [ ] **Step 4: Write simple DeepEval smoke test**

Create basic test to verify DeepEval integration:

```python
# Add to conftest.py for smoke test

def test_deepeval_import():
    """Smoke test - verify DeepEval can be imported."""
    from deepeval.metrics import AnswerRelevancyMetric
    from deepeval.test_case import LLMTestCase
    
    # Create a simple test case
    test_case = LLMTestCase(
        input="What is 2+2?",
        actual_output="4",
        expected_output="4"
    )
    
    assert test_case.input == "What is 2+2?"
    assert test_case.actual_output == "4"
```

- [ ] **Step 5: Run smoke test**

Run:
```bash
cd backend
pytest tests/deepeval/conftest.py::test_deepeval_import -v
```

Expected: 1 test PASS

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/.env.example backend/tests/deepeval/
git commit -m "feat: add DeepEval integration for workflow testing

- Add deepeval==1.5.0 dependency
- Add DEEPEVAL_API_KEY environment variable
- Create tests/deepeval/ directory structure
- Add pytest fixtures for DeepEval configuration
- Smoke test passing (1/1)

DeepEval will be used for:
- Workflow correctness testing
- Hallucination detection in LLM outputs
- Toxicity/bias checking
- Answer relevancy scoring"
```

---

## Task 4: Workflow Test Suite with DeepEval

**Files:**
- Create: `backend/tests/deepeval/test_workflow_correctness.py`
- Create: `backend/tests/deepeval/test_workflow_hallucination.py`
- Create: `backend/tests/deepeval/test_workflow_toxicity.py`

- [ ] **Step 1: Write correctness tests for onboarding workflow**

Create `backend/tests/deepeval/test_workflow_correctness.py`:

```python
import pytest
from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from app.workflows.teesheet_onboarding import create_teesheet_onboarding_template
from app.services.workflow_orchestrator import WorkflowOrchestrator


@pytest.mark.deepeval
@pytest.mark.asyncio
async def test_onboarding_workflow_generates_correct_config(
    db_session,
    session,
    skip_if_no_deepeval_key
):
    """Test that onboarding workflow generates correct club configuration."""
    # Setup workflow
    template = create_teesheet_onboarding_template(db_session)
    orchestrator = WorkflowOrchestrator(db_session, None)
    
    # Create workflow run
    workflow_run = orchestrator.create_workflow_run(
        template=template,
        session_id=session.id,
        input_data={
            "club_name": "Pebble Beach Golf Links",
            "club_id": "PB001",
            "contact_email": "admin@pebblebeach.com",
            "contact_name": "John Smith",
            "facility_type": "golf_course",
            "modules": ["member", "sms"]
        },
        user_id=1
    )
    
    # Execute workflow
    result = await orchestrator.execute_workflow(workflow_run.id)
    
    # Get config generation step output
    config_step = next(
        step for step in workflow_run.step_executions
        if step.step_name == "config_setup"
    )
    generated_config = config_step.outputs
    
    # Define correctness criteria
    correctness_metric = GEval(
        name="Config Correctness",
        criteria="The generated configuration should correctly include the club name, ID, facility type, and requested modules (member and SMS). It should not include unrequested modules.",
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT
        ],
        threshold=0.7
    )
    
    # Create test case
    test_case = LLMTestCase(
        input=f"Generate configuration for {workflow_run.input_data}",
        actual_output=str(generated_config),
        context=[
            "Club: Pebble Beach Golf Links (PB001)",
            "Facility: golf_course",
            "Modules: member, sms"
        ]
    )
    
    # Assert correctness
    assert_test(test_case, [correctness_metric])


@pytest.mark.deepeval
@pytest.mark.asyncio
async def test_onboarding_workflow_validates_required_fields(
    db_session,
    session,
    skip_if_no_deepeval_key
):
    """Test that workflow properly validates required fields."""
    # Setup
    template = create_teesheet_onboarding_template(db_session)
    orchestrator = WorkflowOrchestrator(db_session, None)
    
    # Create workflow with incomplete data
    workflow_run = orchestrator.create_workflow_run(
        template=template,
        session_id=session.id,
        input_data={
            "club_name": "Test Club",
            # Missing: club_id, contact_email, contact_name
        },
        user_id=1
    )
    
    # Execute workflow (should fail validation)
    try:
        result = await orchestrator.execute_workflow(workflow_run.id)
        validation_passed = False
    except ValueError as e:
        validation_passed = True
        error_message = str(e)
    
    # Verify validation failed appropriately
    assert validation_passed, "Workflow should reject incomplete input"
    assert "required" in error_message.lower() or "missing" in error_message.lower()
```

- [ ] **Step 2: Run correctness tests**

Run:
```bash
cd backend
pytest tests/deepeval/test_workflow_correctness.py -v -m deepeval
```

Expected: 2 tests PASS (if API key configured) or 2 SKIPPED (if no API key)

- [ ] **Step 3: Write hallucination tests**

Create `backend/tests/deepeval/test_workflow_hallucination.py`:

```python
import pytest
from deepeval import assert_test
from deepeval.metrics import HallucinationMetric
from deepeval.test_case import LLMTestCase
from app.workflows.teesheet_onboarding import create_teesheet_onboarding_template
from app.services.workflow_orchestrator import WorkflowOrchestrator


@pytest.mark.deepeval
@pytest.mark.asyncio
async def test_config_generation_does_not_hallucinate(
    db_session,
    session,
    skip_if_no_deepeval_key
):
    """Test that config generation doesn't hallucinate modules or settings not requested."""
    # Setup workflow
    template = create_teesheet_onboarding_template(db_session)
    orchestrator = WorkflowOrchestrator(db_session, None)
    
    # Create workflow with specific module requests
    workflow_run = orchestrator.create_workflow_run(
        template=template,
        session_id=session.id,
        input_data={
            "club_name": "Simple Golf Club",
            "club_id": "SGC001",
            "contact_email": "admin@simplegolf.com",
            "contact_name": "Jane Doe",
            "facility_type": "golf_course",
            "modules": ["sms"]  # ONLY SMS module requested
        },
        user_id=1
    )
    
    # Execute workflow
    result = await orchestrator.execute_workflow(workflow_run.id)
    
    # Get config generation output
    config_step = next(
        step for step in workflow_run.step_executions
        if step.step_name == "config_setup"
    )
    generated_config = config_step.outputs
    
    # Define context (what was actually requested)
    context = [
        "Club name: Simple Golf Club",
        "Club ID: SGC001",
        "Facility type: golf_course",
        "Modules requested: SMS only",
        "Modules NOT requested: member, visitor, clubhouse_pc, green_fee_printer"
    ]
    
    # Check for hallucination
    hallucination_metric = HallucinationMetric(threshold=0.7)
    
    test_case = LLMTestCase(
        input="Generate configuration for Simple Golf Club with SMS module only",
        actual_output=str(generated_config),
        context=context
    )
    
    # Assert no hallucination
    assert_test(test_case, [hallucination_metric])


@pytest.mark.deepeval
@pytest.mark.asyncio
async def test_superuser_creation_uses_provided_email(
    db_session,
    session,
    skip_if_no_deepeval_key
):
    """Test that superuser creation uses provided email, not hallucinated one."""
    # Setup
    template = create_teesheet_onboarding_template(db_session)
    orchestrator = WorkflowOrchestrator(db_session, None)
    
    # Create workflow with specific contact email
    workflow_run = orchestrator.create_workflow_run(
        template=template,
        session_id=session.id,
        input_data={
            "club_name": "Test Club",
            "club_id": "TC001",
            "contact_email": "specific@testclub.com",  # This EXACT email should be used
            "contact_name": "Test Admin",
            "facility_type": "golf_course",
            "modules": []
        },
        user_id=1
    )
    
    # Execute
    result = await orchestrator.execute_workflow(workflow_run.id)
    
    # Get superuser creation step
    superuser_step = next(
        step for step in workflow_run.step_executions
        if step.step_name == "create_superuser"
    )
    
    # Verify no email hallucination
    context = ["Contact email provided: specific@testclub.com"]
    
    hallucination_metric = HallucinationMetric(threshold=0.9)
    
    test_case = LLMTestCase(
        input="Create superuser with email specific@testclub.com",
        actual_output=str(superuser_step.outputs),
        context=context
    )
    
    assert_test(test_case, [hallucination_metric])
```

- [ ] **Step 4: Run hallucination tests**

Run:
```bash
cd backend
pytest tests/deepeval/test_workflow_hallucination.py -v -m deepeval
```

Expected: 2 tests PASS/SKIPPED

- [ ] **Step 5: Write toxicity tests**

Create `backend/tests/deepeval/test_workflow_toxicity.py`:

```python
import pytest
from deepeval import assert_test
from deepeval.metrics import ToxicityMetric, BiasMetric
from deepeval.test_case import LLMTestCase
from app.workflows.teesheet_onboarding import create_teesheet_onboarding_template
from app.services.workflow_orchestrator import WorkflowOrchestrator


@pytest.mark.deepeval
@pytest.mark.asyncio
async def test_config_generation_is_not_toxic(
    db_session,
    session,
    skip_if_no_deepeval_key
):
    """Test that generated configurations contain no toxic content."""
    # Setup
    template = create_teesheet_onboarding_template(db_session)
    orchestrator = WorkflowOrchestrator(db_session, None)
    
    # Create workflow
    workflow_run = orchestrator.create_workflow_run(
        template=template,
        session_id=session.id,
        input_data={
            "club_name": "Riverside Golf Club",
            "club_id": "RGC001",
            "contact_email": "admin@riverside.com",
            "contact_name": "Admin User",
            "facility_type": "golf_course",
            "modules": ["member"]
        },
        user_id=1
    )
    
    # Execute
    result = await orchestrator.execute_workflow(workflow_run.id)
    
    # Get all LLM-generated outputs
    config_step = next(
        step for step in workflow_run.step_executions
        if step.step_name == "config_setup"
    )
    
    # Check toxicity
    toxicity_metric = ToxicityMetric(threshold=0.7)
    
    test_case = LLMTestCase(
        input="Generate club configuration",
        actual_output=str(config_step.outputs)
    )
    
    assert_test(test_case, [toxicity_metric])


@pytest.mark.deepeval
@pytest.mark.asyncio
async def test_approval_prompts_are_not_biased(
    db_session,
    session,
    skip_if_no_deepeval_key
):
    """Test that approval prompts shown to humans are unbiased."""
    # Setup
    template = create_teesheet_onboarding_template(db_session)
    orchestrator = WorkflowOrchestrator(db_session, None)
    
    # Create workflow
    workflow_run = orchestrator.create_workflow_run(
        template=template,
        session_id=session.id,
        input_data={
            "club_name": "International Golf Club",
            "club_id": "IGC001",
            "contact_email": "admin@intgolf.com",
            "contact_name": "Admin User",
            "facility_type": "golf_course",
            "modules": []
        },
        user_id=1
    )
    
    # Execute to approval gate
    result = await orchestrator.execute_workflow(workflow_run.id)
    
    # Get approval prompt
    db_session.refresh(workflow_run)
    approval_prompt = workflow_run.approval_prompt
    
    # Check for bias
    bias_metric = BiasMetric(threshold=0.7)
    
    test_case = LLMTestCase(
        input="Generate approval prompt for configuration review",
        actual_output=approval_prompt if approval_prompt else "No approval prompt generated"
    )
    
    assert_test(test_case, [bias_metric])
```

- [ ] **Step 6: Run all DeepEval tests**

Run:
```bash
cd backend
pytest tests/deepeval/ -v -m deepeval
```

Expected: 6 tests PASS/SKIPPED

- [ ] **Step 7: Commit**

```bash
git add backend/tests/deepeval/
git commit -m "test: add DeepEval workflow test suite

- Add correctness tests for onboarding workflow:
  - Config generation correctness
  - Input validation
- Add hallucination tests:
  - No hallucinated modules
  - Correct email usage
- Add toxicity/bias tests:
  - Generated configs are non-toxic
  - Approval prompts are unbiased
- All tests passing (6/6) or skipped if no API key

DeepEval tests validate:
- Workflow outputs match requirements
- No hallucinated data
- No toxic/biased content in LLM outputs
- Approval prompts are fair and neutral"
```

---

## Task 5: Prompt Template Versioning

**Files:**
- Create: `backend/app/models/prompt_template.py`
- Create: `backend/tests/unit/models/test_prompt_template.py`
- Create: `backend/alembic/versions/xxxx_add_prompt_templates.py`

- [ ] **Step 1: Write test for prompt template model**

Create `backend/tests/unit/models/test_prompt_template.py`:

```python
import pytest
from datetime import datetime, timezone
from app.models.prompt_template import PromptTemplate, PromptTemplateVersion


def test_create_prompt_template(db_session):
    """Should create prompt template with initial version."""
    template = PromptTemplate(
        name="teesheet_config_generation",
        description="Generate club configuration for teesheet onboarding",
        current_version_id=None,
        created_at=datetime.now(timezone.utc)
    )
    
    db_session.add(template)
    db_session.commit()
    
    assert template.id is not None
    assert template.name == "teesheet_config_generation"


def test_create_prompt_template_version(db_session):
    """Should create version of prompt template."""
    # Create template
    template = PromptTemplate(
        name="test_template",
        description="Test template",
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(template)
    db_session.commit()
    
    # Create version
    version = PromptTemplateVersion(
        template_id=template.id,
        version_number=1,
        prompt_text="You are a helpful assistant. Generate config for {{club_name}}.",
        variables={"club_name": "string", "club_id": "string"},
        is_active=True,
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(version)
    db_session.commit()
    
    assert version.id is not None
    assert version.version_number == 1
    assert "{{club_name}}" in version.prompt_text


def test_prompt_template_version_metrics(db_session):
    """Should track metrics for prompt template version."""
    # Create template and version
    template = PromptTemplate(
        name="test_template",
        description="Test",
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(template)
    db_session.commit()
    
    version = PromptTemplateVersion(
        template_id=template.id,
        version_number=1,
        prompt_text="Test prompt",
        variables={},
        is_active=True,
        usage_count=10,
        success_count=8,
        avg_latency_ms=250.5,
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(version)
    db_session.commit()
    
    # Calculate success rate
    success_rate = version.success_count / version.usage_count
    assert success_rate == 0.8
    assert version.avg_latency_ms == 250.5


def test_get_active_version(db_session):
    """Should retrieve active version of template."""
    # Create template
    template = PromptTemplate(
        name="test_template",
        description="Test",
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(template)
    db_session.commit()
    
    # Create old version (inactive)
    old_version = PromptTemplateVersion(
        template_id=template.id,
        version_number=1,
        prompt_text="Old prompt",
        variables={},
        is_active=False,
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(old_version)
    
    # Create new version (active)
    new_version = PromptTemplateVersion(
        template_id=template.id,
        version_number=2,
        prompt_text="New prompt",
        variables={},
        is_active=True,
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(new_version)
    db_session.commit()
    
    # Query active version
    active = db_session.query(PromptTemplateVersion).filter(
        PromptTemplateVersion.template_id == template.id,
        PromptTemplateVersion.is_active == True
    ).first()
    
    assert active.version_number == 2
    assert active.prompt_text == "New prompt"
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd backend
pytest tests/unit/models/test_prompt_template.py -v
```

Expected: FAIL with "No module named 'app.models.prompt_template'"

- [ ] **Step 3: Create prompt template models**

Create `backend/app/models/prompt_template.py`:

```python
from sqlalchemy import Column, Integer, String, Text, JSON, Boolean, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from app.database import Base


class PromptTemplate(Base):
    """Prompt template for LLM interactions with versioning support.
    
    Attributes:
        id: Primary key
        name: Unique template identifier (e.g., 'teesheet_config_generation')
        description: Human-readable description
        current_version_id: ID of currently active version
        created_at: Creation timestamp
        versions: All versions of this template
    """
    
    __tablename__ = "prompt_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    current_version_id = Column(Integer, ForeignKey("prompt_template_versions.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    versions = relationship("PromptTemplateVersion", back_populates="template", foreign_keys="PromptTemplateVersion.template_id")


class PromptTemplateVersion(Base):
    """Version of a prompt template with metrics tracking.
    
    Attributes:
        id: Primary key
        template_id: Foreign key to parent template
        version_number: Sequential version number (1, 2, 3, ...)
        prompt_text: Actual prompt with {{variable}} placeholders
        variables: Schema of variables (JSON dict)
        is_active: Whether this version is currently in use
        usage_count: Number of times this version was used
        success_count: Number of successful executions
        avg_latency_ms: Average LLM response latency
        created_at: Version creation timestamp
        created_by: User ID who created this version
        notes: Optional notes about this version
        template: Relationship to parent template
    """
    
    __tablename__ = "prompt_template_versions"
    
    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("prompt_templates.id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    prompt_text = Column(Text, nullable=False)
    variables = Column(JSON, nullable=False, default=dict)  # {"var_name": "type"}
    is_active = Column(Boolean, default=False, nullable=False)
    usage_count = Column(Integer, default=0, nullable=False)
    success_count = Column(Integer, default=0, nullable=False)
    avg_latency_ms = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    notes = Column(Text, nullable=True)
    
    # Relationships
    template = relationship("PromptTemplate", back_populates="versions", foreign_keys=[template_id])
    
    def calculate_success_rate(self) -> Optional[float]:
        """Calculate success rate for this version.
        
        Returns:
            Success rate (0.0-1.0) or None if no usage
        """
        if self.usage_count == 0:
            return None
        return self.success_count / self.usage_count
    
    def update_metrics(
        self,
        success: bool,
        latency_ms: float
    ):
        """Update metrics after prompt execution.
        
        Args:
            success: Whether execution succeeded
            latency_ms: LLM response latency in milliseconds
        """
        self.usage_count += 1
        if success:
            self.success_count += 1
        
        # Update rolling average latency
        if self.avg_latency_ms is None:
            self.avg_latency_ms = latency_ms
        else:
            # Weighted average (more weight to recent latencies)
            self.avg_latency_ms = (self.avg_latency_ms * 0.9) + (latency_ms * 0.1)
```

- [ ] **Step 4: Create database migration**

Run:
```bash
cd backend
alembic revision -m "add prompt templates and versions"
```

Edit migration file:

```python
def upgrade():
    # Create prompt_templates table
    op.create_table(
        'prompt_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('current_version_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_prompt_templates_id', 'prompt_templates', ['id'])
    op.create_index('ix_prompt_templates_name', 'prompt_templates', ['name'], unique=True)
    
    # Create prompt_template_versions table
    op.create_table(
        'prompt_template_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('prompt_text', sa.Text(), nullable=False),
        sa.Column('variables', sa.JSON(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('usage_count', sa.Integer(), nullable=False),
        sa.Column('success_count', sa.Integer(), nullable=False),
        sa.Column('avg_latency_ms', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['template_id'], ['prompt_templates.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_prompt_template_versions_id', 'prompt_template_versions', ['id'])
    
    # Add foreign key for current_version_id
    op.create_foreign_key(
        'fk_prompt_templates_current_version',
        'prompt_templates', 'prompt_template_versions',
        ['current_version_id'], ['id']
    )


def downgrade():
    op.drop_constraint('fk_prompt_templates_current_version', 'prompt_templates', type_='foreignkey')
    op.drop_index('ix_prompt_template_versions_id', table_name='prompt_template_versions')
    op.drop_table('prompt_template_versions')
    op.drop_index('ix_prompt_templates_name', table_name='prompt_templates')
    op.drop_index('ix_prompt_templates_id', table_name='prompt_templates')
    op.drop_table('prompt_templates')
```

Run migration:
```bash
alembic upgrade head
```

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
cd backend
pytest tests/unit/models/test_prompt_template.py -v
```

Expected: 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/prompt_template.py backend/tests/unit/models/test_prompt_template.py backend/alembic/versions/
git commit -m "feat: add prompt template versioning models

- Create PromptTemplate model for template metadata
- Create PromptTemplateVersion model with:
  - Version number tracking
  - Prompt text with {{variable}} placeholders
  - Variable schema (JSON)
  - Active/inactive status
  - Usage metrics (count, success rate, latency)
- Add database migration for both tables
- All tests passing (4/4)

Enables:
- A/B testing of prompts
- Metric-driven prompt optimization
- Rollback to previous prompt versions
- Track which prompts perform best"
```

---

## Task 6: Analytics Dashboard (Backend API)

**Files:**
- Create: `backend/app/services/analytics_service.py`
- Create: `backend/app/api/analytics.py`
- Create: `backend/app/schemas/analytics.py`
- Create: `backend/tests/unit/services/test_analytics_service.py`
- Create: `backend/tests/unit/api/test_analytics.py`

- [ ] **Step 1: Write test for analytics service**

Create `backend/tests/unit/services/test_analytics_service.py`:

```python
import pytest
from datetime import datetime, timezone, timedelta
from app.services.analytics_service import AnalyticsService
from app.models.workflow import WorkflowRun, WorkflowRunStatus


def test_get_workflow_success_rate(db_session, workflow_template_fixture):
    """Should calculate success rate across all workflow runs."""
    # Create workflow runs with different statuses
    for i in range(10):
        status = WorkflowRunStatus.COMPLETED if i < 7 else WorkflowRunStatus.FAILED
        run = WorkflowRun(
            template_id=workflow_template_fixture.id,
            session_id=1,
            user_id=1,
            status=status,
            input_data={},
            created_at=datetime.now(timezone.utc)
        )
        db_session.add(run)
    db_session.commit()
    
    service = AnalyticsService(db_session)
    success_rate = service.get_workflow_success_rate(workflow_template_fixture.id)
    
    assert success_rate == 0.7  # 7 out of 10 succeeded


def test_get_average_workflow_duration(db_session, workflow_template_fixture):
    """Should calculate average duration for completed workflows."""
    # Create completed workflows with different durations
    now = datetime.now(timezone.utc)
    for i in range(5):
        run = WorkflowRun(
            template_id=workflow_template_fixture.id,
            session_id=1,
            user_id=1,
            status=WorkflowRunStatus.COMPLETED,
            input_data={},
            created_at=now - timedelta(seconds=300),
            started_at=now - timedelta(seconds=300),
            completed_at=now - timedelta(seconds=300 - (i * 60))  # 60s, 120s, 180s, 240s, 300s
        )
        db_session.add(run)
    db_session.commit()
    
    service = AnalyticsService(db_session)
    avg_duration = service.get_average_workflow_duration(workflow_template_fixture.id)
    
    # Average: (60 + 120 + 180 + 240 + 300) / 5 = 180 seconds
    assert avg_duration == 180.0


def test_get_step_failure_analysis(db_session, workflow_run_factory, workflow_step_execution_factory):
    """Should identify which steps fail most frequently."""
    workflow_run = workflow_run_factory()
    
    # Create step executions: init succeeds, config fails often
    for i in range(10):
        # Init step - always succeeds
        workflow_step_execution_factory(
            workflow_run_id=workflow_run.id,
            step_name="init_database",
            status="COMPLETED"
        )
        
        # Config step - fails 30% of the time
        status = "FAILED" if i < 3 else "COMPLETED"
        workflow_step_execution_factory(
            workflow_run_id=workflow_run.id,
            step_name="config_setup",
            status=status
        )
    
    service = AnalyticsService(db_session)
    failures = service.get_step_failure_analysis(workflow_run.template_id)
    
    # Should return step failure rates
    assert len(failures) == 2
    assert failures["config_setup"]["failure_rate"] == 0.3
    assert failures["init_database"]["failure_rate"] == 0.0


def test_get_prompt_version_comparison(db_session):
    """Should compare performance metrics across prompt versions."""
    from app.models.prompt_template import PromptTemplate, PromptTemplateVersion
    
    # Create template with 2 versions
    template = PromptTemplate(
        name="test_prompt",
        description="Test",
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(template)
    db_session.commit()
    
    # Version 1: 70% success rate
    v1 = PromptTemplateVersion(
        template_id=template.id,
        version_number=1,
        prompt_text="V1",
        variables={},
        is_active=False,
        usage_count=100,
        success_count=70,
        avg_latency_ms=200.0,
        created_at=datetime.now(timezone.utc)
    )
    
    # Version 2: 85% success rate
    v2 = PromptTemplateVersion(
        template_id=template.id,
        version_number=2,
        prompt_text="V2",
        variables={},
        is_active=True,
        usage_count=100,
        success_count=85,
        avg_latency_ms=180.0,
        created_at=datetime.now(timezone.utc)
    )
    
    db_session.add_all([v1, v2])
    db_session.commit()
    
    service = AnalyticsService(db_session)
    comparison = service.get_prompt_version_comparison(template.id)
    
    assert len(comparison) == 2
    assert comparison[0]["version_number"] == 1
    assert comparison[0]["success_rate"] == 0.7
    assert comparison[1]["version_number"] == 2
    assert comparison[1]["success_rate"] == 0.85
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd backend
pytest tests/unit/services/test_analytics_service.py -v
```

Expected: FAIL with "No module named 'app.services.analytics_service'"

- [ ] **Step 3: Create analytics service**

Create `backend/app/services/analytics_service.py`:

```python
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.workflow import WorkflowRun, WorkflowStepExecution, WorkflowRunStatus
from app.models.prompt_template import PromptTemplate, PromptTemplateVersion


class AnalyticsService:
    """Service for workflow and prompt analytics.
    
    Queries workflow execution data and prompt template metrics for analytics dashboard.
    
    Usage:
        service = AnalyticsService(db_session)
        
        # Workflow analytics
        success_rate = service.get_workflow_success_rate(template_id)
        avg_duration = service.get_average_workflow_duration(template_id)
        failures = service.get_step_failure_analysis(template_id)
        
        # Prompt analytics
        comparison = service.get_prompt_version_comparison(template_id)
    """
    
    def __init__(self, db: Session):
        """Initialize analytics service.
        
        Args:
            db: Database session
        """
        self.db = db
    
    def get_workflow_success_rate(
        self,
        template_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> float:
        """Calculate workflow success rate.
        
        Args:
            template_id: Workflow template ID
            start_date: Optional start date for filtering
            end_date: Optional end date for filtering
            
        Returns:
            Success rate (0.0-1.0)
        """
        query = self.db.query(WorkflowRun).filter(
            WorkflowRun.template_id == template_id,
            WorkflowRun.status.in_([
                WorkflowRunStatus.COMPLETED,
                WorkflowRunStatus.FAILED
            ])
        )
        
        if start_date:
            query = query.filter(WorkflowRun.created_at >= start_date)
        if end_date:
            query = query.filter(WorkflowRun.created_at <= end_date)
        
        total_count = query.count()
        if total_count == 0:
            return 0.0
        
        success_count = query.filter(
            WorkflowRun.status == WorkflowRunStatus.COMPLETED
        ).count()
        
        return success_count / total_count
    
    def get_average_workflow_duration(
        self,
        template_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Optional[float]:
        """Calculate average workflow duration in seconds.
        
        Args:
            template_id: Workflow template ID
            start_date: Optional start date for filtering
            end_date: Optional end date for filtering
            
        Returns:
            Average duration in seconds, or None if no completed workflows
        """
        query = self.db.query(WorkflowRun).filter(
            WorkflowRun.template_id == template_id,
            WorkflowRun.status == WorkflowRunStatus.COMPLETED,
            WorkflowRun.started_at.isnot(None),
            WorkflowRun.completed_at.isnot(None)
        )
        
        if start_date:
            query = query.filter(WorkflowRun.created_at >= start_date)
        if end_date:
            query = query.filter(WorkflowRun.created_at <= end_date)
        
        workflows = query.all()
        
        if not workflows:
            return None
        
        durations = [
            (w.completed_at - w.started_at).total_seconds()
            for w in workflows
        ]
        
        return sum(durations) / len(durations)
    
    def get_step_failure_analysis(
        self,
        template_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Dict[str, Any]]:
        """Analyze which workflow steps fail most frequently.
        
        Args:
            template_id: Workflow template ID
            start_date: Optional start date for filtering
            end_date: Optional end date for filtering
            
        Returns:
            Dict mapping step names to failure analysis
        """
        # Get all step executions for this template's workflow runs
        query = self.db.query(WorkflowStepExecution).join(
            WorkflowRun,
            WorkflowStepExecution.workflow_run_id == WorkflowRun.id
        ).filter(
            WorkflowRun.template_id == template_id
        )
        
        if start_date:
            query = query.filter(WorkflowRun.created_at >= start_date)
        if end_date:
            query = query.filter(WorkflowRun.created_at <= end_date)
        
        executions = query.all()
        
        # Group by step name and count successes/failures
        step_stats: Dict[str, Dict[str, int]] = {}
        
        for execution in executions:
            step_name = execution.step_name
            if step_name not in step_stats:
                step_stats[step_name] = {"total": 0, "failed": 0}
            
            step_stats[step_name]["total"] += 1
            if execution.status == "FAILED":
                step_stats[step_name]["failed"] += 1
        
        # Calculate failure rates
        analysis = {}
        for step_name, stats in step_stats.items():
            analysis[step_name] = {
                "total_executions": stats["total"],
                "failed_executions": stats["failed"],
                "failure_rate": stats["failed"] / stats["total"] if stats["total"] > 0 else 0.0
            }
        
        return analysis
    
    def get_prompt_version_comparison(
        self,
        template_id: int
    ) -> List[Dict[str, Any]]:
        """Compare performance metrics across prompt template versions.
        
        Args:
            template_id: Prompt template ID
            
        Returns:
            List of version metrics sorted by version number
        """
        versions = self.db.query(PromptTemplateVersion).filter(
            PromptTemplateVersion.template_id == template_id
        ).order_by(PromptTemplateVersion.version_number).all()
        
        comparison = []
        for version in versions:
            success_rate = version.calculate_success_rate()
            comparison.append({
                "version_number": version.version_number,
                "usage_count": version.usage_count,
                "success_count": version.success_count,
                "success_rate": success_rate if success_rate is not None else 0.0,
                "avg_latency_ms": version.avg_latency_ms,
                "is_active": version.is_active,
                "created_at": version.created_at.isoformat()
            })
        
        return comparison
    
    def get_dashboard_summary(
        self,
        template_id: int
    ) -> Dict[str, Any]:
        """Get summary statistics for dashboard.
        
        Args:
            template_id: Workflow template ID
            
        Returns:
            Dashboard summary dict
        """
        return {
            "success_rate": self.get_workflow_success_rate(template_id),
            "avg_duration_seconds": self.get_average_workflow_duration(template_id),
            "step_failures": self.get_step_failure_analysis(template_id),
            "total_runs": self.db.query(WorkflowRun).filter(
                WorkflowRun.template_id == template_id
            ).count()
        }
```

- [ ] **Step 4: Create API schemas**

Create `backend/app/schemas/analytics.py`:

```python
from pydantic import BaseModel
from typing import Dict, List, Optional


class WorkflowAnalyticsResponse(BaseModel):
    """Response schema for workflow analytics."""
    success_rate: float
    avg_duration_seconds: Optional[float]
    total_runs: int


class StepFailureAnalysis(BaseModel):
    """Step failure analysis."""
    step_name: str
    total_executions: int
    failed_executions: int
    failure_rate: float


class PromptVersionMetrics(BaseModel):
    """Metrics for a prompt template version."""
    version_number: int
    usage_count: int
    success_count: int
    success_rate: float
    avg_latency_ms: Optional[float]
    is_active: bool
    created_at: str


class DashboardSummaryResponse(BaseModel):
    """Dashboard summary response."""
    success_rate: float
    avg_duration_seconds: Optional[float]
    step_failures: Dict[str, Dict[str, float]]
    total_runs: int
```

- [ ] **Step 5: Create analytics API endpoints**

Create `backend/app/api/analytics.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.services.analytics_service import AnalyticsService
from app.schemas.analytics import (
    WorkflowAnalyticsResponse,
    StepFailureAnalysis,
    PromptVersionMetrics,
    DashboardSummaryResponse
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/workflows/{template_id}/success-rate", response_model=WorkflowAnalyticsResponse)
async def get_workflow_success_rate(
    template_id: int,
    db: Session = Depends(get_db)
):
    """Get workflow success rate and basic metrics."""
    service = AnalyticsService(db)
    
    return {
        "success_rate": service.get_workflow_success_rate(template_id),
        "avg_duration_seconds": service.get_average_workflow_duration(template_id),
        "total_runs": len(db.query(WorkflowRun).filter(WorkflowRun.template_id == template_id).all())
    }


@router.get("/workflows/{template_id}/step-failures", response_model=List[StepFailureAnalysis])
async def get_step_failure_analysis(
    template_id: int,
    db: Session = Depends(get_db)
):
    """Get step-by-step failure analysis."""
    service = AnalyticsService(db)
    analysis = service.get_step_failure_analysis(template_id)
    
    return [
        {
            "step_name": step_name,
            **stats
        }
        for step_name, stats in analysis.items()
    ]


@router.get("/prompts/{template_id}/version-comparison", response_model=List[PromptVersionMetrics])
async def get_prompt_version_comparison(
    template_id: int,
    db: Session = Depends(get_db)
):
    """Compare performance across prompt template versions."""
    service = AnalyticsService(db)
    return service.get_prompt_version_comparison(template_id)


@router.get("/dashboard/{template_id}", response_model=DashboardSummaryResponse)
async def get_dashboard_summary(
    template_id: int,
    db: Session = Depends(get_db)
):
    """Get dashboard summary statistics."""
    service = AnalyticsService(db)
    return service.get_dashboard_summary(template_id)
```

- [ ] **Step 6: Run tests to verify they pass**

Run:
```bash
cd backend
pytest tests/unit/services/test_analytics_service.py -v
```

Expected: 4 tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/analytics_service.py backend/app/api/analytics.py backend/app/schemas/analytics.py backend/tests/unit/services/test_analytics_service.py
git commit -m "feat: add analytics dashboard backend API

- Create AnalyticsService with workflow and prompt analytics:
  - get_workflow_success_rate() - calculate completion rate
  - get_average_workflow_duration() - avg execution time
  - get_step_failure_analysis() - identify failing steps
  - get_prompt_version_comparison() - A/B test results
  - get_dashboard_summary() - all metrics in one call
- Create analytics API endpoints:
  - GET /analytics/workflows/{id}/success-rate
  - GET /analytics/workflows/{id}/step-failures
  - GET /analytics/prompts/{id}/version-comparison
  - GET /analytics/dashboard/{id}
- Create Pydantic schemas for responses
- All tests passing (4/4)

Powers analytics dashboard with:
- Real-time workflow success metrics
- Step-level failure analysis
- Prompt version performance comparison
- Executive dashboard summaries"
```

---

## Task 7: Analytics Dashboard (Frontend Components)

**Files:**
- Create: `frontend/src/components/analytics/WorkflowSuccessRate.tsx`
- Create: `frontend/src/components/analytics/WorkflowDurationChart.tsx`
- Create: `frontend/src/components/analytics/StepFailureAnalysis.tsx`
- Create: `frontend/src/components/analytics/PromptVersionComparison.tsx`
- Create: `frontend/src/pages/analytics/dashboard.tsx`
- Create: `frontend/src/lib/api/analytics.ts`

- [ ] **Step 1: Create analytics API client**

Create `frontend/src/lib/api/analytics.ts`:

```typescript
import { api } from './client';

export interface WorkflowAnalytics {
  success_rate: number;
  avg_duration_seconds: number | null;
  total_runs: number;
}

export interface StepFailure {
  step_name: string;
  total_executions: number;
  failed_executions: number;
  failure_rate: number;
}

export interface PromptVersionMetrics {
  version_number: number;
  usage_count: number;
  success_count: number;
  success_rate: number;
  avg_latency_ms: number | null;
  is_active: boolean;
  created_at: string;
}

export interface DashboardSummary {
  success_rate: number;
  avg_duration_seconds: number | null;
  step_failures: Record<string, { total_executions: number; failed_executions: number; failure_rate: number }>;
  total_runs: number;
}

export const analyticsApi = {
  getWorkflowSuccessRate: (templateId: number) =>
    api.get<WorkflowAnalytics>(`/analytics/workflows/${templateId}/success-rate`),
  
  getStepFailures: (templateId: number) =>
    api.get<StepFailure[]>(`/analytics/workflows/${templateId}/step-failures`),
  
  getPromptVersionComparison: (templateId: number) =>
    api.get<PromptVersionMetrics[]>(`/analytics/prompts/${templateId}/version-comparison`),
  
  getDashboardSummary: (templateId: number) =>
    api.get<DashboardSummary>(`/analytics/dashboard/${templateId}`)
};
```

- [ ] **Step 2: Create WorkflowSuccessRate component**

Create `frontend/src/components/analytics/WorkflowSuccessRate.tsx`:

```typescript
import React, { useEffect, useState } from 'react';
import { analyticsApi, WorkflowAnalytics } from '@/lib/api/analytics';

interface WorkflowSuccessRateProps {
  templateId: number;
}

export const WorkflowSuccessRate: React.FC<WorkflowSuccessRateProps> = ({ templateId }) => {
  const [data, setData] = useState<WorkflowAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const response = await analyticsApi.getWorkflowSuccessRate(templateId);
        setData(response.data);
      } catch (err) {
        setError('Failed to load success rate');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [templateId]);

  if (loading) return <div className="animate-pulse">Loading...</div>;
  if (error) return <div className="text-red-600">{error}</div>;
  if (!data) return null;

  const successPercentage = (data.success_rate * 100).toFixed(1);
  const avgDurationMinutes = data.avg_duration_seconds 
    ? (data.avg_duration_seconds / 60).toFixed(1) 
    : 'N/A';

  return (
    <div className="bg-white shadow rounded-lg p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Workflow Performance</h3>
      
      <div className="grid grid-cols-3 gap-4">
        <div>
          <p className="text-sm text-gray-600">Success Rate</p>
          <p className="text-3xl font-bold text-green-600">{successPercentage}%</p>
        </div>
        
        <div>
          <p className="text-sm text-gray-600">Avg Duration</p>
          <p className="text-3xl font-bold text-blue-600">{avgDurationMinutes} min</p>
        </div>
        
        <div>
          <p className="text-sm text-gray-600">Total Runs</p>
          <p className="text-3xl font-bold text-gray-900">{data.total_runs}</p>
        </div>
      </div>
    </div>
  );
};
```

- [ ] **Step 3: Create StepFailureAnalysis component**

Create `frontend/src/components/analytics/StepFailureAnalysis.tsx`:

```typescript
import React, { useEffect, useState } from 'react';
import { analyticsApi, StepFailure } from '@/lib/api/analytics';

interface StepFailureAnalysisProps {
  templateId: number;
}

export const StepFailureAnalysis: React.FC<StepFailureAnalysisProps> = ({ templateId }) => {
  const [data, setData] = useState<StepFailure[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const response = await analyticsApi.getStepFailures(templateId);
        // Sort by failure rate descending
        const sorted = response.data.sort((a, b) => b.failure_rate - a.failure_rate);
        setData(sorted);
      } catch (err) {
        console.error('Failed to load step failures', err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [templateId]);

  if (loading) return <div>Loading step analysis...</div>;

  return (
    <div className="bg-white shadow rounded-lg p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Step Failure Analysis</h3>
      
      <div className="space-y-4">
        {data.map((step) => (
          <div key={step.step_name} className="border-l-4 border-gray-200 pl-4">
            <div className="flex justify-between items-center mb-2">
              <span className="font-medium text-gray-900">{step.step_name}</span>
              <span className={`text-sm font-semibold ${
                step.failure_rate > 0.1 ? 'text-red-600' : 'text-green-600'
              }`}>
                {(step.failure_rate * 100).toFixed(1)}% failure rate
              </span>
            </div>
            
            <div className="w-full bg-gray-200 rounded-full h-2.5">
              <div 
                className={`h-2.5 rounded-full ${
                  step.failure_rate > 0.1 ? 'bg-red-600' : 'bg-green-600'
                }`}
                style={{ width: `${step.failure_rate * 100}%` }}
              />
            </div>
            
            <p className="text-xs text-gray-600 mt-1">
              {step.failed_executions} failures out of {step.total_executions} executions
            </p>
          </div>
        ))}
      </div>
    </div>
  );
};
```

- [ ] **Step 4: Create PromptVersionComparison component**

Create `frontend/src/components/analytics/PromptVersionComparison.tsx`:

```typescript
import React, { useEffect, useState } from 'react';
import { analyticsApi, PromptVersionMetrics } from '@/lib/api/analytics';

interface PromptVersionComparisonProps {
  templateId: number;
}

export const PromptVersionComparison: React.FC<PromptVersionComparisonProps> = ({ templateId }) => {
  const [data, setData] = useState<PromptVersionMetrics[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const response = await analyticsApi.getPromptVersionComparison(templateId);
        setData(response.data);
      } catch (err) {
        console.error('Failed to load prompt versions', err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [templateId]);

  if (loading) return <div>Loading prompt versions...</div>;

  return (
    <div className="bg-white shadow rounded-lg p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Prompt Version Performance</h3>
      
      <table className="min-w-full divide-y divide-gray-200">
        <thead>
          <tr>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Version</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Usage</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Success Rate</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Avg Latency</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200">
          {data.map((version) => (
            <tr key={version.version_number} className={version.is_active ? 'bg-blue-50' : ''}>
              <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                v{version.version_number}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                {version.usage_count}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm">
                <span className={`font-semibold ${
                  version.success_rate > 0.8 ? 'text-green-600' : 'text-yellow-600'
                }`}>
                  {(version.success_rate * 100).toFixed(1)}%
                </span>
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                {version.avg_latency_ms?.toFixed(0) || 'N/A'} ms
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm">
                {version.is_active && (
                  <span className="px-2 py-1 text-xs font-semibold rounded-full bg-blue-100 text-blue-800">
                    Active
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
```

- [ ] **Step 5: Create analytics dashboard page**

Create `frontend/src/pages/analytics/dashboard.tsx`:

```typescript
import React from 'react';
import { useRouter } from 'next/router';
import { WorkflowSuccessRate } from '@/components/analytics/WorkflowSuccessRate';
import { StepFailureAnalysis } from '@/components/analytics/StepFailureAnalysis';
import { PromptVersionComparison } from '@/components/analytics/PromptVersionComparison';

export default function AnalyticsDashboard() {
  const router = useRouter();
  const { templateId } = router.query;
  
  const numericTemplateId = templateId ? parseInt(templateId as string, 10) : null;

  if (!numericTemplateId) {
    return (
      <div className="flex items-center justify-center h-screen">
        <p className="text-gray-600">Select a workflow template to view analytics</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">Workflow Analytics Dashboard</h1>
          <p className="mt-2 text-sm text-gray-600">
            Monitor workflow performance and optimize prompts based on real data
          </p>
        </div>

        <div className="space-y-6">
          {/* Success Rate Summary */}
          <WorkflowSuccessRate templateId={numericTemplateId} />
          
          {/* Step Failure Analysis */}
          <StepFailureAnalysis templateId={numericTemplateId} />
          
          {/* Prompt Version Comparison */}
          <PromptVersionComparison templateId={numericTemplateId} />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Test frontend components**

Run frontend development server and verify:
```bash
cd frontend
npm run dev
```

Navigate to: `http://localhost:3000/analytics/dashboard?templateId=1`

Expected:
- Dashboard loads without errors
- Success rate displays correctly
- Step failures show with progress bars
- Prompt versions appear in table

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/analytics/ frontend/src/pages/analytics/ frontend/src/lib/api/analytics.ts
git commit -m "feat: add analytics dashboard frontend components

- Create analytics API client with TypeScript types
- Create WorkflowSuccessRate component:
  - Display success rate, avg duration, total runs
  - Color-coded metrics (green for success)
- Create StepFailureAnalysis component:
  - Bar chart visualization of failure rates
  - Sorted by failure rate descending
  - Highlights high-failure steps in red
- Create PromptVersionComparison component:
  - Table of all prompt versions
  - Success rate and latency comparison
  - Highlights active version
- Create analytics dashboard page:
  - Combines all components
  - Accepts templateId query param
  - Responsive grid layout

Dashboard provides:
- Real-time workflow performance monitoring
- Visual step failure analysis
- Prompt A/B test results
- Data-driven optimization insights"
```

---

## Task 8: Documentation

**Files:**
- Create: `backend/docs/phase-3-complete.md`
- Modify: `backend/README.md`

- [ ] **Step 1: Create Phase 3 completion documentation**

Create `backend/docs/phase-3-complete.md`:

```markdown
# Phase 3: Onboarding Workflow + Testing + Analytics - COMPLETE ✅

## Overview

Phase 3 adds complete teesheet onboarding workflow with approval gates, DeepEval testing suite, prompt versioning, and analytics dashboard.

## What Was Built

### 1. Teesheet Onboarding Workflow

**Purpose**: Automate club onboarding with human approval gates

**Components**:
- `app/workflows/teesheet_onboarding.py` - Complete workflow template
- 5-step workflow: init → superuser → config → approval → validate

**Workflow Steps**:
```
1. init_database (BRS tool)
   └─ Creates club-specific database
   
2. create_superuser (BRS tool)
   └─ Creates admin account
   
3. config_setup (LLM decision)
   └─ Generates club configuration
   
4. approval_gate_config (Human approval)
   └─ Reviews generated config before deployment
   
5. validate_config (BRS tool)
   └─ Validates configuration is correct
```

**Usage**:
```python
from app.workflows.teesheet_onboarding import create_teesheet_onboarding_template

template = create_teesheet_onboarding_template(db_session)

orchestrator = WorkflowOrchestrator(db_session, None)
workflow_run = orchestrator.create_workflow_run(
    template=template,
    session_id=session.id,
    input_data={
        "club_name": "Pebble Beach Golf Links",
        "club_id": "PB001",
        "contact_email": "admin@pebblebeach.com",
        "contact_name": "John Smith",
        "facility_type": "golf_course",
        "modules": ["member", "sms"]
    },
    user_id=1
)

result = await orchestrator.execute_workflow(workflow_run.id)
```

### 2. Approval Gate System

**Purpose**: Human-in-the-loop for business decisions

**Components**:
- `app/services/approval_service.py` - Approval orchestration
- `WAITING_APPROVAL` status in WorkflowRun
- Approval fields: approval_data, approval_prompt, approved_by, approved_at

**Usage**:
```python
from app.services.approval_service import ApprovalService

service = ApprovalService(db_session)

# Request approval
service.request_approval(
    workflow_run_id=123,
    approval_data={"config": {...}},
    approval_prompt="Please review the generated configuration"
)

# Process approval
service.process_approval(
    workflow_run_id=123,
    approved=True,
    user_id=1,
    notes="Config looks good"
)

# Query pending approvals
pending = service.get_pending_approvals()
```

**Approval Gates Used For**:
- Configuration review before deployment
- Green fee rate approval
- Booking rule validation
- Any business decision requiring human judgment

### 3. DeepEval Testing Suite

**Purpose**: Test workflow correctness, hallucination, and toxicity

**Components**:
- `tests/deepeval/test_workflow_correctness.py` - Correctness tests
- `tests/deepeval/test_workflow_hallucination.py` - Hallucination tests
- `tests/deepeval/test_workflow_toxicity.py` - Toxicity/bias tests

**Running Tests**:
```bash
# Set DeepEval API key
export DEEPEVAL_API_KEY=your_key

# Run all DeepEval tests
pytest tests/deepeval/ -v -m deepeval

# Run specific test category
pytest tests/deepeval/test_workflow_correctness.py -v
```

**Test Coverage**:
- ✅ Config generation correctness
- ✅ Input validation
- ✅ No hallucinated modules
- ✅ Correct email usage
- ✅ Non-toxic outputs
- ✅ Unbiased approval prompts

### 4. Prompt Template Versioning

**Purpose**: A/B test prompts and track performance

**Components**:
- `app/models/prompt_template.py` - PromptTemplate + PromptTemplateVersion models
- Database tables: `prompt_templates`, `prompt_template_versions`

**Usage**:
```python
from app.models.prompt_template import PromptTemplate, PromptTemplateVersion

# Create template
template = PromptTemplate(
    name="teesheet_config_generation",
    description="Generate club configuration"
)
db.add(template)
db.commit()

# Create version 1
v1 = PromptTemplateVersion(
    template_id=template.id,
    version_number=1,
    prompt_text="Generate config for {{club_name}}",
    variables={"club_name": "string"},
    is_active=True
)
db.add(v1)
db.commit()

# Update metrics after usage
v1.update_metrics(success=True, latency_ms=250.5)
db.commit()

# Calculate success rate
success_rate = v1.calculate_success_rate()
```

**Metrics Tracked**:
- Usage count
- Success count
- Success rate
- Average latency
- Active/inactive status

### 5. Analytics Dashboard

**Purpose**: Monitor workflow performance and optimize prompts

**Components**:
- `app/services/analytics_service.py` - Analytics queries
- `app/api/analytics.py` - REST API endpoints
- `frontend/src/components/analytics/*` - React components
- `frontend/src/pages/analytics/dashboard.tsx` - Dashboard page

**API Endpoints**:
```
GET /analytics/workflows/{id}/success-rate
GET /analytics/workflows/{id}/step-failures
GET /analytics/prompts/{id}/version-comparison
GET /analytics/dashboard/{id}
```

**Dashboard Features**:
- Workflow success rate visualization
- Average workflow duration
- Step-by-step failure analysis
- Prompt version performance comparison
- Real-time metrics updates

**Accessing Dashboard**:
```
http://localhost:3000/analytics/dashboard?templateId=1
```

## System Capabilities After Phase 3

✅ Complete onboarding workflow automation  
✅ Human approval gates for business decisions  
✅ LLM output testing (correctness, hallucination, toxicity)  
✅ Prompt versioning with A/B testing  
✅ Analytics dashboard for performance monitoring  
✅ Data-driven prompt optimization  
✅ Step failure analysis for troubleshooting  

## Database Schema Updates

**New Tables**:
```sql
-- Prompt templates
CREATE TABLE prompt_templates (
    id INTEGER PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    current_version_id INTEGER,
    created_at DATETIME NOT NULL
);

-- Prompt template versions
CREATE TABLE prompt_template_versions (
    id INTEGER PRIMARY KEY,
    template_id INTEGER NOT NULL,
    version_number INTEGER NOT NULL,
    prompt_text TEXT NOT NULL,
    variables JSON NOT NULL,
    is_active BOOLEAN NOT NULL,
    usage_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    avg_latency_ms FLOAT,
    created_at DATETIME NOT NULL,
    created_by INTEGER,
    notes TEXT,
    FOREIGN KEY (template_id) REFERENCES prompt_templates(id),
    FOREIGN KEY (created_by) REFERENCES users(id)
);
```

**Modified Tables**:
```sql
-- workflow_runs table additions
ALTER TABLE workflow_runs ADD COLUMN approval_data JSON;
ALTER TABLE workflow_runs ADD COLUMN approval_prompt TEXT;
ALTER TABLE workflow_runs ADD COLUMN approved_by INTEGER;
ALTER TABLE workflow_runs ADD COLUMN approved_at DATETIME;
ALTER TABLE workflow_runs ADD COLUMN approval_notes TEXT;
```

## Test Coverage

- Unit tests: 8 tests passing (analytics + approval)
- Integration tests: 3 tests passing (onboarding workflow)
- DeepEval tests: 6 tests passing (correctness, hallucination, toxicity)
- Total: 17 tests passing

## Environment Variables

New variables in `.env`:
```bash
# DeepEval
DEEPEVAL_API_KEY=your_api_key_here
```

## Next Steps

**Phase 4: Production Hardening**
- Add Guardrails AI for content filtering
- Implement A/B testing framework
- Build reinforcement loop for optimization
- Add performance monitoring and alerts
- Production deployment configuration

## Critical Learnings

1. **Approval Gates Are Workflow Nodes** - Treat as first-class workflow steps with WAITING_APPROVAL status
2. **DeepEval Requires Real Executions** - Mock mode works but test against real BRS tools for production confidence
3. **Analytics Drives Optimization** - Track metrics from day 1, optimize based on data not intuition
4. **Prompt Versioning Is Essential** - Never deploy new prompts without versioning and A/B testing
5. **Step Failure Analysis Finds Issues Fast** - Visualizing step failures highlights problem areas immediately

## How to Verify Phase 3

```bash
# 1. Run all tests
cd backend
pytest tests/ -v

# 2. Run DeepEval tests (requires API key)
export DEEPEVAL_API_KEY=your_key
pytest tests/deepeval/ -v -m deepeval

# 3. Start backend
cd backend
uvicorn app.main:app --reload

# 4. Start frontend
cd frontend
npm run dev

# 5. Access analytics dashboard
open http://localhost:3000/analytics/dashboard?templateId=1

# 6. Create and execute onboarding workflow
# (Use API or frontend to test workflow execution)
```

## Files Modified/Created in Phase 3

**Created**:
- `app/workflows/teesheet_onboarding.py`
- `app/services/approval_service.py`
- `app/services/analytics_service.py`
- `app/models/prompt_template.py`
- `app/api/analytics.py`
- `app/schemas/analytics.py`
- `tests/deepeval/*` (6 test files)
- `tests/unit/services/test_approval_service.py`
- `tests/unit/services/test_analytics_service.py`
- `tests/unit/models/test_prompt_template.py`
- `tests/integration/test_teesheet_onboarding_e2e.py`
- `frontend/src/components/analytics/*` (4 components)
- `frontend/src/pages/analytics/dashboard.tsx`
- `frontend/src/lib/api/analytics.ts`

**Modified**:
- `app/models/workflow.py` (added approval fields)
- `requirements.txt` (added deepeval)
- `.env.example` (added DEEPEVAL_API_KEY)
```

- [ ] **Step 2: Update README with Phase 3 status**

Modify `backend/README.md`:

```markdown
# Add to "Development Phases" section

## Phase 3: Onboarding Workflow + Testing + Analytics ✅

**Completed**: 2026-05-01

- ✅ Teesheet onboarding workflow template (5 steps)
- ✅ Approval gate system (human-in-the-loop)
- ✅ DeepEval testing suite (correctness, hallucination, toxicity)
- ✅ Prompt template versioning with metrics
- ✅ Analytics dashboard (backend + frontend)
- ✅ Step failure analysis
- ✅ Prompt version performance comparison

**See**: `docs/phase-3-complete.md`
```

- [ ] **Step 3: Commit**

```bash
git add backend/docs/phase-3-complete.md backend/README.md
git commit -m "docs: add Phase 3 completion documentation

- Document complete onboarding workflow with code examples
- Document approval gate system and usage
- Document DeepEval testing suite
- Document prompt versioning and A/B testing
- Document analytics dashboard features
- List all database schema changes
- Provide verification checklist
- Update README with Phase 3 status

Phase 3 Complete: ✅
- 17 tests passing
- All systems operational
- Ready for Phase 4 (Production Hardening)"
```

---

## Phase 3 Complete! ✅

**Summary**: 8 of 8 tasks complete (100%)

**What We Build**:
- Teesheet onboarding workflow template
- Approval gate implementation (human-in-loop)
- DeepEval integration + test suite
- Prompt template versioning
- Analytics dashboard (backend + frontend)

**Ready for Phase 4**: Production Hardening (Guardrails AI, A/B testing, reinforcement loop)

---

## Phase 3 Dependencies

**Requires Phase 2 Complete**:
- Langfuse (for analytics queries)
- Instructor (for config generation)
- BRS Tool Gateway (for workflow steps)
- Mock Mode (for testing)

**New Dependencies**:
- DeepEval API key (for testing)
- Langfuse PostgreSQL access (for analytics)

---

## Critical Learnings

1. **Approval Gates Pause Execution** - Use WAITING_APPROVAL status + resume pattern
2. **DeepEval Tests Real Workflows** - Not mocks, test actual BRS tool execution
3. **Analytics Query Langfuse DB** - Direct PostgreSQL for performance
4. **Prompt Versioning Enables A/B** - Track metrics per version for optimization
5. **Onboarding is Multi-Step** - Sequential dependencies (init → superuser → config → validate)

