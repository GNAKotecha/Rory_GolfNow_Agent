"""
Tests for RunState cursor persistence mechanism.

Tests:
- Cursor persistence
- Cursor validation (tenant, age)
- Cursor retrieval
- Resume from valid cursor
- Handle missing/invalid cursors
- Backward compatibility
"""
import pytest
from datetime import datetime, timezone, timedelta
from app.services.run_state import RunState


class TestCursorPersistence:
    """Test cursor persistence mechanism."""

    def test_persist_cursor_minimal(self):
        """Test cursor persistence with minimal parameters."""
        run_state = RunState(
            run_id="test-run-1",
            session_id=1,
            user_id=100,
        )

        run_state.persist_cursor(
            step_number=5,
            message_index=10
        )

        assert run_state.cursor is not None
        assert run_state.cursor['step_number'] == 5
        assert run_state.cursor['message_index'] == 10
        assert run_state.cursor['workflow_id'] is None
        assert run_state.cursor['tenant_id'] is None
        assert 'timestamp' in run_state.cursor
        assert 'metadata' in run_state.cursor

    def test_persist_cursor_full(self):
        """Test cursor persistence with all parameters."""
        run_state = RunState(
            run_id="test-run-2",
            session_id=2,
            user_id=200,
        )

        metadata = {"custom_field": "value", "retry_count": 3}
        run_state.persist_cursor(
            step_number=8,
            message_index=16,
            workflow_id="workflow-123",
            tenant_id=42,
            additional_metadata=metadata
        )

        assert run_state.cursor is not None
        assert run_state.cursor['step_number'] == 8
        assert run_state.cursor['message_index'] == 16
        assert run_state.cursor['workflow_id'] == "workflow-123"
        assert run_state.cursor['tenant_id'] == 42
        assert run_state.cursor['metadata'] == metadata

    def test_get_cursor(self):
        """Test cursor retrieval."""
        run_state = RunState(
            run_id="test-run-3",
            session_id=3,
            user_id=300,
        )

        # No cursor initially
        assert run_state.get_cursor() is None

        # Persist and retrieve
        run_state.persist_cursor(step_number=1, message_index=2)
        cursor = run_state.get_cursor()

        assert cursor is not None
        assert cursor['step_number'] == 1
        assert cursor['message_index'] == 2


class TestCursorValidation:
    """Test cursor validation logic."""

    def test_validate_cursor_no_cursor(self):
        """Test validation fails when no cursor exists."""
        run_state = RunState(
            run_id="test-run-4",
            session_id=4,
            user_id=400,
        )

        # validate_cursor requires tenant_id but returns False when no cursor exists
        assert not run_state.validate_cursor(current_tenant_id=1)

    def test_validate_cursor_success(self):
        """Test validation succeeds with valid cursor."""
        run_state = RunState(
            run_id="test-run-5",
            session_id=5,
            user_id=500,
        )

        run_state.persist_cursor(
            step_number=3,
            message_index=6,
            tenant_id=1
        )

        assert run_state.validate_cursor(current_tenant_id=1)

    def test_validate_cursor_tenant_mismatch(self):
        """Test validation fails on tenant mismatch."""
        run_state = RunState(
            run_id="test-run-6",
            session_id=6,
            user_id=600,
        )

        run_state.persist_cursor(
            step_number=2,
            message_index=4,
            tenant_id=1
        )

        # Different tenant
        assert not run_state.validate_cursor(current_tenant_id=2)

    def test_validate_cursor_no_tenant_check(self):
        """Test validation requires current_tenant_id parameter."""
        run_state = RunState(
            run_id="test-run-7",
            session_id=7,
            user_id=700,
        )

        run_state.persist_cursor(
            step_number=2,
            message_index=4,
            tenant_id=1
        )

        # current_tenant_id is now required - ValueError if not provided
        import pytest
        with pytest.raises(ValueError, match="current_tenant_id is required"):
            run_state.validate_cursor(current_tenant_id=None)

    def test_validate_cursor_expired(self):
        """Test validation fails for expired cursor."""
        run_state = RunState(
            run_id="test-run-8",
            session_id=8,
            user_id=800,
        )

        run_state.persist_cursor(
            step_number=1,
            message_index=2,
            tenant_id=1
        )

        # Manually set old timestamp
        old_time = datetime.now(timezone.utc) - timedelta(minutes=65)
        run_state.cursor['timestamp'] = old_time.isoformat()

        # Should fail with default 60-minute limit
        assert not run_state.validate_cursor(current_tenant_id=1, max_age_minutes=60)

    def test_validate_cursor_custom_age_limit(self):
        """Test validation with custom age limit."""
        run_state = RunState(
            run_id="test-run-9",
            session_id=9,
            user_id=900,
        )

        run_state.persist_cursor(
            step_number=1,
            message_index=2,
            tenant_id=1
        )

        # Set timestamp 45 minutes ago
        old_time = datetime.now(timezone.utc) - timedelta(minutes=45)
        run_state.cursor['timestamp'] = old_time.isoformat()

        # Should fail with 30-minute limit
        assert not run_state.validate_cursor(current_tenant_id=1, max_age_minutes=30)

        # Should pass with 60-minute limit
        assert run_state.validate_cursor(current_tenant_id=1, max_age_minutes=60)

    def test_validate_cursor_invalid_timestamp(self):
        """Test validation fails with invalid timestamp."""
        run_state = RunState(
            run_id="test-run-10",
            session_id=10,
            user_id=1000,
        )

        run_state.persist_cursor(
            step_number=1,
            message_index=2
        )

        # Corrupt timestamp
        run_state.cursor['timestamp'] = "invalid-timestamp"

        # Must pass tenant_id; invalid timestamp should return False
        assert not run_state.validate_cursor(current_tenant_id=1)


class TestCursorResume:
    """Test cursor resume functionality."""

    def test_resume_from_cursor_success(self):
        """Test successful resume from valid cursor."""
        run_state = RunState(
            run_id="test-run-11",
            session_id=11,
            user_id=1100,
        )

        run_state.persist_cursor(
            step_number=5,
            message_index=10,
            tenant_id=1,
            workflow_id="wf-123"
        )

        cursor = run_state.resume_from_cursor(current_tenant_id=1)

        assert cursor is not None
        assert cursor['step_number'] == 5
        assert cursor['message_index'] == 10
        assert cursor['workflow_id'] == "wf-123"

    def test_resume_from_cursor_invalid(self):
        """Test resume fails with invalid cursor."""
        run_state = RunState(
            run_id="test-run-12",
            session_id=12,
            user_id=1200,
        )

        run_state.persist_cursor(
            step_number=3,
            message_index=6,
            tenant_id=1
        )

        # Wrong tenant
        cursor = run_state.resume_from_cursor(current_tenant_id=2)

        assert cursor is None

    def test_resume_from_cursor_no_cursor(self):
        """Test resume fails when no cursor exists."""
        run_state = RunState(
            run_id="test-run-13",
            session_id=13,
            user_id=1300,
        )

        cursor = run_state.resume_from_cursor(current_tenant_id=1)

        assert cursor is None


class TestCursorSerialization:
    """Test cursor survives serialization/deserialization."""

    def test_cursor_serialization_json(self):
        """Test cursor persists through JSON serialization."""
        run_state = RunState(
            run_id="test-run-14",
            session_id=14,
            user_id=1400,
        )

        run_state.persist_cursor(
            step_number=7,
            message_index=14,
            tenant_id=5,
            workflow_id="wf-456",
            additional_metadata={"key": "value"}
        )

        # Serialize and deserialize
        json_str = run_state.to_json()
        restored_state = RunState.from_json(json_str)

        # Verify cursor preserved
        assert restored_state.cursor is not None
        assert restored_state.cursor['step_number'] == 7
        assert restored_state.cursor['message_index'] == 14
        assert restored_state.cursor['tenant_id'] == 5
        assert restored_state.cursor['workflow_id'] == "wf-456"
        assert restored_state.cursor['metadata']['key'] == "value"

    def test_cursor_serialization_dict(self):
        """Test cursor persists through dict serialization."""
        run_state = RunState(
            run_id="test-run-15",
            session_id=15,
            user_id=1500,
        )

        run_state.persist_cursor(
            step_number=9,
            message_index=18,
            tenant_id=3
        )

        # Serialize and deserialize
        state_dict = run_state.to_dict()
        restored_state = RunState.from_dict(state_dict)

        # Verify cursor preserved
        assert restored_state.cursor is not None
        assert restored_state.cursor['step_number'] == 9
        assert restored_state.cursor['message_index'] == 18
        assert restored_state.cursor['tenant_id'] == 3


class TestBackwardCompatibility:
    """Test backward compatibility with existing code."""

    def test_runstate_without_cursor(self):
        """Test RunState works without cursor field."""
        run_state = RunState(
            run_id="test-run-16",
            session_id=16,
            user_id=1600,
        )

        # Should work without cursor
        assert run_state.cursor is None
        assert run_state.get_cursor() is None
        # validate_cursor requires tenant_id param, returns False when no cursor
        assert not run_state.validate_cursor(current_tenant_id=1)

    def test_serialization_without_cursor(self):
        """Test serialization works when cursor is None."""
        run_state = RunState(
            run_id="test-run-17",
            session_id=17,
            user_id=1700,
        )

        # Serialize without cursor
        json_str = run_state.to_json()
        restored_state = RunState.from_json(json_str)

        # Should restore with cursor=None
        assert restored_state.cursor is None

    def test_deserialization_old_state(self):
        """Test deserializing old RunState without cursor field."""
        # Simulate old state dict without cursor field
        old_state_dict = {
            "run_id": "test-run-18",
            "session_id": 18,
            "user_id": 1800,
            "model": None,
            "max_steps": 10,
            "current_step": 0,
            "status": "running",
            "stopped_reason": None,
            "error": None,
            "messages": [],
            "steps": [],
            "completed_action_keys": [],
            "retry_counts": {},
            "pending_approval": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "paused_at": None,
            "resumed_at": None,
            "metadata": {}
        }

        # Should restore without error (cursor defaults to None)
        restored_state = RunState.from_dict(old_state_dict)

        assert restored_state.run_id == "test-run-18"
        assert restored_state.cursor is None


class TestCursorIntegrationWithApproval:
    """Test cursor integration with approval flow."""

    def test_resume_after_approval_with_cursor(self):
        """Test resume_after_approval validates cursor."""
        run_state = RunState(
            run_id="test-run-19",
            session_id=19,
            user_id=1900,
        )

        # Set up pending approval
        run_state.pause_for_approval(
            pending_tool=type('PendingToolCall', (), {
                'tool_name': 'test_tool',
                'arguments': {},
                'tool_call_id': 'call-123',
                'reason': 'test',
                'risk_level': 'low'
            })()
        )

        # Persist cursor
        run_state.persist_cursor(
            step_number=4,
            message_index=8,
            tenant_id=1
        )

        # Resume after approval
        run_state.resume_after_approval(approved=True)

        # Cursor should still be present and valid
        assert run_state.cursor is not None
        assert run_state.validate_cursor(current_tenant_id=1)

    def test_resume_after_approval_invalid_cursor(self):
        """Test resume_after_approval with invalid cursor logs warning."""
        run_state = RunState(
            run_id="test-run-20",
            session_id=20,
            user_id=2000,
        )

        # Set up pending approval
        run_state.pause_for_approval(
            pending_tool=type('PendingToolCall', (), {
                'tool_name': 'test_tool',
                'arguments': {},
                'tool_call_id': 'call-456',
                'reason': 'test',
                'risk_level': 'medium'
            })()
        )

        # Persist cursor with tenant 1
        run_state.persist_cursor(
            step_number=2,
            message_index=4,
            tenant_id=1
        )

        # Make cursor invalid (expired)
        old_time = datetime.now(timezone.utc) - timedelta(minutes=90)
        run_state.cursor['timestamp'] = old_time.isoformat()

        # Resume after approval - should log warning but not fail
        run_state.resume_after_approval(approved=True)

        # Status should still be updated
        assert run_state.status == "running"
        assert run_state.resumed_at is not None
