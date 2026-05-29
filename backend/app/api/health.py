from fastapi import APIRouter
from app.db.session import check_db_connection
from app.services.ollama import check_ollama_connection
from app.core.config import settings

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health_check():
    """
    Health check endpoint that verifies:
    - Backend is running
    - Database is connected
    - Configured LLM backend is reachable
    """
    db_healthy = check_db_connection()
    llm_healthy = await check_ollama_connection()
    llm_provider = "api_key" if settings.use_api_key else "ollama"

    overall_healthy = db_healthy and llm_healthy

    return {
        "status": "healthy" if overall_healthy else "degraded",
        "checks": {
            "database": "connected" if db_healthy else "failed",
            "llm": "connected" if llm_healthy else "failed",
        },
        "llm_provider": llm_provider,
    }
