"""Runtime harness for agent execution control.

Provides:
- Step counting and max_steps enforcement
- Repeat action detection (loop prevention)
- No-progress detection (stuck state)
- Timeout handling
- Audit logging for control decisions
"""
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from datetime import datetime, timedelta, timezone
import logging

logger = logging.getLogger(__name__)


# ==============================================================================
# Stop Reasons
# ==============================================================================

class StopReason(Enum):
    """Reasons why agent execution stopped."""
    MAX_STEPS = "max_steps"
    LOOP_DETECTED = "loop_detected"
    NO_PROGRESS = "no_progress"
    TIMEOUT = "timeout"
    COMPLETED = "completed"
    ERROR = "error"


# ==============================================================================
# Harness Configuration
# ==============================================================================

class HarnessConfig:
    """Configuration for runtime harness."""

    def __init__(
        self,
        max_steps: int = 50,
        max_repeat_action: int = 3,
        no_progress_window: int = 5,
        timeout_seconds: int = 300,
    ):
        """
        Args:
            max_steps: Maximum number of agent steps before stopping
            max_repeat_action: Max times same action can repeat consecutively
            no_progress_window: Number of steps to check for progress
            timeout_seconds: Maximum execution time in seconds
        """
        self.max_steps = max_steps
        self.max_repeat_action = max_repeat_action
        self.no_progress_window = no_progress_window
        self.timeout_seconds = timeout_seconds


# ==============================================================================
# Harness State
# ==============================================================================

class HarnessState:
    """Tracks execution state for runtime control."""

    def __init__(self, config: HarnessConfig):
        self.config = config
        self.step_count = 0
        self.action_history: List[str] = []
        self.progress_markers: List[str] = []
        self.start_time = datetime.now(timezone.utc)
        self.audit_log: List[Dict[str, Any]] = []

    def elapsed_seconds(self) -> float:
        """Get elapsed time in seconds."""
        return (datetime.now(timezone.utc) - self.start_time).total_seconds()


# ==============================================================================
# Control Checks
# ==============================================================================

def check_max_steps(state: HarnessState) -> Optional[StopReason]:
    """Check if max steps exceeded."""
    if state.step_count >= state.config.max_steps:
        _audit(state, "max_steps_exceeded", {
            "step_count": state.step_count,
            "max_steps": state.config.max_steps,
        })
        return StopReason.MAX_STEPS
    return None


def check_loop_detected(state: HarnessState) -> Optional[StopReason]:
    """Check if agent is repeating same action."""
    if len(state.action_history) < state.config.max_repeat_action:
        return None

    # Get last N actions
    recent = state.action_history[-state.config.max_repeat_action:]

    # Check if all identical
    if len(set(recent)) == 1:
        _audit(state, "loop_detected", {
            "action": recent[0],
            "repeat_count": len(recent),
            "max_repeat_action": state.config.max_repeat_action,
        })
        return StopReason.LOOP_DETECTED

    return None


def check_no_progress(state: HarnessState) -> Optional[StopReason]:
    """Check if agent is making progress."""
    window = state.config.no_progress_window

    if len(state.progress_markers) < window:
        return None

    # Get last N progress markers
    recent = state.progress_markers[-window:]

    # Check if all identical (no progress)
    if len(set(recent)) == 1:
        _audit(state, "no_progress_detected", {
            "window_size": window,
            "marker": recent[0],
        })
        return StopReason.NO_PROGRESS

    return None


def check_timeout(state: HarnessState) -> Optional[StopReason]:
    """Check if execution timeout exceeded."""
    elapsed = state.elapsed_seconds()

    if elapsed >= state.config.timeout_seconds:
        _audit(state, "timeout_exceeded", {
            "elapsed_seconds": elapsed,
            "timeout_seconds": state.config.timeout_seconds,
        })
        return StopReason.TIMEOUT

    return None


# ==============================================================================
# Step Execution
# ==============================================================================

def should_continue(state: HarnessState) -> Tuple[bool, Optional[StopReason]]:
    """
    Check all control conditions.

    Returns:
        (should_continue, stop_reason)
    """
    # Check timeout first (most critical)
    if reason := check_timeout(state):
        return False, reason

    # Check step limit
    if reason := check_max_steps(state):
        return False, reason

    # Check for loops
    if reason := check_loop_detected(state):
        return False, reason

    # Check for progress
    if reason := check_no_progress(state):
        return False, reason

    return True, None


def record_action(state: HarnessState, action: str) -> None:
    """Record an agent action for loop detection."""
    state.action_history.append(action)
    _audit(state, "action_recorded", {"action": action})


def record_progress(state: HarnessState, marker: str) -> None:
    """Record a progress marker for no-progress detection."""
    state.progress_markers.append(marker)
    _audit(state, "progress_recorded", {"marker": marker})


def increment_step(state: HarnessState) -> None:
    """Increment step counter."""
    state.step_count += 1
    _audit(state, "step_incremented", {"step_count": state.step_count})


# ==============================================================================
# Audit Logging
# ==============================================================================

def _audit(state: HarnessState, event: str, data: Dict[str, Any]) -> None:
    """Record audit event."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "step": state.step_count,
        "elapsed_seconds": state.elapsed_seconds(),
        "data": data,
    }
    state.audit_log.append(entry)
    logger.info(f"Harness audit: {event}", extra=entry)


def get_audit_summary(state: HarnessState) -> Dict[str, Any]:
    """Get summary of harness execution."""
    return {
        "total_steps": state.step_count,
        "total_actions": len(state.action_history),
        "elapsed_seconds": state.elapsed_seconds(),
        "audit_events": len(state.audit_log),
        "action_sequence": state.action_history[-10:],  # Last 10 actions
        "progress_sequence": state.progress_markers[-10:],  # Last 10 markers
    }


# ==============================================================================
# High-Level Execution Context
# ==============================================================================

class ExecutionContext:
    """Context manager for harness-controlled execution."""

    def __init__(self, config: Optional[HarnessConfig] = None):
        self.config = config or HarnessConfig()
        self.state: Optional[HarnessState] = None

    def __enter__(self) -> HarnessState:
        """Start execution context."""
        self.state = HarnessState(self.config)
        _audit(self.state, "execution_started", {
            "config": {
                "max_steps": self.config.max_steps,
                "max_repeat_action": self.config.max_repeat_action,
                "no_progress_window": self.config.no_progress_window,
                "timeout_seconds": self.config.timeout_seconds,
            }
        })
        return self.state

    def __exit__(self, exc_type, exc_val, exc_tb):
        """End execution context."""
        if self.state:
            _audit(self.state, "execution_ended", get_audit_summary(self.state))
        return False


# ==============================================================================
# Tool Call Tracking (for action detection)
# ==============================================================================

def normalize_tool_call(tool_name: str, args: Dict[str, Any]) -> str:
    """
    Normalize tool call to string for comparison.

    Only includes stable parameters (excludes timestamps, random IDs, etc.)
    """
    # Sort args for consistent ordering
    sorted_args = sorted(args.items())

    # Build signature
    arg_str = ", ".join(f"{k}={v}" for k, v in sorted_args)
    return f"{tool_name}({arg_str})"


def extract_action_signature(tool_call: Dict[str, Any]) -> str:
    """
    Extract action signature from tool call for loop detection.

    Args:
        tool_call: Dict with 'name' and 'arguments' keys

    Returns:
        Normalized action signature
    """
    name = tool_call.get("name", "unknown")
    args = tool_call.get("arguments", {})

    # Filter out non-deterministic args
    stable_args = {
        k: v for k, v in args.items()
        if k not in ["timestamp", "request_id", "session_id"]
    }

    return normalize_tool_call(name, stable_args)
