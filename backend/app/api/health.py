from fastapi import APIRouter
from app.db.session import check_db_connection
from app.services.ollama import check_ollama_connection

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health_check():
    """
    Health check endpoint that verifies:
    - Backend is running
    - Database is connected
    - Ollama is reachable
    """
    db_healthy = check_db_connection()
    ollama_healthy = await check_ollama_connection()

    overall_healthy = db_healthy and ollama_healthy

    return {
        "status": "healthy" if overall_healthy else "degraded",
        "checks": {
            "database": "connected" if db_healthy else "failed",
            "ollama": "connected" if ollama_healthy else "failed"
        }
    }
