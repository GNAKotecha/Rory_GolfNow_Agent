import os
import pytest
from app.core.langfuse_config import LangfuseConfig


@pytest.fixture
def mock_langfuse_env(monkeypatch):
    """Set up mock environment variables for Langfuse."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "mock_public_key")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "mock_secret_key")
    monkeypatch.setenv("LANGFUSE_HOST", "http://localhost:3000")
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")


def test_get_callback_handler_returns_handler(mock_langfuse_env):
    """Should create callback handler with metadata."""
    handler = LangfuseConfig.get_callback_handler(
        user_id="test_user",
        session_id="test_session",
        trace_name="test_workflow"
    )

    assert handler is not None
    # Verify handler is a CallbackHandler instance
    from langfuse.callback import CallbackHandler
    assert isinstance(handler, CallbackHandler)


def test_get_callback_handler_returns_none_when_disabled(monkeypatch):
    """Should return None when Langfuse is disabled."""
    monkeypatch.setenv("LANGFUSE_ENABLED", "false")
    handler = LangfuseConfig.get_callback_handler()
    assert handler is None