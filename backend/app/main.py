import logging
import sys
from contextlib import asynccontextmanager

# Configure Python logging to output to stdout (captured by uvicorn)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.health import router as health_router
from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.admin_analytics import router as admin_analytics_router
from app.api.analytics import router as analytics_router
from app.api.sessions import router as sessions_router
from app.api.chat import router as chat_router
from app.api.chat_ws import router as chat_ws_router
from app.api.ollama_compat import router as ollama_compat_router
from app.api.credentials import router as credentials_router
from app.api.tenants import router as tenants_router
from app.api.integrations import router as integrations_router
from app.api.skills import router as skills_router
from app.api.workflows import router as workflows_router
from app.api.test_results import router as test_results_router
from app.api.traces import router as traces_router

# Global MCP registry instance
_global_mcp_registry = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager."""
    global _global_mcp_registry

    # Startup
    from app.db.init_db import init_db
    from app.services.ollama import startup_ollama_client_pool
    from app.services.mcp_registry import MCPToolRegistry
    from app.config.mcp_config import Environment
    import os

    # Initialize database
    init_db()

    # Task C1: Start shared HTTP client pool for Ollama
    await startup_ollama_client_pool()

    # Initialize MCP registry with aiohttp sessions
    env_name = os.environ.get("ENVIRONMENT", "development")
    env = Environment[env_name.upper()] if env_name.upper() in Environment.__members__ else Environment.DEVELOPMENT
    _global_mcp_registry = MCPToolRegistry(env)
    await _global_mcp_registry.initialize()
    logging.info("MCP registry initialized with pre-created aiohttp sessions")

    yield

    # Shutdown
    from app.services.ollama import shutdown_ollama_client_pool

    # Task C1: Shutdown shared HTTP client pool
    await shutdown_ollama_client_pool()

    # Close MCP registry sessions
    if _global_mcp_registry:
        await _global_mcp_registry.close()
        logging.info("MCP registry sessions closed")


app = FastAPI(
    title="Internal Agent MVP",
    description="Backend orchestration service for hosted agent",
    version="0.1.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://localhost:3003",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health_router)
app.include_router(auth_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(admin_analytics_router, prefix="/api")
app.include_router(analytics_router, prefix="/api")
app.include_router(sessions_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(chat_ws_router, prefix="/api")  # WebSocket endpoint
app.include_router(ollama_compat_router)  # Ollama-compatible endpoints for Open WebUI
app.include_router(credentials_router, prefix="/api")  # Credential management
app.include_router(tenants_router, prefix="/api/admin", tags=["admin"])  # Tenant management
app.include_router(integrations_router, prefix="/api", tags=["integrations"])  # MCP integrations management
app.include_router(skills_router, prefix="/api", tags=["skills"])  # Skills management
app.include_router(workflows_router, prefix="/api", tags=["workflows"])  # Workflows management
app.include_router(test_results_router, tags=["test-results"])  # Test result tracking
app.include_router(traces_router, prefix="/api", tags=["admin"])  # Langfuse trace exploration


def get_global_mcp_registry():
    """Get the global MCP registry instance."""
    return _global_mcp_registry


@app.get("/")
async def root():
    return {
        "service": "Internal Agent Backend",
        "version": "0.1.0",
        "status": "running"
    }
