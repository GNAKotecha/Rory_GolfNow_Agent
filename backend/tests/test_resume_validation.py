"""
Unit tests for resume validation service.

Tests:
- ResumeCursor creation and validation
- Tenant isolation
- Cursor age validation
- Message deduplication
- Resume workflow integration
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch
import asyncio

from app.services.resume_validation import (
    ResumeCursor,
    ResumeValidationResult,
    WorkflowResumeService,
)
from app.services.run_state import RunState
from app.models.models import User


class TestResumeCursor:
    """Test ResumeCursor dataclass."""

    def test_create_cursor_from_run_state(self):
        """Test creating cursor from RunState."""
        run_state = RunState(
            run_id="test-run-123",
            session_id=1,
            user_id=10,
        )
        # Add messages to set message_index
        run_state.messages = [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "msg2"},
            {"role": "user", "content": "msg3"},
            {"role": "assistant", "content": "msg4"},
            {"role": "user", "content": "msg5"},
        ]

        cursor = ResumeCursor.create(
            run_state=run_state,
            step_number=10,
            workflow_type="onboarding",
            tenant_id=42,
            additional_metadata={"tool": "create_club"},
        )

        assert cursor.run_id == "test-run-123"
        assert cursor.tenant_id == 42
        assert cursor.step_number == 10
        assert cursor.message_index == 5
        assert cursor.workflow_type == "onboarding"
        assert cursor.metadata["tool"] == "create_club"
        assert isinstance(cursor.timestamp, datetime)

    def test_create_cursor_with_no_messages(self):
        """Test creating cursor when no messages exist."""
        run_state = RunState(
            run_id="test-run-123",
            session_id=1,
            user_id=10,
        )
        # No messages - should default to 0

        cursor = ResumeCursor.create(
            run_state=run_state,
            step_number=10,
            workflow_type="onboarding",
            tenant_id=42,
        )

        assert cursor.message_index == 0  # No messages = index 0

    def test_validate_cursor_success(self):
        """Test successful cursor validation."""
        cursor = ResumeCursor(
            run_id="test-run-123",
            tenant_id=42,
            step_number=10,
            message_index=5,
            workflow_type="onboarding",
            timestamp=datetime.now(timezone.utc),
        )

        assert cursor.validate(current_tenant_id=42, max_age_minutes=60) is True

    def test_validate_cursor_tenant_mismatch(self):
        """Test cursor validation fails on tenant mismatch."""
        cursor = ResumeCursor(
            run_id="test-run-123",
            tenant_id=42,
            step_number=10,
            message_index=5,
            workflow_type="onboarding",
            timestamp=datetime.now(timezone.utc),
        )

        # Different tenant ID should fail
        assert cursor.validate(current_tenant_id=99, max_age_minutes=60) is False

    def test_validate_cursor_age_expired(self):
        """Test cursor validation fails when cursor is too old."""
        # Create cursor from 2 hours ago
        old_timestamp = datetime.now(timezone.utc) - timedelta(hours=2)
        cursor = ResumeCursor(
            run_id="test-run-123",
            tenant_id=42,
            step_number=10,
            message_index=5,
            workflow_type="onboarding",
            timestamp=old_timestamp,
        )

        # Max age 60 minutes should fail
        assert cursor.validate(current_tenant_id=42, max_age_minutes=60) is False

    def test_validate_cursor_age_just_valid(self):
        """Test cursor validation succeeds when cursor is just within age limit."""
        # Create cursor from 59 minutes ago
        recent_timestamp = datetime.now(timezone.utc) - timedelta(minutes=59)
        cursor = ResumeCursor(
            run_id="test-run-123",
            tenant_id=42,
            step_number=10,
            message_index=5,
            workflow_type="onboarding",
            timestamp=recent_timestamp,
        )

        assert cursor.validate(current_tenant_id=42, max_age_minutes=60) is True

    def test_serialize_cursor(self):
        """Test cursor serialization."""
        timestamp = datetime.now(timezone.utc)
        cursor = ResumeCursor(
            run_id="test-run-123",
            tenant_id=42,
            step_number=10,
            message_index=5,
            workflow_type="onboarding",
            timestamp=timestamp,
            metadata={"tool": "create_club"},
        )

        serialized = cursor.serialize()

        assert serialized["run_id"] == "test-run-123"
        assert serialized["tenant_id"] == 42
        assert serialized["step_number"] == 10
        assert serialized["message_index"] == 5
        assert serialized["workflow_type"] == "onboarding"
        assert serialized["timestamp"] == timestamp.isoformat()
        assert serialized["metadata"]["tool"] == "create_club"

    def test_deserialize_cursor(self):
        """Test cursor deserialization."""
        timestamp = datetime.now(timezone.utc)
        data = {
            "run_id": "test-run-123",
            "tenant_id": 42,
            "step_number": 10,
            "message_index": 5,
            "workflow_type": "onboarding",
            "timestamp": timestamp.isoformat(),
            "metadata": {"tool": "create_club"},
        }

        cursor = ResumeCursor.deserialize(data)

        assert cursor.run_id == "test-run-123"
        assert cursor.tenant_id == 42
        assert cursor.step_number == 10
        assert cursor.message_index == 5
        assert cursor.workflow_type == "onboarding"
        assert cursor.timestamp == timestamp
        assert cursor.metadata["tool"] == "create_club"


class TestWorkflowResumeService:
    """Test WorkflowResumeService."""

    @pytest.mark.asyncio
    async def test_validate_resume_success(self):
        """Test successful resume validation."""
        # Create run state with valid cursor
        run_state = RunState(
            run_id="test-run-123",
            session_id=1,
            user_id=10,
        )
        # Add messages
        run_state.messages = [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "msg2"},
            {"role": "user", "content": "msg3"},
            {"role": "assistant", "content": "msg4"},
            {"role": "user", "content": "msg5"},
            {"role": "user", "content": "msg6"},  # New message to process
        ]

        cursor = ResumeCursor.create(
            run_state=run_state,
            step_number=10,
            workflow_type="onboarding",
            tenant_id=42,
        )
        run_state.persist_cursor(
            step_number=10,
            message_index=5,  # Cursor at message 5, but we now have 6 messages
            tenant_id=42,
            workflow_id="wf-123",
            additional_metadata=cursor.metadata,
        )

        # Create user with matching tenant
        user = Mock(spec=User)
        user.tenant_id = 42

        # Validate
        result = await WorkflowResumeService.validate_resume(
            run_state=run_state,
            current_user=user,
            max_age_minutes=60,
        )

        assert result.valid is True
        assert result.cursor is not None
        assert result.cursor.run_id == "test-run-123"
        assert result.error_code is None

    @pytest.mark.asyncio
    async def test_validate_resume_no_cursor(self):
        """Test resume validation fails when no cursor exists."""
        run_state = RunState(
            run_id="test-run-123",
            session_id=1,
            user_id=10,
        )

        user = Mock(spec=User)
        user.tenant_id = 42

        result = await WorkflowResumeService.validate_resume(
            run_state=run_state,
            current_user=user,
        )

        assert result.valid is False
        assert result.error_code == "NO_CURSOR"
        assert result.cursor is None

    @pytest.mark.asyncio
    async def test_validate_resume_invalid_cursor_format(self):
        """Test resume validation fails with malformed cursor."""
        run_state = RunState(
            run_id="test-run-123",
            session_id=1,
            user_id=10,
        )
        # Store invalid cursor data
        run_state.cursor = {"invalid": "data"}

        user = Mock(spec=User)
        user.tenant_id = 42

        result = await WorkflowResumeService.validate_resume(
            run_state=run_state,
            current_user=user,
        )

        assert result.valid is False
        assert result.error_code == "INVALID_CURSOR_FORMAT"

    @pytest.mark.asyncio
    async def test_validate_resume_tenant_mismatch(self):
        """Test resume validation fails on tenant mismatch."""
        run_state = RunState(
            run_id="test-run-123",
            session_id=1,
            user_id=10,
        )
        run_state.messages = [{"role": "user", "content": f"msg{i}"} for i in range(6)]

        run_state.persist_cursor(
            step_number=10,
            message_index=5,
            tenant_id=42,
            workflow_id="wf-123",
        )

        # User from different tenant
        user = Mock(spec=User)
        user.tenant_id = 99

        result = await WorkflowResumeService.validate_resume(
            run_state=run_state,
            current_user=user,
        )

        assert result.valid is False
        assert result.error_code == "VALIDATION_FAILED"

    @pytest.mark.asyncio
    async def test_validate_resume_no_new_messages(self):
        """Test resume validation fails when no new messages exist."""
        run_state = RunState(
            run_id="test-run-123",
            session_id=1,
            user_id=10,
        )

        # Cursor with same message index as current messages
        cursor = ResumeCursor(
            run_id="test-run-123",
            tenant_id=42,
            step_number=5,
            message_index=10,
            workflow_type="onboarding",
            timestamp=datetime.now(timezone.utc),
        )
        run_state.cursor = cursor.serialize()

        user = Mock(spec=User)
        user.tenant_id = 42

        result = await WorkflowResumeService.validate_resume(
            run_state=run_state,
            current_user=user,
        )

        assert result.valid is False
        assert result.error_code == "NO_NEW_MESSAGES"

    @pytest.mark.asyncio
    async def test_resume_workflow_success(self):
        """Test successful workflow resume."""
        run_state = RunState(
            run_id="test-run-123",
            session_id=1,
            user_id=10,
        )
        run_state.messages = [{"role": "user", "content": f"msg{i}"} for i in range(6)]

        # persist_cursor stores workflow_id (gets mapped to workflow_type=unknown in deserialize)
        run_state.persist_cursor(
            step_number=10,
            message_index=5,
            tenant_id=42,
            workflow_id="wf-onboarding-123",
            additional_metadata={"workflow_classification": "onboarding"},
        )

        user = Mock(spec=User)
        user.tenant_id = 42

        result = await WorkflowResumeService.resume_workflow(
            run_state=run_state,
            current_user=user,
        )

        assert result["status"] == "RESUMED"
        assert result["step"] == 10
        assert result["message_index"] == 5
        assert result["run_id"] == "test-run-123"
        # workflow_type defaults to "unknown" since persist_cursor doesn't store it
        assert result["workflow_type"] in ["unknown", "onboarding"]

    @pytest.mark.asyncio
    async def test_resume_workflow_validation_failure(self):
        """Test resume workflow raises error on validation failure."""
        run_state = RunState(
            run_id="test-run-123",
            session_id=1,
            user_id=10,
        )
        # No cursor

        user = Mock(spec=User)
        user.tenant_id = 42

        with pytest.raises(ValueError) as exc_info:
            await WorkflowResumeService.resume_workflow(
                run_state=run_state,
                current_user=user,
            )

        assert "Resume validation failed" in str(exc_info.value)
        assert "NO_CURSOR" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_resume_workflow_expired_cursor(self):
        """Test resume workflow fails with expired cursor."""
        run_state = RunState(
            run_id="test-run-123",
            session_id=1,
            user_id=10,
        )
        run_state.messages = [{"role": "user", "content": f"msg{i}"} for i in range(6)]

        # Create expired cursor (2 hours old)
        old_timestamp = datetime.now(timezone.utc) - timedelta(hours=2)
        cursor = ResumeCursor(
            run_id="test-run-123",
            tenant_id=42,
            step_number=10,
            message_index=5,
            workflow_type="onboarding",
            timestamp=old_timestamp,
        )
        run_state.cursor = cursor.serialize()

        user = Mock(spec=User)
        user.tenant_id = 42

        with pytest.raises(ValueError) as exc_info:
            await WorkflowResumeService.resume_workflow(
                run_state=run_state,
                current_user=user,
                max_age_minutes=60,
            )

        assert "Resume validation failed" in str(exc_info.value)


class TestResumeValidationResult:
    """Test ResumeValidationResult dataclass."""

    def test_success_property(self):
        """Test success property is alias for valid."""
        result = ResumeValidationResult(valid=True)
        assert result.success is True

        result = ResumeValidationResult(valid=False)
        assert result.success is False

    def test_result_with_error(self):
        """Test result with error details."""
        result = ResumeValidationResult(
            valid=False,
            error_code="NO_CURSOR",
            error_message="No resume cursor found",
        )

        assert result.valid is False
        assert result.success is False
        assert result.error_code == "NO_CURSOR"
        assert result.error_message == "No resume cursor found"
        assert result.cursor is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
