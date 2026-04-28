"""Comprehensive error handling for agent execution."""
from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """Types of errors during agent execution."""
    TOOL_FAILURE = "tool_failure"
    MALFORMED_OUTPUT = "malformed_output"
    LOOP_DETECTED = "loop_detected"
    LOW_CONFIDENCE = "low_confidence"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    RESOURCE_EXHAUSTED = "resource_exhausted"


@dataclass
class ErrorContext:
    """Context for error decision making."""
    error_type: ErrorType
    step_number: int
    tool_name: Optional[str]
    error_message: str
    retry_count: int
    metadata: Dict[str, Any]


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


class AgentErrorHandler:
    """Handles errors during agent execution."""

    def __init__(self, max_retries: int = 3):
        """
        Initialize error handler.

        Args:
            max_retries: Maximum number of retries for transient failures
        """
        self.max_retries = max_retries

    def decide_recovery(self, context: ErrorContext) -> ErrorRecoveryAction:
        """
        Decide how to recover from an error.

        Args:
            context: Error context with type, step, tool info

        Returns:
            Recovery action to take
        """
        # Tool failure - retry with exponential backoff
        if context.error_type == ErrorType.TOOL_FAILURE:
            if context.retry_count < self.max_retries:
                return ErrorRecoveryAction(
                    strategy=ErrorRecoveryStrategy.RETRY,
                    reason="Transient tool failure, retrying",
                    retry_delay_seconds=2.0 ** context.retry_count,  # Exponential backoff
                )
            else:
                # Check if there's a fallback tool
                fallback = self._find_fallback_tool(context.tool_name)
                if fallback:
                    return ErrorRecoveryAction(
                        strategy=ErrorRecoveryStrategy.FALLBACK,
                        reason=f"Max retries exceeded, using fallback: {fallback}",
                        fallback_tool=fallback,
                    )
                else:
                    return ErrorRecoveryAction(
                        strategy=ErrorRecoveryStrategy.SKIP,
                        reason="No fallback available, skipping step",
                    )

        # Malformed output - retry with clarification
        elif context.error_type == ErrorType.MALFORMED_OUTPUT:
            if context.retry_count < 2:
                return ErrorRecoveryAction(
                    strategy=ErrorRecoveryStrategy.RETRY,
                    reason="Malformed output, retrying with clarified prompt",
                )
            else:
                return ErrorRecoveryAction(
                    strategy=ErrorRecoveryStrategy.ABORT,
                    reason="Persistent malformed output, aborting",
                )

        # Loop detected - abort immediately
        elif context.error_type == ErrorType.LOOP_DETECTED:
            return ErrorRecoveryAction(
                strategy=ErrorRecoveryStrategy.ABORT,
                reason="Agent loop detected, stopping execution",
            )

        # Low confidence - ask user for guidance
        elif context.error_type == ErrorType.LOW_CONFIDENCE:
            return ErrorRecoveryAction(
                strategy=ErrorRecoveryStrategy.ASK_USER,
                reason="Low confidence in action, requesting user guidance",
            )

        # Timeout - abort
        elif context.error_type == ErrorType.TIMEOUT:
            return ErrorRecoveryAction(
                strategy=ErrorRecoveryStrategy.ABORT,
                reason="Execution timeout, stopping workflow",
            )

        # Rate limit - retry with longer backoff
        elif context.error_type == ErrorType.RATE_LIMIT:
            return ErrorRecoveryAction(
                strategy=ErrorRecoveryStrategy.RETRY,
                reason="Rate limit hit, retrying with backoff",
                retry_delay_seconds=60.0,  # Wait 1 minute
            )

        # Default: abort
        else:
            return ErrorRecoveryAction(
                strategy=ErrorRecoveryStrategy.ABORT,
                reason=f"Unhandled error type: {context.error_type}",
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
        confidence_keywords = {
            "certain": 0.9,
            "confident": 0.8,
            "likely": 0.7,
            "probably": 0.6,
            "maybe": 0.5,
            "unsure": 0.4,
            "uncertain": 0.3,
            "guess": 0.2,
        }

        response_lower = llm_response.lower()
        for keyword, score in confidence_keywords.items():
            if keyword in response_lower:
                return score

        # Default: medium confidence
        return 0.7
