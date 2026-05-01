import os
from typing import Optional
from langfuse import Langfuse


class LangfuseConfig:
    """Singleton for Langfuse client and callback configuration.

    Usage:
        handler = LangfuseConfig.get_callback_handler(
            user_id="user_123",
            session_id="session_456",
            trace_name="onboarding_workflow"
        )

        # Use in LangGraph
        config = RunnableConfig(callbacks=[handler] if handler else [])
    """

    _instance: Optional[Langfuse] = None

    @classmethod
    def get_instance(cls) -> Optional[Langfuse]:
        """Get or create Langfuse client singleton.

        Returns:
            Langfuse client if enabled, None otherwise
        """
        if not cls._is_enabled():
            return None

        if cls._instance is None:
            cls._instance = Langfuse(
                public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
                secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
                host=os.getenv("LANGFUSE_HOST", "http://localhost:3000")
            )

        return cls._instance

    @classmethod
    def get_callback_handler(
        cls,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        trace_name: Optional[str] = None
    ) -> Optional[dict]:
        """Create callback configuration for tracing.

        Args:
            user_id: User ID for trace grouping
            session_id: Session ID for trace grouping
            trace_name: Human-readable trace name

        Returns:
            Dictionary with trace metadata if Langfuse is enabled, None otherwise
        """
        if not cls._is_enabled():
            return None

        instance = cls.get_instance()
        if instance is None:
            return None

        # Return a configuration dictionary for trace tracking
        return {
            "user_id": user_id,
            "session_id": session_id,
            "trace_name": trace_name,
            "public_key": os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            "secret_key": os.getenv("LANGFUSE_SECRET_KEY", ""),
            "host": os.getenv("LANGFUSE_HOST", "http://localhost:3000")
        }

    @staticmethod
    def _is_enabled() -> bool:
        """Check if Langfuse is enabled via environment variable."""
        return os.getenv("LANGFUSE_ENABLED", "true").lower() == "true"