"""
Gateway MCP Server

FastAPI application exposing business-level MCP tools with unified
policy, authentication, audit, and credential handling.

Port: 8090
Transport: HTTP/SSE (MCP protocol)
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Callable, Optional

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from gateway_mcp import __version__
from gateway_mcp.core.config import get_settings, Settings
from gateway_mcp.core.executors import (
    DockerExecBackend,
    JobRunnerBackend,
    K8sExecBackend,
    MCPProxyBackend,
    MockExecutorBackend,
)
from gateway_mcp.core.errors import GatewayError, CredentialMissingError
from gateway_mcp.core.middleware import create_middleware_pipeline
from gateway_mcp.core.transport import create_mcp_router
from gateway_mcp.tools import create_full_registry, ToolRegistry
from gateway_mcp.tools.base import Tool

logger = logging.getLogger(__name__)

# Lazy imports for credential store (may not be available in all environments)
_credential_store = None
_credential_encryption = None


def _init_credential_store():
    """
    Initialize credential store with encryption and DB session.
    
    Called lazily on first credential fetch to avoid import-time
    side effects and allow graceful degradation if DB is not available.
    """
    global _credential_store, _credential_encryption
    
    if _credential_store is not None:
        return _credential_store
    
    try:
        from gateway_mcp.core.credentials.store import (
            CredentialEncryption,
            CredentialStore,
        )
        from app.db.session import SessionLocal
        
        # Initialize encryption (reads GATEWAY_CREDENTIAL_ENCRYPTION_KEY from env)
        _credential_encryption = CredentialEncryption()
        
        # Create DB session
        db_session = SessionLocal()
        
        # Create store with no OAuth flow (refresh handled separately)
        _credential_store = CredentialStore(
            db_session=db_session,
            encryption=_credential_encryption,
            oauth_flow=None,  # OAuth refresh will be handled by dedicated service
            oauth_base_url="/api/credentials",
        )
        
        logger.info("CredentialStore initialized successfully")
        return _credential_store
        
    except ValueError as e:
        # Missing encryption key
        logger.warning(f"CredentialStore not available: {e}")
        return None
    except Exception as e:
        # DB not available or other error
        logger.warning(f"CredentialStore initialization failed: {e}")
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown."""
    settings = get_settings()
    logger.info(
        f"Gateway MCP starting: env={settings.env}, "
        f"executor={settings.executor_backend}, port=8090"
    )
    
    # Initialize tool registry with ALL 9 MVP tools (BRS + Atlassian)
    registry = create_full_registry()
    app.state.registry = registry
    logger.info(f"Registered {len(registry)} tools")
    
    yield
    logger.info("Gateway MCP shutting down")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    if settings is None:
        settings = get_settings()

    logger.info(f"Service token from settings: {settings.service_token[:20] if settings.service_token else 'EMPTY'}...")

    app = FastAPI(
        title="Gateway MCP",
        description="Business-level MCP tools with policy, auth, and audit",
        version=__version__,
        lifespan=lifespan,
    )

    # Store settings on app state
    app.state.settings = settings

    # Initialize tool registry with ALL 9 MVP tools (BRS + Atlassian)
    registry = create_full_registry()
    app.state.registry = registry

    # Create executor router for per-tool backend selection
    executor_router, credential_fetcher = _create_executor_router(settings)
    
    # Initialize credential store for external tool scope checking
    credential_store = _init_credential_store()
    
    # Initialize middleware pipeline with executor routing and credential store
    pipeline = create_middleware_pipeline(
        settings,
        executor_router=executor_router,
        credential_store=credential_store,
        credential_fetcher=credential_fetcher,
    )
    app.state.pipeline = pipeline

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
        
        Checks:
        - Configuration loaded
        - Executor backend available (if configured)
        - Configured services reachable (iterates services from config)
        """
        settings = app.state.settings
        checks: dict[str, Any] = {
            "config": True,
            "env": settings.env,
            "executor_backend": settings.executor_backend,
        }
        
        # Check configured services reachability
        services = getattr(settings, "services", {})
        services_status: dict[str, bool] = {}
        
        for service_name, service_config in services.items():
            # Only check HTTP services with URLs (skip container-based services)
            service_url = None
            if isinstance(service_config, dict):
                service_url = service_config.get("url")
            elif hasattr(service_config, "url"):
                service_url = service_config.url
            
            if service_url:
                services_status[service_name] = await _check_service_reachable(service_url)
        
        if services_status:
            checks["services"] = services_status
        
        # Check executor backend availability
        executor_backend = settings.executor_backend
        if executor_backend == "docker_exec":
            checks["executor_available"] = await _check_docker_available()
            
            # Check BRS container prerequisites for write tools
            if checks["executor_available"]:
                brs_status = await _check_brs_prerequisites()
                checks["brs_prerequisites"] = brs_status
                
                # Warn but don't fail readiness if BRS containers missing
                # (gateway is still functional for non-BRS tools)
                if brs_status.get("message"):
                    checks["warnings"] = checks.get("warnings", [])
                    checks["warnings"].append(brs_status["message"])
                    
        elif executor_backend == "mock":
            checks["executor_available"] = True
        else:
            # Unknown backend - assume available for now
            checks["executor_available"] = True
        
        # Determine overall status
        all_healthy = checks.get("config", False) and checks.get("executor_available", False)
        
        # Check all HTTP services are reachable
        if services_status:
            all_services_healthy = all(services_status.values())
            all_healthy = all_healthy and all_services_healthy
        
        status = "ready" if all_healthy else "not_ready"
        
        response = {
            "status": status,
            **checks,
        }
        
        if not all_healthy:
            # Return 503 for failed readiness
            from fastapi.responses import JSONResponse
            return JSONResponse(content=response, status_code=503)
        
        return response

    @app.get("/tools")
    async def list_tools() -> dict[str, Any]:
        """
        Debug endpoint - list registered tools.
        
        Returns simplified tool list for debugging.
        Canonical list is via MCP POST /mcp/tools/list.
        """
        registry: ToolRegistry = app.state.registry
        tools = registry.get_all()
        
        return {
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "risk_level": t.risk_level.value,
                    "requires_approval": t.requires_approval,
                    "allowed_environments": [e.value for e in t.allowed_environments],
                }
                for t in tools
            ],
            "count": len(tools),
        }

    # Include MCP transport routes
    mcp_router = create_mcp_router(registry, pipeline)
    app.include_router(mcp_router)

    return app


def _create_executor_factory(settings: Settings):
    """
    Create an executor factory for middleware ToolContext injection.

    This ensures tool handlers get a concrete backend in real runtime
    (not only in tests where executors are manually injected).
    
    DEPRECATED: Use _create_executor_router for per-tool routing.
    """
    backend_name = settings.executor_backend

    if backend_name == "docker_exec":
        backend = DockerExecBackend(settings)
    elif backend_name == "k8s_exec":
        backend = K8sExecBackend(settings)
    elif backend_name == "job_runner":
        backend = JobRunnerBackend(settings)
    else:
        backend = MockExecutorBackend()

    return lambda: backend


def _create_executor_router(
    settings: Settings,
) -> tuple[Callable[[Tool], Any], Callable[[str, str], str] | None]:
    """
    Create executor router for per-tool backend selection.
    
    Routes:
    - BRS tools (no required_scopes) → env-based backend (docker_exec/k8s_exec/job_runner)
    - External tools (with required_scopes) → MCPProxyBackend
    
    Args:
        settings: Gateway settings
        
    Returns:
        Tuple of (executor_router, credential_fetcher)
        - executor_router: Function (tool: Tool) -> ExecutorBackend
        - credential_fetcher: Function (user_id: str, provider: str) -> bearer_token
    """
    backend_name = settings.executor_backend
    
    # Create BRS backend based on environment config
    if backend_name == "docker_exec":
        brs_backend = DockerExecBackend(settings)
    elif backend_name == "k8s_exec":
        brs_backend = K8sExecBackend(settings)
    elif backend_name == "job_runner":
        brs_backend = JobRunnerBackend(settings)
    else:
        brs_backend = MockExecutorBackend()
    
    # Create credential fetcher that uses CredentialStore
    def credential_fetcher(user_id: str, provider: str) -> str:
        """
        Fetch OAuth credential for user/provider from CredentialStore.
        
        Args:
            user_id: User ID (string, converted to int for DB lookup)
            provider: Provider name (e.g., "atlassian", "github")
            
        Returns:
            Bearer token string (format: "Bearer <token>")
            
        Raises:
            CredentialMissingError: If no credential found or store not available
        """
        store = _init_credential_store()
        
        if store is None:
            raise CredentialMissingError(
                provider=provider,
                reconnect_url=f"/api/credentials/{provider}/authorize",
                audit_id=None,
            )
        
        try:
            user_id_int = int(user_id)
        except (ValueError, TypeError):
            raise CredentialMissingError(
                provider=provider,
                reconnect_url=f"/api/credentials/{provider}/authorize",
                audit_id=None,
            )
        
        credential = store.get_credential(user_id_int, provider)
        return credential.as_bearer()
    
    # Create MCP proxy backend for external tools
    mcp_proxy: MCPProxyBackend | None = None
    
    # Only create MCP proxy if upstream MCPs are configured
    if settings.upstream_mcps:
        mcp_proxy = MCPProxyBackend(settings, credential_fetcher=credential_fetcher)
    
    def executor_router(tool: Tool) -> Any:
        """Route to appropriate executor based on tool type."""
        if tool.is_external():
            # External tools (Jira, GitHub) use MCP proxy
            if mcp_proxy is None:
                raise RuntimeError(
                    f"Tool '{tool.name}' requires upstream MCP but none configured"
                )
            return mcp_proxy
        else:
            # BRS tools use environment-based backend
            return brs_backend
    
    return executor_router, credential_fetcher


async def _check_service_reachable(url: str, timeout: float = 2.0) -> bool:
    """Check if a service URL is reachable via HTTP GET."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{url}/health")
            return response.status_code < 500
    except Exception:
        return False


async def _check_docker_available() -> bool:
    """Check if Docker daemon is available."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "info",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        returncode = await asyncio.wait_for(proc.wait(), timeout=2.0)
        return returncode == 0
    except Exception:
        return False


async def _check_container_running(container_name: str) -> bool:
    """Check if a specific Docker container is running."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "inspect", "-f", "{{.State.Running}}", container_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=2.0)
        return stdout.decode().strip().lower() == "true"
    except Exception:
        return False


async def _check_brs_prerequisites() -> dict[str, Any]:
    """
    Check if BRS write tool prerequisites are available.
    
    Returns:
        Dict with status details for each prerequisite
    """
    # Container names used by BRS tools - may vary by deployment
    brs_containers = ["brs-teesheet", "php"]
    
    checks: dict[str, Any] = {
        "docker_available": await _check_docker_available(),
        "containers": {},
    }
    
    if not checks["docker_available"]:
        checks["message"] = "Docker daemon not available"
        return checks
    
    # Check each BRS container
    for container in brs_containers:
        checks["containers"][container] = await _check_container_running(container)
    
    # Check if any BRS container is available
    if not any(checks["containers"].values()):
        checks["message"] = (
            f"No BRS containers running. Required: {', '.join(brs_containers)}. "
            "BRS write tools (create_club, create_admin_user) will fail."
        )
    
    return checks


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
