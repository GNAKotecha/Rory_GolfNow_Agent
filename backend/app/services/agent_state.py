"""Agent state management for tracking execution history."""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Set
from datetime import datetime, timezone
import hashlib
import json


@dataclass
class ActionRecord:
    """Record of a completed action."""
    action_type: str  # "tool_call", "plan_step", "retrieval"
    action_key: str  # Unique identifier for deduplication
    timestamp: datetime
    result: Any
    success: bool


@dataclass
class AgentState:
    """Tracks agent execution state."""
    session_id: int
    current_step: int
    completed_actions: List[ActionRecord] = field(default_factory=list)
    action_keys_seen: Set[str] = field(default_factory=set)
    plan_steps: List[str] = field(default_factory=list)
    plan_completed: List[bool] = field(default_factory=list)

    def has_action_been_completed(self, action_type: str, action_data: Dict[str, Any]) -> bool:
        """Check if an action has already been completed (deduplication)."""
        action_key = self._generate_action_key(action_type, action_data)
        return action_key in self.action_keys_seen

    def record_action(self, action_type: str, action_data: Dict[str, Any], result: Any, success: bool):
        """Record a completed action."""
        action_key = self._generate_action_key(action_type, action_data)

        record = ActionRecord(
            action_type=action_type,
            action_key=action_key,
            timestamp=datetime.now(timezone.utc),
            result=result,
            success=success,
        )

        self.completed_actions.append(record)
        self.action_keys_seen.add(action_key)

    def _generate_action_key(self, action_type: str, action_data: Dict[str, Any]) -> str:
        """Generate unique key for action deduplication."""
        # Normalize data for consistent hashing
        normalized = json.dumps(action_data, sort_keys=True)
        hash_obj = hashlib.sha256(f"{action_type}:{normalized}".encode())
        return hash_obj.hexdigest()

    def detect_loop(self, window_size: int = 3) -> bool:
        """Detect if agent is stuck in a loop."""
        if len(self.completed_actions) < window_size * 2:
            return False

        # Check if recent actions repeat
        recent = self.completed_actions[-window_size:]
        previous = self.completed_actions[-window_size*2:-window_size]

        recent_keys = [a.action_key for a in recent]
        previous_keys = [a.action_key for a in previous]

        return recent_keys == previous_keys
