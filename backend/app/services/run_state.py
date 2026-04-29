"""Run state management and approval flow.

Provides:
- RunState serialization for pause/resume
- Pending approval record creation
- Resume from saved state after approve/reject
- Auto-approve for low-risk actions
- Async-safe DB operations using thread pool
"""
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field, asdict, fields
from datetime import datetime, timezone
from enum import Enum
import asyncio
import json
import threading
import logging

logger = logging.getLogger(__name__)


class RunStatus(Enum):
    """Status of an agentic run."""
    RUNNING = "running"
    PAUSED_FOR_APPROVAL = "paused_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ApprovalDecision(Enum):
    """User's decision on approval request."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_APPROVED = "auto_approved"
    EXPIRED = "expired"


@dataclass
class PendingToolCall:
    """A tool call awaiting approval."""
    tool_name: str
    arguments: Dict[str, Any]
    tool_call_id: str
    reason: str  # Why approval is needed
    risk_level: str = "medium"  # low, medium, high


@dataclass
class RunStateStep:
    """Serializable representation of an agentic step."""
    step_number: int
    llm_response_type: str  # "text" or "tool_calls"
    llm_response_content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_executions: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class RunState:
    """
    Complete state of an agentic run for pause/resume.
    
    This allows:
    - Serializing state before approval pause
    - Resuming from exact point after approve/reject
    - Debugging failed runs
    """
    # Identifiers
    run_id: str
    session_id: int
    user_id: int
    
    # Configuration
    model: Optional[str] = None
    max_steps: int = 10
    current_step: int = 0
    
    # Status
    status: str = "running"
    stopped_reason: Optional[str] = None
    error: Optional[str] = None
    
    # Messages (current conversation state)
    messages: List[Dict[str, Any]] = field(default_factory=list)
    
    # Execution history
    steps: List[Dict[str, Any]] = field(default_factory=list)  # Serialized AgenticSteps
    
    # State management
    completed_action_keys: Set[str] = field(default_factory=set)
    retry_counts: Dict[str, int] = field(default_factory=dict)
    
    # Pending approval
    pending_approval: Optional[Dict[str, Any]] = None
    
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    paused_at: Optional[str] = None
    resumed_at: Optional[str] = None
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        data = asdict(self)
        # Convert set to list for JSON serialization
        data["completed_action_keys"] = list(self.completed_action_keys)
        return json.dumps(data, default=str)
    
    @classmethod
    def from_json(cls, json_str: str) -> "RunState":
        """Deserialize from JSON string with field whitelist."""
        data = json.loads(json_str)
        return cls._from_validated_dict(data)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data["completed_action_keys"] = list(self.completed_action_keys)
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunState":
        """Create from dictionary with field whitelist."""
        return cls._from_validated_dict(data)
    
    @classmethod
    def _from_validated_dict(cls, data: Dict[str, Any]) -> "RunState":
        """Create from dictionary, only accepting known fields."""
        # Get allowed field names from dataclass definition
        allowed_fields = {f.name for f in fields(cls)}
        
        # Filter to only allowed fields
        filtered_data = {k: v for k, v in data.items() if k in allowed_fields}
        
        # Warn about ignored fields
        ignored_fields = set(data.keys()) - allowed_fields
        if ignored_fields:
            logger.warning(f"RunState deserialization ignored unknown fields: {ignored_fields}")
        
        # Convert list back to set for completed_action_keys
        filtered_data["completed_action_keys"] = set(filtered_data.get("completed_action_keys", []))
        
        return cls(**filtered_data)
    
    def pause_for_approval(self, pending_tool: PendingToolCall):
        """Pause the run for approval."""
        self.status = RunStatus.PAUSED_FOR_APPROVAL.value
        self.paused_at = datetime.now(timezone.utc).isoformat()
        self.pending_approval = {
            "tool_name": pending_tool.tool_name,
            "arguments": pending_tool.arguments,
            "tool_call_id": pending_tool.tool_call_id,
            "reason": pending_tool.reason,
            "risk_level": pending_tool.risk_level,
        }
        self.updated_at = datetime.now(timezone.utc).isoformat()
    
    def resume_after_approval(self, approved: bool, user_comment: Optional[str] = None):
        """Resume after approval decision."""
        self.status = RunStatus.RUNNING.value
        self.resumed_at = datetime.now(timezone.utc).isoformat()
        
        if self.pending_approval:
            self.pending_approval["decision"] = (
                ApprovalDecision.APPROVED.value if approved 
                else ApprovalDecision.REJECTED.value
            )
            self.pending_approval["decided_at"] = self.resumed_at
            self.pending_approval["user_comment"] = user_comment
        
        self.updated_at = datetime.now(timezone.utc).isoformat()
    
    def mark_completed(self, response: str, reason: str = "completed"):
        """Mark run as completed."""
        self.status = RunStatus.COMPLETED.value
        self.stopped_reason = reason
        self.updated_at = datetime.now(timezone.utc).isoformat()
        self.metadata["final_response"] = response
    
    def mark_failed(self, error: str, reason: str = "error"):
        """Mark run as failed."""
        self.status = RunStatus.FAILED.value
        self.stopped_reason = reason
        self.error = error
        self.updated_at = datetime.now(timezone.utc).isoformat()


@dataclass
class ApprovalRecord:
    """Record of an approval request and response."""
    id: Optional[int] = None
    run_id: str = ""
    session_id: int = 0
    user_id: int = 0
    
    # Tool information
    tool_name: str = ""
    tool_arguments: Dict[str, Any] = field(default_factory=dict)
    tool_call_id: str = ""
    
    # Request details
    reason: str = ""
    risk_level: str = "medium"
    
    # Serialized run state for resume
    run_state_json: str = ""
    
    # Decision
    decision: str = "pending"  # ApprovalDecision value
    decided_by: Optional[int] = None  # User ID of approver
    decided_at: Optional[datetime] = None
    user_comment: Optional[str] = None
    
    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None  # Auto-expire if not decided


class ApprovalService:
    """
    Manages approval workflow for write operations.
    
    Responsibilities:
    - Create pending approval records
    - Store serialized RunState
    - Track approval decisions
    - Support auto-approval for allowlisted actions
    - Resume execution after approval
    """
    
    def __init__(self, db_session=None):
        self.db = db_session
        self._auto_approve_allowlist: Set[str] = set()
        
        # Default low-risk actions that can be auto-approved
        self._low_risk_patterns: List[str] = [
            "get", "list", "read", "search", "query", "fetch",
            "describe", "show", "count", "exists", "check", "validate"
        ]
    
    def set_auto_approve_allowlist(self, tool_names: Set[str]):
        """Set explicit list of tools that can be auto-approved."""
        self._auto_approve_allowlist = tool_names
        logger.info(f"Set auto-approve allowlist: {tool_names}")
    
    def can_auto_approve(self, tool_name: str) -> bool:
        """
        Check if a tool action can be auto-approved.
        
        Auto-approval requires:
        1. Tool is explicitly allowlisted, OR
        2. Tool matches low-risk pattern AND is not a write operation
        """
        # Explicit allowlist takes precedence
        if tool_name in self._auto_approve_allowlist:
            return True
        
        tool_lower = tool_name.lower()
        
        # Check if it matches low-risk patterns
        matches_low_risk = any(
            pattern in tool_lower
            for pattern in self._low_risk_patterns
        )
        
        # Must NOT contain write patterns
        write_patterns = [
            "create", "update", "delete", "write", "modify",
            "insert", "remove", "drop", "set", "patch", "put"
        ]
        
        is_write = any(
            pattern in tool_lower
            for pattern in write_patterns
        )
        
        return matches_low_risk and not is_write
    
    def classify_risk(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        Classify risk level of a tool operation.
        
        Returns: "low", "medium", "high"
        """
        tool_lower = tool_name.lower()
        
        # High risk: destructive operations
        high_risk_patterns = ["delete", "drop", "remove", "truncate", "destroy"]
        if any(p in tool_lower for p in high_risk_patterns):
            return "high"
        
        # Medium risk: modifications
        medium_risk_patterns = ["update", "modify", "set", "patch", "write"]
        if any(p in tool_lower for p in medium_risk_patterns):
            return "medium"
        
        # Low risk: create/insert (can be undone)
        low_risk_patterns = ["create", "insert", "add", "put"]
        if any(p in tool_lower for p in low_risk_patterns):
            return "low"
        
        # Default to medium for unknown
        return "medium"
    
    def create_approval_request(
        self,
        run_state: RunState,
        tool_call: PendingToolCall,
    ) -> ApprovalRecord:
        """
        Create a pending approval record with serialized run state.
        """
        record = ApprovalRecord(
            run_id=run_state.run_id,
            session_id=run_state.session_id,
            user_id=run_state.user_id,
            tool_name=tool_call.tool_name,
            tool_arguments=tool_call.arguments,
            tool_call_id=tool_call.tool_call_id,
            reason=tool_call.reason,
            risk_level=tool_call.risk_level,
            run_state_json=run_state.to_json(),
            decision=ApprovalDecision.PENDING.value,
        )
        
        logger.info(
            f"Created approval request for {tool_call.tool_name}",
            extra={
                "run_id": run_state.run_id,
                "session_id": run_state.session_id,
                "tool_name": tool_call.tool_name,
                "risk_level": tool_call.risk_level,
            }
        )
        
        return record
    
    async def save_approval_request(
        self,
        record: ApprovalRecord,
    ) -> int:
        """
        Save approval request to database (async-safe, thread-safe).
        
        Creates a new DB session inside the thread pool to avoid
        thread-safety issues with SQLAlchemy sessions.
        
        Returns:
            Approval record ID
        """
        def _sync_save():
            from app.models.models import Approval
            from app.db.session import SessionLocal
            
            # Create new session for this thread (SQLAlchemy sessions are not thread-safe)
            with SessionLocal() as db:
                db_record = Approval(
                    session_id=record.session_id,
                    request_type=f"tool:{record.tool_name}",
                    request_data={
                        "run_id": record.run_id,
                        "tool_name": record.tool_name,
                        "arguments": record.tool_arguments,
                        "tool_call_id": record.tool_call_id,
                        "reason": record.reason,
                        "risk_level": record.risk_level,
                        "run_state_json": record.run_state_json,
                    },
                    approved=None,  # Pending
                )
                
                db.add(db_record)
                db.commit()
                db.refresh(db_record)
                
                return db_record.id
        
        return await asyncio.to_thread(_sync_save)
    
    async def get_pending_approvals(
        self,
        session_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get pending approval requests, optionally filtered by session ID
        (async-safe, thread-safe).
        
        Creates a new DB session inside the thread pool to avoid
        thread-safety issues with SQLAlchemy sessions.
        """
        def _sync_query(filter_session_id: Optional[int]):
            from app.models.models import Approval
            from app.db.session import SessionLocal
            
            # Create new session for this thread (SQLAlchemy sessions are not thread-safe)
            with SessionLocal() as db:
                query = db.query(Approval).filter(Approval.approved.is_(None))
                
                if filter_session_id:
                    query = query.filter(Approval.session_id == filter_session_id)
                
                records = query.all()
                
                return [
                    {
                        "id": r.id,
                        "session_id": r.session_id,
                        "request_type": r.request_type,
                        "request_data": r.request_data,
                        "created_at": r.created_at.isoformat(),
                    }
                    for r in records
                ]
        
        return await asyncio.to_thread(_sync_query, session_id)
    
    async def process_approval_decision(
        self,
        approval_id: int,
        approved: bool,
        decided_by: int,
        comment: Optional[str] = None,
    ) -> Optional[RunState]:
        """
        Process approval decision and return resumable RunState (async-safe, thread-safe).
        
        Creates a new DB session inside the thread pool to avoid
        thread-safety issues with SQLAlchemy sessions.
        
        Returns:
            RunState ready to resume, or None if not found
        """
        def _sync_process(
            p_approval_id: int,
            p_approved: bool,
            p_decided_by: int,
            p_comment: Optional[str],
        ):
            from app.models.models import Approval
            from app.db.session import SessionLocal
            
            # Create new session for this thread (SQLAlchemy sessions are not thread-safe)
            with SessionLocal() as db:
                record = db.query(Approval).filter(Approval.id == p_approval_id).first()
                
                if record is None:
                    logger.warning(f"Approval record {p_approval_id} not found")
                    return None
                
                if record.approved is not None:
                    logger.warning(f"Approval record {p_approval_id} already processed")
                    return None
                
                # Update record
                record.approved = 1 if p_approved else 0
                record.responded_at = datetime.now(timezone.utc)
                
                # Store decision metadata
                request_data = record.request_data or {}
                request_data["decision_by"] = p_decided_by
                request_data["decision_comment"] = p_comment
                record.request_data = request_data
                
                db.commit()
                
                return request_data.get("run_state_json")
        
        run_state_json = await asyncio.to_thread(
            _sync_process, approval_id, approved, decided_by, comment
        )
        
        if run_state_json is None:
            return None
        
        # Restore RunState (not DB operation, can be sync)
        try:
            run_state = RunState.from_json(run_state_json)
            run_state.resume_after_approval(approved, comment)
            
            logger.info(
                f"Processed approval {approval_id}: {'approved' if approved else 'rejected'}",
                extra={
                    "approval_id": approval_id,
                    "run_id": run_state.run_id,
                    "approved": approved,
                }
            )
            
            return run_state
            
        except Exception as e:
            logger.error(f"Failed to restore run state from approval {approval_id}: {e}")
            return None
    
    def build_pending_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        tool_call_id: str,
    ) -> PendingToolCall:
        """Build a PendingToolCall with risk classification."""
        risk_level = self.classify_risk(tool_name, arguments)
        
        # Generate reason based on tool
        tool_lower = tool_name.lower()
        if "delete" in tool_lower or "remove" in tool_lower:
            reason = f"Destructive operation: {tool_name} will permanently remove data"
        elif "update" in tool_lower or "modify" in tool_lower:
            reason = f"Modification: {tool_name} will change existing data"
        elif "create" in tool_lower or "insert" in tool_lower:
            reason = f"Create operation: {tool_name} will add new data"
        else:
            reason = f"Write operation: {tool_name} requires approval"
        
        return PendingToolCall(
            tool_name=tool_name,
            arguments=arguments,
            tool_call_id=tool_call_id,
            reason=reason,
            risk_level=risk_level,
        )


# Singleton approval service (thread-safe)
_approval_service: Optional[ApprovalService] = None
_approval_service_lock = threading.Lock()


def get_approval_service(db_session=None) -> ApprovalService:
    """
    Get or create the global approval service (thread-safe).
    
    Note: Returns a new instance if db_session is provided to avoid
    mutating the singleton's db session which would be thread-unsafe.
    """
    global _approval_service
    
    # If caller provides a db_session, return a fresh instance
    # to avoid thread-unsafe mutation of singleton state
    if db_session is not None:
        return ApprovalService(db_session)
    
    # Fast path: already initialized
    if _approval_service is not None:
        return _approval_service
    
    # Slow path: double-checked locking
    with _approval_service_lock:
        if _approval_service is None:
            _approval_service = ApprovalService(None)
    return _approval_service


def reset_approval_service():
    """Reset the global approval service (for testing)."""
    global _approval_service
    with _approval_service_lock:
        _approval_service = None
