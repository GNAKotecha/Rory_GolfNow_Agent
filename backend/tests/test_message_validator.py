"""Tests for Ollama message validation."""
import pytest

from app.services.message_validator import (
    OllamaMessageValidator,
    MessageValidationError,
    ValidationResult,
    get_message_validator,
    reset_message_validator,
)


class TestMessageValidation:
    """Test message validation functionality."""

    @pytest.fixture(autouse=True)
    def reset(self):
        """Reset global message validator."""
        reset_message_validator()
        yield
        reset_message_validator()

    @pytest.fixture
    def validator(self):
        """Create message validator without DB."""
        return OllamaMessageValidator(db_session=None)

    def test_validate_valid_messages(self, validator):
        """Test validation of valid message list."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        result = validator.validate_messages(messages)

        assert result.valid is True
        assert len(result.errors) == 0
        assert len(result.sanitized_messages) == 3

    def test_validate_empty_messages(self, validator):
        """Test validation fails for empty messages."""
        result = validator.validate_messages([])

        assert result.valid is False
        assert any("empty" in e.lower() for e in result.errors)

    def test_validate_missing_role(self, validator):
        """Test validation fails for missing role."""
        messages = [
            {"content": "Hello!"},
        ]

        result = validator.validate_messages(messages)

        assert result.valid is False
        assert any("role" in e.lower() for e in result.errors)

    def test_validate_invalid_role(self, validator):
        """Test validation fails for invalid role."""
        messages = [
            {"role": "invalid_role", "content": "Hello!"},
        ]

        result = validator.validate_messages(messages)

        assert result.valid is False
        assert any("invalid role" in e.lower() for e in result.errors)

    def test_validate_empty_user_content(self, validator):
        """Test validation fails for empty user message content."""
        messages = [
            {"role": "user", "content": ""},
        ]

        result = validator.validate_messages(messages)

        assert result.valid is False
        assert any("empty content" in e.lower() for e in result.errors)

    def test_validate_none_user_content(self, validator):
        """Test validation fails for None user message content."""
        messages = [
            {"role": "user", "content": None},
        ]

        result = validator.validate_messages(messages)

        assert result.valid is False

    def test_validate_assistant_with_tool_calls(self, validator):
        """Test validation allows assistant message with tool_calls and empty content."""
        messages = [
            {"role": "user", "content": "Search for something"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "search"}}
                ],
            },
        ]

        result = validator.validate_messages(messages)

        assert result.valid is True
        assert len(result.sanitized_messages) == 2

    def test_validate_tool_message_without_id(self, validator):
        """Test validation fails for tool message without tool_call_id."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "tool", "content": "Result"},
        ]

        result = validator.validate_messages(messages)

        assert result.valid is False
        assert any("tool_call_id" in e.lower() for e in result.errors)

    def test_validate_tool_message_with_id(self, validator):
        """Test validation passes for tool message with tool_call_id."""
        messages = [
            {"role": "user", "content": "Search"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call_1", "function": {"name": "search"}}],
            },
            {
                "role": "tool",
                "content": "Results here",
                "tool_call_id": "call_1",
            },
        ]

        result = validator.validate_messages(messages)

        assert result.valid is True
        assert len(result.sanitized_messages) == 3

    def test_validate_no_user_message(self, validator):
        """Test validation fails when no user message present."""
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "assistant", "content": "Hi"},
        ]

        result = validator.validate_messages(messages)

        assert result.valid is False
        assert any("user message" in e.lower() for e in result.errors)

    def test_validate_preserves_tool_calls(self, validator):
        """Test that tool_calls are preserved in sanitized output."""
        tool_calls = [
            {"id": "call_1", "function": {"name": "search", "arguments": {}}}
        ]
        messages = [
            {"role": "user", "content": "Search"},
            {"role": "assistant", "content": "", "tool_calls": tool_calls},
        ]

        result = validator.validate_messages(messages)

        assert result.valid is True
        assistant_msg = result.sanitized_messages[1]
        assert assistant_msg["tool_calls"] == tool_calls

    def test_validate_sequence_warning_for_orphan_tool(self, validator):
        """Test warning when tool message has no matching call."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Let me search..."},
            {"role": "tool", "content": "Results", "tool_call_id": "orphan_id"},
            {"role": "user", "content": "Thanks"},
        ]

        result = validator.validate_messages(messages)

        # Should pass but with warning
        assert result.valid is True
        assert len(result.warnings) > 0
        assert any("no matching" in w.lower() for w in result.warnings)


class TestMessageValidatorEnsure:
    """Test ensure_valid_messages method."""

    @pytest.fixture
    def validator(self):
        return OllamaMessageValidator(db_session=None)

    def test_ensure_valid_returns_sanitized(self, validator):
        """Test ensure returns sanitized messages on success."""
        messages = [
            {"role": "user", "content": "Hello"},
        ]

        result = validator.ensure_valid_messages(messages)

        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_ensure_raises_on_invalid(self, validator):
        """Test ensure raises exception on invalid messages."""
        with pytest.raises(MessageValidationError) as exc_info:
            validator.ensure_valid_messages([])

        assert exc_info.value.error_type == "context_lost"

    def test_ensure_raises_with_recovery_hint(self, validator):
        """Test exception includes recovery hint when applicable."""
        # Without session_id, no recovery possible
        with pytest.raises(MessageValidationError) as exc_info:
            validator.ensure_valid_messages([], session_id=None)

        assert exc_info.value.recoverable is False

    def test_create_minimal_context(self, validator):
        """Test creating minimal valid context."""
        messages = validator.create_minimal_context(
            user_message="Hello",
            system_prompt="Be helpful",
        )

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "Be helpful"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Hello"

    def test_create_minimal_context_no_system(self, validator):
        """Test creating minimal context without system prompt."""
        messages = validator.create_minimal_context(
            user_message="Hello",
        )

        assert len(messages) == 1
        assert messages[0]["role"] == "user"


class TestFailedRunLogging:
    """Test failed run logging functionality."""

    @pytest.fixture
    def validator(self):
        return OllamaMessageValidator(db_session=None)

    def test_failed_run_logged(self, validator):
        """Test that failed validations are logged."""
        validator.validate_messages([], session_id=1, run_id="run-123")

        failed_runs = validator.get_failed_runs()
        assert len(failed_runs) >= 1
        assert any(r["run_id"] == "run-123" for r in failed_runs)

    def test_failed_run_log_limit(self, validator):
        """Test failed run log doesn't grow unbounded."""
        # Generate many failures
        for i in range(150):
            validator.validate_messages([], session_id=i, run_id=f"run-{i}")

        # Should be capped at 100
        failed_runs = validator.get_failed_runs(limit=200)
        assert len(failed_runs) <= 100

    def test_filter_failed_runs_by_session(self, validator):
        """Test filtering failed runs by session."""
        validator.validate_messages([], session_id=1, run_id="run-1")
        validator.validate_messages([], session_id=2, run_id="run-2")
        validator.validate_messages([], session_id=1, run_id="run-3")

        session_1_runs = validator.get_failed_runs(session_id=1)
        assert all(r["session_id"] == 1 for r in session_1_runs)


class TestGlobalMessageValidator:
    """Test global singleton message validator."""

    def test_singleton_pattern(self):
        """Test singleton creation and reset."""
        reset_message_validator()

        v1 = get_message_validator()
        v2 = get_message_validator()
        assert v1 is v2

        reset_message_validator()
        v3 = get_message_validator()
        assert v3 is not v1

    def test_db_session_injection(self):
        """Test injecting DB session returns new instance (thread-safe)."""
        reset_message_validator()

        v1 = get_message_validator()
        assert v1.db is None

        # With db_session, returns NEW instance (not singleton) for thread safety
        mock_db = object()
        v2 = get_message_validator(db_session=mock_db)
        assert v2 is not v1  # Different instance - thread-safe
        assert v2.db is mock_db
        assert v1.db is None  # Singleton unchanged
