"""Task planning and verification for agent execution."""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import logging
import json

logger = logging.getLogger(__name__)


class PlanStepStatus(Enum):
    """Status of a plan step."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    """Single step in task plan."""
    step_number: int
    description: str
    status: PlanStepStatus
    dependencies: List[int] = field(default_factory=list)
    verification_criteria: Optional[str] = None
    result: Optional[Any] = None


@dataclass
class TaskPlan:
    """Complete task plan."""
    task_description: str
    steps: List[PlanStep]
    current_step: int = 0

    def get_next_step(self) -> Optional[PlanStep]:
        """Get next pending step with satisfied dependencies."""
        for step in self.steps:
            if step.status != PlanStepStatus.PENDING:
                continue

            # Check dependencies
            if all(
                self.steps[dep - 1].status == PlanStepStatus.COMPLETED
                for dep in step.dependencies
            ):
                return step

        return None

    def mark_step_completed(self, step_number: int, result: Any):
        """Mark step as completed."""
        step = self.steps[step_number - 1]
        step.status = PlanStepStatus.COMPLETED
        step.result = result

    def mark_step_failed(self, step_number: int, error: str):
        """Mark step as failed."""
        step = self.steps[step_number - 1]
        step.status = PlanStepStatus.FAILED
        step.result = error

    def is_complete(self) -> bool:
        """Check if all steps are complete."""
        return all(
            step.status in [PlanStepStatus.COMPLETED, PlanStepStatus.SKIPPED]
            for step in self.steps
        )

    def get_progress(self) -> float:
        """Get completion percentage."""
        completed = sum(
            1 for step in self.steps
            if step.status in [PlanStepStatus.COMPLETED, PlanStepStatus.SKIPPED]
        )
        return completed / len(self.steps) if self.steps else 0.0


class AgentPlanner:
    """Creates and manages task plans."""

    async def create_plan(
        self,
        task_description: str,
        ollama_client: Any,
        available_tools: List[str],
    ) -> TaskPlan:
        """
        Use LLM to create a task plan.

        Args:
            task_description: What the user wants to accomplish
            ollama_client: For LLM planning
            available_tools: Tools agent can use

        Returns:
            TaskPlan with steps
        """
        # Prompt LLM to create plan
        planning_prompt = f"""Given the following task: {task_description}

Available tools: {', '.join(available_tools)}

Create a step-by-step plan to accomplish this task. For each step:
1. Describe what needs to be done
2. List any dependencies (which steps must complete first)
3. Define verification criteria (how to know the step succeeded)

Format as JSON:
{{
  "steps": [
    {{
      "step_number": 1,
      "description": "...",
      "dependencies": [],
      "verification_criteria": "..."
    }},
    ...
  ]
}}
"""

        try:
            response = await ollama_client.generate_chat_completion(
                messages=[{"role": "user", "content": planning_prompt}],
            )

            # Extract JSON from response
            plan_data = self._extract_json(response)

            if not plan_data or "steps" not in plan_data:
                logger.warning("Failed to parse plan from LLM response, creating simple plan")
                # Fallback: create single-step plan
                return TaskPlan(
                    task_description=task_description,
                    steps=[
                        PlanStep(
                            step_number=1,
                            description=task_description,
                            status=PlanStepStatus.PENDING,
                            dependencies=[],
                            verification_criteria=None,
                        )
                    ],
                )

            steps = [
                PlanStep(
                    step_number=step_data["step_number"],
                    description=step_data["description"],
                    status=PlanStepStatus.PENDING,
                    dependencies=step_data.get("dependencies", []),
                    verification_criteria=step_data.get("verification_criteria"),
                )
                for step_data in plan_data["steps"]
            ]

            logger.info(
                f"Created plan with {len(steps)} steps",
                extra={"task": task_description, "steps": len(steps)}
            )

            return TaskPlan(
                task_description=task_description,
                steps=steps,
            )

        except Exception as e:
            logger.error(f"Error creating plan: {e}")
            # Fallback: create single-step plan
            return TaskPlan(
                task_description=task_description,
                steps=[
                    PlanStep(
                        step_number=1,
                        description=task_description,
                        status=PlanStepStatus.PENDING,
                        dependencies=[],
                        verification_criteria=None,
                    )
                ],
            )

    async def verify_step(
        self,
        step: PlanStep,
        execution_result: Any,
        ollama_client: Any,
    ) -> bool:
        """
        Verify if a step was completed successfully.

        Args:
            step: Step to verify
            execution_result: Result from step execution
            ollama_client: For LLM verification

        Returns:
            True if step passed verification
        """
        if not step.verification_criteria:
            # No criteria - assume success if no error
            return execution_result is not None and not isinstance(execution_result, Exception)

        # Use LLM to verify
        verification_prompt = f"""Step: {step.description}
Verification criteria: {step.verification_criteria}
Execution result: {execution_result}

Did this step complete successfully? Respond with YES or NO and explain why.
"""

        try:
            response = await ollama_client.generate_chat_completion(
                messages=[{"role": "user", "content": verification_prompt}],
            )

            response_upper = response.strip().upper()
            verified = response_upper.startswith("YES")

            logger.info(
                f"Step verification: {'passed' if verified else 'failed'}",
                extra={
                    "step": step.step_number,
                    "description": step.description,
                    "verified": verified,
                }
            )

            return verified

        except Exception as e:
            logger.error(f"Error verifying step: {e}")
            # On error, assume success if result exists
            return execution_result is not None

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Extract JSON from LLM response.

        Args:
            text: Response text that may contain JSON

        Returns:
            Parsed JSON or None
        """
        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Look for JSON between code blocks
        if "```json" in text:
            parts = text.split("```json")
            if len(parts) > 1:
                json_part = parts[1].split("```")[0].strip()
                try:
                    return json.loads(json_part)
                except json.JSONDecodeError:
                    pass

        # Look for JSON between braces
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

        return None
