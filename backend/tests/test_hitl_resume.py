"""Tests for HITL resume functionality.

Tests the user_response WebSocket flow and token persistence.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.services.headless_events import (
    HeadlessEventBuilder,
    HeadlessEventType,
    AskUserReason,
    RemediationOption,
    InMemoryResumeTokenStore,
    ResumeTokenStore,
    get_default_token_store,
    set_default_token_store,
    validate_user_response,
    UserResponse,
    UserResponseValidationResult,
)


class TestUserResponseValidation:
    """Tests for validate_user_response function."""
    
    @pytest.fixture
    def token_store(self):
        """Create a fresh token store for each test."""
        return InMemoryResumeTokenStore()
    
    @pytest.mark.asyncio
    async def test_missing_resume_token_returns_error(self, token_store):
        """user_response without resume_token returns error."""
        data = {
            "type": "user_response",
            "session_id": 1,
            # No resume_token
        }
        
        result = await validate_user_response(data, token_store)
        
        assert not result.valid
        assert result.error_type == "missing_token"
        assert "resume_token" in result.error.lower()
        assert result.remediation_options is not None
    
    @pytest.mark.asyncio
    async def test_invalid_token_returns_error(self, token_store):
        """user_response with invalid/unknown token returns error."""
        data = {
            "type": "user_response",
            "session_id": 1,
            "resume_token": "nonexistent-token-uuid",
        }
        
        result = await validate_user_response(data, token_store)
        
        assert not result.valid
        assert result.error_type == "invalid_token"
        assert "invalid" in result.error.lower() or "expired" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_expired_token_returns_error(self, token_store):
        """user_response with expired token returns error."""
        # Store token with 0 TTL (immediate expiry)
        token = "test-expired-token"
        await token_store.store(token, {"run_id": "test-run"}, ttl_seconds=0)
        
        # Wait a tiny bit to ensure expiry
        await asyncio.sleep(0.01)
        
        data = {
            "type": "user_response",
            "session_id": 1,
            "resume_token": token,
        }
        
        result = await validate_user_response(data, token_store)
        
        assert not result.valid
        assert result.error_type == "invalid_token"
    
    @pytest.mark.asyncio
    async def test_run_id_mismatch_returns_error(self, token_store):
        """user_response with mismatched run_id is rejected."""
        token = "test-token"
        await token_store.store(token, {"run_id": "original-run-id"}, ttl_seconds=3600)
        
        data = {
            "type": "user_response",
            "session_id": 1,
            "resume_token": token,
            "run_id": "different-run-id",  # Mismatched!
        }
        
        result = await validate_user_response(data, token_store)
        
        assert not result.valid
        assert result.error_type == "run_id_mismatch"
        assert "mismatch" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_valid_token_returns_success(self, token_store):
        """user_response with valid token returns success with context."""
        token = "valid-token"
        context = {
            "run_id": "test-run-id",
            "reason": "auth_required",
            "step_number": 3,
            "context": {"tool_name": "test_tool"},
        }
        await token_store.store(token, context, ttl_seconds=3600)
        
        data = {
            "type": "user_response",
            "session_id": 1,
            "resume_token": token,
            "run_id": "test-run-id",  # Matches token context
            "selected_option_id": "provide_credentials",
        }
        
        result = await validate_user_response(data, token_store)
        
        assert result.valid
        assert result.error is None
        assert result.token_context is not None
        assert result.token_context["run_id"] == "test-run-id"
        assert result.token_context["reason"] == "auth_required"
    
    @pytest.mark.asyncio
    async def test_valid_token_without_request_run_id(self, token_store):
        """user_response without run_id in request is valid (uses token's run_id)."""
        token = "valid-token"
        context = {"run_id": "test-run-id", "reason": "semantic_error"}
        await token_store.store(token, context, ttl_seconds=3600)
        
        data = {
            "type": "user_response",
            "session_id": 1,
            "resume_token": token,
            # No run_id - that's OK, we use token's run_id
        }
        
        result = await validate_user_response(data, token_store)
        
        assert result.valid
        assert result.token_context["run_id"] == "test-run-id"


class TestTokenStorePersistence:
    """Tests for token store persistence through HeadlessEventBuilder."""
    
    @pytest.mark.asyncio
    async def test_ask_user_creates_token(self):
        """ask_user event creates a resume token."""
        store = InMemoryResumeTokenStore()
        builder = HeadlessEventBuilder(run_id="test-run", token_store=store)
        
        event = builder.ask_user(
            reason=AskUserReason.AUTH_REQUIRED,
            title="Auth Needed",
            message="Please authenticate",
            step_number=1,
        )
        
        # Token should be in payload
        resume_token = event.payload.get("resume_token")
        assert resume_token is not None
        
        # Token should be stored in-memory
        assert resume_token in builder._pending_resume_tokens
    
    @pytest.mark.asyncio
    async def test_persist_resume_token_stores_durably(self):
        """persist_resume_token stores token in durable store."""
        store = InMemoryResumeTokenStore()
        builder = HeadlessEventBuilder(run_id="test-run", token_store=store)
        
        event = builder.ask_user(
            reason=AskUserReason.VALIDATION_FAILED,
            title="Validation Error",
            message="Invalid input",
            step_number=2,
        )
        
        resume_token = event.payload.get("resume_token")
        
        # Persist to durable store
        await builder.persist_resume_token(resume_token)
        
        # Should be retrievable from store
        context = await store.get(resume_token)
        assert context is not None
        assert context["run_id"] == "test-run"
        assert context["reason"] == "validation_failed"
    
    @pytest.mark.asyncio
    async def test_consume_token_removes_from_store(self):
        """Consuming a token removes it from the store."""
        store = InMemoryResumeTokenStore()
        token = "test-token"
        await store.store(token, {"run_id": "test-run"}, ttl_seconds=3600)
        
        # First consume returns context
        context = await store.consume(token)
        assert context is not None
        assert context["run_id"] == "test-run"
        
        # Second consume returns None (token is gone)
        context2 = await store.consume(token)
        assert context2 is None
    
    @pytest.mark.asyncio
    async def test_token_context_includes_step_info(self):
        """Token context includes step number and reason."""
        store = InMemoryResumeTokenStore()
        builder = HeadlessEventBuilder(run_id="run-123", token_store=store)
        
        event = builder.ask_user(
            reason=AskUserReason.RBAC_DENIED,
            title="Permission Denied",
            message="You don't have access",
            context={"tool_name": "admin_tool", "required_role": "admin"},
            step_number=5,
        )
        
        resume_token = event.payload.get("resume_token")
        await builder.persist_resume_token(resume_token)
        
        context = await store.get(resume_token)
        assert context["step_number"] == 5
        assert context["reason"] == "rbac_denied"
        assert context["context"]["tool_name"] == "admin_tool"


class TestPlanProgressEventContract:
    """Tests for plan_progress event contract compliance."""
    
    def test_plan_progress_includes_run_id(self):
        """plan_progress event includes run_id."""
        builder = HeadlessEventBuilder(run_id="plan-run-123")
        
        event = builder.plan_progress(
            progress=0.5,
            current_step=3,
            current_step_description="Execute query",
            verified=True,
        )
        
        event_dict = event.to_dict()
        
        assert event_dict["run_id"] == "plan-run-123"
        assert event_dict["type"] == "plan_progress"
    
    def test_plan_progress_includes_timestamp(self):
        """plan_progress event includes timestamp."""
        builder = HeadlessEventBuilder(run_id="plan-run-123")
        
        event = builder.plan_progress(progress=0.75)
        event_dict = event.to_dict()
        
        assert "timestamp" in event_dict
        # Should be ISO format
        datetime.fromisoformat(event_dict["timestamp"].replace("Z", "+00:00"))
    
    def test_plan_progress_includes_payload_fields(self):
        """plan_progress includes all expected payload fields."""
        builder = HeadlessEventBuilder(run_id="plan-run-123")
        
        event = builder.plan_progress(
            progress=0.6,
            current_step=4,
            current_step_description="Validate results",
            verified=True,
        )
        
        event_dict = event.to_dict()
        
        assert event_dict["progress"] == 0.6
        assert event_dict["current_step"] == "Validate results"
        assert event_dict["verified"] is True
        assert event_dict["step_number"] == 4
    
    def test_plan_progress_minimal_fields(self):
        """plan_progress works with just progress."""
        builder = HeadlessEventBuilder(run_id="plan-run-123")
        
        event = builder.plan_progress(progress=0.25)
        event_dict = event.to_dict()
        
        assert event_dict["progress"] == 0.25
        assert "run_id" in event_dict
        assert "timestamp" in event_dict
        assert "type" in event_dict


class TestUserResponsePayload:
    """Tests for UserResponse parsing and serialization."""
    
    def test_user_response_from_dict(self):
        """UserResponse parses from dictionary."""
        data = {
            "resume_token": "test-token",
            "selected_option_id": "retry",
            "input_values": {"api_key": "secret123"},
            "freeform_text": "Please try with this key",
        }
        
        response = UserResponse.from_dict(data)
        
        assert response.resume_token == "test-token"
        assert response.selected_option_id == "retry"
        assert response.input_values["api_key"] == "secret123"
        assert response.freeform_text == "Please try with this key"
    
    def test_user_response_to_dict(self):
        """UserResponse serializes to dictionary."""
        response = UserResponse(
            resume_token="test-token",
            selected_option_id="skip",
            input_values={},
            freeform_text=None,
        )
        
        data = response.to_dict()
        
        assert data["resume_token"] == "test-token"
        assert data["selected_option_id"] == "skip"
        assert "timestamp" in data
    
    def test_user_response_handles_missing_optional_fields(self):
        """UserResponse handles missing optional fields."""
        data = {
            "resume_token": "test-token",
            # No other fields
        }
        
        response = UserResponse.from_dict(data)
        
        assert response.resume_token == "test-token"
        assert response.selected_option_id is None
        assert response.input_values == {}
        assert response.freeform_text is None


class TestGlobalTokenStore:
    """Tests for global token store management."""
    
    def test_get_default_creates_store(self):
        """get_default_token_store creates store if not set."""
        # Reset global store
        import app.services.headless_events as he
        original = he._default_token_store
        he._default_token_store = None
        
        try:
            store = get_default_token_store()
            assert store is not None
            assert isinstance(store, InMemoryResumeTokenStore)
        finally:
            he._default_token_store = original
    
    def test_set_default_overrides_store(self):
        """set_default_token_store overrides the global store."""
        import app.services.headless_events as he
        original = he._default_token_store
        
        try:
            custom_store = InMemoryResumeTokenStore()
            set_default_token_store(custom_store)
            
            retrieved = get_default_token_store()
            assert retrieved is custom_store
        finally:
            he._default_token_store = original
