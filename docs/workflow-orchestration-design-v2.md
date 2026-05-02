# Workflow Orchestration Design - Revised

## Architecture Decisions

### 1. LangGraph for Workflow Execution ✅

**Decision: Use LangGraph as the workflow execution engine**

**Why:**
- Built specifically for agentic workflows with LLM decision points
- State persistence and checkpointing (resume interrupted workflows)
- Graph-based state machines with conditional edges
- Handles parallel execution naturally
- Battle-tested by LangChain ecosystem

**Integration Approach:**
```python
# backend/app/services/workflow_orchestrator.py

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresCheckpointer

class WorkflowOrchestrator:
    """
    Wraps LangGraph for workflow execution.
    
    LangGraph handles:
    - State machine execution
    - Persistence/checkpointing
    - Conditional routing
    - Parallel execution
    
    We handle:
    - Loading workflow templates from DB
    - Converting templates to LangGraph definitions
    - Tool registry integration
    - Metrics collection
    - Approval gate orchestration
    """
    
    def __init__(self, db: Session, agentic_service: AgenticService):
        self.db = db
        self.agentic_service = agentic_service
        # Use PostgreSQL for LangGraph checkpoints (reuse existing DB)
        self.checkpointer = PostgresCheckpointer.from_conn_string(DATABASE_URL)
    
    def build_graph_from_template(self, template: WorkflowTemplate) -> StateGraph:
        """Convert workflow template JSON to LangGraph StateGraph."""
        graph = StateGraph(WorkflowState)
        
        # Add nodes for each step
        for step in template.definition["steps"]:
            graph.add_node(step["id"], self._create_step_node(step))
        
        # Add edges based on dependencies
        for step in template.definition["steps"]:
            for dep in step.get("dependencies", []):
                graph.add_edge(dep, step["id"])
        
        # Add conditional edges for approval gates
        # Add error handling edges
        # ...
        
        graph.set_entry_point(template.definition["entry_point"])
        return graph.compile(checkpointer=self.checkpointer)
```

**Benefits:**
- Don't reinvent state machine logic
- Get persistence for free
- Easier to reason about workflows as graphs
- Community support and updates

---

### Error Recovery with LangGraph

**Wire existing ErrorRecoveryStrategy enum into graph conditional edges:**

```python
from backend.app.models.models import ErrorRecoveryStrategy
from langgraph.graph import END

class WorkflowOrchestrator:
    def _create_step_node_with_error_handling(self, step: Dict):
        """Create LangGraph node with error recovery."""
        
        async def node_func(state: WorkflowState) -> WorkflowState:
            strategy = step.get("error_recovery", ErrorRecoveryStrategy.FAIL_FAST)
            max_retries = step.get("max_retries", 3)
            attempt = state.get(f"{step['id']}_attempt", 0)
            
            try:
                # Execute step
                result = await self._execute_step(step, state)
                state[step["id"]] = result
                state[f"{step['id']}_status"] = "success"
                return state
                
            except Exception as e:
                # Record error metrics
                await self.metrics.record_step_error(
                    workflow_run_id=state["workflow_run_id"],
                    step_id=step["id"],
                    error=e,
                    attempt=attempt + 1
                )
                
                # Apply recovery strategy
                if strategy == ErrorRecoveryStrategy.RETRY and attempt < max_retries:
                    state[f"{step['id']}_attempt"] = attempt + 1
                    state[f"{step['id']}_status"] = "retrying"
                    return state  # Will retry via conditional edge
                    
                elif strategy == ErrorRecoveryStrategy.FALLBACK:
                    # Execute fallback step
                    fallback_id = step.get("fallback_step")
                    state[f"{step['id']}_status"] = "failed_fallback"
                    state["next_step"] = fallback_id
                    return state
                    
                elif strategy == ErrorRecoveryStrategy.ESCALATE:
                    # Pause workflow, notify admin
                    state[f"{step['id']}_status"] = "escalated"
                    state["workflow_status"] = "waiting_escalation"
                    await self.approval_service.create_escalation(
                        workflow_run_id=state["workflow_run_id"],
                        step_id=step["id"],
                        error=str(e)
                    )
                    return state
                    
                else:  # FAIL_FAST or ABORT_WORKFLOW
                    state[f"{step['id']}_status"] = "failed"
                    state["workflow_status"] = "failed"
                    state["error"] = str(e)
                    raise
        
        return node_func
```

---

### Unified Approval Gate Node

**Single approval node pattern for all human-in-the-loop decisions:**

```python
async def _approval_gate_node(self, state: WorkflowState) -> WorkflowState:
    """Universal approval gate for all human reviews."""
    current_step = state["current_step"]
    step_config = state["steps"][current_step]
    
    # Create approval request
    approval = await self.approval_service.create_approval_request(
        workflow_run_id=state["workflow_run_id"],
        step_id=current_step,
        review_data=step_config["review_data"],
        approver_role=step_config["approver_role"]
    )
    
    # Wait for approval (workflow pauses here via checkpointer)
    state["workflow_status"] = "waiting_approval"
    state["pending_approval_id"] = approval.id
    
    return state
```

---

### MCP Integration Flow

**BRS Tool Server Registration:**

```python
# backend/app/services/brs_tools/server.py
from mcp.server import Server
from mcp.types import Tool, TextContent

class BRSToolServer:
    """MCP server exposing BRS operations."""
    
    def __init__(self):
        self.server = Server("brs-tools")
        self._register_tools()
    
    async def brs_teesheet_init(self, club_name: str, club_id: str) -> Dict[str, Any]:
        """Execute: ./bin/teesheet init"""
        import subprocess
        result = subprocess.run(
            ["./bin/teesheet", "init", club_name, club_id],
            cwd="/path/to/brs-teesheet",
            capture_output=True,
            text=True
        )
        return {
            "success": result.returncode == 0,
            "database": f"{club_name}_db",
            "stdout": result.stdout
        }
```

---

### Workflow Classification Link

**Add FK to WorkflowTemplate model:**

```python
class WorkflowTemplate(Base):
    __tablename__ = "workflow_templates"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    
    # Link to workflow classification
    workflow_category = Column(SQLEnum(WorkflowCategory), nullable=False)  # NEW
    
    definition = Column(JSON, nullable=False)
```

---

### Observability Integration (Langfuse)

**Add Langfuse tracing to workflow execution:**

```python
from langfuse.callback import CallbackHandler
from langchain_core.runnables import RunnableConfig

class WorkflowOrchestrator:
    def __init__(self, db: Session, agentic_service: AgenticService):
        self.db = db
        self.agentic_service = agentic_service
        self.checkpointer = PostgresCheckpointer.from_conn_string(DATABASE_URL)
        
        # Initialize Langfuse
        self.langfuse_handler = CallbackHandler(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST  # Self-hosted instance
        )
    
    async def execute_workflow(self, workflow_run_id: int) -> WorkflowState:
        """Execute workflow with full observability."""
        workflow_run = self.db.query(WorkflowRun).get(workflow_run_id)
        graph = self.build_graph_from_template(workflow_run.template)
        
        # Execute with Langfuse tracing
        result = await graph.ainvoke(
            workflow_run.input_data,
            config=RunnableConfig(
                callbacks=[self.langfuse_handler],
                configurable={"thread_id": str(workflow_run_id)}
            )
        )
        return result
```

**Langfuse automatically tracks:**
- Workflow execution spans
- LLM calls (tokens, latency, cost)
- Tool calls (inputs, outputs)
- Error traces

---

### Output Validation (Instructor + Guardrails)

**Structured output validation with Instructor:**

```python
import instructor
from pydantic import BaseModel, Field

ollama_client = instructor.patch(OllamaClient())

class ClubConfig(BaseModel):
    """Validated club configuration schema."""
    club_name: str = Field(..., min_length=3, max_length=100)
    club_id: str = Field(..., pattern=r'^[A-Z]{3,5}\d{3,5}$')
    contact_email: str = Field(..., pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    modules_to_enable: List[str]

# Usage
config = ollama_client.chat.completions.create(
    model="qwen2.5:32b",
    messages=[...],
    response_model=ClubConfig,
    max_retries=3  # Retry on validation failure
)
```

**Content safety with Guardrails:**

```python
from guardrails import Guard
from guardrails.hub import DetectPII

pii_guard = Guard().use(DetectPII, on_fail="fix")
sanitized = pii_guard.validate(llm_output)
```

---

### Parallel Execution Patterns

**Fan-out/fan-in with LangGraph:**

```python
def build_graph_with_parallel(self, template: WorkflowTemplate):
    graph = StateGraph(WorkflowState)
    
    for step in template.definition["steps"]:
        if step["type"] == "parallel_tool_calls":
            # Create fan-out node
            graph.add_node(f"{step['id']}_fanout", lambda s: s)
            
            # Create parallel execution nodes
            for tool_config in step["tools"]:
                node_id = f"{step['id']}_{tool_config['tool']}"
                graph.add_node(node_id, self._create_tool_node(tool_config))
                graph.add_edge(f"{step['id']}_fanout", node_id)
            
            # Create fan-in node
            graph.add_node(f"{step['id']}_fanin", self._collect_results)
            for tool_config in step["tools"]:
                node_id = f"{step['id']}_{tool_config['tool']}"
                graph.add_edge(node_id, f"{step['id']}_fanin")
    
    return graph.compile(checkpointer=self.checkpointer)
```

**Template JSON:**
```json
{
  "id": "enable_modules",
  "type": "parallel_tool_calls",
  "tools": [
    {"tool": "brs_enable_member_module"},
    {"tool": "brs_enable_sms_module"}
  ]
}
```

---

### Rollback/Compensation (Saga Pattern)

**Compensating actions for failed workflows:**

```python
async def _handle_failure_node(self, state: WorkflowState) -> WorkflowState:
    """Orchestrate compensating actions for completed steps."""
    completed_steps = state.get("completed_steps", [])
    
    # Execute compensations in reverse order
    for step_id in reversed(completed_steps):
        step_config = next(s for s in state["template"]["steps"] if s["id"] == step_id)
        
        if "compensation" in step_config:
            await self._execute_compensation(step_config["compensation"], state)
            state[f"{step_id}_compensated"] = True
    
    state["workflow_status"] = "rolled_back"
    return state
```

**Template with compensation:**
```json
{
  "id": "init_database",
  "type": "tool_call",
  "tool": "brs_teesheet_init",
  "compensation": {
    "type": "tool_call",
    "tool": "brs_teesheet_drop_database",
    "inputs": {"club_name": "{{input.club_name}}"}
  }
}
```

---

## 2. Testing Strategy

### Test Pyramid

#### Unit Tests (70%)
**Service-level testing:**
```python
# tests/unit/test_workflow_orchestrator.py
def test_load_workflow_template():
    """Test loading workflow template from DB."""
    pass

def test_build_graph_from_template():
    """Test converting template JSON to LangGraph."""
    pass

def test_step_execution_success():
    """Test individual step execution with mock tools."""
    pass

def test_step_execution_failure_retry():
    """Test retry logic on step failure."""
    pass

# tests/unit/test_brs_tools.py  
def test_brs_teesheet_init_success():
    """Test teesheet init with mocked subprocess."""
    pass

def test_brs_teesheet_init_validation():
    """Test input validation before execution."""
    pass

def test_brs_create_superuser_idempotent():
    """Test superuser creation is idempotent."""
    pass
```

#### Integration Tests (20%)
**End-to-end workflow testing with real database:**
```python
# tests/integration/test_onboarding_workflow.py

@pytest.mark.integration
async def test_teesheet_core_onboarding_happy_path(db_session, mock_brs_tools):
    """
    Test complete onboarding workflow:
    1. Load template
    2. Execute all steps
    3. Verify database state
    4. Check metrics recorded
    """
    input_data = {
        "club_name": "Test Golf Club",
        "contact_email": "admin@test.com"
    }
    
    orchestrator = WorkflowOrchestrator(db_session, agentic_service)
    workflow_run = await orchestrator.start_workflow(
        "teesheet_core_onboarding",
        input_data,
        session_id=1
    )
    
    # Execute workflow
    result = await orchestrator.execute_until_completion(workflow_run.id)
    
    # Assertions
    assert result.status == WorkflowRunStatus.COMPLETED
    assert result.output_data["club_id"] is not None
    
    # Verify metrics recorded
    metrics = db_session.query(StepMetrics).filter_by(
        workflow_run_id=workflow_run.id
    ).all()
    assert len(metrics) == expected_step_count

@pytest.mark.integration  
async def test_onboarding_workflow_with_approval_gate(db_session):
    """Test workflow pauses at approval gate and resumes correctly."""
    pass

@pytest.mark.integration
async def test_onboarding_workflow_failure_recovery(db_session):
    """Test workflow failure, rollback, and retry."""
    pass
```

#### E2E Tests (10%)
**Full system testing with real tools (in staging environment):**
```python
# tests/e2e/test_real_onboarding.py

@pytest.mark.e2e
@pytest.mark.skip("Requires real BRS environment")
async def test_real_club_onboarding_end_to_end():
    """
    Test against real BRS staging environment.
    
    WARNING: Creates real database, real configs.
    Only run in isolated staging environment.
    """
    pass
```

### Test Infrastructure

**Mock BRS Tools:**
```python
# tests/mocks/brs_tools.py

class MockBRSToolServer:
    """Mock BRS tool server for testing."""
    
    def __init__(self):
        self.teesheet_init_calls = []
        self.superuser_create_calls = []
    
    async def brs_teesheet_init(self, club_name: str, club_id: str):
        self.teesheet_init_calls.append({"club_name": club_name, "club_id": club_id})
        return {"success": True, "database": f"{club_name}_db"}
    
    async def brs_create_superuser(self, club_name: str, email: str, name: str):
        self.superuser_create_calls.append({"club_name": club_name, "email": email})
        return {"success": True, "user_id": 123}
```

**Fixture Strategy:**
```python
# tests/conftest.py

@pytest.fixture
def workflow_template_factory(db_session):
    """Factory for creating test workflow templates."""
    def _create(name: str, steps: List[Dict]) -> WorkflowTemplate:
        template = WorkflowTemplate(
            name=name,
            version="1.0.0-test",
            definition={"steps": steps}
        )
        db_session.add(template)
        db_session.commit()
        return template
    return _create

@pytest.fixture
def mock_brs_tools():
    """Mock BRS tool server."""
    return MockBRSToolServer()
```

### CI/CD Integration
```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run unit tests
        run: pytest tests/unit/ -v
  
  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:14
    steps:
      - name: Run integration tests
        run: pytest tests/integration/ -v
```

---

## 3. Metrics & Data-Driven Development 📊

### Metrics Collection Architecture

**New Database Models for Telemetry:**

```python
# backend/app/models/metrics.py

class StepMetrics(Base):
    """Granular metrics per workflow step execution."""
    __tablename__ = "step_metrics"
    
    id = Column(Integer, primary_key=True)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"))
    step_execution_id = Column(Integer, ForeignKey("workflow_step_executions.id"))
    
    # Performance metrics
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    
    # Execution metrics
    attempt_number = Column(Integer, default=1)
    success = Column(Boolean, nullable=False)
    error_type = Column(String(255), nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Resource metrics
    tokens_used = Column(Integer, nullable=True)  # If LLM step
    tool_latency_ms = Column(Integer, nullable=True)  # If tool call
    
    # Context
    input_hash = Column(String(64), nullable=True)  # Hash of inputs for deduplication
    output_hash = Column(String(64), nullable=True)


class LLMDecisionMetrics(Base):
    """Track LLM decisions and their outcomes."""
    __tablename__ = "llm_decision_metrics"
    
    id = Column(Integer, primary_key=True)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"))
    step_execution_id = Column(Integer, ForeignKey("workflow_step_executions.id"))
    
    # Decision context
    decision_point = Column(String(255), nullable=False)  # "tool_selection", "parameter_extraction", etc.
    prompt_template_id = Column(String(255), nullable=True)  # Track which prompt version
    prompt_hash = Column(String(64), nullable=False)  # Hash of actual prompt sent
    
    # LLM response
    model_used = Column(String(100), nullable=False)
    response_raw = Column(Text, nullable=False)
    decision_parsed = Column(JSON, nullable=False)  # Structured decision
    
    # Outcome
    decision_correct = Column(Boolean, nullable=True)  # Human validation later
    correction_needed = Column(Boolean, default=False)
    correction_data = Column(JSON, nullable=True)  # What should have been done
    
    # Performance
    tokens_used = Column(Integer)
    latency_ms = Column(Integer)
    temperature = Column(Float)
    
    created_at = Column(DateTime, default=datetime.utcnow)


class PromptTemplate(Base):
    """Version-controlled prompt templates."""
    __tablename__ = "prompt_templates"
    
    id = Column(Integer, primary_key=True)
    template_id = Column(String(255), nullable=False)  # "tool_selection_v1"
    version = Column(Integer, nullable=False)
    
    template_text = Column(Text, nullable=False)
    
    # Performance tracking
    times_used = Column(Integer, default=0)
    success_rate = Column(Float, nullable=True)  # Updated periodically
    avg_tokens = Column(Integer, nullable=True)
    
    # Metadata
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    deprecated_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        UniqueConstraint('template_id', 'version', name='uq_template_version'),
    )


class WorkflowRunMetrics(Base):
    """Aggregate metrics per workflow run."""
    __tablename__ = "workflow_run_metrics"
    
    id = Column(Integer, primary_key=True)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"), unique=True)
    
    # Overall metrics
    total_steps = Column(Integer, nullable=False)
    successful_steps = Column(Integer, default=0)
    failed_steps = Column(Integer, default=0)
    retried_steps = Column(Integer, default=0)
    
    # Performance
    total_duration_ms = Column(Integer, nullable=True)
    llm_tokens_total = Column(Integer, default=0)
    tool_calls_total = Column(Integer, default=0)
    
    # Quality
    approval_gates_passed = Column(Integer, default=0)
    approval_gates_rejected = Column(Integer, default=0)
    
    # Human feedback
    workflow_quality_score = Column(Integer, nullable=True)  # 1-5 rating
    human_feedback = Column(Text, nullable=True)
```

### Metrics Collection Service

```python
# backend/app/services/metrics_collector.py

class MetricsCollector:
    """Collects and analyzes workflow execution metrics."""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def record_step_start(
        self, 
        workflow_run_id: int, 
        step_execution_id: int,
        attempt_number: int = 1
    ) -> StepMetrics:
        """Record step execution start."""
        metrics = StepMetrics(
            workflow_run_id=workflow_run_id,
            step_execution_id=step_execution_id,
            attempt_number=attempt_number,
            started_at=datetime.utcnow(),
            success=False  # Will update on completion
        )
        self.db.add(metrics)
        self.db.commit()
        return metrics
    
    async def record_step_completion(
        self,
        metrics_id: int,
        success: bool,
        error_type: str = None,
        error_message: str = None,
        output_data: Any = None
    ):
        """Record step execution completion."""
        metrics = self.db.query(StepMetrics).get(metrics_id)
        metrics.completed_at = datetime.utcnow()
        metrics.duration_ms = int((metrics.completed_at - metrics.started_at).total_seconds() * 1000)
        metrics.success = success
        metrics.error_type = error_type
        metrics.error_message = error_message
        
        if output_data:
            metrics.output_hash = hashlib.sha256(
                json.dumps(output_data, sort_keys=True).encode()
            ).hexdigest()
        
        self.db.commit()
    
    async def record_llm_decision(
        self,
        workflow_run_id: int,
        step_execution_id: int,
        decision_point: str,
        prompt_template_id: str,
        prompt_text: str,
        model_used: str,
        response: str,
        decision_parsed: Dict,
        tokens_used: int,
        latency_ms: int,
        temperature: float
    ) -> LLMDecisionMetrics:
        """Record LLM decision for later analysis."""
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
            temperature=temperature
        )
        self.db.add(decision_metrics)
        self.db.commit()
        
        # Update prompt template usage stats
        self._update_prompt_stats(prompt_template_id)
        
        return decision_metrics
    
    def get_workflow_success_rate(self, template_name: str, days: int = 30) -> float:
        """Calculate workflow success rate over time period."""
        pass
    
    def get_step_failure_analysis(self, template_name: str, step_id: str) -> Dict:
        """Analyze why a specific step fails."""
        pass
    
    def get_prompt_performance_comparison(self, decision_point: str) -> List[Dict]:
        """Compare different prompt versions for same decision point."""
        pass
```

### Reinforcement & Prompt Optimization

```python
# backend/app/services/prompt_optimizer.py

class PromptOptimizer:
    """
    Analyzes LLM decision metrics and suggests prompt improvements.
    
    Strategies:
    1. A/B testing: Try multiple prompts, track success rates
    2. Failure analysis: Extract patterns from failed decisions
    3. Auto-tuning: Adjust temperature, max_tokens based on outcomes
    4. Few-shot learning: Add successful examples to prompts
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    async def analyze_decision_point(self, decision_point: str) -> Dict[str, Any]:
        """
        Analyze all LLM decisions for a specific decision point.
        
        Returns:
        - Success rate by prompt template
        - Common failure patterns
        - Recommended prompt improvements
        """
        decisions = self.db.query(LLMDecisionMetrics).filter_by(
            decision_point=decision_point
        ).all()
        
        # Group by prompt template
        by_template = {}
        for d in decisions:
            if d.prompt_template_id not in by_template:
                by_template[d.prompt_template_id] = []
            by_template[d.prompt_template_id].append(d)
        
        # Calculate success rates
        template_stats = {}
        for template_id, template_decisions in by_template.items():
            correct = sum(1 for d in template_decisions if d.decision_correct)
            total = len(template_decisions)
            template_stats[template_id] = {
                "success_rate": correct / total if total > 0 else 0,
                "sample_size": total,
                "avg_tokens": np.mean([d.tokens_used for d in template_decisions]),
                "avg_latency_ms": np.mean([d.latency_ms for d in template_decisions])
            }
        
        # Find failure patterns
        failed_decisions = [d for d in decisions if d.decision_correct == False]
        failure_patterns = self._extract_failure_patterns(failed_decisions)
        
        return {
            "decision_point": decision_point,
            "template_performance": template_stats,
            "failure_patterns": failure_patterns,
            "recommendations": self._generate_recommendations(template_stats, failure_patterns)
        }
    
    def _extract_failure_patterns(self, failed_decisions: List[LLMDecisionMetrics]) -> List[Dict]:
        """Extract common patterns from failed decisions."""
        # Cluster similar failures
        # Look for common input characteristics
        # Identify edge cases
        pass
    
    def _generate_recommendations(self, template_stats: Dict, failure_patterns: List) -> List[str]:
        """Generate actionable recommendations for prompt improvement."""
        recommendations = []
        
        # Recommend best performing template
        best_template = max(template_stats.items(), key=lambda x: x[1]["success_rate"])
        recommendations.append(f"Use {best_template[0]} (success rate: {best_template[1]['success_rate']:.2%})")
        
        # Suggest adding examples for common failures
        for pattern in failure_patterns[:3]:  # Top 3
            recommendations.append(f"Add few-shot example for: {pattern['description']}")
        
        return recommendations
    
    async def create_ab_test(
        self,
        decision_point: str,
        prompt_variants: List[str],
        traffic_split: List[float]
    ) -> str:
        """
        Create A/B test for prompt variants.
        
        Returns test_id for tracking.
        """
        pass
```

### Analytics Dashboard

**New admin endpoints:**
```python
# backend/app/api/analytics.py

@router.get("/analytics/workflows/{template_name}/performance")
async def get_workflow_performance(
    template_name: str,
    days: int = 30,
    db: Session = Depends(get_db)
):
    """
    Get workflow performance metrics:
    - Success rate over time
    - Average duration
    - Failure points
    - Step-by-step breakdown
    """
    pass

@router.get("/analytics/prompts/{decision_point}")
async def get_prompt_performance(
    decision_point: str,
    db: Session = Depends(get_db)
):
    """
    Get prompt performance comparison:
    - Success rate by template version
    - Token usage
    - Latency
    - A/B test results
    """
    pass

@router.post("/analytics/llm-decision/{decision_id}/feedback")
async def submit_llm_decision_feedback(
    decision_id: int,
    feedback: LLMDecisionFeedback,
    db: Session = Depends(get_db)
):
    """
    Submit feedback on LLM decision correctness.
    
    Used to train the reinforcement loop.
    """
    decision = db.query(LLMDecisionMetrics).get(decision_id)
    decision.decision_correct = feedback.correct
    if not feedback.correct:
        decision.correction_needed = True
        decision.correction_data = feedback.correction
    db.commit()
```

### Metric-Driven Development Workflow

1. **Build**: Implement workflow with instrumentation
2. **Deploy**: Run in staging/production
3. **Collect**: Gather metrics on every execution
4. **Analyze**: Weekly review of:
   - Workflow success rates
   - Step failure hotspots
   - Prompt performance
5. **Optimize**: 
   - A/B test new prompts
   - Refine failing steps
   - Add few-shot examples
6. **Iterate**: Redeploy and measure improvement

---

## Revised Implementation Plan

### Phase 1: Core Engine + Metrics (Week 1-2)
- Database models (workflows + metrics)
- LangGraph integration
- MetricsCollector service
- Basic workflow execution with full instrumentation

### Phase 2: BRS Tools + Testing (Week 2-3)
- BRS MCP tool server
- Mock BRS tools
- Unit test suite
- Integration test suite

### Phase 3: Onboarding Workflow + Analytics (Week 3-4)
- Teesheet onboarding template
- Prompt templates with versioning
- Analytics dashboard
- PromptOptimizer service

### Phase 4: Reinforcement Loop (Week 4-5)
- A/B testing framework
- Feedback collection UI
- Auto-prompt tuning
- Performance monitoring alerts

## Key Benefits

1. **LangGraph**: Proven state machine, don't reinvent wheel
2. **Comprehensive Testing**: Confidence in production deployments
3. **Metrics First-Class**: Every decision tracked, every failure analyzed
4. **Continuous Improvement**: Data-driven prompt optimization
5. **Scalable**: Foundation for multiple workflows

## Open Questions

1. **LangGraph vs LangChain Agent Executor**: LangGraph for workflows, Agent Executor for conversational?
2. **Metric Retention**: How long to keep detailed metrics? (Recommend: 90 days detailed, 1 year aggregated)
3. **A/B Test Traffic**: What % of production traffic for experiments? (Recommend: Start 10%, increase if stable)
