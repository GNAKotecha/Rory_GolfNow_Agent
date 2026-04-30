"""Workflow orchestration service using LangGraph."""
import os
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from langgraph.graph import StateGraph
from langgraph.checkpoint.postgres import PostgresSaver

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
