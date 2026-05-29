"""Headless/CLI-ready event contract for agent workflow streaming.

Task E1: Defines stable request/response event contract for headless/CLI mode.
Task E2: Adds structured HITL (Human-in-the-loop) payloads for ask_user scenarios.

All events include a run_id correlation field for multi-run reconciliation.

P1 Fix: ResumeTokenStore interface for durable token storage.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import uuid
import logging

logger = logging.getLogger(__name__)


class ResumeTokenStore(ABC):
    """Abstract interface for durable resume token storage.
    
    Default in-memory implementation is process-local. For hosted/distributed
    deployments, implement with Redis or similar backing store.
    """
    
    @abstractmethod
    async def store(self, token: str, context: Dict[str, Any], ttl_seconds: int = 3600) -> None:
        """Store a resume token with context.
        
        Args:
            token: Unique resume token
            context: Context dict to store (reason, step_number, etc.)
            ttl_seconds: Time-to-live in seconds (default 1 hour)
        """
        pass
    
    @abstractmethod
    async def get(self, token: str) -> Optional[Dict[str, Any]]:
        """Get context for a resume token without consuming it.
        
        Returns None if token doesn't exist or has expired.
        """
        pass
    
    @abstractmethod
    async def consume(self, token: str) -> Optional[Dict[str, Any]]:
        """Get and delete a resume token.
        
        Returns the context if token existed, None otherwise.
        """
        pass


class InMemoryResumeTokenStore(ResumeTokenStore):
    """In-memory implementation of ResumeTokenStore.
    
    WARNING: Tokens are lost on process restart. Use Redis-backed implementation
    for production hosted deployments.
    """
    
    def __init__(self):
        self._tokens: Dict[str, Dict[str, Any]] = {}
    
    async def store(self, token: str, context: Dict[str, Any], ttl_seconds: int = 3600) -> None:
        self._tokens[token] = {
            **context,
            "_expires_at": datetime.now(timezone.utc).timestamp() + ttl_seconds,
        }
    
    async def get(self, token: str) -> Optional[Dict[str, Any]]:
        data = self._tokens.get(token)
        if data is None:
            return None
        # Check expiry
        if data.get("_expires_at", 0) < datetime.now(timezone.utc).timestamp():
            del self._tokens[token]
            return None
        # Return without internal fields
        return {k: v for k, v in data.items() if not k.startswith("_")}
    
    async def consume(self, token: str) -> Optional[Dict[str, Any]]:
        data = self._tokens.pop(token, None)
        if data is None:
            return None
        # Check expiry
        if data.get("_expires_at", 0) < datetime.now(timezone.utc).timestamp():
            return None
        # Return without internal fields
        return {k: v for k, v in data.items() if not k.startswith("_")}


# Global default token store (can be replaced at startup with Redis-backed store)
_default_token_store: Optional[ResumeTokenStore] = None


def get_default_token_store() -> ResumeTokenStore:
    """Get the default token store (creates in-memory store if not set)."""
    global _default_token_store
    if _default_token_store is None:
        logger.warning(
            "Using in-memory ResumeTokenStore - tokens will be lost on restart. "
            "Set a Redis-backed store for production."
        )
        _default_token_store = InMemoryResumeTokenStore()
    return _default_token_store


def set_default_token_store(store: ResumeTokenStore) -> None:
    """Set the default token store (call at startup to use Redis-backed store)."""
    global _default_token_store
    _default_token_store = store


class HeadlessEventType(str, Enum):
    """Canonical event types for headless/CLI streaming.
    
    Each event type has a well-defined payload contract.
    """
    # Workflow lifecycle
    WORKFLOW_START = "workflow_start"
    WORKFLOW_COMPLETE = "workflow_complete"
    WORKFLOW_ERROR = "workflow_error"
    
    # Step events
    STEP = "step"
    
    # Tool events
    TOOL_EXECUTING = "tool_executing"
    TOOL_RESULT = "tool_result"
    TOOL_ERROR = "tool_error"
    
    # Human-in-the-loop
    ASK_USER = "ask_user"
    USER_RESPONSE = "user_response"
    
    # Planning events (optional)
    PLAN_CREATED = "plan_created"
    PLAN_PROGRESS = "plan_progress"
    
    # State events
    LOOP_DETECTED = "loop_detected"
    LOW_CONFIDENCE = "low_confidence"
    MAX_STEPS_REACHED = "max_steps_reached"
    APPROVAL_REQUEST = "approval_request"
    
    # Final output
    FINAL_RESPONSE = "final_response"


class AskUserReason(str, Enum):
    """Reasons for human-in-the-loop intervention.
    
    Used to categorize ask_user events for appropriate UI rendering.
    """
    AUTH_REQUIRED = "auth_required"
    VALIDATION_FAILED = "validation_failed"
    RBAC_DENIED = "rbac_denied"
    SEMANTIC_ERROR = "semantic_error"
    TRANSPORT_EXHAUSTED = "transport_exhausted"
    TERMINAL_ERROR = "terminal_error"
    USER_INPUT_NEEDED = "user_input_needed"
    APPROVAL_NEEDED = "approval_needed"
    AMBIGUOUS_INTENT = "ambiguous_intent"


class InputFieldType(str, Enum):
    """Input field types for structured user prompts."""
    TEXT = "text"
    PASSWORD = "password"
    SELECT = "select"
    MULTISELECT = "multiselect"
    CONFIRM = "confirm"
    NUMBER = "number"
    FILE = "file"


@dataclass
class InputField:
    """A single input field for user prompts.
    
    Supports various field types for CLI/UI rendering.
    """
    name: str
    label: str
    field_type: InputFieldType = InputFieldType.TEXT
    required: bool = True
    default: Optional[Any] = None
    placeholder: Optional[str] = None
    options: Optional[List[Dict[str, str]]] = None  # For select/multiselect: [{"value": "x", "label": "X"}]
    validation_pattern: Optional[str] = None  # Regex pattern for validation
    min_value: Optional[float] = None  # For number fields
    max_value: Optional[float] = None  # For number fields
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, omitting None values."""
        result = {
            "name": self.name,
            "label": self.label,
            "field_type": self.field_type.value if isinstance(self.field_type, InputFieldType) else self.field_type,
            "required": self.required,
        }
        if self.default is not None:
            result["default"] = self.default
        if self.placeholder:
            result["placeholder"] = self.placeholder
        if self.options:
            result["options"] = self.options
        if self.validation_pattern:
            result["validation_pattern"] = self.validation_pattern
        if self.min_value is not None:
            result["min_value"] = self.min_value
        if self.max_value is not None:
            result["max_value"] = self.max_value
        return result


@dataclass
class RemediationOption:
    """A selectable option for remediation.
    
    Represents an action the user can take to resolve an issue.
    """
    id: str
    label: str
    description: Optional[str] = None
    action: str = "continue"  # "continue", "retry", "skip", "abort"
    requires_input: bool = False
    input_fields: List[InputField] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "id": self.id,
            "label": self.label,
            "action": self.action,
            "requires_input": self.requires_input,
        }
        if self.description:
            result["description"] = self.description
        if self.input_fields:
            result["input_fields"] = [f.to_dict() for f in self.input_fields]
        return result


@dataclass
class AskUserPayload:
    """Structured payload for ask_user events.
    
    Task E2: Enables CLI/UI to render consistent prompts and collect user input.
    """
    reason: AskUserReason
    title: str
    message: str
    options: List[RemediationOption] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    resume_token: Optional[str] = None  # Token for resuming workflow after user response
    timeout_seconds: Optional[int] = None  # How long to wait for user response
    allow_freeform: bool = True  # Allow freeform text response
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "reason": self.reason.value if isinstance(self.reason, AskUserReason) else self.reason,
            "title": self.title,
            "message": self.message,
            "options": [o.to_dict() for o in self.options],
            "context": self.context,
            "resume_token": self.resume_token,
            "timeout_seconds": self.timeout_seconds,
            "allow_freeform": self.allow_freeform,
        }


@dataclass
class UserResponse:
    """Response from user for ask_user prompts.
    
    Task E2: Envelope for corrected input continuation.
    """
    resume_token: str
    selected_option_id: Optional[str] = None
    input_values: Dict[str, Any] = field(default_factory=dict)
    freeform_text: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "resume_token": self.resume_token,
            "selected_option_id": self.selected_option_id,
            "input_values": self.input_values,
            "freeform_text": self.freeform_text,
            "timestamp": self.timestamp.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserResponse":
        """Create from dictionary (for parsing incoming responses)."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        elif timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        return cls(
            resume_token=data["resume_token"],
            selected_option_id=data.get("selected_option_id"),
            input_values=data.get("input_values", {}),
            freeform_text=data.get("freeform_text"),
            timestamp=timestamp,
        )


@dataclass
class HeadlessEvent:
    """Base event with correlation ID and timestamp.
    
    All events include run_id for multi-run reconciliation.
    """
    type: HeadlessEventType
    run_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    step_number: Optional[int] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "type": self.type.value if isinstance(self.type, HeadlessEventType) else self.type,
            "run_id": self.run_id,
            "timestamp": self.timestamp.isoformat(),
        }
        if self.step_number is not None:
            result["step_number"] = self.step_number
        result.update(self.payload)
        return result


class HeadlessEventBuilder:
    """Builder for creating properly structured headless events.
    
    Ensures all events have required fields and proper structure.
    
    P1 Fix: Token store can be provided for durable resume token storage.
    """
    
    def __init__(
        self,
        run_id: Optional[str] = None,
        token_store: Optional[ResumeTokenStore] = None,
    ):
        """Initialize builder with optional run_id and token store.
        
        Args:
            run_id: Correlation ID for the run. Auto-generated if not provided.
            token_store: Optional durable token store. If not provided, uses
                in-memory fallback (tokens lost on restart).
        """
        self.run_id = run_id or str(uuid.uuid4())
        self._token_store = token_store
        # Fallback in-memory storage (used when token_store not provided or for sync operations)
        self._pending_resume_tokens: Dict[str, Dict[str, Any]] = {}
    
    async def store_resume_token(
        self,
        token: str,
        context: Dict[str, Any],
        ttl_seconds: int = 3600,
    ) -> None:
        """Store a resume token with context (async, uses durable store if available).
        
        Args:
            token: The resume token to store
            context: Context dict with reason, step_number, etc.
            ttl_seconds: Token expiry time
        """
        if self._token_store:
            await self._token_store.store(token, context, ttl_seconds)
        else:
            # Fallback to in-memory
            self._pending_resume_tokens[token] = {
                **context,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
    
    async def get_resume_token_context(self, token: str) -> Optional[Dict[str, Any]]:
        """Get context for a resume token (async, checks durable store first).
        
        Returns None if token doesn't exist.
        """
        if self._token_store:
            return await self._token_store.get(token)
        return self._pending_resume_tokens.get(token)
    
    async def consume_resume_token_async(self, token: str) -> Optional[Dict[str, Any]]:
        """Consume a resume token asynchronously (checks durable store first).
        
        Returns the context if token existed, None otherwise.
        """
        if self._token_store:
            return await self._token_store.consume(token)
        return self._pending_resume_tokens.pop(token, None)
    
    def workflow_start(
        self,
        available_tools: int,
        max_steps: int,
        workflow_type: Optional[str] = None,
        model: Optional[str] = None,
    ) -> HeadlessEvent:
        """Create workflow_start event."""
        return HeadlessEvent(
            type=HeadlessEventType.WORKFLOW_START,
            run_id=self.run_id,
            payload={
                "available_tools": available_tools,
                "max_steps": max_steps,
                "workflow_type": workflow_type,
                "model": model,
            },
        )
    
    def workflow_complete(
        self,
        total_steps: int,
        stopped_reason: str,
        duration_ms: Optional[int] = None,
    ) -> HeadlessEvent:
        """Create workflow_complete event."""
        return HeadlessEvent(
            type=HeadlessEventType.WORKFLOW_COMPLETE,
            run_id=self.run_id,
            step_number=total_steps,
            payload={
                "total_steps": total_steps,
                "stopped_reason": stopped_reason,
                "duration_ms": duration_ms,
            },
        )
    
    def workflow_error(
        self,
        error: str,
        error_type: Optional[str] = None,
        step_number: Optional[int] = None,
        recoverable: bool = False,
    ) -> HeadlessEvent:
        """Create workflow_error event."""
        return HeadlessEvent(
            type=HeadlessEventType.WORKFLOW_ERROR,
            run_id=self.run_id,
            step_number=step_number,
            payload={
                "error": error,
                "error_type": error_type,
                "recoverable": recoverable,
            },
        )
    
    def step(
        self,
        step_number: int,
        action: str,
        tool_names: Optional[List[str]] = None,
        tool_count: Optional[int] = None,
        max_steps: int = 10,
    ) -> HeadlessEvent:
        """Create step event."""
        return HeadlessEvent(
            type=HeadlessEventType.STEP,
            run_id=self.run_id,
            step_number=step_number,
            payload={
                "action": action,
                "tool_names": tool_names,
                "tool_count": tool_count or (len(tool_names) if tool_names else 0),
                "max_steps": max_steps,
            },
        )
    
    def tool_executing(
        self,
        tool_name: str,
        tool_index: int,
        tool_total: int,
        step_number: int,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> HeadlessEvent:
        """Create tool_executing event."""
        # Truncate argument values for display
        safe_args = {}
        if arguments:
            for k, v in arguments.items():
                v_str = str(v)
                safe_args[k] = v_str[:100] + "..." if len(v_str) > 100 else v
        
        return HeadlessEvent(
            type=HeadlessEventType.TOOL_EXECUTING,
            run_id=self.run_id,
            step_number=step_number,
            payload={
                "tool_name": tool_name,
                "tool_index": tool_index,
                "tool_total": tool_total,
                "arguments": safe_args,
            },
        )
    
    def tool_result(
        self,
        tool_name: str,
        step_number: int,
        success: bool,
        duration_ms: Optional[int] = None,
        result_preview: Optional[str] = None,
        error: Optional[str] = None,
    ) -> HeadlessEvent:
        """Create tool_result event."""
        payload: Dict[str, Any] = {
            "tool_name": tool_name,
            "success": success,
        }
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        if result_preview:
            payload["result_preview"] = result_preview[:500]  # Truncate preview
        if error:
            payload["error"] = error
        
        return HeadlessEvent(
            type=HeadlessEventType.TOOL_RESULT,
            run_id=self.run_id,
            step_number=step_number,
            payload=payload,
        )
    
    def tool_error(
        self,
        tool_name: str,
        step_number: int,
        error: str,
        error_type: Optional[str] = None,
        http_status: Optional[int] = None,
        retryable: bool = False,
        attempt_index: int = 0,
        attempt_budget: int = 3,
        recovery_strategy: Optional[str] = None,
        terminal: bool = False,
        duration_ms: Optional[int] = None,
    ) -> HeadlessEvent:
        """Create tool_error event."""
        return HeadlessEvent(
            type=HeadlessEventType.TOOL_ERROR,
            run_id=self.run_id,
            step_number=step_number,
            payload={
                "tool_name": tool_name,
                "error": error,
                "error_type": error_type,
                "http_status": http_status,
                "retryable": retryable,
                "attempt_index": attempt_index,
                "attempt_budget": attempt_budget,
                "recovery_strategy": recovery_strategy,
                "terminal": terminal,
                "duration_ms": duration_ms,
            },
        )
    
    def ask_user(
        self,
        reason: AskUserReason,
        title: str,
        message: str,
        options: Optional[List[RemediationOption]] = None,
        context: Optional[Dict[str, Any]] = None,
        step_number: Optional[int] = None,
        timeout_seconds: Optional[int] = 300,
        allow_freeform: bool = True,
    ) -> HeadlessEvent:
        """Create ask_user event with structured remediation payload.
        
        Generates a resume_token and stores context in-memory for sync access.
        Call persist_resume_token() after emitting event for durable storage.
        """
        resume_token = str(uuid.uuid4())
        
        # Store in-memory for sync access (also stored durably via persist_resume_token)
        token_context = {
            "reason": reason.value if isinstance(reason, AskUserReason) else reason,
            "context": context or {},
            "step_number": step_number,
            "run_id": self.run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._pending_resume_tokens[resume_token] = token_context
        
        payload = AskUserPayload(
            reason=reason,
            title=title,
            message=message,
            options=options or [],
            context=context or {},
            resume_token=resume_token,
            timeout_seconds=timeout_seconds,
            allow_freeform=allow_freeform,
        )
        
        return HeadlessEvent(
            type=HeadlessEventType.ASK_USER,
            run_id=self.run_id,
            step_number=step_number,
            payload=payload.to_dict(),
        )
    
    async def persist_resume_token(self, token: str, ttl_seconds: int = 3600) -> None:
        """Persist a resume token to durable storage if available.
        
        Call this after emitting an ask_user event to ensure token survives restart.
        """
        token_context = self._pending_resume_tokens.get(token)
        if token_context and self._token_store:
            await self._token_store.store(token, token_context, ttl_seconds)
    
    def final_response(
        self,
        message: str,
        step_number: Optional[int] = None,
        confidence: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> HeadlessEvent:
        """Create final_response event."""
        payload: Dict[str, Any] = {
            "message": message,
        }
        if confidence is not None:
            payload["confidence"] = confidence
        if metadata:
            payload["metadata"] = metadata
        
        return HeadlessEvent(
            type=HeadlessEventType.FINAL_RESPONSE,
            run_id=self.run_id,
            step_number=step_number,
            payload=payload,
        )
    
    def loop_detected(self, step_number: int) -> HeadlessEvent:
        """Create loop_detected event."""
        return HeadlessEvent(
            type=HeadlessEventType.LOOP_DETECTED,
            run_id=self.run_id,
            step_number=step_number,
            payload={"step": step_number},
        )
    
    def low_confidence(self, confidence: float, step_number: Optional[int] = None) -> HeadlessEvent:
        """Create low_confidence event."""
        return HeadlessEvent(
            type=HeadlessEventType.LOW_CONFIDENCE,
            run_id=self.run_id,
            step_number=step_number,
            payload={"confidence": confidence},
        )
    
    def max_steps_reached(self, max_steps: int, step_number: int) -> HeadlessEvent:
        """Create max_steps_reached event."""
        return HeadlessEvent(
            type=HeadlessEventType.MAX_STEPS_REACHED,
            run_id=self.run_id,
            step_number=step_number,
            payload={"max_steps": max_steps},
        )
    
    def approval_request(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        step_number: Optional[int] = None,
    ) -> HeadlessEvent:
        """Create approval_request event."""
        return HeadlessEvent(
            type=HeadlessEventType.APPROVAL_REQUEST,
            run_id=self.run_id,
            step_number=step_number,
            payload={
                "tool_name": tool_name,
                "arguments": arguments,
            },
        )
    
    def plan_created(self, steps: List[str]) -> HeadlessEvent:
        """Create plan_created event."""
        return HeadlessEvent(
            type=HeadlessEventType.PLAN_CREATED,
            run_id=self.run_id,
            payload={"steps": steps},
        )
    
    def plan_progress(
        self,
        progress: float,
        current_step: Optional[int] = None,
        current_step_description: Optional[str] = None,
        verified: Optional[bool] = None,
    ) -> HeadlessEvent:
        """Create plan_progress event.
        
        Args:
            progress: Progress percentage (0.0-1.0 or 0-100)
            current_step: Current step number
            current_step_description: Description of current step
            verified: Whether current step was verified
        """
        payload: Dict[str, Any] = {"progress": progress}
        if current_step_description:
            payload["current_step"] = current_step_description
        if verified is not None:
            payload["verified"] = verified
        
        return HeadlessEvent(
            type=HeadlessEventType.PLAN_PROGRESS,
            run_id=self.run_id,
            step_number=current_step,
            payload=payload,
        )
    
    def validate_resume_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate a resume token and return its context if valid."""
        return self._pending_resume_tokens.get(token)
    
    def consume_resume_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Consume a resume token (removes it) and return its context."""
        return self._pending_resume_tokens.pop(token, None)


# Factory functions for common ask_user scenarios
def create_auth_remediation_options() -> List[RemediationOption]:
    """Create remediation options for authentication failures."""
    return [
        RemediationOption(
            id="provide_credentials",
            label="Provide credentials",
            description="Enter or update authentication credentials",
            action="continue",
            requires_input=True,
            input_fields=[
                InputField(
                    name="api_key",
                    label="API Key",
                    field_type=InputFieldType.PASSWORD,
                    placeholder="Enter your API key",
                ),
            ],
        ),
        RemediationOption(
            id="skip_tool",
            label="Skip this tool",
            description="Continue without using this tool",
            action="skip",
        ),
        RemediationOption(
            id="abort",
            label="Cancel workflow",
            description="Stop the workflow entirely",
            action="abort",
        ),
    ]


def create_validation_remediation_options(
    missing_fields: Optional[List[str]] = None,
) -> List[RemediationOption]:
    """Create remediation options for validation failures."""
    input_fields = []
    if missing_fields:
        for field_name in missing_fields:
            input_fields.append(
                InputField(
                    name=field_name,
                    label=field_name.replace("_", " ").title(),
                    placeholder=f"Enter {field_name}",
                )
            )
    
    return [
        RemediationOption(
            id="provide_values",
            label="Provide missing values",
            description="Enter the required values",
            action="retry",
            requires_input=True,
            input_fields=input_fields,
        ),
        RemediationOption(
            id="skip_tool",
            label="Skip this tool",
            description="Continue without using this tool",
            action="skip",
        ),
        RemediationOption(
            id="abort",
            label="Cancel workflow",
            action="abort",
        ),
    ]


def create_semantic_error_remediation_options() -> List[RemediationOption]:
    """Create remediation options for semantic errors."""
    return [
        RemediationOption(
            id="retry_with_correction",
            label="Retry with correction",
            description="Try again with corrected input",
            action="retry",
            requires_input=True,
            input_fields=[
                InputField(
                    name="correction",
                    label="Corrected input",
                    field_type=InputFieldType.TEXT,
                    placeholder="Describe how to correct the issue",
                ),
            ],
        ),
        RemediationOption(
            id="use_alternative",
            label="Try alternative approach",
            description="Let the model try a different approach",
            action="continue",
        ),
        RemediationOption(
            id="skip_tool",
            label="Skip this tool",
            action="skip",
        ),
        RemediationOption(
            id="abort",
            label="Cancel workflow",
            action="abort",
        ),
    ]


def create_approval_remediation_options(tool_name: str) -> List[RemediationOption]:
    """Create remediation options for approval requests."""
    return [
        RemediationOption(
            id="approve",
            label=f"Approve {tool_name}",
            description="Allow the tool to execute",
            action="continue",
        ),
        RemediationOption(
            id="deny",
            label="Deny",
            description="Reject and skip this tool",
            action="skip",
        ),
        RemediationOption(
            id="abort",
            label="Cancel workflow",
            action="abort",
        ),
    ]


# Event validation helpers
REQUIRED_FIELDS_BY_TYPE: Dict[str, List[str]] = {
    HeadlessEventType.WORKFLOW_START.value: ["available_tools", "max_steps"],
    HeadlessEventType.WORKFLOW_COMPLETE.value: ["total_steps", "stopped_reason"],
    HeadlessEventType.WORKFLOW_ERROR.value: ["error"],
    HeadlessEventType.STEP.value: ["action"],
    HeadlessEventType.TOOL_EXECUTING.value: ["tool_name", "tool_index", "tool_total"],
    HeadlessEventType.TOOL_RESULT.value: ["tool_name", "success"],
    HeadlessEventType.TOOL_ERROR.value: ["tool_name", "error"],
    HeadlessEventType.ASK_USER.value: ["reason", "title", "message"],
    HeadlessEventType.USER_RESPONSE.value: ["resume_token"],
    HeadlessEventType.FINAL_RESPONSE.value: ["message"],
    HeadlessEventType.LOOP_DETECTED.value: ["step"],
    HeadlessEventType.LOW_CONFIDENCE.value: ["confidence"],
    HeadlessEventType.MAX_STEPS_REACHED.value: ["max_steps"],
    HeadlessEventType.APPROVAL_REQUEST.value: ["tool_name", "arguments"],
    HeadlessEventType.PLAN_CREATED.value: ["steps"],
    HeadlessEventType.PLAN_PROGRESS.value: ["progress"],
}


def validate_event(event: Union[HeadlessEvent, Dict[str, Any]]) -> List[str]:
    """Validate a headless event has all required fields.
    
    Returns:
        List of missing field names (empty if valid).
    """
    if isinstance(event, HeadlessEvent):
        event_dict = event.to_dict()
    else:
        event_dict = event
    
    missing = []
    
    # All events require type and run_id
    if "type" not in event_dict:
        missing.append("type")
    if "run_id" not in event_dict:
        missing.append("run_id")
    
    event_type = event_dict.get("type")
    if event_type and event_type in REQUIRED_FIELDS_BY_TYPE:
        for field_name in REQUIRED_FIELDS_BY_TYPE[event_type]:
            if field_name not in event_dict:
                missing.append(field_name)
    
    return missing


# P1 Fix: Map error types to appropriate AskUserReason for structured remediation
ERROR_TYPE_TO_ASK_USER_REASON: Dict[str, AskUserReason] = {
    "auth_failure": AskUserReason.AUTH_REQUIRED,
    "rbac_denied": AskUserReason.RBAC_DENIED,
    "validation_error": AskUserReason.VALIDATION_FAILED,
    "tool_not_found": AskUserReason.TERMINAL_ERROR,
    "contract_error": AskUserReason.TERMINAL_ERROR,
    "resource_exhausted": AskUserReason.TRANSPORT_EXHAUSTED,
    "timeout": AskUserReason.TRANSPORT_EXHAUSTED,
    "rate_limit": AskUserReason.TRANSPORT_EXHAUSTED,
    "tool_failure": AskUserReason.SEMANTIC_ERROR,
    "malformed_output": AskUserReason.SEMANTIC_ERROR,
}


def get_ask_user_reason_for_error_type(error_type: str) -> AskUserReason:
    """Map an error type string to the appropriate AskUserReason.
    
    Args:
        error_type: Error type string (e.g., "auth_failure", "validation_error")
        
    Returns:
        Appropriate AskUserReason for UI rendering
    """
    return ERROR_TYPE_TO_ASK_USER_REASON.get(error_type, AskUserReason.TERMINAL_ERROR)


def create_rbac_remediation_options() -> List[RemediationOption]:
    """Create remediation options for RBAC/permission denied errors."""
    return [
        RemediationOption(
            id="request_access",
            label="Request access",
            description="Submit a request for elevated permissions",
            action="continue",
            requires_input=True,
            input_fields=[
                InputField(
                    name="justification",
                    label="Justification",
                    field_type=InputFieldType.TEXT,
                    placeholder="Why do you need access?",
                ),
            ],
        ),
        RemediationOption(
            id="use_alternative",
            label="Try alternative",
            description="Let the agent try a different approach",
            action="continue",
        ),
        RemediationOption(
            id="skip_tool",
            label="Skip this tool",
            description="Continue without using this tool",
            action="skip",
        ),
        RemediationOption(
            id="abort",
            label="Cancel workflow",
            description="Stop the workflow entirely",
            action="abort",
        ),
    ]


def get_remediation_options_for_error_type(
    error_type: str,
    missing_fields: Optional[List[str]] = None,
    tool_name: Optional[str] = None,
) -> List[RemediationOption]:
    """Get appropriate remediation options for an error type.
    
    Args:
        error_type: Error type string
        missing_fields: Optional list of missing field names for validation errors
        tool_name: Optional tool name for approval-style options
        
    Returns:
        List of remediation options appropriate for the error type
    """
    if error_type == "auth_failure":
        return create_auth_remediation_options()
    elif error_type == "rbac_denied":
        return create_rbac_remediation_options()
    elif error_type == "validation_error":
        return create_validation_remediation_options(missing_fields)
    elif error_type in ("tool_failure", "malformed_output"):
        return create_semantic_error_remediation_options()
    else:
        # Generic terminal error options
        return [
            RemediationOption(
                id="retry",
                label="Retry",
                description="Try the operation again",
                action="retry",
            ),
            RemediationOption(
                id="skip",
                label="Skip",
                description="Skip this operation and continue",
                action="skip",
            ),
            RemediationOption(
                id="abort",
                label="Cancel",
                description="Stop the workflow",
                action="abort",
            ),
        ]


@dataclass
class UserResponseValidationResult:
    """Result of validating a user_response payload."""
    valid: bool
    error: Optional[str] = None
    error_type: Optional[str] = None  # "invalid_token", "expired_token", "run_id_mismatch"
    token_context: Optional[Dict[str, Any]] = None
    remediation_options: Optional[List[RemediationOption]] = None


async def validate_user_response(
    data: Dict[str, Any],
    token_store: Optional[ResumeTokenStore] = None,
) -> UserResponseValidationResult:
    """Validate a user_response WebSocket payload.
    
    Checks:
    - Required fields present (resume_token)
    - Token exists and is valid
    - run_id matches token context (if provided)
    
    Args:
        data: The raw WebSocket message dict
        token_store: Token store to validate against (uses default if not provided)
        
    Returns:
        Validation result with error details or token context on success
    """
    store = token_store or get_default_token_store()
    
    # Check required fields
    resume_token = data.get("resume_token")
    if not resume_token:
        return UserResponseValidationResult(
            valid=False,
            error="Missing required field: resume_token",
            error_type="missing_token",
            remediation_options=[
                RemediationOption(
                    id="retry_request",
                    label="Retry",
                    description="Submit a new request to get a fresh resume token",
                    action="retry",
                ),
            ],
        )
    
    # Look up token context
    token_context = await store.get(resume_token)
    if token_context is None:
        return UserResponseValidationResult(
            valid=False,
            error="Invalid or expired resume token",
            error_type="invalid_token",
            remediation_options=[
                RemediationOption(
                    id="start_over",
                    label="Start over",
                    description="The previous workflow state has expired. Please re-submit your original request.",
                    action="retry",
                ),
            ],
        )
    
    # Check run_id correlation if provided
    request_run_id = data.get("run_id")
    token_run_id = token_context.get("run_id")
    if request_run_id and token_run_id and request_run_id != token_run_id:
        return UserResponseValidationResult(
            valid=False,
            error=f"run_id mismatch: request has {request_run_id}, token expects {token_run_id}",
            error_type="run_id_mismatch",
            remediation_options=[
                RemediationOption(
                    id="use_correct_run",
                    label="Use correct run",
                    description="Ensure you're responding to the correct workflow",
                    action="retry",
                ),
            ],
        )
    
    return UserResponseValidationResult(
        valid=True,
        token_context=token_context,
    )
