"""
Gateway MCP Server

FastAPI application exposing business-level MCP tools with unified
policy, authentication, audit, and credential handling.

Port: 8090
Transport: HTTP/SSE (MCP protocol)
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from gateway_mcp import __version__
from gateway_mcp.core.config import get_settings, Settings
from gateway_mcp.core.errors import GatewayError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown."""
    settings = get_settings()
    logger.info(
        f"Gateway MCP starting: env={settings.env}, "
        f"executor={settings.executor_backend}, port=8090"
    )
    yield
    logger.info("Gateway MCP shutting down")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    if settings is None:
        settings = get_settings()

    app = FastAPI(
        title="Gateway MCP",
        description="Business-level MCP tools with policy, auth, and audit",
        version=__version__,
        lifespan=lifespan,
    )

    # Store settings on app state
    app.state.settings = settings

    @app.exception_handler(GatewayError)
    async def gateway_error_handler(request: Request, exc: GatewayError) -> JSONResponse:
        """Handle GatewayError exceptions with structured response."""
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "audit_id": exc.audit_id,
                    "retryable": exc.retryable,
                    "reconnect_url": exc.reconnect_url,
                }
            },
        )

    # Health endpoints
    @app.get("/health")
    async def health() -> dict[str, str]:
        """
        Liveness probe - process is up.
        Always returns 200.
        """
        return {"status": "healthy", "version": __version__}

    @app.get("/ready")
    async def ready() -> dict[str, Any]:
        """
        Readiness probe - dependencies reachable.
        Returns 503 if executor backend or services are unreachable.
        
        TODO: Implement actual dependency checks when executors are built.
        """
        # MVP: just check settings loaded
        settings = app.state.settings
        return {
            "status": "ready",
            "env": settings.env,
            "executor_backend": settings.executor_backend,
        }

    @app.get("/tools")
    async def list_tools() -> dict[str, Any]:
        """
        Debug endpoint - list registered tools.
        Canonical list is via MCP tools/list.
        
        TODO: Wire to ToolRegistry when implemented.
        """
        return {
            "tools": [],
            "count": 0,
            "note": "Tool registration pending - see MCP tools/list for canonical list",
        }

    # TODO: Add MCP HTTP/SSE transport routes
    # TODO: Add OAuth callback routes (delegated to main backend)

    return app


# Create default app instance
app = create_app()


def run():
    """Run the Gateway MCP server."""
    port = int(os.environ.get("GATEWAY_PORT", "8090"))
    host = os.environ.get("GATEWAY_HOST", "0.0.0.0")
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    uvicorn.run(
        "gateway_mcp.main:app",
        host=host,
        port=port,
        reload=os.environ.get("GATEWAY_ENV", "local") == "local",
    )


if __name__ == "__main__":
    run()
