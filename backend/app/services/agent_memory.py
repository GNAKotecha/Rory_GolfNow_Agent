"""Cross-session memory for agent personalization."""
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone
from contextlib import contextmanager
import json
import logging

logger = logging.getLogger(__name__)


class AgentMemory:
    """Manages cross-session memory storage."""

    def __init__(self, db: Session):
        """
        Initialize agent memory.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
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
            logger.error(f"Batch rollback due to error: {e}")
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

            logger.info(
                f"Stored user preference: {key}",
                extra={"user_id": user_id, "key": key}
            )
        except Exception as e:
            logger.error(f"Failed to store user preference: {e}")
            if not self._batch_mode:
                self.db.rollback()
            raise

    def get_user_preferences(self, user_id: int) -> Dict[str, Any]:
        """
        Retrieve all user preferences.

        Args:
            user_id: User ID

        Returns:
            Dictionary of preferences
        """
        try:
            result = self.db.execute(
                text("SELECT key, value FROM user_preferences WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            return {row.key: json.loads(row.value) for row in result}
        except Exception as e:
            logger.error(f"Failed to get user preferences: {e}")
            return {}

    def store_workflow_outcome(
        self,
        user_id: int,
        workflow_type: str,
        outcome: str,
        context: Dict[str, Any]
    ):
        """
        Store outcome of a workflow (for learning patterns).

        Args:
            user_id: User ID
            workflow_type: Type of workflow
            outcome: Outcome status
            context: Additional context information
        """
        try:
            self.db.execute(
                text("""
                    INSERT INTO workflow_memory (user_id, workflow_type, outcome, context, created_at)
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

            logger.info(
                f"Stored workflow outcome",
                extra={
                    "user_id": user_id,
                    "workflow_type": workflow_type,
                    "outcome": outcome
                }
            )
        except Exception as e:
            logger.error(f"Failed to store workflow outcome: {e}")
            if not self._batch_mode:
                self.db.rollback()
            raise

    def get_relevant_past_outcomes(
        self,
        user_id: int,
        workflow_type: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant past outcomes for context.

        Args:
            user_id: User ID
            workflow_type: Type of workflow
            limit: Maximum number of results

        Returns:
            List of past workflow outcomes
        """
        try:
            result = self.db.execute(
                text("""
                    SELECT outcome, context, created_at
                    FROM workflow_memory
                    WHERE user_id = :user_id AND workflow_type = :workflow_type
                    ORDER BY created_at DESC
                    LIMIT :limit
                """),
                {"user_id": user_id, "workflow_type": workflow_type, "limit": limit}
            )

            return [
                {
                    "outcome": row.outcome,
                    "context": json.loads(row.context),
                    "created_at": row.created_at,
                }
                for row in result
            ]
        except Exception as e:
            logger.error(f"Failed to get past outcomes: {e}")
            return []

    def store_domain_knowledge(
        self,
        user_id: int,
        domain: str,
        knowledge: str,
        source: str
    ):
        """
        Store domain-specific knowledge discovered during execution.

        Args:
            user_id: User ID
            domain: Domain category
            knowledge: Knowledge content
            source: Source of knowledge
        """
        try:
            self.db.execute(
                text("""
                    INSERT INTO domain_knowledge (user_id, domain, knowledge, source, created_at)
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

            logger.info(
                f"Stored domain knowledge",
                extra={"user_id": user_id, "domain": domain}
            )
        except Exception as e:
            logger.error(f"Failed to store domain knowledge: {e}")
            if not self._batch_mode:
                self.db.rollback()
            raise

    def get_domain_knowledge(
        self,
        user_id: int,
        domain: str,
        limit: int = 10
    ) -> List[str]:
        """
        Retrieve domain knowledge for context injection.

        Args:
            user_id: User ID
            domain: Domain category
            limit: Maximum number of results

        Returns:
            List of knowledge items
        """
        try:
            result = self.db.execute(
                text("""
                    SELECT knowledge
                    FROM domain_knowledge
                    WHERE user_id = :user_id AND domain = :domain
                    ORDER BY created_at DESC
                    LIMIT :limit
                """),
                {"user_id": user_id, "domain": domain, "limit": limit}
            )
            return [row.knowledge for row in result]
        except Exception as e:
            logger.error(f"Failed to get domain knowledge: {e}")
            return []
