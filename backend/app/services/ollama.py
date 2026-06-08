"""Ollama client service for LLM completions.

Task C1: HTTP client pooling for reduced connection churn and improved latency.
Task C3: Tool-call protocol normalizer hardening with telemetry.
"""
import asyncio
import httpx
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple
from app.core.config import settings

logger = logging.getLogger(__name__)


# ==============================================================================
# Task C3: Tool-Call Parser Telemetry
# ==============================================================================

@dataclass
class ToolCallParserMetrics:
    """
    Telemetry counters for tool-call fallback parser usage.
    
    Task C3: Track which parsing paths are used to identify model behavior patterns.
    """
    # Native tool_calls field used (preferred)
    native_tool_calls: int = 0
    
    # Fallback parsers used
    tagged_xml_parsed: int = 0  # <tool_call>...</tool_call>
    prefixed_json_parsed: int = 0  # tool_name {...}
    raw_json_object_parsed: int = 0  # {"name": ..., "arguments": ...}
    raw_json_tool_calls_array: int = 0  # {"tool_calls": [...]}
    embedded_json_extracted: int = 0  # JSON found in text
    
    # Validation failures
    schema_validation_rejected: int = 0  # Parsed but failed validation
    json_parse_failed: int = 0  # JSON parsing failed
    
    # Text responses (no tool call detected)
    text_responses: int = 0
    
    def to_dict(self) -> Dict[str, int]:
        """Return metrics as dict for logging/export."""
        return {
            "native_tool_calls": self.native_tool_calls,
            "tagged_xml_parsed": self.tagged_xml_parsed,
            "prefixed_json_parsed": self.prefixed_json_parsed,
            "raw_json_object_parsed": self.raw_json_object_parsed,
            "raw_json_tool_calls_array": self.raw_json_tool_calls_array,
            "embedded_json_extracted": self.embedded_json_extracted,
            "schema_validation_rejected": self.schema_validation_rejected,
            "json_parse_failed": self.json_parse_failed,
            "text_responses": self.text_responses,
        }


# Global telemetry instance
_parser_metrics = ToolCallParserMetrics()


def get_parser_metrics() -> ToolCallParserMetrics:
    """Get the global parser metrics instance."""
    return _parser_metrics


def reset_parser_metrics() -> None:
    """Reset parser metrics (useful for testing)."""
    global _parser_metrics
    _parser_metrics = ToolCallParserMetrics()


# ==============================================================================
# Task C1: Shared HTTP Client Pool
# ==============================================================================

class OllamaHTTPClientPool:
    """
    Manages a shared httpx.AsyncClient for Ollama requests.
    
    Benefits:
    - Connection reuse (HTTP keep-alive)
    - Reduced TCP handshake overhead
    - Connection pooling across concurrent requests
    
    Lifecycle:
    - Call startup() on app startup
    - Call shutdown() on app shutdown
    """
    
    _instance: Optional["OllamaHTTPClientPool"] = None
    
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._default_timeout = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "60"))
        # Metrics for observability
        self._request_count = 0
        self._connection_reuse_count = 0
        # Task C1 fix: Lock to prevent race condition during concurrent first-use
        self._startup_lock = asyncio.Lock()
    
    @classmethod
    def get_instance(cls) -> "OllamaHTTPClientPool":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    async def startup(self) -> None:
        """Initialize the HTTP client pool. Call on app startup."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._default_timeout, connect=10.0),
                limits=httpx.Limits(
                    max_keepalive_connections=5,
                    max_connections=10,
                    keepalive_expiry=30.0,
                ),
            )
            logger.info("OllamaHTTPClientPool started", extra={
                "default_timeout": self._default_timeout,
                "max_connections": 10,
            })
    
    async def shutdown(self) -> None:
        """Close the HTTP client pool. Call on app shutdown."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            logger.info("OllamaHTTPClientPool shutdown", extra={
                "total_requests": self._request_count,
                "connection_reuses": self._connection_reuse_count,
            })
            self._client = None
    
    async def get_client(self) -> httpx.AsyncClient:
        """
        Get the shared HTTP client.
        
        Auto-initializes if not started (for backward compatibility).
        Uses double-check locking to prevent race condition under concurrent first-use.
        """
        # Fast path: client already initialized
        if self._client is not None and not self._client.is_closed:
            self._connection_reuse_count += 1 if self._request_count > 0 else 0
            self._request_count += 1
            return self._client
        
        # Slow path: acquire lock for initialization
        async with self._startup_lock:
            # Double-check after acquiring lock
            if self._client is None or self._client.is_closed:
                await self.startup()
        
        self._connection_reuse_count += 1 if self._request_count > 0 else 0
        self._request_count += 1
        return self._client
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get client pool metrics."""
        return {
            "total_requests": self._request_count,
            "connection_reuses": self._connection_reuse_count,
            "is_active": self._client is not None and not self._client.is_closed,
        }


# Module-level convenience functions for lifecycle management
async def startup_ollama_client_pool() -> None:
    """Initialize the shared Ollama HTTP client pool."""
    await OllamaHTTPClientPool.get_instance().startup()


async def shutdown_ollama_client_pool() -> None:
    """Shutdown the shared Ollama HTTP client pool."""
    await OllamaHTTPClientPool.get_instance().shutdown()


# ==============================================================================
# Ollama Client
# ==============================================================================

class OllamaError(Exception):
    """Ollama service error."""
    pass


class OllamaClient:
    """Client for interacting with the configured LLM API.
    
    Supports two modes:
    - `USE_API_KEY=false` (default): Ollama endpoint (`OLLAMA_URL`)
    - `USE_API_KEY=true`: Anthropic-compatible API endpoint
      (`ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN`)

    Task C1: Uses shared HTTP client pool for connection reuse.
    """

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None):
        """
        Initialize Ollama client.
        
        Args:
            http_client: Optional explicit HTTP client. If not provided,
                        uses the shared pool.
        """
        self.use_api_key = bool(settings.use_api_key)
        self.base_url = (
            settings.anthropic_base_url if self.use_api_key else settings.ollama_url
        ).rstrip("/")
        self.auth_token = settings.anthropic_auth_token if self.use_api_key else ""
        self.default_model = (
            os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
            if self.use_api_key
            else os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:32b")
        )
        self._explicit_client = http_client
        self._pool = OllamaHTTPClientPool.get_instance()

    def _api_headers(self) -> Dict[str, str]:
        """Auth headers for API-key mode."""
        if not self.use_api_key:
            return {}
        token = self.auth_token
        return {
            "Authorization": f"Bearer {token}",
            "x-api-key": token,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _extract_text_content(content: Any) -> str:
        """
        Extract plain text from model message content.

        Handles:
        - plain string content
        - OpenAI/Anthropic-style block arrays
        """
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict):
                    # OpenAI-like structured block
                    if isinstance(item.get("text"), str):
                        parts.append(item["text"])
                    # Anthropic block format
                    elif item.get("type") == "text" and isinstance(item.get("text"), str):
                        parts.append(item["text"])
            return "".join(parts).strip()
        return ""
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get HTTP client - explicit client or shared pool."""
        if self._explicit_client is not None:
            return self._explicit_client
        return await self._pool.get_client()

    async def check_connection(self) -> bool:
        """Check if configured LLM service is reachable."""
        try:
            client = await self._get_client()
            if self.use_api_key:
                # For API key backend (Keystone), try /v1/models first
                # Fall back to /health if that doesn't exist
                try:
                    response = await client.get(
                        f"{self.base_url}/v1/models",
                        headers=self._api_headers(),
                        timeout=5.0,
                    )
                    return response.status_code == 200
                except:
                    # Fallback: try a health endpoint or just check connectivity
                    try:
                        response = await client.get(
                            f"{self.base_url}/health",
                            headers=self._api_headers(),
                            timeout=5.0,
                        )
                        return response.status_code == 200
                    except:
                        # If neither endpoint exists, just verify we can reach the server
                        # by trying to connect (will raise if unreachable)
                        response = await client.head(
                            self.base_url,
                            headers=self._api_headers(),
                            timeout=5.0,
                        )
                        return response.status_code in (200, 404, 405)
            else:
                response = await client.get(f"{self.base_url}/api/tags", timeout=5.0)
                return response.status_code == 200
        except Exception as e:
            provider = "API key backend" if self.use_api_key else "Ollama"
            print(f"{provider} connection failed: {e}")
            return False

    async def list_models(self) -> List[str]:
        """List available models from configured LLM backend."""
        try:
            client = await self._get_client()
            if self.use_api_key:
                response = await client.get(
                    f"{self.base_url}/v1/models",
                    headers=self._api_headers(),
                    timeout=10.0,
                )
                response.raise_for_status()
                data = response.json()
                # OpenAI-compatible shape: {"data": [{"id": "..."}]}
                if isinstance(data, dict) and isinstance(data.get("data"), list):
                    return [
                        m.get("id")
                        for m in data["data"]
                        if isinstance(m, dict) and isinstance(m.get("id"), str)
                    ]
                # Fallback shape: [{"id": "..."}]
                if isinstance(data, list):
                    return [
                        m.get("id")
                        for m in data
                        if isinstance(m, dict) and isinstance(m.get("id"), str)
                    ]
                return []

            response = await client.get(f"{self.base_url}/api/tags", timeout=10.0)
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
        Generate a chat completion from the configured LLM backend.

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
            client = await self._get_client()
            if self.use_api_key:
                url = f"{self.base_url}/v1/chat/completions"
                payload = {
                    "model": model_name,
                    "messages": messages,
                    "stream": False,
                }
                headers = self._api_headers()

                logger.debug(
                    "Making API request",
                    extra={
                        "url": url,
                        "model": model_name,
                        "headers": {k: v[:20] + '...' if len(str(v)) > 20 else v for k, v in headers.items()},
                        "message_count": len(messages),
                    }
                )

                response = await client.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=60.0,
                )
            else:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": model_name,
                        "messages": messages,
                        "stream": False,
                        "keep_alive": keep_alive,
                    },
                    timeout=60.0,
                )

            if response.status_code == 404:
                # Log the full response for debugging
                try:
                    error_detail = response.json()
                except:
                    error_detail = response.text

                logger.error(
                    f"API returned 404 for model",
                    extra={
                        "model": model_name,
                        "endpoint": f"{self.base_url}/v1/chat/completions" if self.use_api_key else f"{self.base_url}/api/chat",
                        "response_status": response.status_code,
                        "response_body": error_detail,
                        "use_api_key": self.use_api_key,
                        "base_url": self.base_url,
                    }
                )

                if self.use_api_key:
                    raise OllamaError(f"Model '{model_name}' not found on API backend")
                raise OllamaError(
                    f"Model '{model_name}' not found. "
                    f"Pull it with: docker exec infrastructure-ollama-1 ollama pull {model_name}"
                )

            response.raise_for_status()

            response.raise_for_status()
            data = response.json()

            # Extract assistant text across both response formats
            if self.use_api_key:
                choices = data.get("choices", [])
                first_choice = choices[0] if choices else {}
                message_obj = first_choice.get("message", {}) if isinstance(first_choice, dict) else {}
                assistant_message = self._extract_text_content(message_obj.get("content"))
            else:
                assistant_message = self._extract_text_content(
                    data.get("message", {}).get("content", "")
                )

            if not assistant_message:
                raise OllamaError("Empty response from model service")

            return assistant_message

        except httpx.TimeoutException:
            raise OllamaError("LLM request timed out")
        except httpx.ConnectError:
            raise OllamaError("Cannot connect to model service")
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in (401, 403):
                raise OllamaError("Authentication failed for API backend token")
            # Log response body for debugging 400 errors
            try:
                error_body = e.response.text
                logger.error(f"LLM HTTP {status} error response: {error_body[:500]}")
            except Exception:
                pass
            raise OllamaError(f"LLM HTTP error: {status}")
        except Exception as e:
            if isinstance(e, OllamaError):
                raise
            raise OllamaError(f"LLM request failed: {str(e)}")

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
        
        # Get tool names for validation (Task C3)
        valid_tool_names = set()
        if tools:
            for tool in tools:
                if isinstance(tool, dict) and "function" in tool:
                    fn = tool["function"]
                    if isinstance(fn, dict) and "name" in fn:
                        valid_tool_names.add(fn["name"])

        try:
            client = await self._get_client()
            if self.use_api_key:
                # OpenAI-compatible tool-calling path.
                api_payload: Dict[str, Any] = {
                    "model": model_name,
                    "messages": messages,
                    "stream": False,
                }
                if tools:
                    api_payload["tools"] = tools
                    api_payload["tool_choice"] = "auto"

                response = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    headers=self._api_headers(),
                    json=api_payload,
                    timeout=60.0,
                )

                if response.status_code == 404:
                    raise OllamaError(f"Model '{model_name}' not found on API backend")

                response.raise_for_status()
                data = response.json()

                choices = data.get("choices", [])
                first_choice = choices[0] if choices else {}
                message = first_choice.get("message", {}) if isinstance(first_choice, dict) else {}
                if not isinstance(message, dict):
                    message = {}

                tool_calls = message.get("tool_calls") or []
                if tool_calls:
                    return {
                        "type": "tool_calls",
                        "tool_calls": tool_calls,
                    }

                content = self._extract_text_content(message.get("content"))
                if not content:
                    raise OllamaError("Empty response from model service")
                return {
                    "type": "text",
                    "content": content,
                }

            response = await client.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=60.0,
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
            
            def _validate_tool_call_schema(tc: Dict[str, Any]) -> bool:
                """
                Task C3: Strict schema validation for tool calls.
                
                Returns True only if:
                - name is a non-empty string
                - arguments is present (dict or string)
                - name matches a known tool if validation enabled
                """
                if not isinstance(tc, dict):
                    return False
                
                name = tc.get("name")
                if not isinstance(name, str) or not name.strip():
                    return False
                
                # Validate name matches known tools (if tools provided)
                if valid_tool_names and name not in valid_tool_names:
                    logger.debug(
                        f"Tool call rejected: unknown tool name '{name}'",
                        extra={"known_tools": list(valid_tool_names)},
                    )
                    _parser_metrics.schema_validation_rejected += 1
                    return False
                
                # arguments must be present
                if "arguments" not in tc:
                    return False
                
                return True

            # ================================================================
            # Task C3: Prioritized tool-call parsing with telemetry
            # Priority: native tool_calls > tagged XML > prefixed JSON > raw JSON
            # ================================================================
            
            # PRIORITY 1: Native tool_calls field (preferred, with schema validation)
            if "tool_calls" in message and message["tool_calls"]:
                # Task C3 fix: Validate native tool_calls against known tools
                validated_tool_calls = []
                for tc in message["tool_calls"]:
                    # P1 fix: Guard against malformed non-dict entries (string/null)
                    if not isinstance(tc, dict):
                        logger.warning(
                            f"Native tool_call entry is not a dict, skipping: {type(tc).__name__}",
                            extra={"malformed_entry": tc},
                        )
                        continue
                    
                    # Extract name from native format: {"function": {"name": ..., "arguments": ...}}
                    func_data = tc.get("function", {})
                    if not isinstance(func_data, dict):
                        logger.warning(
                            f"Native tool_call.function is not a dict, skipping",
                            extra={"func_data": func_data},
                        )
                        continue
                    
                    tc_name = func_data.get("name")
                    tc_args = func_data.get("arguments", {})
                    
                    # Build internal schema for validation
                    internal_tc = {"name": tc_name, "arguments": tc_args}
                    if _validate_tool_call_schema(internal_tc):
                        validated_tool_calls.append(tc)
                    else:
                        logger.warning(
                            f"Native tool_call rejected by schema validation: {tc_name}",
                            extra={"tool_call": tc},
                        )
                
                if validated_tool_calls:
                    _parser_metrics.native_tool_calls += 1
                    logger.info(
                        "Using native tool_calls field (preferred)",
                        extra={"count": len(validated_tool_calls), "original_count": len(message["tool_calls"])},
                    )
                    return {
                        "type": "tool_calls",
                        "tool_calls": validated_tool_calls
                    }
                # All native tool_calls rejected - fall through to content parsing
            
            # No native tool_calls - check content for fallback parsing
            content = message.get("content", "")
            if not content:
                raise OllamaError("Empty response from Ollama")
            
            # PRIORITY 2: Tagged XML tool calls (Qwen templates)
            tagged_tool_calls = []
            for pattern in [
                r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
                r"<\|tool_call_start\|>\s*(\{.*?\})\s*<\|tool_call_end\|>",
            ]:
                for match in re.finditer(pattern, content, flags=re.DOTALL):
                    try:
                        parsed = json.loads(match.group(1))
                        if _validate_tool_call_schema(parsed):
                            tagged_tool_calls.append(
                                _build_tool_call(
                                    name=parsed["name"],
                                    arguments=parsed["arguments"],
                                )
                            )
                    except json.JSONDecodeError:
                        _parser_metrics.json_parse_failed += 1
                        continue

            if tagged_tool_calls:
                _parser_metrics.tagged_xml_parsed += 1
                logger.info(
                    "Detected tagged tool calls in text content (fallback)",
                    extra={"count": len(tagged_tool_calls), "parser": "tagged_xml"},
                )
                return {"type": "tool_calls", "tool_calls": tagged_tool_calls}

            # PRIORITY 3: Prefixed JSON format (tool_name {json})
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
                        tc = {"name": prefixed_tool_name, "arguments": prefixed_args}
                        if _validate_tool_call_schema(tc):
                            _parser_metrics.prefixed_json_parsed += 1
                            logger.info(
                                "Detected tool call in prefixed text format (fallback)",
                                extra={"tool_name": prefixed_tool_name, "parser": "prefixed_json"},
                            )
                            return {
                                "type": "tool_calls",
                                "tool_calls": [
                                    _build_tool_call(prefixed_tool_name, prefixed_args)
                                ],
                            }
                except json.JSONDecodeError:
                    _parser_metrics.json_parse_failed += 1

            # PRIORITY 4: Raw JSON content
            try:
                parsed_content = json.loads(content)
                if isinstance(parsed_content, dict):
                    # 4a: tool_calls array in JSON
                    if "tool_calls" in parsed_content and isinstance(parsed_content["tool_calls"], list):
                        normalized = []
                        for tc in parsed_content["tool_calls"]:
                            if _validate_tool_call_schema(tc):
                                normalized.append(_build_tool_call(tc["name"], tc["arguments"]))
                        if normalized:
                            _parser_metrics.raw_json_tool_calls_array += 1
                            logger.info(
                                "Detected tool_calls array in JSON text content (fallback)",
                                extra={"count": len(normalized), "parser": "json_array"},
                            )
                            return {"type": "tool_calls", "tool_calls": normalized}
                    
                    # 4b: Single JSON tool call object
                    elif "name" in parsed_content and "arguments" in parsed_content:
                        if _validate_tool_call_schema(parsed_content):
                            _parser_metrics.raw_json_object_parsed += 1
                            logger.info(
                                "Detected single JSON tool call in text content (fallback)",
                                extra={"tool_name": parsed_content.get("name"), "parser": "json_object"},
                            )
                            return {
                                "type": "tool_calls",
                                "tool_calls": [
                                    _build_tool_call(parsed_content["name"], parsed_content["arguments"])
                                ],
                            }
            except json.JSONDecodeError:
                pass

            # PRIORITY 5: Embedded JSON in text (last resort)
            if "name" in content and "arguments" in content:
                json_start = content.find("{")
                if json_start != -1:
                    for json_end in range(len(content), json_start, -1):
                        json_candidate = content[json_start:json_end].strip()
                        if json_candidate.endswith("}"):
                            try:
                                tool_call_data = json.loads(json_candidate)
                                if _validate_tool_call_schema(tool_call_data):
                                    _parser_metrics.embedded_json_extracted += 1
                                    logger.info(
                                        "Detected embedded JSON tool call in text (fallback)",
                                        extra={
                                            "tool_name": tool_call_data.get("name"),
                                            "json_start_pos": json_start,
                                            "parser": "embedded_json",
                                        }
                                    )
                                    return {
                                        "type": "tool_calls",
                                        "tool_calls": [
                                            _build_tool_call(
                                                tool_call_data["name"],
                                                tool_call_data["arguments"],
                                                call_id=f"call_{id(tool_call_data)}",
                                            )
                                        ]
                                    }
                            except json.JSONDecodeError:
                                _parser_metrics.json_parse_failed += 1
                                continue

            # No tool calls detected - return text response
            _parser_metrics.text_responses += 1
            return {
                "type": "text",
                "content": content
            }

        except httpx.TimeoutException:
            raise OllamaError("LLM request timed out")
        except httpx.ConnectError:
            raise OllamaError("Cannot connect to model service")
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in (401, 403):
                raise OllamaError("Authentication failed for API backend token")
            # Log response body for debugging 400 errors
            try:
                error_body = e.response.text
                logger.error(f"LLM HTTP {status} error response: {error_body[:500]}")
            except Exception:
                pass
            raise OllamaError(f"LLM HTTP error: {status}")
        except Exception as e:
            if isinstance(e, OllamaError):
                raise
            raise OllamaError(f"LLM request failed: {str(e)}")


# Backward compatibility
async def check_ollama_connection() -> bool:
    """Check if configured LLM service is reachable."""
    client = OllamaClient()
    return await client.check_connection()
