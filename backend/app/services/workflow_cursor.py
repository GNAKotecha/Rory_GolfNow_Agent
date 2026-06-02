"""Workflow cursor mechanism for precise resume boundaries.

Provides:
- Lightweight checkpoint tracking (step + message index)
- Tenant-aware cursor validation
- JSON serialization for storage in RunState.metadata
- Cursor replay protection
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class WorkflowCursor:
    """Precise workflow execution checkpoint for pause/resume.

    Tracks the exact boundary where execution can safely resume:
    - step_number: Which workflow step was last completed
    - message_index: Index in RunState.messages array (for idempotency)
    - workflow_id: Identifier for the workflow type (e.g., "onboarding", "booking_create")
    - tenant_id: Tenant context for isolation
    - timestamp: When checkpoint was created
    - metadata: Extensible storage for workflow-specific state
    """
    step_number: int
    message_index: int
    workflow_id: str
    tenant_id: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def serialize(self) -> str:
        """Convert cursor to JSON string for storage."""
        data = {
            'step_number': self.step_number,
            'message_index': self.message_index,
            'workflow_id': self.workflow_id,
            'tenant_id': self.tenant_id,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata
        }
        return json.dumps(data)

    @classmethod
    def deserialize(cls, cursor_json: str) -> 'WorkflowCursor':
        """Reconstruct cursor from serialized JSON."""
        try:
            data = json.loads(cursor_json)
            return cls(
                step_number=data['step_number'],
                message_index=data['message_index'],
                workflow_id=data['workflow_id'],
                tenant_id=data['tenant_id'],
                timestamp=datetime.fromisoformat(data['timestamp']),
                metadata=data.get('metadata', {})
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to deserialize cursor: {e}")
            raise ValueError(f"Invalid cursor format: {e}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for embedding in RunState.metadata."""
        return {
            'step_number': self.step_number,
            'message_index': self.message_index,
            'workflow_id': self.workflow_id,
            'tenant_id': self.tenant_id,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkflowCursor':
        """Reconstruct from dictionary (from RunState.metadata)."""
        return cls(
            step_number=data['step_number'],
            message_index=data['message_index'],
            workflow_id=data['workflow_id'],
            tenant_id=data['tenant_id'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            metadata=data.get('metadata', {})
        )

    def validate(self, current_tenant_id: int, max_age_seconds: int = 86400) -> bool:
        """Validate cursor before resume.

        Args:
            current_tenant_id: Current user's tenant ID
            max_age_seconds: Maximum cursor age (default 24 hours)

        Returns:
            True if cursor is valid for resume

        Raises:
            ValueError: If validation fails with reason
        """
        # Tenant isolation check
        if self.tenant_id != current_tenant_id:
            raise ValueError(
                f"Cursor tenant mismatch: cursor={self.tenant_id}, current={current_tenant_id}"
            )

        # Age check (prevent replay of very old cursors)
        age = (datetime.now(timezone.utc) - self.timestamp).total_seconds()
        if age > max_age_seconds:
            raise ValueError(
                f"Cursor expired: age={age:.0f}s > max={max_age_seconds}s"
            )

        # Basic sanity checks
        if self.step_number < 0:
            raise ValueError(f"Invalid step_number: {self.step_number}")

        if self.message_index < 0:
            raise ValueError(f"Invalid message_index: {self.message_index}")

        return True

    def is_compatible_with_run_state(self, run_state: 'RunState') -> bool:
        """Check if cursor is compatible with a RunState for resume.

        Verifies:
        - Tenant ID matches
        - Message index is within bounds
        - Step number is within acceptable range

        Args:
            run_state: RunState to validate against

        Returns:
            True if compatible
        """
        # Import here to avoid circular dependency
        from app.services.run_state import RunState

        # Tenant check
        if self.tenant_id != run_state.user_id:  # TODO: Add tenant_id to RunState
            logger.warning(
                f"Cursor tenant {self.tenant_id} != RunState user {run_state.user_id}"
            )
            return False

        # Message index bounds check
        if self.message_index > len(run_state.messages):
            logger.warning(
                f"Cursor message_index {self.message_index} > messages length {len(run_state.messages)}"
            )
            return False

        # Step number sanity check
        if self.step_number > run_state.current_step + 1:
            logger.warning(
                f"Cursor step_number {self.step_number} too far ahead of current_step {run_state.current_step}"
            )
            return False

        return True


def create_cursor(
    run_state: 'RunState',
    workflow_id: str,
    tenant_id: int,
    metadata: Optional[Dict[str, Any]] = None
) -> WorkflowCursor:
    """Create a cursor from current RunState.

    Args:
        run_state: Current execution state
        workflow_id: Identifier for workflow type
        tenant_id: Tenant context
        metadata: Optional workflow-specific metadata

    Returns:
        WorkflowCursor checkpoint
    """
    return WorkflowCursor(
        step_number=run_state.current_step,
        message_index=len(run_state.messages),
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        metadata=metadata or {}
    )


def persist_cursor_in_run_state(run_state: 'RunState', cursor: WorkflowCursor) -> None:
    """Persist cursor in RunState.metadata.

    Stores cursor in metadata['cursor'] for serialization with RunState.

    Args:
        run_state: RunState to update
        cursor: Cursor to persist
    """
    run_state.metadata['cursor'] = cursor.to_dict()
    logger.info(
        f"Persisted cursor: step={cursor.step_number}, "
        f"msg_idx={cursor.message_index}, workflow={cursor.workflow_id}"
    )


def restore_cursor_from_run_state(run_state: 'RunState') -> Optional[WorkflowCursor]:
    """Restore cursor from RunState.metadata.

    Args:
        run_state: RunState to read from

    Returns:
        WorkflowCursor if present, None otherwise
    """
    cursor_data = run_state.metadata.get('cursor')
    if not cursor_data:
        return None

    try:
        cursor = WorkflowCursor.from_dict(cursor_data)
        logger.info(
            f"Restored cursor: step={cursor.step_number}, "
            f"msg_idx={cursor.message_index}, workflow={cursor.workflow_id}"
        )
        return cursor
    except (KeyError, ValueError) as e:
        logger.error(f"Failed to restore cursor from RunState: {e}")
        return None
