"""Ollama message validation and recovery.

Provides:
- Never call model with empty messages
- Rebuild from persisted state where possible
- Fail with recoverable context-lost error
- Log failed runs to DB with bounded in-memory LRU cache
"""
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from collections import OrderedDict
import logging
import json
import threading

logger = logging.getLogger(__name__)

# LRU cache size for in-memory failed runs
FAILED_RUNS_CACHE_SIZE = 100


class MessageValidationError(Exception):
    """Exception raised when message validation fails."""
    
    def __init__(
        self,
        message: str,
        error_type: str,
        recoverable: bool = False,
        recovery_hint: Optional[str] = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.recoverable = recoverable
        self.recovery_hint = recovery_hint


class MessageRole(Enum):
    """Valid message roles."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ValidationResult:
    """Result of message validation."""
    valid: bool
    errors: List[str]
    warnings: List[str]
    sanitized_messages: List[Dict[str, Any]]
    recovery_applied: bool = False
    recovery_details: Optional[str] = None


@dataclass
class FailedRunLog:
    """Log entry for a failed run due to validation issues."""
    session_id: int
    run_id: Optional[str]
    error_type: str
    error_message: str
    original_message_count: int
    timestamp: str
    context: Dict[str, Any]


class OllamaMessageValidator:
    """
    Validates and sanitizes messages for Ollama API.
    
    Responsibilities:
    - Validate message structure
    - Ensure non-empty message list
    - Validate role sequences
    - Sanitize content
    - Attempt recovery from invalid state
    - Log failed runs to DB with bounded LRU cache
    """
    
    def __init__(self, db_session=None):
        self.db = db_session
        # Use OrderedDict for LRU behavior
        self._failed_runs_cache: OrderedDict[str, FailedRunLog] = OrderedDict()
        self._cache_lock = threading.Lock()
    
    # =========================================================================
    # Validation
    # =========================================================================
    
    def validate_messages(
        self,
        messages: List[Dict[str, Any]],
        session_id: Optional[int] = None,
        run_id: Optional[str] = None,
    ) -> ValidationResult:
        """
        Validate messages for Ollama API call.
        
        Args:
            messages: List of message dictionaries
            session_id: Optional session ID for logging
            run_id: Optional run ID for logging
        
        Returns:
            ValidationResult with sanitized messages
        """
        errors: List[str] = []
        warnings: List[str] = []
        sanitized: List[Dict[str, Any]] = []
        recovery_applied = False
        recovery_details = None
        
        # Check empty messages
        if not messages:
            errors.append("Messages list is empty")
            self._log_failed_run(
                session_id=session_id or 0,
                run_id=run_id,
                error_type="empty_messages",
                error_message="Messages list is empty",
                message_count=0,
                context={}
            )
            return ValidationResult(
                valid=False,
                errors=errors,
                warnings=warnings,
                sanitized_messages=[],
                recovery_applied=False,
            )
        
        # Validate each message
        for i, msg in enumerate(messages):
            msg_errors, msg_warnings, sanitized_msg = self._validate_single_message(msg, i)
            errors.extend(msg_errors)
            warnings.extend(msg_warnings)
            
            if sanitized_msg:
                sanitized.append(sanitized_msg)
        
        # Check if we still have messages after sanitization
        if not sanitized:
            errors.append("No valid messages after sanitization")
            self._log_failed_run(
                session_id=session_id or 0,
                run_id=run_id,
                error_type="no_valid_messages",
                error_message="All messages failed validation",
                message_count=len(messages),
                context={"original_errors": errors[:5]}
            )
            return ValidationResult(
                valid=False,
                errors=errors,
                warnings=warnings,
                sanitized_messages=[],
            )
        
        # Validate message sequence
        seq_errors, seq_warnings = self._validate_message_sequence(sanitized)
        errors.extend(seq_errors)
        warnings.extend(seq_warnings)
        
        # Check for required user message
        has_user_message = any(m.get("role") == "user" for m in sanitized)
        if not has_user_message:
            errors.append("Messages must contain at least one user message")
            
            # Attempt recovery if we have persisted state
            if session_id and self.db:
                recovered_messages = self._attempt_recovery_from_db(session_id)
                if recovered_messages:
                    sanitized = recovered_messages
                    recovery_applied = True
                    recovery_details = "Recovered messages from database"
                    errors = []  # Clear errors if recovery successful
                    warnings.append("Messages recovered from persisted state")
        
        valid = len(errors) == 0
        
        if not valid:
            self._log_failed_run(
                session_id=session_id or 0,
                run_id=run_id,
                error_type="validation_failed",
                error_message="; ".join(errors),
                message_count=len(messages),
                context={"errors": errors, "warnings": warnings}
            )
        
        return ValidationResult(
            valid=valid,
            errors=errors,
            warnings=warnings,
            sanitized_messages=sanitized,
            recovery_applied=recovery_applied,
            recovery_details=recovery_details,
        )
    
    def _validate_single_message(
        self,
        msg: Dict[str, Any],
        index: int,
    ) -> Tuple[List[str], List[str], Optional[Dict[str, Any]]]:
        """Validate a single message."""
        errors: List[str] = []
        warnings: List[str] = []
        
        # Check required fields
        if not isinstance(msg, dict):
            errors.append(f"Message {index}: not a dictionary")
            return errors, warnings, None
        
        # Validate role
        role = msg.get("role")
        if not role:
            errors.append(f"Message {index}: missing 'role' field")
            return errors, warnings, None
        
        valid_roles = ["system", "user", "assistant", "tool"]
        if role not in valid_roles:
            errors.append(f"Message {index}: invalid role '{role}', must be one of {valid_roles}")
            return errors, warnings, None
        
        # Validate content
        content = msg.get("content")
        
        # Tool messages need tool_call_id
        if role == "tool":
            tool_call_id = msg.get("tool_call_id")
            if not tool_call_id:
                errors.append(f"Message {index}: tool message missing 'tool_call_id'")
                return errors, warnings, None
            
            # Tool content can be empty/None if there was an error
            if content is None:
                content = ""
                warnings.append(f"Message {index}: tool message has empty content")
        
        # Assistant messages can have empty content if they have tool_calls
        elif role == "assistant":
            tool_calls = msg.get("tool_calls")
            if not content and not tool_calls:
                warnings.append(f"Message {index}: assistant message has no content and no tool_calls")
                content = ""  # Allow empty but warn
        
        # User and system messages need content
        else:
            if content is None or (isinstance(content, str) and not content.strip()):
                errors.append(f"Message {index}: {role} message has empty content")
                return errors, warnings, None
        
        # Build sanitized message
        sanitized: Dict[str, Any] = {
            "role": role,
            "content": str(content) if content else "",
        }
        
        # Preserve tool_calls for assistant messages
        if role == "assistant" and msg.get("tool_calls"):
            sanitized["tool_calls"] = msg["tool_calls"]
        
        # Preserve tool_call_id for tool messages
        if role == "tool" and msg.get("tool_call_id"):
            sanitized["tool_call_id"] = msg["tool_call_id"]
        
        return errors, warnings, sanitized
    
    def _validate_message_sequence(
        self,
        messages: List[Dict[str, Any]],
    ) -> Tuple[List[str], List[str]]:
        """Validate message sequence (order and pairing)."""
        errors: List[str] = []
        warnings: List[str] = []
        
        # Check system message is first (if present)
        has_system = any(m.get("role") == "system" for m in messages)
        if has_system and messages[0].get("role") != "system":
            warnings.append("System message should be first in conversation")
        
        # Check tool messages follow assistant with tool_calls
        for i, msg in enumerate(messages):
            if msg.get("role") == "tool":
                # Find preceding assistant message with matching tool_call_id
                tool_call_id = msg.get("tool_call_id")
                found_call = False
                
                for j in range(i - 1, -1, -1):
                    prev = messages[j]
                    if prev.get("role") == "assistant":
                        tool_calls = prev.get("tool_calls", [])
                        for tc in tool_calls:
                            if tc.get("id") == tool_call_id:
                                found_call = True
                                break
                        break
                
                if not found_call:
                    warnings.append(
                        f"Tool message at {i} has no matching tool_call "
                        f"(tool_call_id: {tool_call_id})"
                    )
        
        return errors, warnings
    
    # =========================================================================
    # Recovery
    # =========================================================================
    
    def _attempt_recovery_from_db(
        self,
        session_id: int,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Attempt to recover messages from database.
        
        Args:
            session_id: Session to recover from
        
        Returns:
            Recovered messages or None
        """
        if self.db is None:
            return None
        
        try:
            from app.models.models import Message as MessageModel, Session as SessionModel
            
            # Get session
            session = self.db.query(SessionModel).filter(
                SessionModel.id == session_id
            ).first()
            
            if not session:
                logger.warning(f"Cannot recover - session {session_id} not found")
                return None
            
            # Get recent messages
            db_messages = self.db.query(MessageModel).filter(
                MessageModel.session_id == session_id
            ).order_by(MessageModel.created_at.desc()).limit(20).all()
            
            if not db_messages:
                logger.warning(f"Cannot recover - no messages in session {session_id}")
                return None
            
            # Convert to format
            recovered = []
            for msg in reversed(db_messages):  # Oldest first
                recovered.append({
                    "role": msg.role.value if hasattr(msg.role, "value") else str(msg.role),
                    "content": msg.content,
                })
            
            logger.info(
                f"Recovered {len(recovered)} messages from session {session_id}"
            )
            
            return recovered
            
        except Exception as e:
            logger.error(f"Message recovery failed: {e}")
            return None
    
    def rebuild_from_run_state(
        self,
        run_state_json: str,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Rebuild messages from serialized RunState.
        
        Args:
            run_state_json: Serialized RunState
        
        Returns:
            Reconstructed messages or None
        """
        try:
            from app.services.run_state import RunState
            
            run_state = RunState.from_json(run_state_json)
            
            if run_state.messages:
                logger.info(
                    f"Rebuilt {len(run_state.messages)} messages from RunState"
                )
                return run_state.messages
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to rebuild from RunState: {e}")
            return None
    
    # =========================================================================
    # Logging
    # =========================================================================
    
    def _log_failed_run(
        self,
        session_id: int,
        run_id: Optional[str],
        error_type: str,
        error_message: str,
        message_count: int,
        context: Dict[str, Any],
    ):
        """
        Log a failed run to both in-memory LRU cache and database.
        
        Uses bounded LRU cache in memory for fast access.
        Persists to DB for durability and analytics.
        """
        timestamp = datetime.now(timezone.utc)
        log_entry = FailedRunLog(
            session_id=session_id,
            run_id=run_id,
            error_type=error_type,
            error_message=error_message,
            original_message_count=message_count,
            timestamp=timestamp.isoformat(),
            context=context,
        )
        
        # Add to LRU cache (thread-safe)
        cache_key = f"{session_id}:{run_id}:{timestamp.isoformat()}"
        with self._cache_lock:
            # Move to end if exists, or add
            self._failed_runs_cache[cache_key] = log_entry
            self._failed_runs_cache.move_to_end(cache_key)
            
            # Evict oldest if over capacity
            while len(self._failed_runs_cache) > FAILED_RUNS_CACHE_SIZE:
                self._failed_runs_cache.popitem(last=False)
        
        # Persist to DB if session available
        if self.db is not None:
            try:
                from app.models.models import FailedRun
                
                db_entry = FailedRun(
                    session_id=session_id if session_id else None,
                    run_id=run_id,
                    error_type=error_type,
                    error_message=error_message,
                    original_message_count=message_count,
                    context=context,
                    created_at=timestamp,
                )
                self.db.add(db_entry)
                self.db.commit()
            except Exception as e:
                logger.warning(f"Failed to persist failed run to DB: {e}")
                # Don't fail - in-memory logging still worked
        
        logger.error(
            f"Message validation failed",
            extra={
                "session_id": session_id,
                "run_id": run_id,
                "error_type": error_type,
                "error_message": error_message,
                "message_count": message_count,
            }
        )
    
    def get_failed_runs(
        self,
        session_id: Optional[int] = None,
        limit: int = 20,
        from_db: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get recent failed run logs.
        
        Args:
            session_id: Optional filter by session
            limit: Max number of results
            from_db: If True, query DB instead of cache
        """
        if from_db and self.db is not None:
            return self._get_failed_runs_from_db(session_id, limit)
        
        # Get from in-memory LRU cache
        with self._cache_lock:
            runs = list(self._failed_runs_cache.values())
        
        if session_id:
            runs = [r for r in runs if r.session_id == session_id]
        
        return [
            {
                "session_id": r.session_id,
                "run_id": r.run_id,
                "error_type": r.error_type,
                "error_message": r.error_message,
                "message_count": r.original_message_count,
                "timestamp": r.timestamp,
            }
            for r in runs[-limit:]
        ]
    
    def _get_failed_runs_from_db(
        self,
        session_id: Optional[int],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Query failed runs from database."""
        try:
            from app.models.models import FailedRun
            
            query = self.db.query(FailedRun).order_by(FailedRun.created_at.desc())
            
            if session_id:
                query = query.filter(FailedRun.session_id == session_id)
            
            query = query.limit(limit)
            
            return [
                {
                    "session_id": r.session_id,
                    "run_id": r.run_id,
                    "error_type": r.error_type,
                    "error_message": r.error_message,
                    "message_count": r.original_message_count,
                    "timestamp": r.created_at.isoformat() if r.created_at else None,
                }
                for r in query.all()
            ]
        except Exception as e:
            logger.warning(f"Failed to query failed runs from DB: {e}")
            return []
    
    # =========================================================================
    # Convenience methods
    # =========================================================================
    
    def ensure_valid_messages(
        self,
        messages: List[Dict[str, Any]],
        session_id: Optional[int] = None,
        run_id: Optional[str] = None,
        allow_recovery: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Validate messages and raise if invalid (with recovery attempt).
        
        Args:
            messages: Messages to validate
            session_id: Session ID for recovery
            run_id: Run ID for logging
            allow_recovery: Whether to attempt recovery
        
        Returns:
            Validated/sanitized messages
        
        Raises:
            MessageValidationError: If validation fails
        """
        result = self.validate_messages(messages, session_id, run_id)
        
        if result.valid:
            return result.sanitized_messages
        
        # Try recovery if enabled
        if allow_recovery and session_id and self.db:
            recovered = self._attempt_recovery_from_db(session_id)
            if recovered:
                # Re-validate recovered messages
                retry_result = self.validate_messages(recovered, session_id, run_id)
                if retry_result.valid:
                    return retry_result.sanitized_messages
        
        # Determine if error is recoverable
        recoverable = session_id is not None and self.db is not None
        
        raise MessageValidationError(
            message="; ".join(result.errors),
            error_type="context_lost" if "empty" in str(result.errors).lower() else "validation_failed",
            recoverable=recoverable,
            recovery_hint=(
                "Session messages may be recoverable from database"
                if recoverable else None
            ),
        )
    
    def create_minimal_context(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Create minimal valid context when full context unavailable.
        
        Used as fallback when recovery fails.
        """
        messages: List[Dict[str, Any]] = []
        
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt,
            })
        
        messages.append({
            "role": "user",
            "content": user_message,
        })
        
        return messages


# Singleton validator (thread-safe)
_message_validator: Optional[OllamaMessageValidator] = None
_message_validator_lock = threading.Lock()


def get_message_validator(db_session=None) -> OllamaMessageValidator:
    """
    Get or create the global message validator (thread-safe).
    
    Note: Returns a new instance if db_session is provided to avoid
    mutating the singleton's db session which would be thread-unsafe.
    """
    global _message_validator
    
    # If caller provides a db_session, return a fresh instance
    # to avoid thread-unsafe mutation of singleton state
    if db_session is not None:
        return OllamaMessageValidator(db_session)
    
    # Fast path: already initialized
    if _message_validator is not None:
        return _message_validator
    
    # Slow path: double-checked locking
    with _message_validator_lock:
        if _message_validator is None:
            _message_validator = OllamaMessageValidator(None)
    return _message_validator


def reset_message_validator():
    """Reset the global message validator (for testing)."""
    global _message_validator
    with _message_validator_lock:
        _message_validator = None
