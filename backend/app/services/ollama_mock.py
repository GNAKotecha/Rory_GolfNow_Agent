"""Mock Ollama client for deterministic testing."""
from typing import List, Dict


class MockOllamaClient:
    """
    Mock Ollama client that returns canned responses.

    Usage in tests:
        from app.services.ollama_mock import MockOllamaClient

        # Patch the real client
        ollama_client = MockOllamaClient()
        ollama_client.set_response("This is a test response")

        # Now API calls will return the mocked response
    """

    def __init__(self):
        self.base_url = "http://mock-ollama"
        self.default_model = "mock-model"
        self._response = "This is a mocked response."
        self._should_error = False
        self._error_message = "Mocked error"

    def set_response(self, response: str):
        """Set the canned response to return."""
        self._response = response

    def set_error(self, error_message: str):
        """Make the next call fail with an error."""
        self._should_error = True
        self._error_message = error_message

    def clear_error(self):
        """Clear error state."""
        self._should_error = False

    async def check_connection(self) -> bool:
        """Mock connection check."""
        return not self._should_error

    async def list_models(self) -> List[str]:
        """Mock model list."""
        if self._should_error:
            from app.services.ollama import OllamaError
            raise OllamaError(self._error_message)
        return ["mock-model-1", "mock-model-2"]

    async def generate_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        stream: bool = False,
    ) -> str:
        """Mock chat completion."""
        if self._should_error:
            from app.services.ollama import OllamaError
            raise OllamaError(self._error_message)

        # For deterministic testing, return the canned response
        return self._response


# Example test usage
"""
import pytest
from app.services.ollama_mock import MockOllamaClient
from app.api.ollama_compat import router
from fastapi.testclient import TestClient

def test_chat_with_mock():
    # Setup
    mock_client = MockOllamaClient()
    mock_client.set_response("This is a deterministic test response")

    # Inject mock (in real test, use dependency injection or monkeypatch)
    # Then call API
    response = client.post("/ollama/api/chat", json={
        "model": "mock",
        "messages": [{"role": "user", "content": "test"}],
        "stream": False
    })

    assert response.status_code == 200
    assert "deterministic test response" in response.json()["message"]["content"]
"""
