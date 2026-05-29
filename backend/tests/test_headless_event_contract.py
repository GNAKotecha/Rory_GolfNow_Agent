"""Contract tests for headless/CLI event contract.

Task E1: Validates required fields per event type.
Task E2: Validates ask_user and user_response envelopes.
"""
import pytest
from datetime import datetime, timezone
from typing import Dict, Any

from app.services.headless_events import (
    HeadlessEventType,
    HeadlessEvent,
    HeadlessEventBuilder,
    AskUserReason,
    AskUserPayload,
    UserResponse,
    InputField,
    InputFieldType,
    RemediationOption,
    validate_event,
    REQUIRED_FIELDS_BY_TYPE,
    create_auth_remediation_options,
    create_validation_remediation_options,
    create_semantic_error_remediation_options,
    create_approval_remediation_options,
)


class TestHeadlessEventContract:
    """Test that all events have required fields."""
    
    def test_all_event_types_have_validation_rules(self):
        """Every event type must have validation rules defined."""
        for event_type in HeadlessEventType:
            assert event_type.value in REQUIRED_FIELDS_BY_TYPE, (
                f"Event type {event_type.value} missing from REQUIRED_FIELDS_BY_TYPE"
            )
    
    def test_workflow_start_required_fields(self):
        """workflow_start must have available_tools and max_steps."""
        builder = HeadlessEventBuilder(run_id="test-run")
        event = builder.workflow_start(available_tools=5, max_steps=10)
        
        event_dict = event.to_dict()
        
        assert event_dict["type"] == "workflow_start"
        assert event_dict["run_id"] == "test-run"
        assert "timestamp" in event_dict
        assert event_dict["available_tools"] == 5
        assert event_dict["max_steps"] == 10
        
        # Validate no missing fields
        missing = validate_event(event)
        assert missing == [], f"Missing fields: {missing}"
    
    def test_workflow_complete_required_fields(self):
        """workflow_complete must have total_steps and stopped_reason."""
        builder = HeadlessEventBuilder(run_id="test-run")
        event = builder.workflow_complete(total_steps=5, stopped_reason="completed")
        
        event_dict = event.to_dict()
        
        assert event_dict["type"] == "workflow_complete"
        assert event_dict["run_id"] == "test-run"
        assert event_dict["total_steps"] == 5
        assert event_dict["stopped_reason"] == "completed"
        
        missing = validate_event(event)
        assert missing == [], f"Missing fields: {missing}"
    
    def test_workflow_error_required_fields(self):
        """workflow_error must have error."""
        builder = HeadlessEventBuilder(run_id="test-run")
        event = builder.workflow_error(error="Connection failed", error_type="transport")
        
        event_dict = event.to_dict()
        
        assert event_dict["type"] == "workflow_error"
        assert event_dict["error"] == "Connection failed"
        
        missing = validate_event(event)
        assert missing == [], f"Missing fields: {missing}"
    
    def test_step_required_fields(self):
        """step must have action."""
        builder = HeadlessEventBuilder(run_id="test-run")
        event = builder.step(step_number=1, action="tool_calls", tool_names=["get_clubs"])
        
        event_dict = event.to_dict()
        
        assert event_dict["type"] == "step"
        assert event_dict["step_number"] == 1
        assert event_dict["action"] == "tool_calls"
        
        missing = validate_event(event)
        assert missing == [], f"Missing fields: {missing}"
    
    def test_tool_executing_required_fields(self):
        """tool_executing must have tool_name, tool_index, tool_total."""
        builder = HeadlessEventBuilder(run_id="test-run")
        event = builder.tool_executing(
            tool_name="get_club",
            tool_index=1,
            tool_total=3,
            step_number=2,
            arguments={"club_id": "123"},
        )
        
        event_dict = event.to_dict()
        
        assert event_dict["type"] == "tool_executing"
        assert event_dict["tool_name"] == "get_club"
        assert event_dict["tool_index"] == 1
        assert event_dict["tool_total"] == 3
        
        missing = validate_event(event)
        assert missing == [], f"Missing fields: {missing}"
    
    def test_tool_result_required_fields(self):
        """tool_result must have tool_name and success."""
        builder = HeadlessEventBuilder(run_id="test-run")
        event = builder.tool_result(
            tool_name="get_club",
            step_number=2,
            success=True,
            duration_ms=150,
        )
        
        event_dict = event.to_dict()
        
        assert event_dict["type"] == "tool_result"
        assert event_dict["tool_name"] == "get_club"
        assert event_dict["success"] is True
        
        missing = validate_event(event)
        assert missing == [], f"Missing fields: {missing}"
    
    def test_tool_error_required_fields(self):
        """tool_error must have tool_name and error."""
        builder = HeadlessEventBuilder(run_id="test-run")
        event = builder.tool_error(
            tool_name="get_club",
            step_number=2,
            error="Connection refused",
            error_type="transport",
            retryable=True,
        )
        
        event_dict = event.to_dict()
        
        assert event_dict["type"] == "tool_error"
        assert event_dict["tool_name"] == "get_club"
        assert event_dict["error"] == "Connection refused"
        
        missing = validate_event(event)
        assert missing == [], f"Missing fields: {missing}"
    
    def test_final_response_required_fields(self):
        """final_response must have message."""
        builder = HeadlessEventBuilder(run_id="test-run")
        event = builder.final_response(message="Operation completed successfully.")
        
        event_dict = event.to_dict()
        
        assert event_dict["type"] == "final_response"
        assert event_dict["message"] == "Operation completed successfully."
        
        missing = validate_event(event)
        assert missing == [], f"Missing fields: {missing}"
    
    def test_loop_detected_required_fields(self):
        """loop_detected must have step."""
        builder = HeadlessEventBuilder(run_id="test-run")
        event = builder.loop_detected(step_number=5)
        
        event_dict = event.to_dict()
        
        assert event_dict["type"] == "loop_detected"
        assert event_dict["step"] == 5
        
        missing = validate_event(event)
        assert missing == [], f"Missing fields: {missing}"
    
    def test_low_confidence_required_fields(self):
        """low_confidence must have confidence."""
        builder = HeadlessEventBuilder(run_id="test-run")
        event = builder.low_confidence(confidence=0.4)
        
        event_dict = event.to_dict()
        
        assert event_dict["type"] == "low_confidence"
        assert event_dict["confidence"] == 0.4
        
        missing = validate_event(event)
        assert missing == [], f"Missing fields: {missing}"
    
    def test_max_steps_reached_required_fields(self):
        """max_steps_reached must have max_steps."""
        builder = HeadlessEventBuilder(run_id="test-run")
        event = builder.max_steps_reached(max_steps=10, step_number=10)
        
        event_dict = event.to_dict()
        
        assert event_dict["type"] == "max_steps_reached"
        assert event_dict["max_steps"] == 10
        
        missing = validate_event(event)
        assert missing == [], f"Missing fields: {missing}"
    
    def test_approval_request_required_fields(self):
        """approval_request must have tool_name and arguments."""
        builder = HeadlessEventBuilder(run_id="test-run")
        event = builder.approval_request(
            tool_name="delete_club",
            arguments={"club_id": "123"},
        )
        
        event_dict = event.to_dict()
        
        assert event_dict["type"] == "approval_request"
        assert event_dict["tool_name"] == "delete_club"
        assert event_dict["arguments"] == {"club_id": "123"}
        
        missing = validate_event(event)
        assert missing == [], f"Missing fields: {missing}"
    
    def test_plan_created_required_fields(self):
        """plan_created must have steps."""
        builder = HeadlessEventBuilder(run_id="test-run")
        event = builder.plan_created(steps=["Step 1", "Step 2"])
        
        event_dict = event.to_dict()
        
        assert event_dict["type"] == "plan_created"
        assert event_dict["steps"] == ["Step 1", "Step 2"]
        
        missing = validate_event(event)
        assert missing == [], f"Missing fields: {missing}"
    
    def test_plan_progress_required_fields(self):
        """plan_progress must have progress."""
        builder = HeadlessEventBuilder(run_id="test-run")
        event = builder.plan_progress(progress=0.5, current_step=2)
        
        event_dict = event.to_dict()
        
        assert event_dict["type"] == "plan_progress"
        assert event_dict["progress"] == 0.5
        
        missing = validate_event(event)
        assert missing == [], f"Missing fields: {missing}"


class TestAskUserContract:
    """Task E2: Test ask_user event contract."""
    
    def test_ask_user_required_fields(self):
        """ask_user must have reason, title, message."""
        builder = HeadlessEventBuilder(run_id="test-run")
        event = builder.ask_user(
            reason=AskUserReason.AUTH_REQUIRED,
            title="Authentication Required",
            message="Please provide API credentials.",
        )
        
        event_dict = event.to_dict()
        
        assert event_dict["type"] == "ask_user"
        assert event_dict["reason"] == "auth_required"
        assert event_dict["title"] == "Authentication Required"
        assert event_dict["message"] == "Please provide API credentials."
        assert "resume_token" in event_dict
        assert event_dict["resume_token"] is not None
        
        missing = validate_event(event)
        assert missing == [], f"Missing fields: {missing}"
    
    def test_ask_user_with_options(self):
        """ask_user can include structured remediation options."""
        builder = HeadlessEventBuilder(run_id="test-run")
        event = builder.ask_user(
            reason=AskUserReason.VALIDATION_FAILED,
            title="Missing Information",
            message="Some required fields are missing.",
            options=[
                RemediationOption(
                    id="provide_values",
                    label="Provide values",
                    action="retry",
                    requires_input=True,
                    input_fields=[
                        InputField(name="club_name", label="Club Name"),
                    ],
                ),
                RemediationOption(id="skip", label="Skip", action="skip"),
            ],
        )
        
        event_dict = event.to_dict()
        
        assert len(event_dict["options"]) == 2
        assert event_dict["options"][0]["id"] == "provide_values"
        assert event_dict["options"][0]["requires_input"] is True
        assert len(event_dict["options"][0]["input_fields"]) == 1
    
    def test_ask_user_generates_resume_token(self):
        """ask_user must generate a valid resume token."""
        builder = HeadlessEventBuilder(run_id="test-run")
        event = builder.ask_user(
            reason=AskUserReason.USER_INPUT_NEEDED,
            title="Input Needed",
            message="Please provide details.",
        )
        
        event_dict = event.to_dict()
        resume_token = event_dict["resume_token"]
        
        # Token should be retrievable from builder
        context = builder.validate_resume_token(resume_token)
        assert context is not None
        assert context["reason"] == AskUserReason.USER_INPUT_NEEDED
    
    def test_ask_user_payload_serialization(self):
        """AskUserPayload should serialize properly."""
        payload = AskUserPayload(
            reason=AskUserReason.SEMANTIC_ERROR,
            title="Tool Error",
            message="The tool returned an error.",
            options=[
                RemediationOption(id="retry", label="Retry", action="retry"),
            ],
            context={"tool_name": "get_club", "error": "Not found"},
            resume_token="test-token",
            timeout_seconds=300,
            allow_freeform=True,
        )
        
        payload_dict = payload.to_dict()
        
        assert payload_dict["reason"] == "semantic_error"
        assert payload_dict["title"] == "Tool Error"
        assert payload_dict["message"] == "The tool returned an error."
        assert len(payload_dict["options"]) == 1
        assert payload_dict["context"]["tool_name"] == "get_club"
        assert payload_dict["resume_token"] == "test-token"
        assert payload_dict["timeout_seconds"] == 300
        assert payload_dict["allow_freeform"] is True


class TestUserResponseContract:
    """Task E2: Test user_response envelope."""
    
    def test_user_response_required_fields(self):
        """user_response must have resume_token."""
        response = UserResponse(resume_token="test-token-123")
        
        response_dict = response.to_dict()
        
        assert response_dict["resume_token"] == "test-token-123"
        assert "timestamp" in response_dict
    
    def test_user_response_with_option_selection(self):
        """user_response can include selected option."""
        response = UserResponse(
            resume_token="test-token",
            selected_option_id="provide_values",
            input_values={"club_name": "Test Club"},
        )
        
        response_dict = response.to_dict()
        
        assert response_dict["selected_option_id"] == "provide_values"
        assert response_dict["input_values"] == {"club_name": "Test Club"}
    
    def test_user_response_with_freeform(self):
        """user_response can include freeform text."""
        response = UserResponse(
            resume_token="test-token",
            freeform_text="I want to create a club named 'Test Golf Club'",
        )
        
        response_dict = response.to_dict()
        
        assert response_dict["freeform_text"] == "I want to create a club named 'Test Golf Club'"
    
    def test_user_response_from_dict(self):
        """UserResponse can be created from dictionary."""
        data = {
            "resume_token": "test-token",
            "selected_option_id": "approve",
            "input_values": {"confirm": True},
            "timestamp": "2026-05-14T10:00:00+00:00",
        }
        
        response = UserResponse.from_dict(data)
        
        assert response.resume_token == "test-token"
        assert response.selected_option_id == "approve"
        assert response.input_values == {"confirm": True}
        assert response.timestamp.year == 2026


class TestRunIdCorrelation:
    """Task E1: Test run_id correlation across events."""
    
    def test_all_events_have_same_run_id(self):
        """All events from same builder should have same run_id."""
        builder = HeadlessEventBuilder(run_id="correlation-test-123")
        
        events = [
            builder.workflow_start(available_tools=5, max_steps=10),
            builder.step(step_number=1, action="tool_calls"),
            builder.tool_executing("get_club", 1, 1, 1),
            builder.tool_result("get_club", 1, success=True),
            builder.final_response("Done"),
            builder.workflow_complete(total_steps=1, stopped_reason="completed"),
        ]
        
        for event in events:
            assert event.to_dict()["run_id"] == "correlation-test-123"
    
    def test_auto_generated_run_id(self):
        """Builder should auto-generate run_id if not provided."""
        builder = HeadlessEventBuilder()
        
        assert builder.run_id is not None
        assert len(builder.run_id) == 36  # UUID format
    
    def test_timestamp_in_all_events(self):
        """All events should have timestamp."""
        builder = HeadlessEventBuilder()
        
        events = [
            builder.workflow_start(available_tools=5, max_steps=10),
            builder.step(step_number=1, action="tool_calls"),
            builder.tool_error("get_club", 1, error="Failed"),
            builder.ask_user(AskUserReason.AUTH_REQUIRED, "Auth", "Please auth"),
            builder.final_response("Done"),
        ]
        
        for event in events:
            event_dict = event.to_dict()
            assert "timestamp" in event_dict
            # Should be ISO format
            datetime.fromisoformat(event_dict["timestamp"].replace("Z", "+00:00"))


class TestInputFieldTypes:
    """Test InputField types and serialization."""
    
    def test_text_field(self):
        """Text field serialization."""
        field = InputField(
            name="username",
            label="Username",
            field_type=InputFieldType.TEXT,
            placeholder="Enter username",
        )
        
        field_dict = field.to_dict()
        
        assert field_dict["name"] == "username"
        assert field_dict["field_type"] == "text"
        assert field_dict["placeholder"] == "Enter username"
    
    def test_password_field(self):
        """Password field serialization."""
        field = InputField(
            name="api_key",
            label="API Key",
            field_type=InputFieldType.PASSWORD,
        )
        
        field_dict = field.to_dict()
        
        assert field_dict["field_type"] == "password"
    
    def test_select_field_with_options(self):
        """Select field with options serialization."""
        field = InputField(
            name="region",
            label="Region",
            field_type=InputFieldType.SELECT,
            options=[
                {"value": "us-east", "label": "US East"},
                {"value": "eu-west", "label": "EU West"},
            ],
        )
        
        field_dict = field.to_dict()
        
        assert field_dict["field_type"] == "select"
        assert len(field_dict["options"]) == 2
    
    def test_number_field_with_range(self):
        """Number field with min/max serialization."""
        field = InputField(
            name="quantity",
            label="Quantity",
            field_type=InputFieldType.NUMBER,
            min_value=1,
            max_value=100,
            default=10,
        )
        
        field_dict = field.to_dict()
        
        assert field_dict["field_type"] == "number"
        assert field_dict["min_value"] == 1
        assert field_dict["max_value"] == 100
        assert field_dict["default"] == 10


class TestRemediationFactories:
    """Test factory functions for common remediation scenarios."""
    
    def test_auth_remediation_options(self):
        """Auth remediation should have credential input option."""
        options = create_auth_remediation_options()
        
        assert len(options) >= 2
        
        credential_option = next((o for o in options if o.id == "provide_credentials"), None)
        assert credential_option is not None
        assert credential_option.requires_input is True
        assert any(f.field_type == InputFieldType.PASSWORD for f in credential_option.input_fields)
    
    def test_validation_remediation_options(self):
        """Validation remediation should include missing field inputs."""
        options = create_validation_remediation_options(missing_fields=["club_name", "region"])
        
        provide_option = next((o for o in options if o.id == "provide_values"), None)
        assert provide_option is not None
        assert provide_option.requires_input is True
        assert len(provide_option.input_fields) == 2
    
    def test_semantic_error_remediation_options(self):
        """Semantic error remediation should offer retry with correction."""
        options = create_semantic_error_remediation_options()
        
        retry_option = next((o for o in options if o.id == "retry_with_correction"), None)
        assert retry_option is not None
        assert retry_option.action == "retry"
    
    def test_approval_remediation_options(self):
        """Approval remediation should have approve/deny options."""
        options = create_approval_remediation_options("delete_club")
        
        assert any(o.id == "approve" for o in options)
        assert any(o.id == "deny" for o in options)


class TestResumeTokenLifecycle:
    """Test resume token creation, validation, and consumption."""
    
    def test_resume_token_created_on_ask_user(self):
        """ask_user should create a resume token."""
        builder = HeadlessEventBuilder()
        event = builder.ask_user(
            reason=AskUserReason.USER_INPUT_NEEDED,
            title="Input",
            message="Provide input",
        )
        
        token = event.to_dict()["resume_token"]
        assert token is not None
        assert builder.validate_resume_token(token) is not None
    
    def test_resume_token_stores_context(self):
        """Resume token should store context for later use."""
        builder = HeadlessEventBuilder()
        builder.ask_user(
            reason=AskUserReason.VALIDATION_FAILED,
            title="Validation",
            message="Missing fields",
            context={"tool_name": "create_club", "missing": ["name"]},
            step_number=3,
        )
        
        # Get token from pending tokens
        token = list(builder._pending_resume_tokens.keys())[0]
        context = builder.validate_resume_token(token)
        
        assert context["reason"] == AskUserReason.VALIDATION_FAILED
        assert context["context"]["tool_name"] == "create_club"
        assert context["step_number"] == 3
    
    def test_consume_resume_token_removes_it(self):
        """Consuming a token should remove it from pending."""
        builder = HeadlessEventBuilder()
        event = builder.ask_user(
            reason=AskUserReason.AUTH_REQUIRED,
            title="Auth",
            message="Please auth",
        )
        
        token = event.to_dict()["resume_token"]
        
        # First consume should succeed
        context = builder.consume_resume_token(token)
        assert context is not None
        
        # Second consume should fail (token removed)
        context = builder.consume_resume_token(token)
        assert context is None
    
    def test_invalid_resume_token_returns_none(self):
        """Invalid token should return None on validation."""
        builder = HeadlessEventBuilder()
        
        context = builder.validate_resume_token("invalid-token")
        assert context is None


class TestEventValidation:
    """Test event validation helper."""
    
    def test_valid_event_returns_empty_list(self):
        """Valid event should return empty missing fields list."""
        builder = HeadlessEventBuilder()
        event = builder.workflow_start(available_tools=5, max_steps=10)
        
        missing = validate_event(event)
        assert missing == []
    
    def test_missing_type_detected(self):
        """Missing type should be detected."""
        event_dict = {"run_id": "test", "available_tools": 5}
        
        missing = validate_event(event_dict)
        assert "type" in missing
    
    def test_missing_run_id_detected(self):
        """Missing run_id should be detected."""
        event_dict = {"type": "workflow_start", "available_tools": 5}
        
        missing = validate_event(event_dict)
        assert "run_id" in missing
    
    def test_missing_required_payload_fields_detected(self):
        """Missing required payload fields should be detected."""
        event_dict = {
            "type": "tool_executing",
            "run_id": "test",
            "tool_name": "get_club",
            # Missing tool_index and tool_total
        }
        
        missing = validate_event(event_dict)
        assert "tool_index" in missing
        assert "tool_total" in missing


class TestArgumentTruncation:
    """Test that large arguments are truncated in events."""
    
    def test_tool_executing_truncates_large_args(self):
        """Large argument values should be truncated."""
        builder = HeadlessEventBuilder()
        long_value = "x" * 200  # 200 chars
        
        event = builder.tool_executing(
            tool_name="process_data",
            tool_index=1,
            tool_total=1,
            step_number=1,
            arguments={"data": long_value},
        )
        
        event_dict = event.to_dict()
        arg_value = event_dict["arguments"]["data"]
        
        # Should be truncated to ~100 chars + "..."
        assert len(arg_value) < len(long_value)
        assert arg_value.endswith("...")
    
    def test_tool_result_truncates_preview(self):
        """Result preview should be truncated."""
        builder = HeadlessEventBuilder()
        long_preview = "y" * 1000
        
        event = builder.tool_result(
            tool_name="get_data",
            step_number=1,
            success=True,
            result_preview=long_preview,
        )
        
        event_dict = event.to_dict()
        preview = event_dict["result_preview"]
        
        # Should be truncated to 500 chars
        assert len(preview) <= 500
