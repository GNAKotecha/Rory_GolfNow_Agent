"""
Session-Scoped Tool Approval Cache

Provides session-level caching for tool approvals.
Once a user approves a tool, subsequent calls skip approval for that session.
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.models import SessionToolApproval

logger = logging.getLogger(__name__)


def compute_pattern_hash(pattern: Optional[dict]) -> str:
    """
    Compute a stable hash for an approval pattern.
    
    Args:
        pattern: Dict pattern or None for "any arguments"
        
    Returns:
        64-character hex hash string
    """
    if pattern is None:
        return hashlib.sha256(b"__null__").hexdigest()
    
    # Sort keys for stable serialization
    serialized = json.dumps(pattern, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(serialized.encode()).hexdigest()


def has_session_approval(
    db: Session,
    session_id: int,
    tool_name: str,
    pattern: Optional[dict] = None,
) -> bool:
    """
    Check if a tool has been approved for this session.
    
    Args:
        db: Database session
        session_id: Chat session ID
        tool_name: Name of the tool
        pattern: Optional pattern dict for contextual matching
        
    Returns:
        True if tool is approved for this session
    """
    pattern_hash = compute_pattern_hash(pattern)
    
    # Check for exact pattern match
    result = db.query(SessionToolApproval.id).filter(
        SessionToolApproval.session_id == session_id,
        SessionToolApproval.tool_name == tool_name,
        SessionToolApproval.pattern_hash == pattern_hash,
    ).first()
    
    if result is not None:
        return True
    
    # Also check for wildcard approval (pattern_hash == null hash)
    # If user approved "any" arguments, it covers all patterns
    null_hash = compute_pattern_hash(None)
    if pattern_hash != null_hash:
        result = db.query(SessionToolApproval.id).filter(
            SessionToolApproval.session_id == session_id,
            SessionToolApproval.tool_name == tool_name,
            SessionToolApproval.pattern_hash == null_hash,
        ).first()
        if result is not None:
            return True
    
    return False


def grant_session_approval(
    db: Session,
    session_id: int,
    tool_name: str,
    user_id: int,
    pattern: Optional[dict] = None,
) -> SessionToolApproval:
    """
    Grant approval for a tool in this session.
    
    Args:
        db: Database session
        session_id: Chat session ID
        tool_name: Name of the tool
        user_id: User granting approval
        pattern: Optional pattern dict for contextual matching
        
    Returns:
        The created or existing approval record
    """
    pattern_hash = compute_pattern_hash(pattern)
    
    # Check if already exists
    existing = db.query(SessionToolApproval).filter(
        SessionToolApproval.session_id == session_id,
        SessionToolApproval.tool_name == tool_name,
        SessionToolApproval.pattern_hash == pattern_hash,
    ).first()
    
    if existing:
        return existing
    
    # Create new approval
    approval = SessionToolApproval(
        session_id=session_id,
        tool_name=tool_name,
        approval_pattern=pattern,
        pattern_hash=pattern_hash,
        approved_at=datetime.utcnow(),
        approved_by=user_id,
    )
    
    db.add(approval)
    db.commit()
    db.refresh(approval)
    
    logger.info(
        f"Session approval granted: tool={tool_name}, session={session_id}",
        extra={
            "session_id": session_id,
            "tool_name": tool_name,
            "pattern_hash": pattern_hash[:16],
            "user_id": user_id,
        }
    )
    
    return approval


def revoke_session_approval(
    db: Session,
    session_id: int,
    tool_name: str,
    pattern: Optional[dict] = None,
) -> bool:
    """
    Revoke approval for a tool in this session.
    
    Args:
        db: Database session
        session_id: Chat session ID
        tool_name: Name of the tool
        pattern: Optional pattern dict (None revokes all patterns for tool)
        
    Returns:
        True if any approvals were revoked
    """
    if pattern is None:
        # Revoke all patterns for this tool
        result = db.query(SessionToolApproval).filter(
            SessionToolApproval.session_id == session_id,
            SessionToolApproval.tool_name == tool_name,
        ).delete()
    else:
        # Revoke specific pattern
        pattern_hash = compute_pattern_hash(pattern)
        result = db.query(SessionToolApproval).filter(
            SessionToolApproval.session_id == session_id,
            SessionToolApproval.tool_name == tool_name,
            SessionToolApproval.pattern_hash == pattern_hash,
        ).delete()
    
    db.commit()
    
    if result > 0:
        logger.info(
            f"Session approval revoked: tool={tool_name}, session={session_id}, count={result}",
            extra={"session_id": session_id, "tool_name": tool_name}
        )
    
    return result > 0


def get_session_approvals(
    db: Session,
    session_id: int,
) -> list[dict[str, Any]]:
    """
    Get all approvals for a session.
    
    Args:
        db: Database session
        session_id: Chat session ID
        
    Returns:
        List of approval records as dicts
    """
    approvals = db.query(SessionToolApproval).filter(
        SessionToolApproval.session_id == session_id
    ).order_by(SessionToolApproval.approved_at).all()
    
    return [
        {
            "id": a.id,
            "tool_name": a.tool_name,
            "approval_pattern": a.approval_pattern,
            "approved_at": a.approved_at.isoformat(),
            "approved_by": a.approved_by,
        }
        for a in approvals
    ]


def extract_approval_pattern(tool_name: str, arguments: dict) -> Optional[dict]:
    """
    Extract the relevant pattern from tool arguments for caching.
    
    Different tools have different pattern strategies:
    - run_sql: database name
    - call_api: method + path prefix
    - Others: None (approve all uses)
    
    Args:
        tool_name: Name of the tool
        arguments: Tool arguments dict
        
    Returns:
        Pattern dict for caching, or None for wildcard approval
    """
    if tool_name == "run_sql":
        # Cache by database
        database = arguments.get("database")
        if database:
            return {"database": database}
        return None
    
    elif tool_name == "call_api":
        # Cache by method + path prefix
        method = arguments.get("method", "GET").upper()
        path = arguments.get("path", "")
        # Use first 50 chars of path for grouping
        path_prefix = path[:50] if len(path) > 50 else path
        return {"method": method, "path_prefix": path_prefix}
    
    # Default: wildcard approval for this tool
    return None
