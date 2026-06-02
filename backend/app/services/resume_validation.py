"""
Resume validation service for workflow continuity.

Provides comprehensive validation for pause/resume workflows with:
- Tenant isolation
- Run ID preservation
- Message deduplication
- Cursor age validation
- Detailed telemetry
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
import logging

from app.services.run_state import RunState
from app.models.models import User

logger = logging.getLogger(__name__)


@dataclass
class ResumeCursor:
    """Comprehensive workflow resume checkpoint with validation."""

    run_id: str
    tenant_id: int
    step_number: int
    message_index: int
    workflow_type: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        run_state: RunState,
        step_number: int,
        workflow_type: str,
        tenant_id: int,
        additional_metadata: Optional[Dict[str, Any]] = None,
    ) -> "ResumeCursor":
        """
        Factory method to create cursor from current run state.

        Args:
            run_state: Current RunState instance
            step_number: Current workflow step number
            workflow_type: Workflow classification (e.g., "onboarding", "club_creation")
            tenant_id: Tenant ID for isolation validation
            additional_metadata: Optional additional context

        Returns:
            ResumeCursor instance
        """
        # Get message index from RunState
        message_index = len(run_state.messages) if run_state.messages else 0

        return cls(
            run_id=run_state.run_id,
            tenant_id=tenant_id,
            step_number=step_number,
            message_index=message_index,
            workflow_type=workflow_type,
            timestamp=datetime.now(timezone.utc),
            metadata=additional_metadata or {},
        )

    def validate(
        self,
        current_tenant_id: int,
        max_age_minutes: int = 60,
    ) -> bool:
        """
        Validate cursor for resumption.

        Args:
            current_tenant_id: Tenant ID of current user
            max_age_minutes: Maximum age in minutes for cursor validity

        Returns:
            True if cursor is valid, False otherwise
        """
        # Tenant validation - prevent cross-tenant replay
        if self.tenant_id != current_tenant_id:
            logger.warning(
                "Tenant mismatch during resume validation",
                extra={
                    "cursor_tenant": self.tenant_id,
                    "current_tenant": current_tenant_id,
                    "run_id": self.run_id,
                },
            )
            return False

        # Age validation - prevent stale cursor replay
        age = datetime.now(timezone.utc) - self.timestamp
        if age.total_seconds() > max_age_minutes * 60:
            logger.warning(
                "Cursor expired during resume validation",
                extra={
                    "cursor_age_minutes": age.total_seconds() / 60,
                    "max_age_minutes": max_age_minutes,
                    "run_id": self.run_id,
                },
            )
            return False

        return True

    def serialize(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "step_number": self.step_number,
            "message_index": self.message_index,
            "workflow_type": self.workflow_type,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> "ResumeCursor":
        """Create from serialized dictionary."""
        data_copy = data.copy()

        # Parse timestamp
        if isinstance(data_copy.get("timestamp"), str):
            data_copy["timestamp"] = datetime.fromisoformat(data_copy["timestamp"])

        # Handle workflow_id (from persist_cursor) vs workflow_type (our model)
        if "workflow_id" in data_copy and "workflow_type" not in data_copy:
            # Move workflow_id to metadata and use "unknown" for workflow_type
            metadata = data_copy.get("metadata", {})
            metadata["workflow_id"] = data_copy.pop("workflow_id")
            data_copy["metadata"] = metadata
            data_copy["workflow_type"] = data_copy.get("workflow_type", "unknown")

        # Extract run_id if not present but available in metadata
        if "run_id" not in data_copy:
            data_copy["run_id"] = data_copy.get("metadata", {}).get("run_id", "unknown")

        return cls(**data_copy)


@dataclass
class ResumeValidationResult:
    """Result of resume validation."""

    valid: bool
    cursor: Optional[ResumeCursor] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def success(self) -> bool:
        """Alias for valid."""
        return self.valid


class WorkflowResumeService:
    """Unified service for workflow resume validation."""

    @staticmethod
    async def validate_resume(
        run_state: RunState,
        current_user: User,
        max_age_minutes: int = 60,
    ) -> ResumeValidationResult:
        """
        Validate workflow resume request.

        Checks:
        - Cursor exists and is valid
        - Tenant isolation
        - Cursor age
        - Message deduplication

        Args:
            run_state: RunState with cursor to validate
            current_user: Current authenticated user
            max_age_minutes: Maximum cursor age in minutes

        Returns:
            ResumeValidationResult with validation status
        """
        # Check if cursor exists
        cursor_data = run_state.get_cursor()
        if not cursor_data:
            logger.info(
                "No cursor found in RunState",
                extra={"run_id": run_state.run_id},
            )
            return ResumeValidationResult(
                valid=False,
                error_code="NO_CURSOR",
                error_message="No resume cursor found",
            )

        # Reconstruct cursor - add run_id from RunState context
        try:
            cursor_data_with_run_id = {**cursor_data, "run_id": run_state.run_id}
            cursor = ResumeCursor.deserialize(cursor_data_with_run_id)
        except (TypeError, ValueError, KeyError) as e:
            logger.error(
                "Invalid cursor format",
                extra={"error": str(e), "run_id": run_state.run_id},
            )
            return ResumeValidationResult(
                valid=False,
                error_code="INVALID_CURSOR_FORMAT",
                error_message=f"Invalid cursor format: {e}",
            )

        # Validate tenant isolation
        if not cursor.validate(current_user.tenant_id, max_age_minutes):
            # Validation logs specific errors internally
            return ResumeValidationResult(
                valid=False,
                error_code="VALIDATION_FAILED",
                error_message="Cursor validation failed (check logs for details)",
            )

        # Check message deduplication
        current_message_count = len(run_state.messages) if run_state.messages else 0
        if cursor.message_index >= current_message_count:
            logger.info(
                "No new messages to process",
                extra={
                    "run_id": run_state.run_id,
                    "cursor_message_index": cursor.message_index,
                    "current_message_count": current_message_count,
                },
            )
            return ResumeValidationResult(
                valid=False,
                error_code="NO_NEW_MESSAGES",
                error_message="No new messages to process",
            )

        logger.info(
            "Resume validation successful",
            extra={
                "run_id": cursor.run_id,
                "tenant_id": cursor.tenant_id,
                "step_number": cursor.step_number,
            },
        )

        return ResumeValidationResult(
            valid=True,
            cursor=cursor,
        )

    @staticmethod
    async def resume_workflow(
        run_state: RunState,
        current_user: User,
        max_age_minutes: int = 60,
    ) -> Dict[str, Any]:
        """
        Resume workflow after validation.

        Args:
            run_state: RunState with cursor to resume from
            current_user: Current authenticated user
            max_age_minutes: Maximum cursor age in minutes

        Returns:
            Dict with resume status and details

        Raises:
            ValueError: If validation fails
        """
        # Validate resume request
        validation = await WorkflowResumeService.validate_resume(
            run_state=run_state,
            current_user=current_user,
            max_age_minutes=max_age_minutes,
        )

        if not validation.valid:
            raise ValueError(
                f"Resume validation failed: {validation.error_message} "
                f"(code: {validation.error_code})"
            )

        cursor = validation.cursor
        assert cursor is not None  # Type narrowing

        # Record telemetry
        await WorkflowResumeService._record_resume_event(
            cursor=cursor,
            tenant_id=current_user.tenant_id,
        )

        return {
            "status": "RESUMED",
            "step": cursor.step_number,
            "message_index": cursor.message_index,
            "run_id": cursor.run_id,
            "workflow_type": cursor.workflow_type,
        }

    @staticmethod
    async def _record_resume_event(
        cursor: ResumeCursor,
        tenant_id: int,
    ) -> None:
        """
        Record resume event for telemetry/observability.

        Args:
            cursor: Resume cursor being used
            tenant_id: Tenant ID for the resume operation
        """
        event = {
            "event_type": "workflow_resume",
            "run_id": cursor.run_id,
            "tenant_id": tenant_id,
            "resume_type": "interruption",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cursor": cursor.serialize(),
        }

        # Log event (in production, this would also send to observability pipeline)
        logger.info(
            "Resume event recorded",
            extra=event,
        )
