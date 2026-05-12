"""Ollama client service for LLM completions."""
import httpx
import json
import logging
import re
import time
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

                def _normalize_arguments(arguments: Any) -> Any:
                    """Best-effort normalization of tool arguments."""
                    if isinstance(arguments, str):
                        try:
                            parsed = json.loads(arguments)
                            return parsed if isinstance(parsed, dict) else arguments
                        except json.JSONDecodeError:
                            return arguments
                    return arguments

                def _build_tool_call(name: str, arguments: Any, call_id: Optional[str] = None) -> Dict[str, Any]:
                    """Convert tool call data to OpenAI-compatible format."""
                    return {
                        "id": call_id or f"call_{int(time.time() * 1000)}",
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": _normalize_arguments(arguments),
                        }
                    }

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

                    # Some Qwen templates may emit tool calls as tagged text blocks.
                    tagged_tool_calls = []
                    for pattern in [
                        r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
                        r"<\|tool_call_start\|>\s*(\{.*?\})\s*<\|tool_call_end\|>",
                    ]:
                        for match in re.finditer(pattern, content, flags=re.DOTALL):
                            try:
                                parsed = json.loads(match.group(1))
                                if "name" in parsed and "arguments" in parsed:
                                    tagged_tool_calls.append(
                                        _build_tool_call(
                                            name=parsed["name"],
                                            arguments=parsed["arguments"],
                                        )
                                    )
                            except json.JSONDecodeError:
                                continue

                    if tagged_tool_calls:
                        logger.info(
                            "Detected tagged tool calls in text content",
                            extra={"count": len(tagged_tool_calls)},
                        )
                        return {"type": "tool_calls", "tool_calls": tagged_tool_calls}

                    # Some models emit tool calls as: <tool_name> { ...json args... }
                    # Example: create_club {"name":"X","country":"GB",...}
                    prefixed_match = re.match(
                        r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s+(\{.*\})\s*$",
                        content,
                        flags=re.DOTALL,
                    )
                    if prefixed_match:
                        prefixed_tool_name = prefixed_match.group(1)
                        prefixed_args_raw = prefixed_match.group(2)
                        try:
                            prefixed_args = json.loads(prefixed_args_raw)
                            if isinstance(prefixed_args, dict):
                                logger.info(
                                    "Detected tool call in prefixed text format",
                                    extra={"tool_name": prefixed_tool_name},
                                )
                                return {
                                    "type": "tool_calls",
                                    "tool_calls": [
                                        _build_tool_call(prefixed_tool_name, prefixed_args)
                                    ],
                                }
                        except json.JSONDecodeError:
                            pass

                    # Some model responses are raw JSON in content.
                    try:
                        parsed_content = json.loads(content)
                        if isinstance(parsed_content, dict):
                            if "tool_calls" in parsed_content and isinstance(parsed_content["tool_calls"], list):
                                normalized = []
                                for tc in parsed_content["tool_calls"]:
                                    if isinstance(tc, dict) and "name" in tc and "arguments" in tc:
                                        normalized.append(_build_tool_call(tc["name"], tc["arguments"]))
                                if normalized:
                                    logger.info(
                                        "Detected tool_calls array in JSON text content",
                                        extra={"count": len(normalized)},
                                    )
                                    return {"type": "tool_calls", "tool_calls": normalized}
                            elif "name" in parsed_content and "arguments" in parsed_content:
                                logger.info(
                                    "Detected single JSON tool call in text content",
                                    extra={"tool_name": parsed_content.get("name")},
                                )
                                return {
                                    "type": "tool_calls",
                                    "tool_calls": [
                                        _build_tool_call(parsed_content["name"], parsed_content["arguments"])
                                    ],
                                }
                    except json.JSONDecodeError:
                        pass

                    # Try to detect and parse JSON tool calls from content
                    # Some models (like qwen2.5-coder) may return tool calls as JSON text
                    # Look for JSON anywhere in the content, not just at the start
                    if "name" in content and "arguments" in content:
                        # Try to find and extract JSON object
                        # Find the first { and try to parse from there
                        json_start = content.find("{")
                        if json_start != -1:
                            # Try to extract complete JSON object
                            for json_end in range(len(content), json_start, -1):
                                json_candidate = content[json_start:json_end].strip()
                                if json_candidate.endswith("}"):
                                    try:
                                        tool_call_data = json.loads(json_candidate)
                                        if "name" in tool_call_data and "arguments" in tool_call_data:
                                            logger.info(
                                                "Detected JSON tool call in text content, converting to tool_calls format",
                                                extra={
                                                    "tool_name": tool_call_data.get("name"),
                                                    "json_start_pos": json_start,
                                                    "had_prefix_text": json_start > 0
                                                }
                                            )

                                            # Ensure arguments is a dict (might be string or dict)
                                            arguments = tool_call_data["arguments"]

                                            # Convert to OpenAI-compatible format
                                            return {
                                                "type": "tool_calls",
                                                "tool_calls": [
                                                    _build_tool_call(
                                                        tool_call_data["name"],
                                                        arguments,
                                                        call_id=f"call_{id(tool_call_data)}",
                                                    )
                                                ]
                                            }
                                    except json.JSONDecodeError:
                                        # Try next position
                                        continue

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
