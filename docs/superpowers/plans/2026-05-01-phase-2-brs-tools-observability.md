# Phase 2: BRS Tools + Core Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add self-hosted Langfuse for workflow tracing, integrate Instructor for structured LLM outputs, and implement BRS Tool Gateway (NOT MCP server) for executing teesheet CLI commands with mock mode for testing.

**Architecture:** Langfuse runs in Docker Compose alongside existing services and instruments all workflow executions via callback handlers. Instructor wraps OllamaClient to enforce Pydantic schemas on LLM outputs. BRS Tool Gateway is an internal service layer (Tool Registry → Execution Layer → Output Parser) that converts tool definitions to CLI subprocess calls with structured output parsing. Mock mode allows development/testing without real CLI.

**Tech Stack:** Langfuse (self-hosted), Instructor, Docker Compose, asyncio subprocess, Pydantic

---

## Task Completion Status

**Progress**: 4 of 9 tasks complete (44%)

- [x] **Task 1**: Langfuse Setup (Docker Compose + Configuration)
- [x] **Task 2**: Langfuse Integration with WorkflowOrchestrator
- [x] **Task 3**: Instructor Integration (OllamaClient Wrapper)
- [x] **Task 4**: BRS Tool Registry (Definitions + Schemas)
- [ ] **Task 5**: BRS Tool Execution Layer (Command Builder + Subprocess) **NEXT**
- [ ] **Task 6**: BRS Tool Output Parser (Instructor Integration)
- [ ] **Task 7**: Mock Mode for BRS Tools
- [ ] **Task 8**: Integration Tests with Mock BRS Tools
- [ ] **Task 9**: Documentation

---

## File Structure

### New Files

```
backend/
├── docker-compose.langfuse.yml          # Langfuse self-hosted stack
├── app/
│   ├── core/
│   │   ├── langfuse_config.py           # Langfuse singleton + callback factory
│   │   └── instructor_client.py         # Instructor-wrapped OllamaClient
│   └── services/
│       └── brs_tools/
│           ├── __init__.py
│           ├── registry.py              # Tool definitions + CLI templates
│           ├── executor.py              # Command builder + subprocess runner
│           ├── parser.py                # Output parser with Instructor
│           ├── mock.py                  # Mock mode for testing
│           └── schemas.py               # Pydantic output schemas
tests/
├── unit/
│   ├── core/
│   │   ├── test_langfuse_config.py
│   │   └── test_instructor_client.py
│   └── services/
│       └── brs_tools/
│           ├── test_registry.py
│           ├── test_executor.py
│           ├── test_parser.py
│           └── test_mock.py
└── integration/
    └── test_brs_tools_e2e.py            # End-to-end with mock CLI
```

### Modified Files

```
backend/
├── app/services/workflow_orchestrator.py  # Add Langfuse callback
├── app/services/ollama.py                # Make OllamaClient compatible with Instructor
├── .env.example                          # Add Langfuse + BRS paths
└── requirements.txt                      # Add langfuse, instructor
```

---

## Task 1: Langfuse Setup (Docker Compose + Configuration)

**Files:**
- Create: `backend/docker-compose.langfuse.yml`
- Create: `backend/app/core/langfuse_config.py`
- Create: `backend/tests/unit/core/test_langfuse_config.py`
- Modify: `backend/.env.example`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Write test for Langfuse config singleton**

Create `backend/tests/unit/core/test_langfuse_config.py`:

```python
import pytest
from app.core.langfuse_config import LangfuseConfig
from langfuse.callback import CallbackHandler


def test_get_instance_returns_same_instance():
    """Singleton pattern should return same instance."""
    instance1 = LangfuseConfig.get_instance()
    instance2 = LangfuseConfig.get_instance()
    assert instance1 is instance2


def test_get_callback_handler_returns_handler():
    """Should create callback handler with metadata."""
    handler = LangfuseConfig.get_callback_handler(
        user_id="test_user",
        session_id="test_session",
        trace_name="test_workflow"
    )
    
    assert isinstance(handler, CallbackHandler)
    # Handler should be configured but we can't inspect internals easily


def test_get_callback_handler_returns_none_when_disabled():
    """Should return None when Langfuse is disabled."""
    import os
    old_enabled = os.environ.get("LANGFUSE_ENABLED")
    os.environ["LANGFUSE_ENABLED"] = "false"
    
    handler = LangfuseConfig.get_callback_handler()
    assert handler is None
    
    if old_enabled:
        os.environ["LANGFUSE_ENABLED"] = old_enabled
    else:
        del os.environ["LANGFUSE_ENABLED"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd backend
pytest tests/unit/core/test_langfuse_config.py -v
```

Expected: FAIL with "No module named 'app.core.langfuse_config'"

- [ ] **Step 3: Add Langfuse dependency**

Modify `backend/requirements.txt`:

```txt
# Add to existing dependencies
langfuse==2.51.7
```

Install:
```bash
cd backend
pip install langfuse==2.51.7
```

- [ ] **Step 4: Run test to verify it still fails**

Run:
```bash
cd backend
pytest tests/unit/core/test_langfuse_config.py -v
```

Expected: FAIL with "No module named 'app.core.langfuse_config'"

- [ ] **Step 5: Create Langfuse config singleton**

Create `backend/app/core/langfuse_config.py`:

```python
import os
from typing import Optional
from langfuse import Langfuse
from langfuse.callback import CallbackHandler


class LangfuseConfig:
    """Singleton for Langfuse client and callback handler factory.
    
    Usage:
        handler = LangfuseConfig.get_callback_handler(
            user_id="user_123",
            session_id="session_456",
            trace_name="onboarding_workflow"
        )
        
        # Use in LangGraph
        config = RunnableConfig(callbacks=[handler] if handler else [])
    """
    
    _instance: Optional[Langfuse] = None
    
    @classmethod
    def get_instance(cls) -> Optional[Langfuse]:
        """Get or create Langfuse client singleton.
        
        Returns:
            Langfuse client if enabled, None otherwise
        """
        if not cls._is_enabled():
            return None
        
        if cls._instance is None:
            cls._instance = Langfuse(
                public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
                secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
                host=os.getenv("LANGFUSE_HOST", "http://localhost:3000")
            )
        
        return cls._instance
    
    @classmethod
    def get_callback_handler(
        cls,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        trace_name: Optional[str] = None
    ) -> Optional[CallbackHandler]:
        """Create callback handler for LangGraph integration.
        
        Args:
            user_id: User ID for trace grouping
            session_id: Session ID for trace grouping
            trace_name: Human-readable trace name
            
        Returns:
            CallbackHandler if Langfuse is enabled, None otherwise
        """
        if not cls._is_enabled():
            return None
        
        instance = cls.get_instance()
        if instance is None:
            return None
        
        return CallbackHandler(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
            host=os.getenv("LANGFUSE_HOST", "http://localhost:3000"),
            user_id=user_id,
            session_id=session_id,
            trace_name=trace_name
        )
    
    @staticmethod
    def _is_enabled() -> bool:
        """Check if Langfuse is enabled via environment variable."""
        return os.getenv("LANGFUSE_ENABLED", "true").lower() == "true"
```

- [ ] **Step 6: Run test to verify it passes**

Run:
```bash
cd backend
pytest tests/unit/core/test_langfuse_config.py -v
```

Expected: 3 tests PASS

- [ ] **Step 7: Create Docker Compose file for Langfuse**

Create `backend/docker-compose.langfuse.yml`:

```yaml
version: '3.8'

services:
  langfuse-postgres:
    image: postgres:15
    container_name: langfuse-postgres
    environment:
      POSTGRES_DB: langfuse
      POSTGRES_USER: langfuse
      POSTGRES_PASSWORD: langfuse_password
    volumes:
      - langfuse-postgres-data:/var/lib/postgresql/data
    ports:
      - "5433:5432"  # Different port to avoid conflict with main DB
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U langfuse"]
      interval: 10s
      timeout: 5s
      retries: 5

  langfuse-server:
    image: langfuse/langfuse:latest
    container_name: langfuse-server
    depends_on:
      langfuse-postgres:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql://langfuse:langfuse_password@langfuse-postgres:5432/langfuse
      NEXTAUTH_URL: http://localhost:3000
      NEXTAUTH_SECRET: changeme_secret_key_min_32_chars_long
      SALT: changeme_salt_min_32_chars_long
      # Telemetry off for self-hosted
      TELEMETRY_ENABLED: "false"
    ports:
      - "3000:3000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/api/public/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  langfuse-postgres-data:
```

- [ ] **Step 8: Update environment example**

Modify `backend/.env.example`:

```bash
# Add Langfuse configuration
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-local-dev
LANGFUSE_SECRET_KEY=sk-lf-local-dev
LANGFUSE_HOST=http://localhost:3000
```

- [ ] **Step 9: Commit**

```bash
git add backend/requirements.txt backend/app/core/langfuse_config.py backend/tests/unit/core/test_langfuse_config.py backend/docker-compose.langfuse.yml backend/.env.example
git commit -m "feat: add Langfuse setup with Docker Compose and config singleton

- Add langfuse==2.51.7 dependency
- Create LangfuseConfig singleton for client and callback factory
- Add docker-compose.langfuse.yml for self-hosted Langfuse
- Add LANGFUSE_* environment variables to .env.example
- All tests passing (3/3)

To start Langfuse:
  docker-compose -f backend/docker-compose.langfuse.yml up -d
  
Access UI at http://localhost:3000"
```

---

## Task 2: Langfuse Integration with WorkflowOrchestrator

**Files:**
- Modify: `backend/app/services/workflow_orchestrator.py`
- Modify: `backend/tests/unit/services/test_workflow_orchestrator.py`

- [ ] **Step 1: Write test for Langfuse callback in workflow execution**

Modify `backend/tests/unit/services/test_workflow_orchestrator.py`:

```python
# Add to existing test file

@pytest.mark.asyncio
async def test_execute_workflow_with_langfuse_tracing(
    db_session,
    workflow_template_fixture,
    session,
    monkeypatch
):
    """Test workflow execution includes Langfuse callback when enabled."""
    # Setup
    from app.core.langfuse_config import LangfuseConfig
    
    # Mock Langfuse to be enabled
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "test-key")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "test-secret")
    
    # Reset singleton
    LangfuseConfig._instance = None
    
    orchestrator = WorkflowOrchestrator(db_session, None)
    
    # Create workflow run
    workflow_run = orchestrator.create_workflow_run(
        template=workflow_template_fixture,
        session_id=session.id,
        input_data={"club_name": "Test Club"},
        user_id=1
    )
    
    # Execute
    result = await orchestrator.execute_workflow(workflow_run.id)
    
    # Verify workflow completed (callback doesn't break execution)
    db_session.refresh(workflow_run)
    assert workflow_run.status == WorkflowRunStatus.COMPLETED
    
    # Note: We can't easily verify callback was called without mocking internals
    # The important test is that execution doesn't break with callback enabled


@pytest.mark.asyncio
async def test_execute_workflow_without_langfuse_tracing(
    db_session,
    workflow_template_fixture,
    session,
    monkeypatch
):
    """Test workflow execution works when Langfuse is disabled."""
    # Disable Langfuse
    monkeypatch.setenv("LANGFUSE_ENABLED", "false")
    
    orchestrator = WorkflowOrchestrator(db_session, None)
    
    # Create workflow run
    workflow_run = orchestrator.create_workflow_run(
        template=workflow_template_fixture,
        session_id=session.id,
        input_data={"club_name": "Test Club"},
        user_id=1
    )
    
    # Execute
    result = await orchestrator.execute_workflow(workflow_run.id)
    
    # Verify workflow completed
    db_session.refresh(workflow_run)
    assert workflow_run.status == WorkflowRunStatus.COMPLETED
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd backend
pytest tests/unit/services/test_workflow_orchestrator.py::test_execute_workflow_with_langfuse_tracing -v
pytest tests/unit/services/test_workflow_orchestrator.py::test_execute_workflow_without_langfuse_tracing -v
```

Expected: Tests may pass because code doesn't use callback yet (no assertion on callback usage)

- [ ] **Step 3: Add Langfuse callback to WorkflowOrchestrator**

Modify `backend/app/services/workflow_orchestrator.py`:

```python
# Add import at top
from app.core.langfuse_config import LangfuseConfig
from langchain_core.runnables import RunnableConfig

# Modify execute_workflow method
async def execute_workflow(self, workflow_run_id: int) -> WorkflowState:
    """Execute a workflow run with full instrumentation.
    
    Args:
        workflow_run_id: ID of the workflow run to execute
        
    Returns:
        Final workflow state after execution
    """
    # Load workflow run
    workflow_run = self.db.query(WorkflowRun).filter(
        WorkflowRun.id == workflow_run_id
    ).first()
    
    if not workflow_run:
        raise ValueError(f"Workflow run {workflow_run_id} not found")
    
    # Update status to RUNNING
    workflow_run.status = WorkflowRunStatus.RUNNING
    workflow_run.started_at = datetime.now(timezone.utc)
    self.db.commit()
    
    try:
        # Build graph from template
        graph = self.build_graph_from_template(workflow_run.template)
        
        # Get Langfuse callback handler
        langfuse_callback = LangfuseConfig.get_callback_handler(
            user_id=str(workflow_run.user_id) if workflow_run.user_id else None,
            session_id=str(workflow_run.session_id),
            trace_name=f"{workflow_run.template.name}_run_{workflow_run.id}"
        )
        
        # Create config with callbacks
        config = RunnableConfig(
            configurable={"thread_id": str(workflow_run_id)},
            callbacks=[langfuse_callback] if langfuse_callback else []
        )
        
        # Execute workflow
        result = await graph.ainvoke(
            workflow_run.input_data,
            config=config
        )
        
        # Update workflow run with results
        workflow_run.status = WorkflowRunStatus.COMPLETED
        workflow_run.completed_at = datetime.now(timezone.utc)
        workflow_run.final_state = result
        self.db.commit()
        
        return result
        
    except Exception as e:
        # Mark workflow as failed
        workflow_run.status = WorkflowRunStatus.FAILED
        workflow_run.completed_at = datetime.now(timezone.utc)
        workflow_run.error_message = str(e)
        self.db.commit()
        raise
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd backend
pytest tests/unit/services/test_workflow_orchestrator.py::test_execute_workflow_with_langfuse_tracing -v
pytest tests/unit/services/test_workflow_orchestrator.py::test_execute_workflow_without_langfuse_tracing -v
```

Expected: 2 tests PASS

- [ ] **Step 5: Run all workflow orchestrator tests**

Run:
```bash
cd backend
pytest tests/unit/services/test_workflow_orchestrator.py -v
```

Expected: All tests PASS (13 total now)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/workflow_orchestrator.py backend/tests/unit/services/test_workflow_orchestrator.py
git commit -m "feat: integrate Langfuse tracing with workflow orchestrator

- Add Langfuse callback handler to execute_workflow()
- Callback includes user_id, session_id, and trace_name metadata
- Traces automatically capture LangGraph execution steps
- Works with Langfuse enabled or disabled
- All tests passing (13/13)

Langfuse will now automatically trace:
- Workflow execution spans
- Step-by-step execution
- LLM calls (when added in Phase 2+)
- Tool calls (BRS tools in this phase)"
```

---

## Task 3: Instructor Integration (OllamaClient Wrapper)

**Files:**
- Create: `backend/app/core/instructor_client.py`
- Create: `backend/tests/unit/core/test_instructor_client.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Write test for Instructor client**

Create `backend/tests/unit/core/test_instructor_client.py`:

```python
import pytest
from pydantic import BaseModel, Field
from app.core.instructor_client import InstructorOllamaClient


class SampleOutput(BaseModel):
    """Sample structured output for testing."""
    club_name: str = Field(description="Name of the golf club")
    club_id: str = Field(description="Unique club identifier")
    database_name: str = Field(description="Database name for the club")


@pytest.mark.asyncio
async def test_generate_structured_returns_typed_output():
    """Should return Pydantic model instance."""
    client = InstructorOllamaClient()
    
    # This will call Ollama, so we need a mock or real Ollama running
    # For now, we'll structure the test to be ready
    prompt = "Extract: Club Name: Test Golf Club, ID: TGC123"
    
    # Skip if no Ollama available (integration test territory)
    pytest.skip("Integration test - requires Ollama running")
    
    result = await client.generate_structured(
        prompt=prompt,
        response_model=SampleOutput,
        temperature=0.0
    )
    
    assert isinstance(result, SampleOutput)
    assert result.club_name == "Test Golf Club"
    assert result.club_id == "TGC123"


def test_instructor_client_can_be_instantiated():
    """Smoke test - can create client."""
    client = InstructorOllamaClient()
    assert client is not None
    assert hasattr(client, 'generate_structured')
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd backend
pytest tests/unit/core/test_instructor_client.py -v
```

Expected: FAIL with "No module named 'app.core.instructor_client'"

- [ ] **Step 3: Add Instructor and LiteLLM dependencies**

Modify `backend/requirements.txt`:

```txt
# Add to existing dependencies
instructor==1.7.0
litellm==1.55.0
```

> **Note:** Instructor doesn't support Ollama directly. We use LiteLLM as the adapter layer which provides OpenAI-compatible interface for Ollama.

Install:
```bash
cd backend
pip install instructor==1.7.0 litellm==1.55.0
```

- [ ] **Step 4: Create Instructor client wrapper**

Create `backend/app/core/instructor_client.py`:

```python
import os
from typing import Type, TypeVar, Optional
import instructor
import litellm
from pydantic import BaseModel

T = TypeVar('T', bound=BaseModel)


class InstructorOllamaClient:
    """Instructor-wrapped Ollama client for structured LLM outputs.
    
    Uses LiteLLM as the adapter layer since Instructor doesn't support
    Ollama natively. LiteLLM provides OpenAI-compatible interface.
    
    Usage:
        client = InstructorOllamaClient()
        
        class ClubConfig(BaseModel):
            club_name: str
            club_id: str
        
        result = await client.generate_structured(
            prompt="Extract club info: Test Golf Club (TGC123)",
            response_model=ClubConfig
        )
        
        assert isinstance(result, ClubConfig)
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        model: str = "qwen2.5-coder:7b"
    ):
        """Initialize Instructor-wrapped Ollama client via LiteLLM.
        
        Args:
            base_url: Ollama API base URL (default: http://localhost:11434)
            model: Default model to use for generation (without ollama/ prefix)
        """
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = model
        
        # Configure LiteLLM for Ollama
        litellm.api_base = self.base_url
        
        # Create Instructor client from LiteLLM
        # from_litellm() wraps litellm.completion with Instructor's validation
        self.client = instructor.from_litellm(litellm.completion)
    
    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        temperature: float = 0.7,
        max_retries: int = 3,
        model: Optional[str] = None
    ) -> T:
        """Generate structured output from LLM.
        
        Args:
            prompt: Input prompt for the LLM
            response_model: Pydantic model class for output validation
            temperature: Sampling temperature (0.0-1.0)
            max_retries: Number of retries on validation failure
            model: Model to use (overrides default)
            
        Returns:
            Instance of response_model with validated data
            
        Raises:
            ValidationError: If output doesn't match schema after retries
        """
        # Use specified model or default, prefix with ollama/
        model_name = f"ollama/{model or self.model}"
        
        # Create messages
        messages = [
            {
                "role": "system",
                "content": "You are a precise data extraction assistant. Extract information exactly as requested and format as JSON."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        # Generate with Instructor retry logic via LiteLLM
        # Note: from_litellm returns a synchronous client, so we wrap in asyncio
        response = self.client(
            model=model_name,
            messages=messages,
            response_model=response_model,
            temperature=temperature,
            max_retries=max_retries,
            api_base=self.base_url
        )
        
        return response
    
    def generate_structured_sync(
        self,
        prompt: str,
        response_model: Type[T],
        temperature: float = 0.7,
        max_retries: int = 3,
        model: Optional[str] = None
    ) -> T:
        """Synchronous version of generate_structured.
        
        Use this in non-async contexts like LangGraph node functions.
        """
        model_name = f"ollama/{model or self.model}"
        
        messages = [
            {
                "role": "system",
                "content": "You are a precise data extraction assistant. Extract information exactly as requested and format as JSON."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        response = self.client(
            model=model_name,
            messages=messages,
            response_model=response_model,
            temperature=temperature,
            max_retries=max_retries,
            api_base=self.base_url
        )
        
        return response
```

- [ ] **Step 5: Run test to verify smoke test passes**

Run:
```bash
cd backend
pytest tests/unit/core/test_instructor_client.py::test_instructor_client_can_be_instantiated -v
```

Expected: 1 test PASS (integration test skipped)

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/app/core/instructor_client.py backend/tests/unit/core/test_instructor_client.py
git commit -m "feat: add Instructor + LiteLLM integration for structured LLM outputs

- Add instructor==1.7.0 and litellm==1.55.0 dependencies
- Create InstructorOllamaClient wrapper using LiteLLM adapter
- LiteLLM provides OpenAI-compatible interface for Ollama
- Automatically validates LLM outputs against Pydantic schemas
- Retries on validation failure (configurable max_retries)
- Both async and sync methods available
- Smoke test passing (1/1)

- Add instructor==1.7.0 dependency
- Create InstructorOllamaClient wrapper for OllamaClient
- Automatically validates LLM outputs against Pydantic schemas
- Retries on validation failure (configurable max_retries)
- Smoke test passing (1/1)

Will be used for:
- Parsing BRS tool outputs into structured formats
- Validating workflow step results
- Extracting structured data from activation forms"
```

---

## Task 4: BRS Tool Registry (Definitions + Schemas)

**Files:**
- Create: `backend/app/services/brs_tools/__init__.py`
- Create: `backend/app/services/brs_tools/registry.py`
- Create: `backend/app/services/brs_tools/schemas.py`
- Create: `backend/tests/unit/services/brs_tools/test_registry.py`

- [ ] **Step 1: Write test for tool registry**

Create `backend/tests/unit/services/brs_tools/test_registry.py`:

```python
import pytest
from app.services.brs_tools.registry import BRSToolRegistry, ToolDefinition
from app.services.brs_tools.schemas import TeesheetInitOutput


def test_registry_get_all_tools():
    """Should return all registered tools."""
    registry = BRSToolRegistry()
    tools = registry.get_all_tools()
    
    assert len(tools) > 0
    assert all(isinstance(tool, ToolDefinition) for tool in tools)


def test_registry_get_tool_by_name():
    """Should retrieve tool by name."""
    registry = BRSToolRegistry()
    tool = registry.get_tool("brs_teesheet_init")
    
    assert tool is not None
    assert tool.name == "brs_teesheet_init"
    assert tool.description
    assert len(tool.parameters) > 0
    assert tool.cli_template
    assert tool.output_schema == TeesheetInitOutput


def test_registry_get_nonexistent_tool_returns_none():
    """Should return None for unknown tool."""
    registry = BRSToolRegistry()
    tool = registry.get_tool("nonexistent_tool")
    
    assert tool is None


def test_tool_definition_cli_template_has_placeholders():
    """CLI template should use {param_name} placeholders."""
    registry = BRSToolRegistry()
    tool = registry.get_tool("brs_teesheet_init")
    
    assert "{club_name}" in tool.cli_template
    assert "{club_id}" in tool.cli_template
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd backend
pytest tests/unit/services/brs_tools/test_registry.py -v
```

Expected: FAIL with "No module named 'app.services.brs_tools.registry'"

- [ ] **Step 3: Create BRS tool schemas**

Create `backend/app/services/brs_tools/__init__.py`:

```python
"""BRS Tool Gateway - Internal service for executing BRS CLI commands.

NOT an MCP server. This is a direct subprocess wrapper with:
- Tool Registry: definitions → CLI templates → output schemas
- Execution Layer: validate → build → run → parse
- Mock Mode: fake CLI responses for dev/test
"""
```

Create `backend/app/services/brs_tools/schemas.py`:

```python
from typing import Optional, List
from pydantic import BaseModel, Field


class TeesheetInitOutput(BaseModel):
    """Output schema for brs_teesheet_init command."""
    success: bool = Field(description="Whether initialization succeeded")
    database_name: str = Field(description="Name of created database")
    stdout: str = Field(description="Raw stdout from CLI command")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class SuperuserCreateOutput(BaseModel):
    """Output schema for brs_create_superuser command."""
    success: bool = Field(description="Whether superuser creation succeeded")
    user_id: Optional[int] = Field(default=None, description="Created user ID")
    email: str = Field(description="Superuser email address")
    stdout: str = Field(description="Raw stdout from CLI command")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class ConfigValidateOutput(BaseModel):
    """Output schema for brs_config_validate command."""
    success: bool = Field(description="Whether configuration is valid")
    errors: List[str] = Field(default_factory=list, description="Validation errors")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    stdout: str = Field(description="Raw stdout from CLI command")
```

- [ ] **Step 4: Create tool registry**

Create `backend/app/services/brs_tools/registry.py`:

```python
from typing import Dict, List, Optional, Type
from dataclasses import dataclass
from pydantic import BaseModel
from app.services.brs_tools.schemas import (
    TeesheetInitOutput,
    SuperuserCreateOutput,
    ConfigValidateOutput
)


@dataclass
class ToolParameter:
    """Definition of a tool parameter."""
    name: str
    type: str  # "string", "integer", "boolean"
    description: str
    required: bool = True
    default: Optional[str] = None


@dataclass
class ToolDefinition:
    """Complete definition of a BRS tool.
    
    Attributes:
        name: Tool identifier (e.g., "brs_teesheet_init")
        description: Human-readable description
        parameters: List of input parameters
        cli_template: Template string for CLI command (uses {param_name} placeholders)
        output_schema: Pydantic model for parsing output
        timeout_seconds: Maximum execution time
    """
    name: str
    description: str
    parameters: List[ToolParameter]
    cli_template: str
    output_schema: Type[BaseModel]
    timeout_seconds: int = 300


class BRSToolRegistry:
    """Registry of all BRS tools with their definitions.
    
    Usage:
        registry = BRSToolRegistry()
        tool = registry.get_tool("brs_teesheet_init")
        
        print(tool.description)
        print(tool.cli_template)
        print(tool.output_schema)
    """
    
    def __init__(self):
        """Initialize registry with tool definitions."""
        self._tools: Dict[str, ToolDefinition] = {}
        self._register_tools()
    
    def _register_tools(self):
        """Register all BRS tools."""
        
        # Tool 1: Teesheet Initialization
        self._tools["brs_teesheet_init"] = ToolDefinition(
            name="brs_teesheet_init",
            description="Initialize a new teesheet database for a golf club",
            parameters=[
                ToolParameter(
                    name="club_name",
                    type="string",
                    description="Name of the golf club (e.g., 'Pebble Beach')",
                    required=True
                ),
                ToolParameter(
                    name="club_id",
                    type="string",
                    description="Unique club identifier (e.g., 'PB001')",
                    required=True
                )
            ],
            cli_template="./bin/teesheet init {club_name} {club_id}",
            output_schema=TeesheetInitOutput,
            timeout_seconds=120
        )
        
        # Tool 2: Superuser Creation
        self._tools["brs_create_superuser"] = ToolDefinition(
            name="brs_create_superuser",
            description="Create a superuser account for club administration",
            parameters=[
                ToolParameter(
                    name="club_name",
                    type="string",
                    description="Name of the golf club",
                    required=True
                ),
                ToolParameter(
                    name="email",
                    type="string",
                    description="Superuser email address",
                    required=True
                ),
                ToolParameter(
                    name="name",
                    type="string",
                    description="Superuser full name",
                    required=True
                )
            ],
            cli_template="./bin/teesheet update-superusers {club_name} --email {email} --name {name}",
            output_schema=SuperuserCreateOutput,
            timeout_seconds=60
        )
        
        # Tool 3: Configuration Validation
        self._tools["brs_config_validate"] = ToolDefinition(
            name="brs_config_validate",
            description="Validate club configuration before deployment",
            parameters=[
                ToolParameter(
                    name="club_id",
                    type="string",
                    description="Unique club identifier",
                    required=True
                )
            ],
            cli_template="./bin/config validate {club_id}",
            output_schema=ConfigValidateOutput,
            timeout_seconds=30
        )
    
    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Get tool definition by name.
        
        Args:
            name: Tool name (e.g., "brs_teesheet_init")
            
        Returns:
            ToolDefinition if found, None otherwise
        """
        return self._tools.get(name)
    
    def get_all_tools(self) -> List[ToolDefinition]:
        """Get all registered tools.
        
        Returns:
            List of all tool definitions
        """
        return list(self._tools.values())
    
    def list_tool_names(self) -> List[str]:
        """Get list of all tool names.
        
        Returns:
            List of tool names
        """
        return list(self._tools.keys())
```

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
cd backend
pytest tests/unit/services/brs_tools/test_registry.py -v
```

Expected: 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/brs_tools/ backend/tests/unit/services/brs_tools/test_registry.py
git commit -m "feat: add BRS tool registry with definitions and schemas

- Create BRSToolRegistry with 3 initial tools:
  - brs_teesheet_init (database initialization)
  - brs_create_superuser (admin account creation)
  - brs_config_validate (configuration validation)
- Define Pydantic schemas for structured tool outputs
- CLI templates use {param_name} placeholders
- All tests passing (4/4)

Registry provides:
- Tool discovery (get_tool, get_all_tools)
- Parameter definitions with validation rules
- CLI command templates for subprocess execution
- Output schemas for Instructor parsing"
```

---

## Task 5: BRS Tool Execution Layer (Command Builder + Subprocess)

**Files:**
- Create: `backend/app/services/brs_tools/executor.py`
- Create: `backend/tests/unit/services/brs_tools/test_executor.py`
- Modify: `backend/.env.example`

- [x] **Step 1: Write test for command builder**

Create `backend/tests/unit/services/brs_tools/test_executor.py`:

```python
import pytest
from app.services.brs_tools.executor import BRSToolExecutor, CommandBuildError
from app.services.brs_tools.registry import BRSToolRegistry


def test_build_command_from_template():
    """Should build CLI command from template and parameters."""
    registry = BRSToolRegistry()
    executor = BRSToolExecutor(registry, brs_teesheet_path="/fake/path")
    
    tool = registry.get_tool("brs_teesheet_init")
    params = {"club_name": "Test Club", "club_id": "TC001"}
    
    command = executor._build_command(tool, params)
    
    assert command == ["./bin/teesheet", "init", "Test Club", "TC001"]


def test_build_command_missing_required_param_raises_error():
    """Should raise error if required parameter is missing."""
    registry = BRSToolRegistry()
    executor = BRSToolExecutor(registry, brs_teesheet_path="/fake/path")
    
    tool = registry.get_tool("brs_teesheet_init")
    params = {"club_name": "Test Club"}  # Missing club_id
    
    with pytest.raises(CommandBuildError) as exc_info:
        executor._build_command(tool, params)
    
    assert "club_id" in str(exc_info.value).lower()


def test_validate_parameters_success():
    """Should validate parameters successfully."""
    registry = BRSToolRegistry()
    executor = BRSToolExecutor(registry, brs_teesheet_path="/fake/path")
    
    tool = registry.get_tool("brs_teesheet_init")
    params = {"club_name": "Test Club", "club_id": "TC001"}
    
    # Should not raise
    executor._validate_parameters(tool, params)


def test_validate_parameters_missing_required():
    """Should raise error for missing required parameters."""
    registry = BRSToolRegistry()
    executor = BRSToolExecutor(registry, brs_teesheet_path="/fake/path")
    
    tool = registry.get_tool("brs_teesheet_init")
    params = {}
    
    with pytest.raises(CommandBuildError):
        executor._validate_parameters(tool, params)


@pytest.mark.asyncio
async def test_execute_tool_integration_skipped():
    """Integration test for actual subprocess execution (skipped in unit tests)."""
    pytest.skip("Integration test - requires actual BRS CLI")
```

- [x] **Step 2: Run test to verify it fails**

Run:
```bash
cd backend
pytest tests/unit/services/brs_tools/test_executor.py -v
```

Expected: FAIL with "No module named 'app.services.brs_tools.executor'"

- [x] **Step 3: Create BRS tool executor**

Create `backend/app/services/brs_tools/executor.py`:

```python
import os
import asyncio
from typing import Dict, Any, List
from app.services.brs_tools.registry import BRSToolRegistry, ToolDefinition


class CommandBuildError(Exception):
    """Raised when command cannot be built from template."""
    pass


class ExecutionError(Exception):
    """Raised when tool execution fails."""
    pass


class BRSToolExecutor:
    """Executes BRS tools via subprocess with timeout and error handling.
    
    Usage:
        registry = BRSToolRegistry()
        executor = BRSToolExecutor(registry, brs_teesheet_path="/path/to/brs-teesheet")
        
        result = await executor.execute_tool(
            tool_name="brs_teesheet_init",
            parameters={"club_name": "Test Club", "club_id": "TC001"}
        )
        
        print(result.returncode)
        print(result.stdout)
    """
    
    def __init__(
        self,
        registry: BRSToolRegistry,
        brs_teesheet_path: str,
        brs_config_path: str = "",
        timeout_multiplier: float = 1.0
    ):
        """Initialize executor with registry and paths.
        
        Args:
            registry: Tool registry for definitions
            brs_teesheet_path: Path to brs-teesheet repository
            brs_config_path: Path to brs-config-api repository
            timeout_multiplier: Multiplier for tool timeouts (for slower systems)
        """
        self.registry = registry
        self.brs_teesheet_path = brs_teesheet_path
        self.brs_config_path = brs_config_path
        self.timeout_multiplier = timeout_multiplier
    
    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> asyncio.subprocess.Process:
        """Execute a BRS tool with given parameters.
        
        Args:
            tool_name: Name of tool to execute
            parameters: Parameter dictionary matching tool definition
            
        Returns:
            Completed subprocess result
            
        Raises:
            CommandBuildError: If command cannot be built
            ExecutionError: If execution fails or times out
        """
        # Get tool definition
        tool = self.registry.get_tool(tool_name)
        if tool is None:
            raise CommandBuildError(f"Tool not found: {tool_name}")
        
        # Validate parameters
        self._validate_parameters(tool, parameters)
        
        # Build command
        command = self._build_command(tool, parameters)
        
        # Determine working directory
        cwd = self._get_working_directory(tool)
        
        # Calculate timeout
        timeout = tool.timeout_seconds * self.timeout_multiplier
        
        # Execute with timeout
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            
            # Store results on process object for compatibility
            process.stdout_bytes = stdout
            process.stderr_bytes = stderr
            process.stdout_text = stdout.decode('utf-8', errors='replace')
            process.stderr_text = stderr.decode('utf-8', errors='replace')
            
            return process
            
        except asyncio.TimeoutError:
            raise ExecutionError(
                f"Tool execution timed out after {timeout}s: {tool_name}"
            )
        except Exception as e:
            raise ExecutionError(f"Tool execution failed: {tool_name}: {e}")
    
    def _validate_parameters(
        self,
        tool: ToolDefinition,
        parameters: Dict[str, Any]
    ):
        """Validate parameters against tool definition.
        
        Args:
            tool: Tool definition
            parameters: Parameter dictionary
            
        Raises:
            CommandBuildError: If validation fails
        """
        # Check required parameters
        for param in tool.parameters:
            if param.required and param.name not in parameters:
                raise CommandBuildError(
                    f"Missing required parameter '{param.name}' for tool '{tool.name}'"
                )
    
    def _build_command(
        self,
        tool: ToolDefinition,
        parameters: Dict[str, Any]
    ) -> List[str]:
        """Build CLI command from template and parameters.
        
        Args:
            tool: Tool definition with CLI template
            parameters: Parameter dictionary
            
        Returns:
            Command as list of strings for subprocess
            
        Raises:
            CommandBuildError: If command cannot be built
        """
        try:
            # Replace placeholders in template
            command_str = tool.cli_template
            for param_name, param_value in parameters.items():
                placeholder = f"{{{param_name}}}"
                command_str = command_str.replace(placeholder, str(param_value))
            
            # Check for unreplaced placeholders
            if "{" in command_str and "}" in command_str:
                raise CommandBuildError(
                    f"Unreplaced placeholders in command: {command_str}"
                )
            
            # Split into list for subprocess
            command_parts = command_str.split()
            return command_parts
            
        except Exception as e:
            raise CommandBuildError(f"Failed to build command: {e}")
    
    def _get_working_directory(self, tool: ToolDefinition) -> str:
        """Get working directory for tool execution.
        
        Args:
            tool: Tool definition
            
        Returns:
            Absolute path to working directory
        """
        # Determine repo based on tool name
        if "teesheet" in tool.name.lower():
            return self.brs_teesheet_path
        elif "config" in tool.name.lower():
            return self.brs_config_path
        else:
            return self.brs_teesheet_path  # Default
```

- [x] **Step 4: Run tests to verify they pass**

Run:
```bash
cd backend
pytest tests/unit/services/brs_tools/test_executor.py -v
```

Expected: 5 tests PASS (1 skipped)

- [x] **Step 5: Update environment example with BRS paths**

Modify `backend/.env.example`:

```bash
# Add BRS repository paths
BRS_TEESHEET_PATH=/path/to/brs-teesheet
BRS_CONFIG_PATH=/path/to/brs-config-api
BRS_TOOL_TIMEOUT_MULTIPLIER=1.0
```

- [x] **Step 6: Commit**

```bash
git add backend/app/services/brs_tools/executor.py backend/tests/unit/services/brs_tools/test_executor.py backend/.env.example
git commit -m "feat: add BRS tool execution layer with subprocess runner

- Create BRSToolExecutor for subprocess execution
- Validate parameters against tool definitions
- Build CLI commands from templates
- Execute with configurable timeout
- Determine working directory based on tool type
- All tests passing (5/5, 1 skipped integration test)

Features:
- Parameter validation before execution
- Template-based command building
- Timeout protection with multiplier for slow systems
- Async subprocess execution
- Captures stdout/stderr for parsing"
```

---

## Task 6: BRS Tool Output Parser (Instructor Integration)

**Files:**
- Create: `backend/app/services/brs_tools/parser.py`
- Create: `backend/tests/unit/services/brs_tools/test_parser.py`

- [ ] **Step 1: Write test for output parser**

Create `backend/tests/unit/services/brs_tools/test_parser.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.brs_tools.parser import BRSToolOutputParser
from app.services.brs_tools.schemas import TeesheetInitOutput
from app.core.instructor_client import InstructorOllamaClient


@pytest.mark.asyncio
async def test_parse_output_with_instructor():
    """Should parse CLI output into structured schema."""
    # Mock Instructor client
    mock_instructor = AsyncMock(spec=InstructorOllamaClient)
    mock_instructor.generate_structured.return_value = TeesheetInitOutput(
        success=True,
        database_name="test_club_db",
        stdout="Database initialized successfully\nCreated database: test_club_db",
        error=None
    )
    
    parser = BRSToolOutputParser(mock_instructor)
    
    # Mock process result
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stdout_text = "Database initialized successfully\nCreated database: test_club_db"
    mock_process.stderr_text = ""
    
    result = await parser.parse_output(
        process=mock_process,
        output_schema=TeesheetInitOutput,
        tool_name="brs_teesheet_init"
    )
    
    assert isinstance(result, TeesheetInitOutput)
    assert result.success is True
    assert result.database_name == "test_club_db"


@pytest.mark.asyncio
async def test_parse_output_fallback_on_instructor_failure():
    """Should fallback to best-effort parsing if Instructor fails."""
    # Mock Instructor client that fails
    mock_instructor = AsyncMock(spec=InstructorOllamaClient)
    mock_instructor.generate_structured.side_effect = Exception("LLM error")
    
    parser = BRSToolOutputParser(mock_instructor)
    
    # Mock process result
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stdout_text = "Some output"
    mock_process.stderr_text = ""
    
    result = await parser.parse_output(
        process=mock_process,
        output_schema=TeesheetInitOutput,
        tool_name="brs_teesheet_init"
    )
    
    # Should return schema with success based on returncode
    assert isinstance(result, TeesheetInitOutput)
    assert result.success is True  # returncode 0
    assert result.stdout == "Some output"


def test_build_parsing_prompt():
    """Should build prompt for Instructor."""
    parser = BRSToolOutputParser(None)
    
    prompt = parser._build_parsing_prompt(
        stdout="Database created: test_db",
        stderr="",
        returncode=0,
        tool_name="brs_teesheet_init"
    )
    
    assert "brs_teesheet_init" in prompt
    assert "Database created: test_db" in prompt
    assert "returncode: 0" in prompt.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd backend
pytest tests/unit/services/brs_tools/test_parser.py -v
```

Expected: FAIL with "No module named 'app.services.brs_tools.parser'"

- [ ] **Step 3: Create output parser**

Create `backend/app/services/brs_tools/parser.py`:

```python
from typing import Type, TypeVar, Optional
import asyncio
from pydantic import BaseModel, ValidationError
from app.core.instructor_client import InstructorOllamaClient

T = TypeVar('T', bound=BaseModel)


class BRSToolOutputParser:
    """Parses BRS tool output into structured Pydantic schemas using Instructor.
    
    Usage:
        instructor = InstructorOllamaClient()
        parser = BRSToolOutputParser(instructor)
        
        process = await executor.execute_tool("brs_teesheet_init", {...})
        result = await parser.parse_output(
            process=process,
            output_schema=TeesheetInitOutput,
            tool_name="brs_teesheet_init"
        )
        
        assert isinstance(result, TeesheetInitOutput)
        print(result.database_name)
    """
    
    def __init__(self, instructor_client: Optional[InstructorOllamaClient] = None):
        """Initialize parser with Instructor client.
        
        Args:
            instructor_client: Instructor client for LLM-based parsing (optional)
        """
        self.instructor_client = instructor_client
    
    async def parse_output(
        self,
        process: asyncio.subprocess.Process,
        output_schema: Type[T],
        tool_name: str
    ) -> T:
        """Parse subprocess output into structured schema.
        
        Args:
            process: Completed subprocess with stdout/stderr
            output_schema: Pydantic model for output structure
            tool_name: Name of tool (for prompt context)
            
        Returns:
            Instance of output_schema with parsed data
            
        Raises:
            ValidationError: If parsing fails and fallback also fails
        """
        stdout = getattr(process, 'stdout_text', '')
        stderr = getattr(process, 'stderr_text', '')
        returncode = process.returncode
        
        # Try Instructor-based parsing if available
        if self.instructor_client:
            try:
                prompt = self._build_parsing_prompt(
                    stdout=stdout,
                    stderr=stderr,
                    returncode=returncode,
                    tool_name=tool_name
                )
                
                result = await self.instructor_client.generate_structured(
                    prompt=prompt,
                    response_model=output_schema,
                    temperature=0.0,  # Deterministic parsing
                    max_retries=2
                )
                
                return result
                
            except Exception as e:
                # Fallback to best-effort parsing
                pass
        
        # Fallback: create schema with minimal data
        return self._fallback_parse(
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
            output_schema=output_schema
        )
    
    def _build_parsing_prompt(
        self,
        stdout: str,
        stderr: str,
        returncode: int,
        tool_name: str
    ) -> str:
        """Build prompt for Instructor to parse CLI output.
        
        Args:
            stdout: Standard output from CLI
            stderr: Standard error from CLI
            returncode: Process exit code
            tool_name: Name of tool
            
        Returns:
            Prompt for LLM
        """
        return f"""Parse the output from the '{tool_name}' CLI command.

Return code: {returncode}

Standard output:
{stdout}

Standard error:
{stderr}

Extract structured information according to the schema. If the command succeeded (returncode 0), set success=True. Extract any relevant IDs, names, or messages from the output."""
    
    def _fallback_parse(
        self,
        stdout: str,
        stderr: str,
        returncode: int,
        output_schema: Type[T]
    ) -> T:
        """Best-effort parsing without LLM.
        
        Args:
            stdout: Standard output
            stderr: Standard error
            returncode: Exit code
            output_schema: Output schema to populate
            
        Returns:
            Schema instance with minimal data
        """
        # Build minimal data based on returncode
        data = {
            "success": returncode == 0,
            "stdout": stdout,
            "error": stderr if returncode != 0 else None
        }
        
        # Try to create schema (may fail if required fields missing)
        try:
            return output_schema(**data)
        except ValidationError:
            # Last resort: add empty/default values for required fields
            # This is hacky but ensures we always return something
            schema_fields = output_schema.__fields__
            for field_name, field_info in schema_fields.items():
                if field_name not in data:
                    # Add default based on type
                    if field_info.annotation == str:
                        data[field_name] = ""
                    elif field_info.annotation == int:
                        data[field_name] = 0
                    elif field_info.annotation == bool:
                        data[field_name] = False
            
            return output_schema(**data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd backend
pytest tests/unit/services/brs_tools/test_parser.py -v
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/brs_tools/parser.py backend/tests/unit/services/brs_tools/test_parser.py
git commit -m "feat: add BRS tool output parser with Instructor integration

- Create BRSToolOutputParser for structured output parsing
- Primary: Use Instructor + LLM for intelligent parsing
- Fallback: Best-effort parsing based on returncode
- Build parsing prompts with context from tool execution
- All tests passing (3/3)

Features:
- LLM-based parsing for complex CLI outputs
- Fallback parsing when LLM unavailable or fails
- Validates against Pydantic schemas
- Deterministic parsing (temperature=0.0)
- Retry logic on validation failure"
```

---

## Task 7: Mock Mode for BRS Tools

**Files:**
- Create: `backend/app/services/brs_tools/mock.py`
- Create: `backend/tests/unit/services/brs_tools/test_mock.py`

- [ ] **Step 1: Write test for mock executor**

Create `backend/tests/unit/services/brs_tools/test_mock.py`:

```python
import pytest
from app.services.brs_tools.mock import MockBRSToolExecutor
from app.services.brs_tools.registry import BRSToolRegistry
from app.services.brs_tools.schemas import TeesheetInitOutput


@pytest.mark.asyncio
async def test_mock_executor_returns_fake_process():
    """Should return fake process with mocked output."""
    registry = BRSToolRegistry()
    mock_executor = MockBRSToolExecutor(registry)
    
    result = await mock_executor.execute_tool(
        tool_name="brs_teesheet_init",
        parameters={"club_name": "Test Club", "club_id": "TC001"}
    )
    
    assert result.returncode == 0
    assert result.stdout_text
    assert "Test Club" in result.stdout_text or "TC001" in result.stdout_text


@pytest.mark.asyncio
async def test_mock_executor_records_call():
    """Should record tool calls for inspection."""
    registry = BRSToolRegistry()
    mock_executor = MockBRSToolExecutor(registry)
    
    await mock_executor.execute_tool(
        tool_name="brs_teesheet_init",
        parameters={"club_name": "Test Club", "club_id": "TC001"}
    )
    
    assert len(mock_executor.call_history) == 1
    call = mock_executor.call_history[0]
    assert call["tool_name"] == "brs_teesheet_init"
    assert call["parameters"]["club_name"] == "Test Club"


@pytest.mark.asyncio
async def test_mock_executor_can_simulate_failure():
    """Should simulate failure when configured."""
    registry = BRSToolRegistry()
    mock_executor = MockBRSToolExecutor(registry, simulate_failure=True)
    
    result = await mock_executor.execute_tool(
        tool_name="brs_teesheet_init",
        parameters={"club_name": "Test Club", "club_id": "TC001"}
    )
    
    assert result.returncode != 0
    assert result.stderr_text
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd backend
pytest tests/unit/services/brs_tools/test_mock.py -v
```

Expected: FAIL with "No module named 'app.services.brs_tools.mock'"

- [ ] **Step 3: Create mock executor**

Create `backend/app/services/brs_tools/mock.py`:

```python
from typing import Dict, Any, List
from datetime import datetime, timezone
from app.services.brs_tools.registry import BRSToolRegistry


class MockProcess:
    """Mock subprocess.Process for testing."""
    
    def __init__(
        self,
        returncode: int,
        stdout_text: str,
        stderr_text: str = ""
    ):
        self.returncode = returncode
        self.stdout_text = stdout_text
        self.stderr_text = stderr_text
        self.stdout_bytes = stdout_text.encode('utf-8')
        self.stderr_bytes = stderr_text.encode('utf-8')


class MockBRSToolExecutor:
    """Mock executor for BRS tools (no real CLI execution).
    
    Usage:
        registry = BRSToolRegistry()
        mock_executor = MockBRSToolExecutor(registry)
        
        result = await mock_executor.execute_tool(
            tool_name="brs_teesheet_init",
            parameters={"club_name": "Test Club", "club_id": "TC001"}
        )
        
        print(result.stdout_text)  # Fake output
        print(mock_executor.call_history)  # Inspect calls
    """
    
    def __init__(
        self,
        registry: BRSToolRegistry,
        simulate_failure: bool = False,
        failure_rate: float = 0.0
    ):
        """Initialize mock executor.
        
        Args:
            registry: Tool registry for definitions
            simulate_failure: Always simulate failures if True
            failure_rate: Random failure rate (0.0-1.0)
        """
        self.registry = registry
        self.simulate_failure = simulate_failure
        self.failure_rate = failure_rate
        self.call_history: List[Dict[str, Any]] = []
    
    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> MockProcess:
        """Execute tool in mock mode (no real CLI).
        
        Args:
            tool_name: Name of tool to execute
            parameters: Parameter dictionary
            
        Returns:
            MockProcess with fake output
        """
        # Record call
        self.call_history.append({
            "tool_name": tool_name,
            "parameters": parameters.copy(),
            "timestamp": datetime.now(timezone.utc)
        })
        
        # Get tool definition
        tool = self.registry.get_tool(tool_name)
        if tool is None:
            return MockProcess(
                returncode=1,
                stdout_text="",
                stderr_text=f"Error: Tool not found: {tool_name}"
            )
        
        # Simulate failure if configured
        if self.simulate_failure:
            return self._generate_failure_output(tool_name, parameters)
        
        # Generate success output
        return self._generate_success_output(tool_name, parameters)
    
    def _generate_success_output(
        self,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> MockProcess:
        """Generate fake success output for tool.
        
        Args:
            tool_name: Name of tool
            parameters: Parameters passed to tool
            
        Returns:
            MockProcess with success output
        """
        if tool_name == "brs_teesheet_init":
            club_name = parameters.get("club_name", "Unknown")
            club_id = parameters.get("club_id", "UNK")
            database_name = f"{club_name.lower().replace(' ', '_')}_db"
            
            stdout = f"""Initializing teesheet for {club_name} ({club_id})
Creating database: {database_name}
Running migrations...
Database initialized successfully
"""
            return MockProcess(returncode=0, stdout_text=stdout)
        
        elif tool_name == "brs_create_superuser":
            email = parameters.get("email", "admin@example.com")
            name = parameters.get("name", "Admin User")
            
            stdout = f"""Creating superuser account
Email: {email}
Name: {name}
Superuser created successfully
User ID: 12345
"""
            return MockProcess(returncode=0, stdout_text=stdout)
        
        elif tool_name == "brs_config_validate":
            club_id = parameters.get("club_id", "UNK")
            
            stdout = f"""Validating configuration for {club_id}
✓ Database connection valid
✓ Teesheet settings valid
✓ Booking rules valid
Configuration is valid
"""
            return MockProcess(returncode=0, stdout_text=stdout)
        
        else:
            # Generic success
            stdout = f"Mock execution of {tool_name} completed successfully\n"
            return MockProcess(returncode=0, stdout_text=stdout)
    
    def _generate_failure_output(
        self,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> MockProcess:
        """Generate fake failure output for tool.
        
        Args:
            tool_name: Name of tool
            parameters: Parameters passed to tool
            
        Returns:
            MockProcess with failure output
        """
        stderr = f"Error: Mock failure for {tool_name}\n"
        return MockProcess(returncode=1, stdout_text="", stderr_text=stderr)
    
    def clear_history(self):
        """Clear call history."""
        self.call_history.clear()
    
    def get_calls_for_tool(self, tool_name: str) -> List[Dict[str, Any]]:
        """Get all recorded calls for a specific tool.
        
        Args:
            tool_name: Tool name to filter by
            
        Returns:
            List of call records
        """
        return [
            call for call in self.call_history
            if call["tool_name"] == tool_name
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd backend
pytest tests/unit/services/brs_tools/test_mock.py -v
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/brs_tools/mock.py backend/tests/unit/services/brs_tools/test_mock.py
git commit -m "feat: add mock executor for BRS tools (no real CLI)

- Create MockBRSToolExecutor for development/testing
- Generate realistic fake outputs for each tool
- Record call history for test assertions
- Support simulated failures
- All tests passing (3/3)

Features:
- No subprocess execution (fast tests)
- Realistic fake outputs matching real CLI behavior
- Call history tracking
- Configurable failure simulation
- Drop-in replacement for BRSToolExecutor in tests"
```

---

## Task 8: Integration Tests with Mock BRS Tools

**Files:**
- Create: `backend/tests/integration/test_brs_tools_e2e.py`

- [ ] **Step 1: Write end-to-end test with all components**

Create `backend/tests/integration/test_brs_tools_e2e.py`:

```python
import pytest
from app.services.brs_tools.registry import BRSToolRegistry
from app.services.brs_tools.mock import MockBRSToolExecutor
from app.services.brs_tools.parser import BRSToolOutputParser
from app.services.brs_tools.schemas import TeesheetInitOutput, SuperuserCreateOutput


@pytest.mark.asyncio
async def test_brs_tool_gateway_e2e_teesheet_init():
    """Test complete flow: registry → mock executor → parser."""
    # Setup
    registry = BRSToolRegistry()
    executor = MockBRSToolExecutor(registry)
    parser = BRSToolOutputParser(instructor_client=None)  # Fallback mode
    
    # Get tool
    tool = registry.get_tool("brs_teesheet_init")
    assert tool is not None
    
    # Execute
    parameters = {"club_name": "Pebble Beach", "club_id": "PB001"}
    process = await executor.execute_tool("brs_teesheet_init", parameters)
    
    # Parse
    result = await parser.parse_output(
        process=process,
        output_schema=TeesheetInitOutput,
        tool_name="brs_teesheet_init"
    )
    
    # Verify
    assert isinstance(result, TeesheetInitOutput)
    assert result.success is True
    assert "pebble_beach_db" in result.database_name.lower()
    assert "Pebble Beach" in result.stdout or "PB001" in result.stdout
    
    # Verify call was recorded
    assert len(executor.call_history) == 1
    assert executor.call_history[0]["tool_name"] == "brs_teesheet_init"


@pytest.mark.asyncio
async def test_brs_tool_gateway_e2e_superuser_create():
    """Test complete flow for superuser creation."""
    # Setup
    registry = BRSToolRegistry()
    executor = MockBRSToolExecutor(registry)
    parser = BRSToolOutputParser(instructor_client=None)
    
    # Execute
    parameters = {
        "club_name": "Pebble Beach",
        "email": "admin@pebblebeach.com",
        "name": "John Admin"
    }
    process = await executor.execute_tool("brs_create_superuser", parameters)
    
    # Parse
    result = await parser.parse_output(
        process=process,
        output_schema=SuperuserCreateOutput,
        tool_name="brs_create_superuser"
    )
    
    # Verify
    assert isinstance(result, SuperuserCreateOutput)
    assert result.success is True
    assert result.email == "admin@pebblebeach.com"
    assert "John Admin" in result.stdout


@pytest.mark.asyncio
async def test_brs_tool_gateway_e2e_failure_handling():
    """Test failure handling through the pipeline."""
    # Setup with failure simulation
    registry = BRSToolRegistry()
    executor = MockBRSToolExecutor(registry, simulate_failure=True)
    parser = BRSToolOutputParser(instructor_client=None)
    
    # Execute (will fail)
    parameters = {"club_name": "Test Club", "club_id": "TC001"}
    process = await executor.execute_tool("brs_teesheet_init", parameters)
    
    # Parse
    result = await parser.parse_output(
        process=process,
        output_schema=TeesheetInitOutput,
        tool_name="brs_teesheet_init"
    )
    
    # Verify failure was captured
    assert isinstance(result, TeesheetInitOutput)
    assert result.success is False
    assert result.error is not None


@pytest.mark.asyncio
async def test_brs_tool_gateway_e2e_workflow_integration():
    """Test BRS tools in a workflow-like sequence."""
    # Setup
    registry = BRSToolRegistry()
    executor = MockBRSToolExecutor(registry)
    parser = BRSToolOutputParser(instructor_client=None)
    
    # Step 1: Initialize teesheet
    init_result = await parser.parse_output(
        process=await executor.execute_tool(
            "brs_teesheet_init",
            {"club_name": "Test Club", "club_id": "TC001"}
        ),
        output_schema=TeesheetInitOutput,
        tool_name="brs_teesheet_init"
    )
    assert init_result.success is True
    
    # Step 2: Create superuser
    superuser_result = await parser.parse_output(
        process=await executor.execute_tool(
            "brs_create_superuser",
            {
                "club_name": "Test Club",
                "email": "admin@test.com",
                "name": "Admin User"
            }
        ),
        output_schema=SuperuserCreateOutput,
        tool_name="brs_create_superuser"
    )
    assert superuser_result.success is True
    
    # Verify call sequence
    assert len(executor.call_history) == 2
    assert executor.call_history[0]["tool_name"] == "brs_teesheet_init"
    assert executor.call_history[1]["tool_name"] == "brs_create_superuser"
```

- [ ] **Step 2: Run test to verify it passes**

Run:
```bash
cd backend
pytest tests/integration/test_brs_tools_e2e.py -v
```

Expected: 4 tests PASS

- [ ] **Step 3: Run all BRS tool tests**

Run:
```bash
cd backend
pytest tests/unit/services/brs_tools/ tests/integration/test_brs_tools_e2e.py -v
```

Expected: All tests PASS (~20 tests total)

- [ ] **Step 4: Commit**

```bash
git add backend/tests/integration/test_brs_tools_e2e.py
git commit -m "test: add end-to-end integration tests for BRS tool gateway

- Test complete pipeline: registry → executor → parser
- Test teesheet init workflow
- Test superuser creation workflow
- Test failure handling
- Test multi-step workflow sequence
- All tests passing (4/4 integration, ~20 total)

Coverage:
- Registry lookup
- Mock execution
- Output parsing
- Call history tracking
- Failure simulation
- Workflow integration patterns"
```

---

## Task 9: Documentation

**Files:**
- Create: `backend/docs/phase-2-complete.md`
- Modify: `backend/README.md`

- [ ] **Step 1: Create Phase 2 completion documentation**

Create `backend/docs/phase-2-complete.md`:

```markdown
# Phase 2: BRS Tools + Core Observability - COMPLETE ✅

## Overview

Phase 2 adds self-hosted Langfuse for workflow tracing, Instructor for structured LLM outputs, and BRS Tool Gateway for executing teesheet CLI commands with mock mode for development/testing.

## What Was Built

### 1. Langfuse (Self-Hosted Observability)

**Purpose**: Trace every workflow execution with full observability

**Components**:
- `docker-compose.langfuse.yml` - Self-hosted Langfuse + PostgreSQL
- `app/core/langfuse_config.py` - Singleton + callback factory
- Integrated with `WorkflowOrchestrator.execute_workflow()`

**Usage**:
```bash
# Start Langfuse
docker-compose -f backend/docker-compose.langfuse.yml up -d

# Access UI
open http://localhost:3000

# Create account and get API keys
# Add to .env:
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
```

**Traces Automatically**:
- Workflow execution spans
- Step-by-step execution
- LLM calls (when added)
- BRS tool calls
- User/session grouping

### 2. Instructor (Structured LLM Outputs)

**Purpose**: Enforce Pydantic schemas on LLM outputs with automatic retry

**Components**:
- `app/core/instructor_client.py` - Wrapper for OllamaClient
- Automatic validation and retry logic

**Usage**:
```python
from app.core.instructor_client import InstructorOllamaClient
from pydantic import BaseModel

class ClubConfig(BaseModel):
    club_name: str
    club_id: str

client = InstructorOllamaClient()
result = await client.generate_structured(
    prompt="Extract: Test Golf Club (TGC123)",
    response_model=ClubConfig
)

assert isinstance(result, ClubConfig)
```

### 3. BRS Tool Gateway

**Purpose**: Execute BRS CLI commands with structured output parsing

**Architecture**:
```
Tool Registry → Execution Layer → Output Parser
     ↓               ↓                  ↓
  Definitions    Subprocess        Instructor
  + Schemas     + Validation       + Fallback
```

**Components**:
- `app/services/brs_tools/registry.py` - Tool definitions + CLI templates
- `app/services/brs_tools/executor.py` - Subprocess runner
- `app/services/brs_tools/parser.py` - Output parser
- `app/services/brs_tools/mock.py` - Mock mode (no real CLI)
- `app/services/brs_tools/schemas.py` - Pydantic output models

**Registered Tools**:
1. `brs_teesheet_init` - Initialize club database
2. `brs_create_superuser` - Create admin account
3. `brs_config_validate` - Validate configuration

**Usage**:
```python
from app.services.brs_tools.registry import BRSToolRegistry
from app.services.brs_tools.executor import BRSToolExecutor
from app.services.brs_tools.parser import BRSToolOutputParser

# Real mode (requires BRS CLI)
registry = BRSToolRegistry()
executor = BRSToolExecutor(registry, brs_teesheet_path="/path/to/brs-teesheet")
parser = BRSToolOutputParser()

process = await executor.execute_tool(
    "brs_teesheet_init",
    {"club_name": "Pebble Beach", "club_id": "PB001"}
)

result = await parser.parse_output(
    process=process,
    output_schema=TeesheetInitOutput,
    tool_name="brs_teesheet_init"
)

print(result.database_name)  # "pebble_beach_db"
```

**Mock Mode** (for tests/dev):
```python
from app.services.brs_tools.mock import MockBRSToolExecutor

executor = MockBRSToolExecutor(registry)
process = await executor.execute_tool("brs_teesheet_init", {...})

# Returns fake output (no real CLI execution)
# Records calls for inspection: executor.call_history
```

## System Capabilities After Phase 2

✅ Workflow execution with full tracing (Langfuse)  
✅ User/session grouping for traces  
✅ LLM output validation (Instructor)  
✅ BRS tool execution with structured parsing  
✅ Mock mode for development/testing  
✅ Fallback parsing when LLM unavailable  
✅ Timeout protection for long-running CLI commands  
✅ Call history tracking for debugging  

## Database Schema

No new tables added in Phase 2. All changes are service-layer only.

## Test Coverage

- Unit tests: 20 tests passing
- Integration tests: 5 tests passing (1 e2e workflow test from Phase 1 + 4 BRS tool tests)
- Total: 25 tests passing

## Environment Variables

New variables in `.env`:
```bash
# Langfuse
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-local-dev
LANGFUSE_SECRET_KEY=sk-lf-local-dev
LANGFUSE_HOST=http://localhost:3000

# BRS Tool Paths
BRS_TEESHEET_PATH=/path/to/brs-teesheet
BRS_CONFIG_PATH=/path/to/brs-config-api
BRS_TOOL_TIMEOUT_MULTIPLIER=1.0
```

## Next Steps

**Phase 3: Onboarding Workflow + Testing + Analytics**
- Build complete teesheet onboarding workflow template
- Add DeepEval for workflow testing
- Create analytics dashboard on Langfuse traces
- Add prompt versioning

## Critical Learnings

1. **Langfuse traces are session-scoped** - Use unique session_id per workflow run
2. **Instructor requires JSON mode** - Set `mode=instructor.Mode.JSON`
3. **Fallback parsing is critical** - Always have non-LLM fallback for reliability
4. **Mock mode accelerates development** - Don't wait for real CLI setup
5. **Tool registry is single source of truth** - All tool definitions in one place

## How to Verify Phase 2

```bash
# 1. Start Langfuse
docker-compose -f backend/docker-compose.langfuse.yml up -d

# 2. Run all tests
cd backend
pytest tests/ -v

# 3. Check Langfuse UI
open http://localhost:3000

# 4. Execute a workflow and see trace appear in Langfuse
```

## Files Modified in Phase 2

**Created**:
- `docker-compose.langfuse.yml`
- `app/core/langfuse_config.py`
- `app/core/instructor_client.py`
- `app/services/brs_tools/*.py` (5 files)
- `tests/unit/core/*.py` (2 files)
- `tests/unit/services/brs_tools/*.py` (4 files)
- `tests/integration/test_brs_tools_e2e.py`

**Modified**:
- `app/services/workflow_orchestrator.py` (added Langfuse callback)
- `requirements.txt` (added langfuse, instructor)
- `.env.example` (added Langfuse + BRS paths)
```

- [ ] **Step 2: Update README with Phase 2 info**

Modify `backend/README.md`:

```markdown
# Add to "Development Phases" section

## Phase 2: BRS Tools + Core Observability ✅

**Completed**: 2026-05-01

- ✅ Self-hosted Langfuse for workflow tracing
- ✅ Instructor for structured LLM outputs
- ✅ BRS Tool Gateway (registry → executor → parser)
- ✅ Mock mode for development/testing
- ✅ 3 BRS tools registered (init, superuser, validate)

**See**: `docs/phase-2-complete.md`
```

- [ ] **Step 3: Commit**

```bash
git add backend/docs/phase-2-complete.md backend/README.md
git commit -m "docs: add Phase 2 completion documentation

- Document Langfuse setup and usage
- Document Instructor integration
- Document BRS Tool Gateway architecture
- Document mock mode for development
- List all registered tools and their usage
- Add environment variable reference
- Update README with Phase 2 status

Phase 2 Complete: ✅
- 25 tests passing
- All systems operational
- Ready for Phase 3 (Onboarding Workflow)"
```

---

## Phase 2 Complete! ✅

**Summary**: 9 of 9 tasks complete (100%)

**What We Built**:
- Self-hosted Langfuse for workflow tracing
- Instructor for structured LLM outputs
- BRS Tool Gateway (NOT MCP server)
  - Tool Registry with 3 registered tools
  - Execution Layer with subprocess runner
  - Output Parser with Instructor integration
  - Mock Mode for development/testing

**Ready for Phase 3**: Onboarding Workflow + Testing + Analytics

---

## Critical Learnings from Phase 2

1. **Langfuse First**: Always add observability before adding complexity (traces help debug Phase 3)
2. **BRS Tool Gateway ≠ MCP**: Internal service layer, not external MCP server
3. **Mock Mode is Essential**: Don't block development on CLI availability
4. **Instructor + Fallback**: Always have non-LLM parsing fallback
5. **Tool Registry Pattern**: Single source of truth for all tool definitions
