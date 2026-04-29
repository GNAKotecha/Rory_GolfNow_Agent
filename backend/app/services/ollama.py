"""Ollama client service for LLM completions."""
import httpx
import json
import logging
from typing import List, Dict, Optional, Any
from app.core.config import settings

logger = logging.getLogger(__name__)


class OllamaError(Exception):
    """Ollama service error."""
    pass


class OllamaClient:
    """Client for interacting with Ollama API."""

    def __init__(self):
        self.base_url = settings.ollama_url
        self.default_model = "qwen2.5-coder:32b"  # Code generation model

    async def check_connection(self) -> bool:
        """Check if Ollama service is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except Exception as e:
            print(f"Ollama connection failed: {e}")
            return False

    async def list_models(self) -> List[str]:
        """List available models."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
                return [model["name"] for model in data.get("models", [])]
        except Exception as e:
            raise OllamaError(f"Failed to list models: {e}")

    async def generate_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        stream: bool = False,
        keep_alive: str = "5m",
    ) -> str:
        """
        Generate a chat completion from Ollama.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name (defaults to self.default_model)
            stream: Whether to stream the response (not yet implemented)
            keep_alive: How long to keep model loaded (default: "5m")
                        Examples: "5m", "10m", "1h", "-1" (unload immediately)

        Returns:
            The assistant's response text

        Raises:
            OllamaError: If the request fails
        """
        if stream:
            raise NotImplementedError("Streaming not yet implemented")

        model_name = model or self.default_model

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": model_name,
                        "messages": messages,
                        "stream": False,
                        "keep_alive": keep_alive,
                    }
                )

                if response.status_code == 404:
                    raise OllamaError(
                        f"Model '{model_name}' not found. "
                        f"Pull it with: docker exec infrastructure-ollama-1 ollama pull {model_name}"
                    )

                response.raise_for_status()
                data = response.json()

                # Extract the assistant's message
                assistant_message = data.get("message", {}).get("content", "")

                if not assistant_message:
                    raise OllamaError("Empty response from Ollama")

                return assistant_message

        except httpx.TimeoutException:
            raise OllamaError("Ollama request timed out")
        except httpx.ConnectError:
            raise OllamaError("Cannot connect to Ollama service")
        except httpx.HTTPStatusError as e:
            raise OllamaError(f"Ollama HTTP error: {e.response.status_code}")
        except Exception as e:
            if isinstance(e, OllamaError):
                raise
            raise OllamaError(f"Ollama request failed: {str(e)}")

    async def generate_chat_completion_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        keep_alive: str = "5m",
    ) -> Dict[str, Any]:
        """
        Generate a chat completion with optional tool calling support.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional tool definitions in OpenAI/Ollama format
            model: Model name (defaults to self.default_model)
            keep_alive: How long to keep model loaded

        Returns:
            Dict containing either:
            - {"type": "text", "content": "response text"}
            - {"type": "tool_calls", "tool_calls": [...]}

        Raises:
            OllamaError: If the request fails
        """
        model_name = model or self.default_model

        payload = {
            "model": model_name,
            "messages": messages,
            "stream": False,
            "keep_alive": keep_alive,
        }

        # Add tools to payload if provided
        if tools:
            payload["tools"] = tools

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json=payload
                )

                if response.status_code == 404:
                    raise OllamaError(
                        f"Model '{model_name}' not found. "
                        f"Pull it with: docker exec infrastructure-ollama-1 ollama pull {model_name}"
                    )

                response.raise_for_status()
                data = response.json()

                # Debug logging to see raw Ollama response
                logger.info(
                    f"Ollama raw response",
                    extra={
                        "model": model_name,
                        "response_keys": list(data.keys()),
                        "message_keys": list(data.get("message", {}).keys()),
                        "message_content_preview": str(data.get("message", {}).get("content", ""))[:200],
                        "has_tool_calls": "tool_calls" in data.get("message", {}),
                    }
                )

                # Extract the assistant's message
                message = data.get("message", {})

                # Check if response contains tool calls
                if "tool_calls" in message and message["tool_calls"]:
                    return {
                        "type": "tool_calls",
                        "tool_calls": message["tool_calls"]
                    }
                else:
                    # Regular text response
                    content = message.get("content", "")
                    if not content:
                        raise OllamaError("Empty response from Ollama")

                    # Try to detect and parse JSON tool calls from content
                    # Some models (like qwen2.5-coder) may return tool calls as JSON text
                    content_stripped = content.strip()
                    if content_stripped.startswith("{") and "name" in content_stripped and "arguments" in content_stripped:
                        try:
                            tool_call_data = json.loads(content_stripped)
                            if "name" in tool_call_data and "arguments" in tool_call_data:
                                logger.info(
                                    "Detected JSON tool call in text content, converting to tool_calls format",
                                    extra={"tool_name": tool_call_data.get("name")}
                                )

                                # Ensure arguments is a dict (might be string or dict)
                                arguments = tool_call_data["arguments"]
                                if isinstance(arguments, str):
                                    try:
                                        arguments = json.loads(arguments)
                                    except json.JSONDecodeError:
                                        # Keep as string if not valid JSON
                                        pass

                                # Convert to OpenAI-compatible format
                                return {
                                    "type": "tool_calls",
                                    "tool_calls": [{
                                        "id": f"call_{id(tool_call_data)}",  # Generate unique ID
                                        "type": "function",
                                        "function": {
                                            "name": tool_call_data["name"],
                                            "arguments": arguments
                                        }
                                    }]
                                }
                        except json.JSONDecodeError:
                            # Not valid JSON, treat as regular text
                            pass

                    return {
                        "type": "text",
                        "content": content
                    }

        except httpx.TimeoutException:
            raise OllamaError("Ollama request timed out")
        except httpx.ConnectError:
            raise OllamaError("Cannot connect to Ollama service")
        except httpx.HTTPStatusError as e:
            raise OllamaError(f"Ollama HTTP error: {e.response.status_code}")
        except Exception as e:
            if isinstance(e, OllamaError):
                raise
            raise OllamaError(f"Ollama request failed: {str(e)}")


# Backward compatibility
async def check_ollama_connection() -> bool:
    """Check if Ollama service is reachable."""
    client = OllamaClient()
    return await client.check_connection()
