"""Tests for run state and approval service."""
import pytest
import json
from datetime import datetime, timezone

from app.services.run_state import (
    RunState,
    RunStatus,
    PendingToolCall,
    ApprovalDecision,
    ApprovalService,
    ApprovalRecord,
    get_approval_service,
    reset_approval_service,
)


class TestRunState:
    """Test RunState serialization and state management."""

    def test_create_run_state(self):
        """Test creating a run state."""
        state = RunState(
            run_id="test-123",
            session_id=1,
            user_id=1,
        )
        
        assert state.run_id == "test-123"
        assert state.session_id == 1
        assert state.status == "running"
        assert state.current_step == 0

    def test_serialize_to_json(self):
        """Test serializing run state to JSON."""
        state = RunState(
            run_id="test-123",
            session_id=1,
            user_id=1,
            messages=[{"role": "user", "content": "Hello"}],
            completed_action_keys={"action1", "action2"},
        )
        
        json_str = state.to_json()
        data = json.loads(json_str)
        
        assert data["run_id"] == "test-123"
        assert data["session_id"] == 1
        assert len(data["messages"]) == 1
        # Set converted to list
        assert set(data["completed_action_keys"]) == {"action1", "action2"}

    def test_deserialize_from_json(self):
        """Test deserializing run state from JSON."""
        original = RunState(
            run_id="test-123",
            session_id=1,
            user_id=1,
            messages=[{"role": "user", "content": "Hello"}],
            completed_action_keys={"action1"},
        )
        
        json_str = original.to_json()
        restored = RunState.from_json(json_str)
        
        assert restored.run_id == original.run_id
        assert restored.session_id == original.session_id
        assert restored.messages == original.messages
        assert restored.completed_action_keys == original.completed_action_keys

    def test_pause_for_approval(self):
        """Test pausing state for approval."""
        state = RunState(
            run_id="test-123",
            session_id=1,
            user_id=1,
        )
        
        pending_tool = PendingToolCall(
            tool_name="delete_record",
            arguments={"id": 123},
            tool_call_id="call-1",
            reason="Destructive operation",
            risk_level="high",
        )
        
        state.pause_for_approval(pending_tool)
        
        assert state.status == RunStatus.PAUSED_FOR_APPROVAL.value
        assert state.paused_at is not None
        assert state.pending_approval is not None
        assert state.pending_approval["tool_name"] == "delete_record"
        assert state.pending_approval["risk_level"] == "high"

    def test_resume_after_approval(self):
        """Test resuming state after approval."""
        state = RunState(
            run_id="test-123",
            session_id=1,
            user_id=1,
            status="paused_for_approval",
            pending_approval={
                "tool_name": "delete_record",
                "arguments": {},
            },
        )
        
        state.resume_after_approval(approved=True, user_comment="Looks good")
        
        assert state.status == RunStatus.RUNNING.value
        assert state.resumed_at is not None
        assert state.pending_approval["decision"] == ApprovalDecision.APPROVED.value
        assert state.pending_approval["user_comment"] == "Looks good"

    def test_mark_completed(self):
        """Test marking state as completed."""
        state = RunState(
            run_id="test-123",
            session_id=1,
            user_id=1,
        )
        
        state.mark_completed("Task done", "completed")
        
        assert state.status == RunStatus.COMPLETED.value
        assert state.stopped_reason == "completed"
        assert state.metadata["final_response"] == "Task done"

    def test_mark_failed(self):
        """Test marking state as failed."""
        state = RunState(
            run_id="test-123",
            session_id=1,
            user_id=1,
        )
        
        state.mark_failed("Connection lost", "error")
        
        assert state.status == RunStatus.FAILED.value
        assert state.stopped_reason == "error"
        assert state.error == "Connection lost"


class TestApprovalService:
    """Test approval service functionality."""

    @pytest.fixture(autouse=True)
    def reset(self):
        """Reset global approval service."""
        reset_approval_service()
        yield
        reset_approval_service()

    @pytest.fixture
    def approval_service(self):
        """Create approval service without DB."""
        return ApprovalService(db_session=None)

    def test_can_auto_approve_read_operations(self, approval_service):
        """Test auto-approval for read operations."""
        assert approval_service.can_auto_approve("get_user") is True
        assert approval_service.can_auto_approve("list_records") is True
        assert approval_service.can_auto_approve("search_items") is True
        assert approval_service.can_auto_approve("fetch_data") is True

    def test_cannot_auto_approve_write_operations(self, approval_service):
        """Test that write operations cannot be auto-approved."""
        assert approval_service.can_auto_approve("create_user") is False
        assert approval_service.can_auto_approve("delete_record") is False
        assert approval_service.can_auto_approve("update_item") is False
        assert approval_service.can_auto_approve("modify_config") is False

    def test_explicit_auto_approve_allowlist(self, approval_service):
        """Test explicit auto-approve allowlist."""
        # By default, write operations not allowed
        assert approval_service.can_auto_approve("create_temp_file") is False
        
        # Add to explicit allowlist
        approval_service.set_auto_approve_allowlist({"create_temp_file"})
        
        # Now allowed
        assert approval_service.can_auto_approve("create_temp_file") is True

    def test_classify_risk_high(self, approval_service):
        """Test high risk classification."""
        assert approval_service.classify_risk("delete_user", {}) == "high"
        assert approval_service.classify_risk("drop_table", {}) == "high"
        assert approval_service.classify_risk("remove_all", {}) == "high"

    def test_classify_risk_medium(self, approval_service):
        """Test medium risk classification."""
        assert approval_service.classify_risk("update_record", {}) == "medium"
        assert approval_service.classify_risk("modify_config", {}) == "medium"
        assert approval_service.classify_risk("set_value", {}) == "medium"

    def test_classify_risk_low(self, approval_service):
        """Test low risk classification."""
        assert approval_service.classify_risk("create_user", {}) == "low"
        assert approval_service.classify_risk("insert_record", {}) == "low"
        assert approval_service.classify_risk("add_item", {}) == "low"

    def test_build_pending_tool_call(self, approval_service):
        """Test building pending tool call with risk classification."""
        pending = approval_service.build_pending_tool_call(
            tool_name="delete_user",
            arguments={"user_id": 123},
            tool_call_id="call-1",
        )
        
        assert pending.tool_name == "delete_user"
        assert pending.arguments == {"user_id": 123}
        assert pending.risk_level == "high"
        assert "permanently remove" in pending.reason.lower()

    def test_create_approval_request(self, approval_service):
        """Test creating approval request."""
        run_state = RunState(
            run_id="run-123",
            session_id=1,
            user_id=1,
        )
        
        pending_tool = PendingToolCall(
            tool_name="delete_record",
            arguments={"id": 123},
            tool_call_id="call-1",
            reason="Destructive operation",
            risk_level="high",
        )
        
        record = approval_service.create_approval_request(run_state, pending_tool)
        
        assert record.run_id == "run-123"
        assert record.session_id == 1
        assert record.tool_name == "delete_record"
        assert record.risk_level == "high"
        assert record.decision == ApprovalDecision.PENDING.value
        
        # Should have serialized run state
        assert len(record.run_state_json) > 0
        restored_state = RunState.from_json(record.run_state_json)
        assert restored_state.run_id == "run-123"


class TestGlobalApprovalService:
    """Test global singleton approval service."""

    def test_singleton_pattern(self):
        """Test singleton creation and reset."""
        reset_approval_service()
        
        svc1 = get_approval_service()
        svc2 = get_approval_service()
        assert svc1 is svc2
        
        reset_approval_service()
        svc3 = get_approval_service()
        assert svc3 is not svc1

    def test_db_session_injection(self):
        """Test injecting DB session returns new instance (thread-safe)."""
        reset_approval_service()
        
        # Create without DB
        svc1 = get_approval_service()
        assert svc1.db is None
        
        # With db_session, returns NEW instance (not singleton) for thread safety
        mock_db = object()
        svc2 = get_approval_service(db_session=mock_db)
        assert svc2 is not svc1  # Different instance - thread-safe
        assert svc2.db is mock_db
        assert svc1.db is None  # Singleton unchanged
