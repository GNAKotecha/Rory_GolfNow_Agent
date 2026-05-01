"""Workflow orchestration service using LangGraph."""
import os
from datetime import datetime
from typing import Dict, Any, Optional, Callable, TypedDict, Annotated
from sqlalchemy.orm import Session
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver

from app.models.workflow import (
    WorkflowTemplate,
    WorkflowRun,
    WorkflowStepExecution,
    WorkflowRunStatus,
    StepStatus
)
from app.services.metrics_collector import MetricsCollector


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
    manages execution, and collects metrics.
    """

    def __init__(self, db: Session):
        self.db = db
        self.metrics = MetricsCollector(db)

        # Initialize PostgreSQL checkpointer for state persistence
        # Only initialize if using actual PostgreSQL (not SQLite for tests)
        database_url = os.getenv("DATABASE_URL", "")
        if database_url and database_url.startswith("postgresql"):
            self.checkpointer = PostgresSaver.from_conn_string(database_url)
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
                input_data=step.get("config", {})
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
                step_exec.output_data = result
                step_exec.completed_at = datetime.utcnow()
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

    async def execute_workflow(
        self,
        workflow_run_id: int
    ) -> WorkflowState:
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
                config={
                    "configurable": {
                        "thread_id": str(workflow_run_id)
                    }
                }
            )

            # Update workflow run
            workflow_run.status = WorkflowRunStatus.COMPLETED
            workflow_run.current_state = {"results": dict(result)}
            workflow_run.completed_at = datetime.utcnow()
            self.db.commit()

            return result

        except Exception as e:
            # Update workflow run
            workflow_run.status = WorkflowRunStatus.FAILED
            workflow_run.current_state = {"error": str(e)}
            self.db.commit()

            raise
