"""Agent state management for tracking execution history.

Tracks all tool execution outcomes (success, failure, skipped, aborted) to enable:
- Accurate deduplication of tool calls
- Loop detection that considers failed/skipped attempts
- Comprehensive audit trail of all actions
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Set, Optional
from datetime import datetime, timezone
import hashlib
import json


class ActionOutcome(Enum):
    """Possible outcomes for a tool action."""
    SUCCESS = "success"
    RETRYABLE_FAILURE = "retryable_failure"  # Transient error, may retry
    NON_RETRYABLE_FAILURE = "non_retryable_failure"  # Auth/validation, won't retry
    SKIPPED = "skipped"  # Explicitly skipped (e.g., circuit breaker)
    ABORTED = "aborted"  # Terminal failure, workflow stopping


# Outcomes that should be considered for loop detection
LOOP_DETECTION_OUTCOMES = {
    ActionOutcome.SUCCESS,
    ActionOutcome.RETRYABLE_FAILURE,
    ActionOutcome.NON_RETRYABLE_FAILURE,
    ActionOutcome.ABORTED,
}


@dataclass
class ActionRecord:
    """Record of a tool action attempt."""
    action_type: str  # "tool_call", "plan_step", "retrieval"
    action_key: str  # Unique identifier for deduplication
    timestamp: datetime
    result: Any
    success: bool  # Kept for backward compatibility
    outcome: ActionOutcome = ActionOutcome.SUCCESS
    error_type: Optional[str] = None  # For failed actions
    http_status: Optional[int] = None  # For HTTP-based failures
    attempt_index: int = 0  # Which attempt this was (0-indexed)
    duration_ms: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/storage."""
        return {
            "action_type": self.action_type,
            "action_key": self.action_key[:16] + "...",  # Truncate hash
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "outcome": self.outcome.value,
            "error_type": self.error_type,
            "http_status": self.http_status,
            "attempt_index": self.attempt_index,
            "duration_ms": self.duration_ms,
        }


@dataclass
class AgentState:
    """Tracks agent execution state with comprehensive action history."""
    session_id: int
    current_step: int
    completed_actions: List[ActionRecord] = field(default_factory=list)
    action_keys_seen: Set[str] = field(default_factory=set)
    plan_steps: List[str] = field(default_factory=list)
    plan_completed: List[bool] = field(default_factory=list)
    
    # Track consecutive failures per tool for loop detection
    _consecutive_failures: Dict[str, int] = field(default_factory=dict)
    
    # Global attempt budget tracking
    _total_attempts: int = 0
    _max_total_attempts: int = 50  # Hard cap on total tool attempts
    
    # Run-scoped retry tracking per canonical fingerprint (tool_name + tool_args)
    # This survives step increments and prevents retry budget reset across steps
    _fingerprint_retry_counts: Dict[str, int] = field(default_factory=dict)
    
    # Task A3: Track reflection attempts per fingerprint
    # Allows model one corrective turn before escalating to user
    _fingerprint_reflection_attempts: Dict[str, int] = field(default_factory=dict)

    def has_action_been_completed(self, action_type: str, action_data: Dict[str, Any]) -> bool:
        """
        Check if an action has already been completed successfully (deduplication).
        
        Only considers successful completions to allow retries of failed actions.
        """
        action_key = self._generate_action_key(action_type, action_data)
        
        # Check if we have a successful completion
        for record in self.completed_actions:
            if record.action_key == action_key and record.outcome == ActionOutcome.SUCCESS:
                return True
        return False
    
    def has_action_failed_terminally(self, action_type: str, action_data: Dict[str, Any]) -> bool:
        """
        Check if an action has failed with a non-retryable error.
        
        Returns True if the action failed with AUTH, VALIDATION, or ABORT outcome.
        """
        action_key = self._generate_action_key(action_type, action_data)
        
        for record in self.completed_actions:
            if record.action_key == action_key and record.outcome in {
                ActionOutcome.NON_RETRYABLE_FAILURE,
                ActionOutcome.ABORTED,
            }:
                return True
        return False
    
    def get_attempt_count(self, action_type: str, action_data: Dict[str, Any]) -> int:
        """Get the number of attempts for a specific action."""
        action_key = self._generate_action_key(action_type, action_data)
        return sum(1 for r in self.completed_actions if r.action_key == action_key)
    
    def is_budget_exhausted(self) -> bool:
        """Check if global attempt budget is exhausted."""
        return self._total_attempts >= self._max_total_attempts

    def record_action(
        self,
        action_type: str,
        action_data: Dict[str, Any],
        result: Any,
        success: bool,
        outcome: ActionOutcome = None,
        error_type: Optional[str] = None,
        http_status: Optional[int] = None,
        duration_ms: Optional[int] = None,
    ):
        """
        Record any action outcome (success, failure, skipped, aborted).
        
        Args:
            action_type: Type of action (e.g., "tool_call")
            action_data: Action parameters for deduplication
            result: Result data (or error info)
            success: Whether the action succeeded
            outcome: Specific outcome type (defaults based on success)
            error_type: Error classification if failed
            http_status: HTTP status code if applicable
            duration_ms: Execution duration in milliseconds
        """
        action_key = self._generate_action_key(action_type, action_data)
        
        # Determine outcome if not provided
        if outcome is None:
            outcome = ActionOutcome.SUCCESS if success else ActionOutcome.RETRYABLE_FAILURE
        
        # Count attempts for this action
        attempt_index = self.get_attempt_count(action_type, action_data)

        record = ActionRecord(
            action_type=action_type,
            action_key=action_key,
            timestamp=datetime.now(timezone.utc),
            result=result,
            success=success,
            outcome=outcome,
            error_type=error_type,
            http_status=http_status,
            attempt_index=attempt_index,
            duration_ms=duration_ms,
        )

        self.completed_actions.append(record)
        self.action_keys_seen.add(action_key)
        self._total_attempts += 1
        
        # Track consecutive failures for the tool
        tool_name = action_data.get("name", "unknown")
        if outcome in {ActionOutcome.RETRYABLE_FAILURE, ActionOutcome.NON_RETRYABLE_FAILURE}:
            self._consecutive_failures[tool_name] = self._consecutive_failures.get(tool_name, 0) + 1
        elif outcome == ActionOutcome.SUCCESS:
            self._consecutive_failures[tool_name] = 0

    def _generate_action_key(self, action_type: str, action_data: Dict[str, Any]) -> str:
        """Generate unique key for action deduplication."""
        # Normalize data for consistent hashing
        normalized = json.dumps(action_data, sort_keys=True)
        hash_obj = hashlib.sha256(f"{action_type}:{normalized}".encode())
        return hash_obj.hexdigest()

    def detect_loop(self, window_size: int = 3) -> bool:
        """
        Detect if agent is stuck in a loop.
        
        Considers ALL outcomes (including failures) to detect loops where:
        - Same tool keeps failing repeatedly
        - Same sequence of actions (success or failure) repeats
        """
        # Consider only actions that matter for loop detection
        relevant_actions = [
            a for a in self.completed_actions 
            if a.outcome in LOOP_DETECTION_OUTCOMES
        ]
        
        if len(relevant_actions) < window_size * 2:
            return False

        # Check if recent actions repeat
        recent = relevant_actions[-window_size:]
        previous = relevant_actions[-window_size*2:-window_size]

        recent_keys = [a.action_key for a in recent]
        previous_keys = [a.action_key for a in previous]

        return recent_keys == previous_keys
    
    def detect_tool_failure_loop(self, tool_name: str, threshold: int = 3) -> bool:
        """
        Detect if a specific tool is stuck in a failure loop.
        
        Args:
            tool_name: Name of the tool to check
            threshold: Number of consecutive failures to consider a loop
            
        Returns:
            True if the tool has failed consecutively >= threshold times
        """
        return self._consecutive_failures.get(tool_name, 0) >= threshold
    
    def get_action_history_summary(self) -> Dict[str, Any]:
        """Get a summary of action history for telemetry."""
        outcomes = {}
        for action in self.completed_actions:
            outcome_key = action.outcome.value
            outcomes[outcome_key] = outcomes.get(outcome_key, 0) + 1
        
        return {
            "total_actions": len(self.completed_actions),
            "total_attempts": self._total_attempts,
            "outcomes": outcomes,
            "unique_actions": len(self.action_keys_seen),
        }
    
    # =========================================================================
    # Run-scoped retry budget tracking (Task A1)
    # =========================================================================
    
    def _generate_fingerprint(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        """
        Generate canonical fingerprint for a tool call.
        
        The fingerprint is based on normalized {tool_name, tool_args} so that:
        - Same tool+args across different steps share retry budget
        - Different args create different fingerprints
        
        Args:
            tool_name: Name of the tool
            tool_args: Tool arguments (will be normalized via sorted JSON)
            
        Returns:
            SHA256 hash fingerprint
        """
        # Normalize args for consistent hashing
        normalized_args = json.dumps(tool_args, sort_keys=True, default=str)
        fingerprint_data = f"{tool_name}:{normalized_args}"
        return hashlib.sha256(fingerprint_data.encode()).hexdigest()
    
    def get_fingerprint_retry_count(self, tool_name: str, tool_args: Dict[str, Any]) -> int:
        """
        Get current retry count for a specific tool+args fingerprint.
        
        This count survives step increments and represents the run-scoped
        retry budget consumption.
        
        Args:
            tool_name: Name of the tool
            tool_args: Tool arguments
            
        Returns:
            Number of retry attempts already made for this fingerprint
        """
        fingerprint = self._generate_fingerprint(tool_name, tool_args)
        return self._fingerprint_retry_counts.get(fingerprint, 0)
    
    def increment_fingerprint_retry(self, tool_name: str, tool_args: Dict[str, Any]) -> int:
        """
        Increment retry count for a specific tool+args fingerprint.
        
        Args:
            tool_name: Name of the tool
            tool_args: Tool arguments
            
        Returns:
            New retry count after increment
        """
        fingerprint = self._generate_fingerprint(tool_name, tool_args)
        current = self._fingerprint_retry_counts.get(fingerprint, 0)
        self._fingerprint_retry_counts[fingerprint] = current + 1
        return current + 1
    
    def can_retry_fingerprint(
        self, 
        tool_name: str, 
        tool_args: Dict[str, Any], 
        budget: int
    ) -> bool:
        """
        Check if a tool+args fingerprint can still be retried within budget.
        
        Args:
            tool_name: Name of the tool
            tool_args: Tool arguments
            budget: Maximum allowed retry attempts
            
        Returns:
            True if retry is allowed, False if budget exhausted
        """
        current = self.get_fingerprint_retry_count(tool_name, tool_args)
        return current < budget
    
    def get_fingerprint_retry_summary(self) -> Dict[str, int]:
        """
        Get summary of retry counts per fingerprint (for telemetry).
        
        Returns:
            Dict mapping fingerprint prefixes to retry counts
        """
        return {
            fp[:16] + "...": count 
            for fp, count in self._fingerprint_retry_counts.items()
        }
    
    # =========================================================================
    # Task A3: Error reflection turn tracking
    # =========================================================================
    
    def get_reflection_attempts(self, tool_name: str, tool_args: Dict[str, Any]) -> int:
        """
        Get the number of reflection attempts for a fingerprint.
        
        Reflection attempts represent times the model was given error context
        and allowed to try a corrective action.
        
        Args:
            tool_name: Name of the tool
            tool_args: Tool arguments
            
        Returns:
            Number of reflection attempts for this fingerprint
        """
        fingerprint = self._generate_fingerprint(tool_name, tool_args)
        return self._fingerprint_reflection_attempts.get(fingerprint, 0)
    
    def increment_reflection_attempt(self, tool_name: str, tool_args: Dict[str, Any]) -> int:
        """
        Increment reflection attempt count for a fingerprint.
        
        Call this when injecting error context into conversation for model correction.
        
        Args:
            tool_name: Name of the tool
            tool_args: Tool arguments
            
        Returns:
            New reflection attempt count after increment
        """
        fingerprint = self._generate_fingerprint(tool_name, tool_args)
        current = self._fingerprint_reflection_attempts.get(fingerprint, 0)
        self._fingerprint_reflection_attempts[fingerprint] = current + 1
        return current + 1
    
    def can_reflect(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        max_reflections: int = 1
    ) -> bool:
        """
        Check if model can have another reflection turn for this fingerprint.
        
        Args:
            tool_name: Name of the tool
            tool_args: Tool arguments
            max_reflections: Maximum allowed reflection attempts (default 1)
            
        Returns:
            True if reflection is allowed, False if should escalate to user
        """
        current = self.get_reflection_attempts(tool_name, tool_args)
        return current < max_reflections
