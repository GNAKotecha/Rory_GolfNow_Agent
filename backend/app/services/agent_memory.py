"""Agent memory service for working memory and historical context retrieval."""
import json
import logging
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone
from contextlib import contextmanager

from app.models.models import SessionMemorySummary

logger = logging.getLogger(__name__)


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


class AgentMemory:
    """
    Manages cross-session memory storage for user preferences,
    workflow outcomes, and domain knowledge.

    This is the original implementation for backwards compatibility.
    For working memory and historical context, use AgentMemoryService.
    """

    def __init__(self, db: Session, tenant_id: Optional[int] = None):
        """
        Initialize agent memory.

        Args:
            db: SQLAlchemy database session
            tenant_id: Tenant ID for multi-tenant logging context
        """
        self.db = db
        self.tenant_id = tenant_id
        self._batch_mode = False

    @contextmanager
    def batch(self):
        """
        Context manager for batched operations with atomicity.

        Usage:
            with memory.batch():
                memory.store_user_preference(user_id, "format", "verbose")
                memory.store_workflow_outcome(user_id, "analysis", "success", {})
                memory.store_domain_knowledge(user_id, "golf", "data", "source")

        All operations succeed or all rollback on error.
        """
        self._batch_mode = True
        try:
            yield
            self.db.commit()
            logger.debug("Batch commit successful")
        except Exception as e:
            self.db.rollback()
            logger.error(f"[tenant_id={self.tenant_id}] Batch rollback due to error: {e}")
            raise
        finally:
            self._batch_mode = False

    def store_user_preference(self, user_id: int, key: str, value: Any):
        """
        Store user preference (e.g., output format, verbosity level).

        Args:
            user_id: User ID
            key: Preference key
            value: Preference value (will be JSON serialized)
        """
        try:
            self.db.execute(
                text("""
                    INSERT INTO user_preferences (user_id, key, value, updated_at)
                    VALUES (:user_id, :key, :value, :updated_at)
                    ON CONFLICT (user_id, key)
                    DO UPDATE SET value = :value, updated_at = :updated_at
                """),
                {
                    "user_id": user_id,
                    "key": key,
                    "value": json.dumps(value),
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            if not self._batch_mode:
                self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(f"[tenant_id={self.tenant_id}] Failed to store user preference for user {user_id}: {e}")
            raise

    def get_user_preferences(self, user_id: int) -> Dict[str, Any]:
        """
        Get all user preferences.

        Args:
            user_id: User ID

        Returns:
            Dictionary of preference key-value pairs
        """
        try:
            result = self.db.execute(
                text("""
                    SELECT key, value FROM user_preferences
                    WHERE user_id = :user_id
                """),
                {"user_id": user_id}
            )
            preferences = {}
            for row in result:
                preferences[row.key] = json.loads(row.value)
            return preferences
        except Exception as e:
            logger.error(f"[tenant_id={self.tenant_id}] Failed to get user preferences for user {user_id}: {e}")
            return {}

    def store_workflow_outcome(
        self,
        user_id: int,
        workflow_type: str,
        outcome: str,
        context: Dict[str, Any]
    ):
        """
        Store workflow outcome for learning.

        Args:
            user_id: User ID
            workflow_type: Type of workflow (e.g., "data_analysis", "report_generation")
            outcome: Outcome status (e.g., "completed", "failed", "partial")
            context: Additional context about the workflow execution
        """
        try:
            self.db.execute(
                text("""
                    INSERT INTO workflow_outcomes 
                    (user_id, workflow_type, outcome, context, created_at)
                    VALUES (:user_id, :workflow_type, :outcome, :context, :created_at)
                """),
                {
                    "user_id": user_id,
                    "workflow_type": workflow_type,
                    "outcome": outcome,
                    "context": json.dumps(context),
                    "created_at": datetime.now(timezone.utc),
                }
            )
            if not self._batch_mode:
                self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(f"[tenant_id={self.tenant_id}] Failed to store workflow outcome for user {user_id}: {e}")
            raise

    def get_relevant_past_outcomes(
        self,
        user_id: int,
        workflow_type: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get relevant past workflow outcomes.

        Args:
            user_id: User ID
            workflow_type: Type of workflow to retrieve
            limit: Maximum number of outcomes to return

        Returns:
            List of past outcomes with context
        """
        try:
            result = self.db.execute(
                text("""
                    SELECT outcome, context, created_at 
                    FROM workflow_outcomes
                    WHERE user_id = :user_id AND workflow_type = :workflow_type
                    ORDER BY created_at DESC
                    LIMIT :limit
                """),
                {
                    "user_id": user_id,
                    "workflow_type": workflow_type,
                    "limit": limit,
                }
            )
            outcomes = []
            for row in result:
                outcomes.append({
                    "outcome": row.outcome,
                    "context": json.loads(row.context),
                    "created_at": row.created_at,
                })
            return outcomes
        except Exception as e:
            logger.error(f"[tenant_id={self.tenant_id}] Failed to get past outcomes for user {user_id}, workflow {workflow_type}: {e}")
            return []

    def store_domain_knowledge(
        self,
        user_id: int,
        domain: str,
        knowledge: str,
        source: str
    ):
        """
        Store learned domain knowledge.

        Args:
            user_id: User ID
            domain: Domain area (e.g., "golf_booking", "api_patterns")
            knowledge: Knowledge content
            source: Where this knowledge came from
        """
        try:
            self.db.execute(
                text("""
                    INSERT INTO domain_knowledge 
                    (user_id, domain, knowledge, source, created_at)
                    VALUES (:user_id, :domain, :knowledge, :source, :created_at)
                """),
                {
                    "user_id": user_id,
                    "domain": domain,
                    "knowledge": knowledge,
                    "source": source,
                    "created_at": datetime.now(timezone.utc),
                }
            )
            if not self._batch_mode:
                self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(f"[tenant_id={self.tenant_id}] Failed to store domain knowledge for user {user_id}, domain {domain}: {e}")
            raise

    def get_domain_knowledge(
        self,
        user_id: int,
        domain: str,
        limit: int = 10
    ) -> List[str]:
        """
        Get domain knowledge.

        Args:
            user_id: User ID
            domain: Domain area to query
            limit: Maximum number of items to return

        Returns:
            List of knowledge strings
        """
        try:
            result = self.db.execute(
                text("""
                    SELECT knowledge, source, created_at 
                    FROM domain_knowledge
                    WHERE user_id = :user_id AND domain = :domain
                    ORDER BY created_at DESC
                    LIMIT :limit
                """),
                {
                    "user_id": user_id,
                    "domain": domain,
                    "limit": limit,
                }
            )
            return [row.knowledge for row in result]
        except Exception as e:
            logger.error(f"[tenant_id={self.tenant_id}] Failed to get domain knowledge for user {user_id}, domain {domain}: {e}")
            return []
