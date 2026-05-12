"""Comprehensive error handling for agent execution.

Provides error classification, recovery strategies, and telemetry for tool failures.
Implements MCP-aligned error handling with fast-fail for auth errors and HITL-safe recovery.
"""
from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
import logging
import os

logger = logging.getLogger(__name__)


# Feature flag for strict terminal behavior (default: True for safety)
STRICT_TOOL_FAILURE_TERMINAL = os.environ.get(
    "STRICT_TOOL_FAILURE_TERMINAL", "true"
).lower() == "true"


class ErrorType(Enum):
    """Types of errors during agent execution."""
    # Retryable errors
    TOOL_FAILURE = "tool_failure"  # Generic/transient tool failure
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    
    # Non-retryable errors (fast-fail)
    AUTH_FAILURE = "auth_failure"  # 401/403 - requires user intervention
    VALIDATION_ERROR = "validation_error"  # 400/schema mismatch
    TOOL_NOT_FOUND = "tool_not_found"  # 404 - tool doesn't exist
    CONTRACT_ERROR = "contract_error"  # Tool response doesn't match schema
    
    # Workflow errors
    MALFORMED_OUTPUT = "malformed_output"
    LOOP_DETECTED = "loop_detected"
    LOW_CONFIDENCE = "low_confidence"
    MAX_RETRIES_EXHAUSTED = "max_retries_exhausted"


class RetryClassification(Enum):
    """Whether an error is retryable."""
    RETRYABLE = "retryable"
    NON_RETRYABLE = "non_retryable"
    CONDITIONAL = "conditional"  # Depends on retry budget


# HTTP status code to error type mapping
HTTP_ERROR_CLASSIFICATION: Dict[int, ErrorType] = {
    400: ErrorType.VALIDATION_ERROR,
    401: ErrorType.AUTH_FAILURE,
    403: ErrorType.AUTH_FAILURE,
    404: ErrorType.TOOL_NOT_FOUND,
    422: ErrorType.VALIDATION_ERROR,
    429: ErrorType.RATE_LIMIT,
    500: ErrorType.TOOL_FAILURE,
    502: ErrorType.TOOL_FAILURE,
    503: ErrorType.TOOL_FAILURE,
    504: ErrorType.TIMEOUT,
}

# Non-retryable error types (fast-fail immediately)
NON_RETRYABLE_ERRORS = {
    ErrorType.AUTH_FAILURE,
    ErrorType.VALIDATION_ERROR,
    ErrorType.TOOL_NOT_FOUND,
    ErrorType.CONTRACT_ERROR,
    ErrorType.LOOP_DETECTED,
}


@dataclass
class ErrorContext:
    """Context for error decision making."""
    error_type: ErrorType
    step_number: int
    tool_name: Optional[str]
    error_message: str
    retry_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    http_status: Optional[int] = None
    attempt_budget: int = 3  # Global retry budget for this tool call


class ErrorRecoveryStrategy(Enum):
    """Recovery strategies for different error types."""
    RETRY = "retry"
    SKIP = "skip"
    FALLBACK = "fallback"
    ABORT = "abort"
    ASK_USER = "ask_user"


@dataclass
class ErrorRecoveryAction:
    """Action to take when recovering from an error."""
    strategy: ErrorRecoveryStrategy
    reason: str
    fallback_tool: Optional[str] = None
    retry_delay_seconds: Optional[float] = None
    remediation_prompt: Optional[str] = None  # For ASK_USER - structured prompt
    terminal: bool = False  # Whether this ends the workflow


@dataclass
class ToolCallTelemetry:
    """Structured telemetry for tool call attempts."""
    tool_name: str
    error_type: Optional[str]
    http_status: Optional[int]
    retryable: bool
    attempt_index: int
    attempt_budget: int
    recovery_strategy: str
    terminal: bool
    duration_ms: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/tracing."""
        return {
            "tool_name": self.tool_name,
            "error_type": self.error_type,
            "http_status": self.http_status,
            "retryable": self.retryable,
            "attempt_index": self.attempt_index,
            "attempt_budget": self.attempt_budget,
            "recovery_strategy": self.recovery_strategy,
            "terminal": self.terminal,
            "duration_ms": self.duration_ms,
        }


def classify_error_from_http_status(status_code: int) -> ErrorType:
    """
    Classify error type from HTTP status code.
    
    Args:
        status_code: HTTP response status code
        
    Returns:
        Appropriate ErrorType for the status
    """
    return HTTP_ERROR_CLASSIFICATION.get(status_code, ErrorType.TOOL_FAILURE)


def classify_error_from_message(error_message: str, http_status: Optional[int] = None) -> ErrorType:
    """
    Classify error type from error message and optional HTTP status.
    
    Args:
        error_message: Error message string
        http_status: Optional HTTP status code
        
    Returns:
        Appropriate ErrorType
    """
    # Check HTTP status first if available
    if http_status:
        return classify_error_from_http_status(http_status)
    
    # Parse error message for classification hints
    msg_lower = error_message.lower()
    
    # Auth errors
    if any(term in msg_lower for term in [
        "unauthorized", "authentication", "401", "403", 
        "forbidden", "invalid token", "expired token",
        "invalid api key", "missing credentials"
    ]):
        return ErrorType.AUTH_FAILURE
    
    # Validation errors
    if any(term in msg_lower for term in [
        "validation", "invalid", "schema", "400", "422",
        "missing required", "type error", "format error"
    ]):
        return ErrorType.VALIDATION_ERROR
    
    # Not found
    if any(term in msg_lower for term in [
        "not found", "404", "unknown tool", "no such"
    ]):
        return ErrorType.TOOL_NOT_FOUND
    
    # Rate limiting
    if any(term in msg_lower for term in [
        "rate limit", "too many requests", "429", "throttl"
    ]):
        return ErrorType.RATE_LIMIT
    
    # Timeout
    if any(term in msg_lower for term in [
        "timeout", "timed out", "504"
    ]):
        return ErrorType.TIMEOUT
    
    # Default to generic tool failure (retryable)
    return ErrorType.TOOL_FAILURE


def is_error_retryable(error_type: ErrorType) -> bool:
    """Check if an error type is retryable."""
    return error_type not in NON_RETRYABLE_ERRORS


class AgentErrorHandler:
    """Handles errors during agent execution with deterministic recovery."""

    def __init__(
        self,
        max_retries: int = 3,
        strict_terminal: bool = STRICT_TOOL_FAILURE_TERMINAL,
    ):
        """
        Initialize error handler.

        Args:
            max_retries: Maximum number of retries for transient failures
            strict_terminal: If True, exhausted retries with no fallback => ABORT
        """
        self.max_retries = max_retries
        self.strict_terminal = strict_terminal

    def classify_error(
        self,
        error_message: str,
        http_status: Optional[int] = None,
    ) -> ErrorType:
        """
        Classify an error into an ErrorType.
        
        Args:
            error_message: The error message
            http_status: Optional HTTP status code
            
        Returns:
            Classified ErrorType
        """
        return classify_error_from_message(error_message, http_status)

    def decide_recovery(self, context: ErrorContext) -> ErrorRecoveryAction:
        """
        Decide how to recover from an error.

        Args:
            context: Error context with type, step, tool info

        Returns:
            Recovery action to take
        """
        # =====================================================================
        # NON-RETRYABLE ERRORS - Fast fail immediately
        # =====================================================================
        
        # Auth failure - requires user intervention
        if context.error_type == ErrorType.AUTH_FAILURE:
            remediation = self._build_auth_remediation_prompt(context)
            return ErrorRecoveryAction(
                strategy=ErrorRecoveryStrategy.ASK_USER,
                reason="Authentication/authorization failed. User action required.",
                remediation_prompt=remediation,
                terminal=True,
            )
        
        # Validation error - bad request, won't succeed on retry
        if context.error_type == ErrorType.VALIDATION_ERROR:
            return ErrorRecoveryAction(
                strategy=ErrorRecoveryStrategy.ABORT,
                reason=f"Validation error: {context.error_message}. Check tool arguments.",
                terminal=True,
            )
        
        # Tool not found - won't magically appear
        if context.error_type == ErrorType.TOOL_NOT_FOUND:
            return ErrorRecoveryAction(
                strategy=ErrorRecoveryStrategy.ABORT,
                reason=f"Tool '{context.tool_name}' not found. Cannot proceed.",
                terminal=True,
            )
        
        # Contract error - tool response doesn't match expected schema
        if context.error_type == ErrorType.CONTRACT_ERROR:
            return ErrorRecoveryAction(
                strategy=ErrorRecoveryStrategy.ABORT,
                reason="Tool response doesn't match expected contract.",
                terminal=True,
            )
        
        # Loop detected - abort immediately
        if context.error_type == ErrorType.LOOP_DETECTED:
            return ErrorRecoveryAction(
                strategy=ErrorRecoveryStrategy.ABORT,
                reason="Agent loop detected, stopping execution.",
                terminal=True,
            )
        
        # =====================================================================
        # RETRYABLE ERRORS - With budget enforcement
        # =====================================================================
        
        # Tool failure - retry with exponential backoff
        if context.error_type == ErrorType.TOOL_FAILURE:
            return self._handle_tool_failure(context)
        
        # Max retries exhausted - terminal
        if context.error_type == ErrorType.MAX_RETRIES_EXHAUSTED:
            return self._handle_exhausted_retries(context)

        # Malformed output - retry with clarification
        if context.error_type == ErrorType.MALFORMED_OUTPUT:
            if context.retry_count < 2:
                return ErrorRecoveryAction(
                    strategy=ErrorRecoveryStrategy.RETRY,
                    reason="Malformed output, retrying with clarified prompt",
                    retry_delay_seconds=1.0,
                )
            else:
                return ErrorRecoveryAction(
                    strategy=ErrorRecoveryStrategy.ABORT,
                    reason="Persistent malformed output, aborting",
                    terminal=True,
                )

        # Low confidence - ask user for guidance
        if context.error_type == ErrorType.LOW_CONFIDENCE:
            return ErrorRecoveryAction(
                strategy=ErrorRecoveryStrategy.ASK_USER,
                reason="Low confidence in action, requesting user guidance",
                remediation_prompt="The agent is uncertain about this action. Please confirm or provide guidance.",
            )

        # Timeout - abort
        if context.error_type == ErrorType.TIMEOUT:
            return ErrorRecoveryAction(
                strategy=ErrorRecoveryStrategy.ABORT,
                reason="Execution timeout, stopping workflow",
                terminal=True,
            )

        # Rate limit - retry with longer backoff
        if context.error_type == ErrorType.RATE_LIMIT:
            if context.retry_count < self.max_retries:
                return ErrorRecoveryAction(
                    strategy=ErrorRecoveryStrategy.RETRY,
                    reason="Rate limit hit, retrying with backoff",
                    retry_delay_seconds=60.0,  # Wait 1 minute
                )
            else:
                return ErrorRecoveryAction(
                    strategy=ErrorRecoveryStrategy.ASK_USER,
                    reason="Rate limit persists after retries. Please wait and try again.",
                    terminal=True,
                )

        # Resource exhausted
        if context.error_type == ErrorType.RESOURCE_EXHAUSTED:
            return ErrorRecoveryAction(
                strategy=ErrorRecoveryStrategy.ABORT,
                reason="Resource exhausted, stopping workflow",
                terminal=True,
            )

        # Default: abort
        return ErrorRecoveryAction(
            strategy=ErrorRecoveryStrategy.ABORT,
            reason=f"Unhandled error type: {context.error_type}",
            terminal=True,
        )

    def _handle_tool_failure(self, context: ErrorContext) -> ErrorRecoveryAction:
        """Handle generic/transient tool failure with retry budget."""
        # Check retry budget
        if context.retry_count < min(self.max_retries, context.attempt_budget):
            return ErrorRecoveryAction(
                strategy=ErrorRecoveryStrategy.RETRY,
                reason=f"Transient tool failure, retrying (attempt {context.retry_count + 1}/{context.attempt_budget})",
                retry_delay_seconds=2.0 ** context.retry_count,  # Exponential backoff
            )
        
        # Exhausted retries
        return self._handle_exhausted_retries(context)
    
    def _handle_exhausted_retries(self, context: ErrorContext) -> ErrorRecoveryAction:
        """Handle exhausted retry budget - ABORT or FALLBACK, never SKIP."""
        # Check for fallback tool
        fallback = self._find_fallback_tool(context.tool_name)
        if fallback:
            return ErrorRecoveryAction(
                strategy=ErrorRecoveryStrategy.FALLBACK,
                reason=f"Max retries exceeded, using fallback: {fallback}",
                fallback_tool=fallback,
            )
        
        # No fallback - ABORT (or ASK_USER in non-strict mode)
        if self.strict_terminal:
            return ErrorRecoveryAction(
                strategy=ErrorRecoveryStrategy.ABORT,
                reason=f"Tool '{context.tool_name}' failed after {context.retry_count} attempts with no fallback. Aborting.",
                terminal=True,
            )
        else:
            # Non-strict mode: ask user what to do
            return ErrorRecoveryAction(
                strategy=ErrorRecoveryStrategy.ASK_USER,
                reason=f"Tool '{context.tool_name}' failed repeatedly. How would you like to proceed?",
                remediation_prompt=(
                    f"The tool '{context.tool_name}' failed after {context.retry_count} attempts.\n"
                    f"Last error: {context.error_message}\n\n"
                    "Options:\n"
                    "1. Retry with different parameters\n"
                    "2. Skip this step and continue\n"
                    "3. Abort the workflow"
                ),
            )
    
    def _build_auth_remediation_prompt(self, context: ErrorContext) -> str:
        """Build a structured remediation prompt for auth failures."""
        tool_name = context.tool_name or "unknown"
        
        # Check for specific auth error hints
        msg_lower = context.error_message.lower()
        
        if "expired" in msg_lower:
            action = "Your authentication token has expired. Please re-authenticate."
        elif "invalid" in msg_lower:
            action = "The authentication credentials are invalid. Please check your API key or token."
        elif "403" in context.error_message or "forbidden" in msg_lower:
            action = "You don't have permission to perform this action. Check your access scope."
        else:
            action = "Authentication failed. Please verify your credentials."
        
        return (
            f"Authentication error for tool '{tool_name}':\n"
            f"{context.error_message}\n\n"
            f"Recommended action: {action}\n\n"
            "To resolve:\n"
            "1. Check if your API key/token is valid and not expired\n"
            "2. Verify you have the required permissions/scopes\n"
            "3. Try refreshing your credentials\n"
            "4. Contact your administrator if the issue persists"
        )

    def _find_fallback_tool(self, failed_tool: Optional[str]) -> Optional[str]:
        """
        Find fallback tool for a failed tool.

        Args:
            failed_tool: Name of tool that failed

        Returns:
            Name of fallback tool or None

        Note: Fallback mappings should only map to tools with compatible
        argument schemas. Never map to execute_bash as this could allow
        shell injection with user-controlled arguments.
        """
        # Define safe fallback mappings (same argument schema required)
        # WARNING: Do NOT add execute_bash as fallback - security risk
        fallbacks: dict = {
            # Add safe fallback mappings here, e.g.:
            # "primary_db_query": "backup_db_query",
        }
        return fallbacks.get(failed_tool)

    def parse_confidence(self, llm_response: str) -> float:
        """
        Parse confidence level from LLM response.

        Args:
            llm_response: Text response from LLM

        Returns:
            Confidence score 0.0-1.0
        """
        # Look for confidence indicators
        # Order matters: check longer/more specific keywords first to avoid substring matches
        # e.g., "uncertain" should be checked before "certain"
        confidence_keywords = {
            "uncertain": 0.3,
            "confident": 0.8,
            "certain": 0.9,
            "probably": 0.6,
            "likely": 0.7,
            "unsure": 0.4,
            "maybe": 0.5,
            "guess": 0.2,
        }

        response_lower = llm_response.lower()
        for keyword, score in confidence_keywords.items():
            if keyword in response_lower:
                return score

        # Default: medium confidence
        return 0.7
