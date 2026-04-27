"""Conversation summarization service.

Generates rolling summaries of conversation history using Ollama.
"""
from typing import List, Dict, Optional
from datetime import datetime, timezone
import logging

from app.services.ollama import OllamaClient, OllamaError
from app.services.history import generate_summary_prompt

logger = logging.getLogger(__name__)


# ==============================================================================
# Summary Generation
# ==============================================================================

async def generate_summary(
    messages: List[Dict],
    existing_summary: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """
    Generate a rolling summary of conversation messages.

    Args:
        messages: Messages to summarize
        existing_summary: Optional existing summary to build upon
        model: Model to use (defaults to Ollama client's default)

    Returns:
        Generated summary text

    Raises:
        OllamaError: If summary generation fails
    """
    if not messages:
        return existing_summary or ""

    logger.info(
        f"Generating summary for {len(messages)} messages",
        extra={
            "message_count": len(messages),
            "has_existing_summary": existing_summary is not None,
        }
    )

    # Build summary prompt
    prompt_parts = []

    if existing_summary:
        prompt_parts.append(f"# Existing Summary\n\n{existing_summary}\n\n")

    prompt_parts.append(generate_summary_prompt(messages))

    full_prompt = "\n".join(prompt_parts)

    # Generate summary using Ollama
    ollama_client = OllamaClient()

    try:
        summary = await ollama_client.generate_chat_completion(
            messages=[
                {
                    "role": "user",
                    "content": full_prompt,
                }
            ],
            model=model,
            keep_alive="5m",  # Keep model warm for next request
        )

        logger.info(
            "Summary generated successfully",
            extra={
                "message_count": len(messages),
                "summary_length": len(summary),
            }
        )

        return summary.strip()

    except OllamaError as e:
        logger.error(
            f"Failed to generate summary: {e}",
            extra={
                "message_count": len(messages),
                "error": str(e),
            },
            exc_info=True,
        )
        raise


async def should_regenerate_summary(
    current_message_count: int,
    message_count_at_summary: int,
    threshold: int = 20,
) -> bool:
    """
    Determine if summary should be regenerated.

    Args:
        current_message_count: Current total message count
        message_count_at_summary: Message count when summary was last generated
        threshold: Number of new messages before regenerating

    Returns:
        True if summary should be regenerated
    """
    new_messages = current_message_count - message_count_at_summary
    return new_messages >= threshold


async def update_session_summary(
    session_id: int,
    messages: List[Dict],
    existing_summary: Optional[str],
    db_session,
    force: bool = False,
) -> Optional[str]:
    """
    Update session summary if needed.

    Args:
        session_id: Session ID
        messages: Full message history
        existing_summary: Current summary (if any)
        db_session: Database session
        force: Force regeneration even if not needed

    Returns:
        New summary or None if not updated
    """
    from app.models.models import Session as SessionModel

    # Get session from DB
    session = db_session.query(SessionModel).filter(
        SessionModel.id == session_id
    ).first()

    if not session:
        logger.warning(f"Session {session_id} not found")
        return None

    # Check if regeneration is needed
    current_count = len(messages)
    at_summary = session.message_count_at_summary or 0

    should_update = force or await should_regenerate_summary(
        current_count,
        at_summary,
    )

    if not should_update:
        logger.debug(f"Summary update not needed for session {session_id}")
        return None

    logger.info(
        f"Updating summary for session {session_id}",
        extra={
            "session_id": session_id,
            "current_messages": current_count,
            "messages_since_summary": current_count - at_summary,
        }
    )

    try:
        # Determine which messages to summarize
        # Summarize older messages, keep recent ones verbatim
        keep_recent = 10
        if current_count > keep_recent:
            messages_to_summarize = messages[:-keep_recent]
        else:
            messages_to_summarize = messages

        # Generate new summary
        new_summary = await generate_summary(
            messages=messages_to_summarize,
            existing_summary=existing_summary,
        )

        # Update session in DB
        session.session_summary = new_summary
        session.summary_generated_at = datetime.now(timezone.utc)
        session.message_count_at_summary = current_count
        db_session.commit()

        logger.info(
            f"Summary updated for session {session_id}",
            extra={
                "session_id": session_id,
                "summary_length": len(new_summary),
                "message_count": current_count,
            }
        )

        return new_summary

    except Exception as e:
        logger.error(
            f"Failed to update summary for session {session_id}: {e}",
            extra={"session_id": session_id, "error": str(e)},
            exc_info=True,
        )
        db_session.rollback()
        return None
