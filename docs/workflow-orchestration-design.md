# Workflow Orchestration Design

## Mapping Existing Architecture to Onboarding Needs

### What Already Exists (Keep & Reuse)

#### ✅ Core Infrastructure
- **AgenticService** - Orchestrates tool calling, handles LLM interaction
- **ApprovalService** - Human-in-the-loop approval gates (perfect for milestone reviews)
- **AgentState** - Tracks execution, prevents loops, deduplicates actions
- **MCPToolRegistry** - Connects to remote MCP servers (will add BRS tools)
- **Worker Service** - Background task execution
- **Database Models**:
  - `User`, `Session`, `Message` - conversation persistence
  - `WorkflowClassification` - workflow categorization
  - `WorkflowOutcome` - success/partial/failed/escalated/pending
  - `ToolCall` - tool execution tracking

#### ✅ Security & Safety
- Bash command allowlist
- Tool approval patterns (write operations require confirmation)
- Resource limits and connection pooling

#### ✅ Admin Infrastructure
- Admin analytics dashboard
- Workflow metrics and tracking
- User management with role-based access

### What We Need to Add (Extend)

#### 🆕 Workflow State Machine Models

```python
# New models to add to backend/app/models/models.py

class WorkflowTemplate(Base):
    """Reusable workflow definitions (e.g., 'teesheet_onboarding')"""
    __tablename__ = "workflow_templates"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)  # "teesheet_onboarding"
    description = Column(Text)
    version = Column(String(50), nullable=False)  # "1.0.0"
    
    # Workflow definition as JSON
    # Structure: {steps: [{id, name, type, config, dependencies}], gates: [...]}
    definition = Column(JSON, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WorkflowRun(Base):
    """Active workflow execution instance"""
    __tablename__ = "workflow_runs"
    
    id = Column(Integer, primary_key=True)
    template_id = Column(Integer, ForeignKey("workflow_templates.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    
    # Current execution state
    status = Column(SQLEnum(WorkflowRunStatus), default=WorkflowRunStatus.RUNNING)
    current_step_index = Column(Integer, default=0)
    
    # Input data (e.g., activation form responses)
    input_data = Column(JSON, nullable=False)
    
    # Execution state (which steps completed, results, etc.)
    state = Column(JSON, nullable=False)  # {steps: {step_id: {status, result, started_at, completed_at}}}
    
    # Output artifacts (e.g., generated configs, club IDs)
    output_data = Column(JSON, nullable=True)
    
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    template = relationship("WorkflowTemplate")
    session = relationship("Session")
    steps = relationship("WorkflowStepExecution", back_populates="workflow_run")


class WorkflowRunStatus(str, enum.Enum):
    """Workflow run status"""
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStepExecution(Base):
    """Individual step execution within a workflow run"""
    __tablename__ = "workflow_step_executions"
    
    id = Column(Integer, primary_key=True)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=False)
    
    step_id = Column(String(255), nullable=False)  # From template definition
    step_name = Column(String(500), nullable=False)
    step_type = Column(String(100), nullable=False)  # "tool_call", "approval_gate", "condition", etc.
    
    status = Column(SQLEnum(StepStatus), default=StepStatus.PENDING)
    
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


class StepStatus(str, enum.Enum):
    """Step execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING_APPROVAL = "waiting_approval"
```

#### 🆕 Workflow Orchestrator Service

```python
# New file: backend/app/services/workflow_orchestrator.py

class WorkflowOrchestrator:
    """
    Orchestrates multi-step workflow execution.
    
    Responsibilities:
    - Load workflow templates
    - Execute steps in dependency order
    - Handle approval gates
    - Track progress
    - Resume interrupted workflows
    """
    
    def __init__(self, db: Session, agentic_service: AgenticService, approval_service: ApprovalService):
        self.db = db
        self.agentic_service = agentic_service
        self.approval_service = approval_service
    
    async def start_workflow(
        self, 
        template_name: str, 
        input_data: Dict[str, Any],
        session_id: int
    ) -> WorkflowRun:
        """Initialize and start a new workflow run."""
        pass
    
    async def execute_next_step(self, workflow_run_id: int) -> WorkflowStepExecution:
        """Execute the next pending step in the workflow."""
        pass
    
    async def handle_step_completion(
        self, 
        workflow_run_id: int, 
        step_id: str, 
        result: Any
    ) -> None:
        """Process step completion and determine next action."""
        pass
    
    async def resume_workflow(self, workflow_run_id: int) -> None:
        """Resume a paused or interrupted workflow."""
        pass
    
    def _evaluate_step_dependencies(self, step_def: Dict, state: Dict) -> bool:
        """Check if step dependencies are satisfied."""
        pass
    
    def _get_next_executable_steps(self, workflow_run: WorkflowRun) -> List[Dict]:
        """Get all steps ready to execute (dependencies satisfied)."""
        pass
```

#### 🆕 BRS Tool MCP Server

New MCP server to expose BRS system operations as tools:

```python
# New directory: backend/app/services/brs_tools/

# backend/app/services/brs_tools/server.py
"""MCP server exposing BRS system tools."""

class BRSToolServer:
    """
    MCP server for BRS operations.
    
    Tools:
    - brs_teesheet_init: Initialize club database
    - brs_create_superuser: Create admin account
    - brs_configure_rates: Setup green fee rates
    - brs_configure_booking_rules: Setup casual/member booking rules
    - brs_enable_module: Enable add-on module (memberships, facilities, etc.)
    - brs_validate_config: Verify configuration completeness
    """
    
    async def brs_teesheet_init(self, club_name: str, club_id: str) -> Dict[str, Any]:
        """Execute: ./bin/teesheet init"""
        pass
    
    async def brs_create_superuser(self, club_name: str, email: str, name: str) -> Dict[str, Any]:
        """Execute: ./bin/teesheet update-superusers CLUB_NAME"""
        pass
    
    async def brs_configure_rates(self, club_id: str, rates_config: Dict) -> Dict[str, Any]:
        """Call brs-config-api to setup rates"""
        pass
    
    # ... more tools
```

## Workflow Definition Format

Example workflow template JSON:

```json
{
  "name": "teesheet_core_onboarding",
  "version": "1.0.0",
  "steps": [
    {
      "id": "validate_input",
      "name": "Validate Activation Form",
      "type": "validation",
      "config": {
        "required_fields": ["club_name", "club_address", "contact_email"]
      }
    },
    {
      "id": "init_database",
      "name": "Initialize Club Database",
      "type": "tool_call",
      "config": {
        "tool": "brs_teesheet_init",
        "inputs": {
          "club_name": "{{input.club_name}}",
          "club_id": "{{generated.club_id}}"
        }
      },
      "dependencies": ["validate_input"]
    },
    {
      "id": "create_superuser",
      "name": "Create Admin Account",
      "type": "tool_call",
      "config": {
        "tool": "brs_create_superuser",
        "inputs": {
          "club_name": "{{input.club_name}}",
          "email": "{{input.contact_email}}",
          "name": "{{input.contact_name}}"
        }
      },
      "dependencies": ["init_database"]
    },
    {
      "id": "review_technical_setup",
      "name": "Review Technical Setup",
      "type": "approval_gate",
      "config": {
        "approver_role": "admin",
        "review_data": ["init_database.result", "create_superuser.result"]
      },
      "dependencies": ["create_superuser"]
    },
    {
      "id": "configure_modules",
      "name": "Enable Add-on Modules",
      "type": "parallel_tool_calls",
      "config": {
        "tools": "{{dynamic_from_input.modules_to_enable}}"
      },
      "dependencies": ["review_technical_setup"]
    }
  ],
  "error_handling": {
    "retry_policy": {
      "max_retries": 3,
      "backoff": "exponential"
    },
    "escalation_on_failure": true
  }
}
```

## Integration Points

### 1. Extend AgentState
Add workflow context to existing state tracking:

```python
@dataclass
class AgentState:
    # Existing fields...
    
    # NEW: Workflow context
    workflow_run_id: Optional[int] = None
    current_workflow_step: Optional[str] = None
    workflow_context: Dict[str, Any] = field(default_factory=dict)
```

### 2. Extend Chat API
Add workflow-specific endpoints:

```python
# backend/app/api/workflows.py

@router.post("/workflows/start")
async def start_workflow(
    template_name: str,
    input_data: Dict[str, Any],
    session_id: int,
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db)
):
    """Start a new workflow run."""
    orchestrator = WorkflowOrchestrator(db, agentic_service, approval_service)
    workflow_run = await orchestrator.start_workflow(template_name, input_data, session_id)
    return {"workflow_run_id": workflow_run.id, "status": workflow_run.status}

@router.get("/workflows/{workflow_run_id}")
async def get_workflow_status(workflow_run_id: int, db: Session = Depends(get_db)):
    """Get workflow execution status and progress."""
    pass

@router.post("/workflows/{workflow_run_id}/resume")
async def resume_workflow(workflow_run_id: int, db: Session = Depends(get_db)):
    """Resume a paused workflow."""
    pass
```

### 3. Admin Dashboard Extension
Add workflow monitoring view:
- Active workflows (in progress)
- Workflow completion rates
- Average time per workflow type
- Failure analysis by step

## Implementation Phases

### Phase 1: Core Workflow Engine (Week 1)
- Database models (WorkflowTemplate, WorkflowRun, WorkflowStepExecution)
- WorkflowOrchestrator service (basic execution)
- Workflow template loader
- Step dependency resolution

### Phase 2: BRS Tools Integration (Week 2)
- BRS MCP tool server
- Wrap brs-teesheet CLI commands
- Wrap brs-config-api calls
- Add to MCP registry

### Phase 3: Onboarding Workflow (Week 3)
- Define teesheet_core_onboarding template
- Test with real activation form data
- Add approval gates
- Error handling and retries

### Phase 4: UI & Monitoring (Week 4)
- Workflow progress UI in Open WebUI
- Admin workflow dashboard
- Workflow template editor (stretch goal)

## Benefits of This Approach

1. **Reuses Existing Infrastructure**:
   - AgenticService handles LLM orchestration
   - ApprovalService handles human-in-loop
   - Security and tool execution already validated

2. **Extends, Doesn't Replace**:
   - Conversational agent still works as before
   - Workflows are opt-in feature layer on top
   - No breaking changes

3. **Incremental Adoption**:
   - Start with one workflow (teesheet onboarding)
   - Add more workflows over time
   - Learn and iterate on workflow patterns

4. **Clear Separation of Concerns**:
   - Workflows = orchestration logic
   - AgenticService = execution engine
   - Tools = primitive operations
   - LLM = decision making where needed

## Open Questions

1. **Workflow Definition Storage**: File-based YAML/JSON vs database?
   - Recommend: Database for versioning and runtime loading
   - Keep JSON files in `backend/workflows/templates/` for version control

2. **LLM Role in Workflows**: When should LLM make decisions vs follow script?
   - Use LLM for: parsing unstructured inputs, generating configs, error diagnosis
   - Use deterministic: step sequencing, validation, tool calling

3. **Long-Running Workflows**: How to handle workflows that take hours/days?
   - Async task queue (Celery/RQ) for background execution
   - Webhook callbacks for step completion
   - Email/Slack notifications for approval gates

4. **Workflow Templates**: Who creates them?
   - Phase 1: Engineers write JSON
   - Phase 2+: UI builder for non-technical staff
