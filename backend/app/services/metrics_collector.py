"""Metrics collection service for workflow instrumentation."""
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.metrics import StepMetrics, LLMDecisionMetrics
from app.models.workflow import StepStatus


class MetricsCollector:
    """Service for recording workflow execution metrics."""

    def __init__(self, db: Session):
        """Initialize MetricsCollector with database session.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def record_step_start(
        self,
        workflow_run_id: int,
        step_execution_id: int,
        attempt_number: int = 1
    ) -> StepMetrics:
        """Record the start of a workflow step execution.

        Args:
            workflow_run_id: ID of the workflow run
            step_execution_id: ID of the step execution
            attempt_number: Retry attempt number (default: 1)

        Returns:
            Created StepMetrics instance
        """
        metrics = StepMetrics(
            workflow_run_id=workflow_run_id,
            step_execution_id=step_execution_id,
            attempt_number=attempt_number,
            started_at=datetime.now(timezone.utc),
            status=StepStatus.RUNNING
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
        output_data: Optional[Dict[str, Any]] = None,
        tokens_used: Optional[int] = None,
        tool_latency_ms: Optional[int] = None
    ) -> StepMetrics:
        """Record the completion of a workflow step execution.

        Args:
            metrics_id: ID of the StepMetrics record to update
            success: Whether the step completed successfully
            error_type: Type of error if failed
            error_message: Error message if failed
            output_data: Output data from the step
            tokens_used: Total tokens consumed
            tool_latency_ms: Tool execution latency in milliseconds

        Returns:
            Updated StepMetrics instance
        """
        metrics = self.db.query(StepMetrics).filter(StepMetrics.id == metrics_id).first()
        if not metrics:
            raise ValueError(f"StepMetrics with id {metrics_id} not found")

        completed_at = datetime.now(timezone.utc)
        metrics.completed_at = completed_at
        metrics.status = StepStatus.COMPLETED if success else StepStatus.FAILED
        metrics.error_type = error_type
        metrics.error_message = error_message
        metrics.output_data = output_data
        metrics.tokens_used = tokens_used
        metrics.tool_latency_ms = tool_latency_ms

        self.db.commit()
        self.db.refresh(metrics)
        return metrics

    def record_llm_decision(
        self,
        workflow_run_id: int,
        step_execution_id: int,
        decision_point: str,
        prompt_template_id: Optional[str],
        prompt_text: str,
        model_used: str,
        response: str,
        decision_parsed: str,
        tokens_used: int,
        latency_ms: int,
        temperature: float
    ) -> LLMDecisionMetrics:
        """Record an LLM decision point during workflow execution.

        Args:
            workflow_run_id: ID of the workflow run
            step_execution_id: ID of the step execution
            decision_point: Type of decision (e.g., 'tool_selection', 'routing')
            prompt_template_id: ID of prompt template used
            prompt_text: Full text of the prompt sent to LLM
            model_used: LLM model used
            response: Response from LLM
            decision_parsed: Parsed decision output
            tokens_used: Total tokens used in the LLM call
            latency_ms: Latency in milliseconds
            temperature: Temperature setting

        Returns:
            Created LLMDecisionMetrics instance
        """
        decision = LLMDecisionMetrics(
            workflow_run_id=workflow_run_id,
            step_execution_id=step_execution_id,
            decision_point=decision_point,
            prompt_template_id=prompt_template_id,
            prompt_text=prompt_text,
            model_used=model_used,
            response=response,
            decision_parsed=decision_parsed,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
            temperature=temperature,
            created_at=datetime.now(timezone.utc)
        )
        self.db.add(decision)
        self.db.commit()
        self.db.refresh(decision)
        return decision

    # Phase 3: Analytics methods (stubs for now)
    def get_workflow_success_rate(self, workflow_template_id: int) -> float:
        """Get success rate for a workflow template.

        Args:
            workflow_template_id: ID of the workflow template

        Returns:
            Success rate as a percentage (0-100)

        Note:
            Implementation planned for Phase 3
        """
        raise NotImplementedError("Analytics methods planned for Phase 3")

    def get_step_failure_analysis(self, workflow_template_id: int) -> Dict[str, Any]:
        """Analyze step failures for a workflow template.

        Args:
            workflow_template_id: ID of the workflow template

        Returns:
            Dictionary containing failure analysis

        Note:
            Implementation planned for Phase 3
        """
        raise NotImplementedError("Analytics methods planned for Phase 3")
