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
        step_name: str
    ) -> StepMetrics:
        """Record the start of a workflow step execution.

        Args:
            workflow_run_id: ID of the workflow run
            step_execution_id: ID of the step execution
            step_name: Name of the step being executed

        Returns:
            Created StepMetrics instance
        """
        metrics = StepMetrics(
            workflow_run_id=workflow_run_id,
            step_execution_id=step_execution_id,
            step_name=step_name,
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
        error_message: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        cost_usd: Optional[float] = None
    ) -> StepMetrics:
        """Record the completion of a workflow step execution.

        Args:
            metrics_id: ID of the StepMetrics record to update
            success: Whether the step completed successfully
            error_message: Error message if failed
            input_tokens: Number of input tokens consumed
            output_tokens: Number of output tokens generated
            cost_usd: Cost in USD for this step

        Returns:
            Updated StepMetrics instance
        """
        metrics = self.db.query(StepMetrics).filter(StepMetrics.id == metrics_id).first()
        if not metrics:
            raise ValueError(f"StepMetrics with id {metrics_id} not found")

        completed_at = datetime.now(timezone.utc)
        metrics.completed_at = completed_at
        metrics.status = StepStatus.COMPLETED if success else StepStatus.FAILED
        metrics.error_message = error_message
        metrics.input_tokens = input_tokens
        metrics.output_tokens = output_tokens
        metrics.cost_usd = cost_usd

        # Calculate total tokens
        if input_tokens is not None and output_tokens is not None:
            metrics.tokens_used = input_tokens + output_tokens
        elif input_tokens is not None:
            metrics.tokens_used = input_tokens
        elif output_tokens is not None:
            metrics.tokens_used = output_tokens

        self.db.commit()
        self.db.refresh(metrics)
        return metrics

    def record_llm_decision(
        self,
        workflow_run_id: int,
        step_execution_id: int,
        step_name: str,
        decision_point: str,
        tokens_used: int,
        latency_ms: int,
        model_used: str,
        temperature: float,
        response_raw: str,
        decision_parsed: str,
        llm_reasoning: Optional[str] = None,
        prompt_template_id: Optional[str] = None,
        prompt_hash: Optional[str] = None
    ) -> LLMDecisionMetrics:
        """Record an LLM decision point during workflow execution.

        Args:
            workflow_run_id: ID of the workflow run
            step_execution_id: ID of the step execution
            step_name: Name of the step where decision was made
            decision_point: Type of decision (e.g., 'tool_selection', 'routing')
            tokens_used: Total tokens used in the LLM call
            latency_ms: Latency in milliseconds
            model_used: LLM model used
            temperature: Temperature setting
            response_raw: Raw response from LLM
            decision_parsed: Parsed decision output
            llm_reasoning: Optional reasoning for the decision
            prompt_template_id: ID of prompt template used
            prompt_hash: Hash of the prompt

        Returns:
            Created LLMDecisionMetrics instance
        """
        decision = LLMDecisionMetrics(
            workflow_run_id=workflow_run_id,
            step_execution_id=step_execution_id,
            step_name=step_name,
            decision_point=decision_point,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
            model_used=model_used,
            temperature=temperature,
            response_raw=response_raw,
            decision_parsed=decision_parsed,
            llm_reasoning=llm_reasoning,
            prompt_template_id=prompt_template_id,
            prompt_hash=prompt_hash,
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
