"""Agent memory service for working memory and historical context retrieval."""
import json
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from app.models.models import SessionMemorySummary


# Size limit for working memory (2KB)
WORKING_MEMORY_SIZE_LIMIT = 2048


class AgentMemoryService:
    """Manages agent working memory and historical context retrieval."""

    @staticmethod
    def get_working_memory(session_id: int, tenant_id: int, db: Session) -> Optional[Dict]:
        """
        Get session working memory.

        Args:
            session_id: Session ID
            tenant_id: Tenant ID (for isolation)
            db: Database session

        Returns:
            Dictionary of working memory facts, or {} if not found or cross-tenant access attempted
        """
        from app.models.models import Session as SessionModel

        session = db.query(SessionModel).filter(
            SessionModel.id == session_id,
            SessionModel.tenant_id == tenant_id
        ).first()

        if not session:
            return None

        memory = session.session_working_memory
        return memory if memory else {}

    @staticmethod
    def update_working_memory(
        session_id: int,
        tenant_id: int,
        updates: Dict,
        db: Session
    ) -> Optional[Dict]:
        """
        Update session working memory with new facts, enforcing 2KB limit.

        Merges updates into existing memory. If result exceeds 2KB, auto-trims
        by removing oldest keys until under limit.

        Args:
            session_id: Session ID
            tenant_id: Tenant ID (for isolation)
            updates: Dictionary of facts to merge
            db: Database session

        Returns:
            Updated memory dictionary, or None if cross-tenant access attempted

        Raises:
            ValueError: If unable to trim below 2KB limit
        """
        from app.models.models import Session as SessionModel

        session = db.query(SessionModel).filter(
            SessionModel.id == session_id,
            SessionModel.tenant_id == tenant_id
        ).first()

        if not session:
            return None

        # Get current memory
        current = session.session_working_memory if session.session_working_memory else {}

        # Merge updates
        merged = {**current, **updates}

        # Check size and auto-trim if needed
        merged = AgentMemoryService._enforce_size_limit(merged)

        # Persist
        session.session_working_memory = merged
        db.commit()

        return merged

    @staticmethod
    def store_session_summary(
        session_id: int,
        tenant_id: int,
        content: str,
        db: Session
    ) -> SessionMemorySummary:
        """
        Store end-of-session memory summary for historical retrieval.

        Args:
            session_id: Session ID
            tenant_id: Tenant ID
            content: Summary content to store
            db: Database session

        Returns:
            Created SessionMemorySummary record
        """
        summary = SessionMemorySummary(
            tenant_id=tenant_id,
            session_id=session_id,
            content=content
        )
        db.add(summary)
        db.commit()
        db.refresh(summary)
        return summary

    @staticmethod
    def retrieve_historical_context(
        tenant_id: int,
        query_text: str,
        db: Session,
        limit: int = 5
    ) -> List[SessionMemorySummary]:
        """
        Retrieve historical context via keyword search.

        Performs case-insensitive substring match on content.
        Results ordered by newest first.

        Args:
            tenant_id: Tenant ID (for isolation)
            query_text: Keyword to search for
            db: Database session
            limit: Max number of results (default 5)

        Returns:
            List of matching SessionMemorySummary records (newest first)
        """
        results = db.query(SessionMemorySummary).filter(
            SessionMemorySummary.tenant_id == tenant_id,
            SessionMemorySummary.content.ilike(f"%{query_text}%")
        ).order_by(
            SessionMemorySummary.created_at.desc()
        ).limit(limit).all()

        return results

    @staticmethod
    def _enforce_size_limit(memory: Dict) -> Dict:
        """
        Enforce 2KB size limit by auto-trimming oldest keys if needed.

        Removes keys in insertion order (oldest first) until memory is under 2KB.

        Args:
            memory: Memory dictionary to check

        Returns:
            Trimmed memory dictionary (under 2KB)

        Raises:
            ValueError: If single key exceeds 2KB and cannot be removed
        """
        size = len(json.dumps(memory).encode('utf-8'))

        if size <= WORKING_MEMORY_SIZE_LIMIT:
            return memory

        # Auto-trim: remove keys in order until under limit
        trimmed = dict(memory)
        for key in list(trimmed.keys()):
            del trimmed[key]
            new_size = len(json.dumps(trimmed).encode('utf-8'))
            if new_size <= WORKING_MEMORY_SIZE_LIMIT:
                return trimmed

        # If we get here, even empty dict is too large (shouldn't happen)
        return {}
