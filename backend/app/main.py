from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.health import router as health_router
from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.admin_analytics import router as admin_analytics_router
from app.api.sessions import router as sessions_router
from app.api.chat import router as chat_router
from app.api.ollama_compat import router as ollama_compat_router

app = FastAPI(
    title="Internal Agent MVP",
    description="Backend orchestration service for hosted agent",
    version="0.1.0"
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
app.include_router(sessions_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(ollama_compat_router)  # Ollama-compatible endpoints for Open WebUI


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    from app.db.init_db import init_db
    init_db()


@app.get("/")
async def root():
    return {
        "service": "Internal Agent Backend",
        "version": "0.1.0",
        "status": "running"
    }
