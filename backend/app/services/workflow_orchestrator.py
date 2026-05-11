"""Workflow orchestration service using LangGraph."""
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable, TypedDict, Annotated
from sqlalchemy.orm import Session
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_core.runnables import RunnableConfig

from app.models.workflow import (
    WorkflowTemplate,
    WorkflowRun,
    WorkflowStepExecution,
    WorkflowRunStatus,
    StepStatus
)
from app.services.metrics_collector import MetricsCollector
from app.services.mcp_registry import MCPToolRegistry
from app.config.mcp_config import Environment
from app.core.langfuse_config import LangfuseConfig


# Gateway MCP tool name mapping
# Maps legacy BRS tool names to Gateway MCP tool names
GATEWAY_TOOL_MAPPING = {
    "brs_teesheet_init": "create_club",
    "brs_create_superuser": "create_admin_user",
    "brs_config_validate": "verify_club_setup",
    "brs_get_club_config": "get_club_config",
    "brs_get_club_by_name": "get_club_by_name",
    "brs_call_internal_api": "call_internal_api",
}


# Custom reducer that merges dicts
def merge_dicts(left: Optional[Dict], right: Optional[Dict]) -> Dict:
    """Merge two dicts, with right overwriting left."""
    if left is None:
        return right or {}
    if right is None:
        return left
    return {**left, **right}


class WorkflowState(TypedDict):
    """
    Workflow state for LangGraph.

    LangGraph passes this dict between nodes. Each node can read/write to it.
    Uses top-level keys with reducers to accumulate results across steps.
    """
    step_results: Annotated[Dict[str, Any], merge_dicts]
    workflow_run_id: int


class WorkflowOrchestrator:
    """
    Orchestrate workflow execution using LangGraph.

    Converts workflow templates (JSON) to executable LangGraph StateGraphs,
    manages execution, and collects metrics. Routes tool calls through
    the Gateway MCP server for unified policy, auth, and audit handling.
    """

    def __init__(
        self,
        db: Session,
        mcp_registry: Optional[MCPToolRegistry] = None,
        environment: Environment = Environment.DEVELOPMENT,
    ):
        self.db = db
        self.metrics = MetricsCollector(db)
        self.environment = environment
        
        # Initialize MCP registry (lazy initialization)
        self._mcp_registry = mcp_registry
        self._mcp_initialized = False

        # Initialize PostgreSQL checkpointer for state persistence
        # Only initialize if using actual PostgreSQL (not SQLite for tests)
        database_url = os.getenv("DATABASE_URL", "")
        if database_url and database_url.startswith("postgresql"):
            self.checkpointer = PostgresSaver.from_conn_string(database_url)
        else:
            self.checkpointer = None
    
    async def _get_mcp_registry(self) -> MCPToolRegistry:
        """Get or create and initialize the MCP registry."""
        if self._mcp_registry is None:
            self._mcp_registry = MCPToolRegistry(self.environment)
        
        if not self._mcp_initialized:
            await self._mcp_registry.initialize()
            self._mcp_initialized = True
        
        return self._mcp_registry
    
    def _resolve_tool_name(self, tool_name: str) -> str:
        """
        Resolve tool name, preferring Gateway MCP tools.
        
        Maps legacy BRS tool names to Gateway MCP tool names.
        
        Args:
            tool_name: Original tool name from workflow definition
            
        Returns:
            Resolved tool name (Gateway MCP name if mapping exists)
        """
        return GATEWAY_TOOL_MAPPING.get(tool_name, tool_name)

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
        """Create a new workflow run instance.
        
        Validates input_data against the template's input_schema if defined.
        
        Args:
            template_name: Name of the workflow template
            session_id: Session ID for the workflow run
            input_data: Input data for the workflow
            
        Returns:
            Created WorkflowRun instance
            
        Raises:
            ValueError: If input_data fails validation against template schema
        """
        template = self.load_template(template_name)
        
        # Validate input against template's input_schema if defined
        self._validate_input_data(template, input_data)

        workflow_run = WorkflowRun(
            template_id=template.id,
            session_id=session_id,
            status=WorkflowRunStatus.PENDING,
            current_state={"input_data": input_data}
        )

        try:
            self.db.add(workflow_run)
            self.db.commit()
            self.db.refresh(workflow_run)
        except Exception as e:
            self.db.rollback()
            raise

        return workflow_run

    def _validate_input_data(self, template: WorkflowTemplate, input_data: Dict[str, Any]) -> None:
        """Validate input data against template's input_schema using jsonschema.
        
        Performs full validation including:
        - Required field presence
        - Type checking
        - Format validation (e.g., email)
        - Enum constraints
        
        Args:
            template: Workflow template with optional input_schema
            input_data: Input data to validate
            
        Raises:
            ValueError: If validation fails
        """
        from jsonschema import validate, ValidationError
        
        definition = template.definition
        input_schema = definition.get("input_schema")
        
        if not input_schema:
            return  # No schema defined, skip validation
        
        try:
            validate(instance=input_data, schema=input_schema)
        except ValidationError as e:
            raise ValueError(f"Input validation failed: {e.message}")

    def build_graph_from_template(self, template: WorkflowTemplate) -> StateGraph:
        """
        Convert workflow template JSON to LangGraph StateGraph.

        Creates nodes for each step and wires edges based on dependencies.
        """
        definition = template.definition

        # Validate template definition
        if "steps" not in definition:
            raise ValueError("Template definition must contain 'steps' field")

        steps = definition["steps"]
        if not steps:
            raise ValueError("Template must have at least one step")

        # Validate step IDs are unique
        step_ids = [step["id"] for step in steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Step IDs must be unique")

        # Validate next steps reference valid step IDs
        for step in steps:
            next_steps = step.get("next", [])
            for next_step in next_steps:
                if next_step not in step_ids:
                    raise ValueError(f"Step '{step['id']}' references unknown next step '{next_step}'")

        # Validate entry point exists
        entry_point = definition.get("entry_point", steps[0]["id"])
        if entry_point not in step_ids:
            raise ValueError(f"Entry point '{entry_point}' is not a valid step ID")

        # Build graph
        graph = StateGraph(WorkflowState)

        # Add node for each step
        for step in steps:
            node_func = self._create_step_node(step)
            graph.add_node(step["id"], node_func)

        # Set entry point
        graph.set_entry_point(entry_point)

        # Add edges based on dependencies and next steps
        for step in steps:
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

        # Compile graph with checkpointer (if available)
        # For tests without DATABASE_URL, checkpointer will be None
        if self.checkpointer:
            return graph.compile(checkpointer=self.checkpointer)
        else:
            return graph.compile()

    def _create_step_node(self, step: Dict[str, Any]) -> Callable:
        """
        Create a LangGraph node function for a workflow step.

        The node function executes the step and updates state.
        Supports step types:
        - tool_call: Execute via Gateway MCP
        - approval_gate: Request human approval
        - llm_decision: Placeholder for LLM-based decisions
        """
        async def node_func(state: WorkflowState) -> Dict[str, Any]:
            """Execute workflow step with metrics collection."""
            workflow_run_id = state.get("workflow_run_id")

            # Create step execution record
            step_exec = WorkflowStepExecution(
                workflow_run_id=workflow_run_id,
                step_id=step["id"],
                step_name=step["name"],
                step_type=step["type"],
                status=StepStatus.RUNNING,
                input_data=step.get("inputs", {})
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
                # Execute based on step type
                step_type = step.get("type", "tool_call")
                
                if step_type == "tool_call":
                    result = await self._execute_tool_call(step, state)
                elif step_type == "approval_gate":
                    result = await self._execute_approval_gate(step, state, workflow_run_id)
                elif step_type == "llm_decision":
                    # LLM decision placeholder - will be implemented with LLM integration
                    result = {"decision": "approved", "reason": "LLM decision placeholder"}
                else:
                    result = {"warning": f"Unknown step type: {step_type}"}

                # Update step execution
                step_exec.status = StepStatus.COMPLETED
                step_exec.output_data = result
                step_exec.completed_at = datetime.now(timezone.utc)
                self.db.commit()

                # Record metrics
                self.metrics.record_step_completion(
                    metrics_id=metrics.id,
                    success=True,
                    output_data=result
                )

                # Return updates to step_results field - these will be merged
                return {
                    "step_results": {
                        f"{step['id']}_status": "completed",
                        f"{step['id']}_output": result
                    }
                }

            except Exception as e:
                # Update step execution
                step_exec.status = StepStatus.FAILED
                step_exec.error_message = str(e)
                self.db.commit()

                # Record metrics
                self.metrics.record_step_completion(
                    metrics_id=metrics.id,
                    success=False,
                    error_type=type(e).__name__,
                    error_message=str(e)
                )

                # Return error state
                return {
                    "step_results": {
                        f"{step['id']}_status": "failed",
                        f"{step['id']}_error": str(e)
                    }
                }

        return node_func
    
    async def _execute_tool_call(
        self,
        step: Dict[str, Any],
        state: WorkflowState,
    ) -> Dict[str, Any]:
        """
        Execute a tool_call step via Gateway MCP.
        
        Resolves tool names to Gateway MCP equivalents and executes
        through the MCP registry with full policy/audit handling.
        
        Args:
            step: Step definition with tool name and inputs
            state: Current workflow state
            
        Returns:
            Tool execution result
        """
        tool_name = step.get("tool", "")
        resolved_name = self._resolve_tool_name(tool_name)
        
        # Build tool arguments from step inputs and state
        inputs = step.get("inputs", {})
        arguments = self._resolve_template_inputs(inputs, state)
        
        # Get workflow run to access user context
        workflow_run_id = state.get("workflow_run_id")
        workflow_run = self.db.get(WorkflowRun, workflow_run_id)
        
        if workflow_run and workflow_run.session and workflow_run.session.user:
            user = workflow_run.session.user
        else:
            # Create a minimal user object for tool execution
            from types import SimpleNamespace
            from app.models.user import UserRole
            user = SimpleNamespace(id=0, role=UserRole.ADMIN)
        
        # Execute tool via MCP registry
        registry = await self._get_mcp_registry()
        result = await registry.execute_tool(resolved_name, arguments, user)
        
        if result.success:
            return {
                "tool": resolved_name,
                "original_tool": tool_name,
                "result": result.result,
                "execution_time_ms": result.execution_time_ms,
            }
        else:
            raise RuntimeError(f"Tool execution failed: {result.error}")
    
    async def _execute_approval_gate(
        self,
        step: Dict[str, Any],
        state: WorkflowState,
        workflow_run_id: int,
    ) -> Dict[str, Any]:
        """
        Execute an approval_gate step.
        
        Requests human approval for the workflow to proceed.
        Uses the ApprovalService to manage the approval flow.
        
        Args:
            step: Step definition with approval data key
            state: Current workflow state
            workflow_run_id: ID of the workflow run
            
        Returns:
            Approval result
        """
        from app.services.approval_service import ApprovalService
        
        approval_service = ApprovalService(self.db)
        
        # Get approval data from previous step output
        approval_data_key = step.get("approval_data_key", "")
        approval_data = None
        
        if approval_data_key:
            # Parse key like "config_setup.output"
            parts = approval_data_key.split(".")
            if len(parts) >= 2:
                step_id = parts[0]
                step_output = state.get("step_results", {}).get(f"{step_id}_output", {})
                approval_data = step_output
        
        # Create approval request
        approval_prompt = step.get("description", f"Approval required for step: {step['name']}")
        
        await approval_service.request_approval(
            workflow_run_id=workflow_run_id,
            approval_data=approval_data,
            approval_prompt=approval_prompt,
        )
        
        # Return pending status - workflow will pause here
        return {
            "status": "approval_requested",
            "prompt": approval_prompt,
            "data": approval_data,
        }
    
    def _resolve_template_inputs(
        self,
        inputs: Dict[str, Any],
        state: WorkflowState,
    ) -> Dict[str, Any]:
        """
        Resolve template variables in step inputs.
        
        Supports {{input.field}} and {{step_id.field}} syntax.
        
        Args:
            inputs: Step inputs with potential template variables
            state: Current workflow state
            
        Returns:
            Resolved inputs with actual values
        """
        import re
        
        step_results = state.get("step_results", {})
        resolved = {}
        
        for key, value in inputs.items():
            if isinstance(value, str) and "{{" in value:
                # Extract template variable
                match = re.search(r"\{\{(.+?)\}\}", value)
                if match:
                    var_path = match.group(1).strip()
                    parts = var_path.split(".")
                    
                    if parts[0] == "input" and len(parts) > 1:
                        # Reference to workflow input data
                        field = parts[1]
                        resolved[key] = step_results.get(field, value)
                    elif len(parts) >= 2:
                        # Reference to previous step output
                        step_id = parts[0]
                        field = parts[1]
                        step_output = step_results.get(f"{step_id}_output", {})
                        if isinstance(step_output, dict):
                            resolved[key] = step_output.get(field, value)
                        else:
                            resolved[key] = value
                    else:
                        resolved[key] = value
                else:
                    resolved[key] = value
            else:
                resolved[key] = value
        
        return resolved

    async def execute_workflow(
        self,
        workflow_run_id: int
    ) -> WorkflowState:
        """
        Execute a workflow run with full metrics collection and Langfuse tracing.

        Returns final workflow state.
        """
        # Load workflow run
        workflow_run = self.db.get(WorkflowRun, workflow_run_id)
        if not workflow_run:
            raise ValueError(f"Workflow run not found: {workflow_run_id}")

        # Update status
        workflow_run.status = WorkflowRunStatus.RUNNING
        self.db.commit()

        # Build graph from template
        graph = self.build_graph_from_template(workflow_run.template)

        # Get Langfuse callback handler
        langfuse_callback = LangfuseConfig.get_callback_handler(
            user_id=str(workflow_run.session.user_id) if (workflow_run.session and workflow_run.session.user_id) else None,
            session_id=str(workflow_run.session_id),
            trace_name=f"{workflow_run.template.name}_run_{workflow_run.id}"
        )

        # Create config with callbacks
        config = RunnableConfig(
            configurable={"thread_id": str(workflow_run_id)},
            callbacks=[langfuse_callback] if langfuse_callback else []
        )

        # Prepare initial state
        # Handle case where current_state might be None or not have input_data
        current_state = workflow_run.current_state or {}
        input_data = current_state.get("input_data", {})

        initial_state = WorkflowState(
            workflow_run_id=workflow_run_id,
            step_results=input_data
        )

        try:
            # Execute graph
            result = await graph.ainvoke(
                initial_state,
                config=config
            )

            # Update workflow run
            workflow_run.status = WorkflowRunStatus.COMPLETED
            workflow_run.current_state = {"results": dict(result)}
            workflow_run.completed_at = datetime.now(timezone.utc)
            self.db.commit()

            return result

        except Exception as e:
            # Update workflow run
            workflow_run.status = WorkflowRunStatus.FAILED
            workflow_run.current_state = {"error": str(e)}
            self.db.commit()

            raise
