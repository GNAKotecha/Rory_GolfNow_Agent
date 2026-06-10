"""Tenant MCP Connection Manager - manages external MCP integrations."""
import os
import logging
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.models import TenantMCPIntegration
from app.models.external_credential import ExternalCredential
from app.services.mcp_client import MCPClient
from app.services.jsonrpc_mcp_client import JsonRpcMCPClient
from app.services.stdio_mcp_client import StdioMCPClient
from app.services.mcp_registry import MCPToolRegistry
from app.config.mcp_config import MCPServerConfig
from gateway_mcp.core.credentials import CredentialEncryption

logger = logging.getLogger(__name__)


class TenantMCPConnectionManager:
    """Manages tenant-scoped external MCP server connections.

    Loads enabled TenantMCPIntegration entries from database,
    creates MCPClient connections, and registers tools with MCPRegistry.
    """

    def __init__(self, registry: MCPToolRegistry):
        """Initialize manager with global MCP registry.

        Args:
            registry: Global MCP tool registry to register external clients with
        """
        self.registry = registry
        self.tenant_clients: Dict[int, MCPClient] = {}  # integration_id -> client
        self.encryption = self._init_encryption()

    def _init_encryption(self) -> Optional[CredentialEncryption]:
        """Initialize credential encryption from environment.

        Returns:
            CredentialEncryption instance or None if key not configured
        """
        encryption_key = os.environ.get("GATEWAY_CREDENTIAL_ENCRYPTION_KEY")
        if not encryption_key:
            logger.warning(
                "GATEWAY_CREDENTIAL_ENCRYPTION_KEY not set - "
                "external integrations will fail to connect"
            )
            return None
        return CredentialEncryption(encryption_key)

    def _detect_protocol_type(self, integration: TenantMCPIntegration) -> str:
        """
        Detect MCP protocol type from configuration.

        Priority:
        1. Explicit config.protocol setting
        2. Command/args presence (stdio)
        3. Known URL patterns (jsonrpc)
        4. Default to REST

        Returns:
            "rest", "jsonrpc", or "stdio"
        """
        config = integration.config

        # 1. Explicit protocol
        if "protocol" in config:
            return config["protocol"]

        # 2. Stdio detection
        if "command" in config:
            return "stdio"

        # 3. JSON-RPC URL patterns (check both base_url and server_url keys)
        base_url = config.get("base_url") or config.get("server_url", "")
        jsonrpc_patterns = [
            "mcp.atlassian.com",
            "api.githubcopilot.com/mcp",
            "/v1/mcp",
            "/jsonrpc",
        ]

        for pattern in jsonrpc_patterns:
            if pattern in base_url:
                return "jsonrpc"

        # 4. Default to REST
        return "rest"

    async def initialize(self):
        """Load and connect all enabled tenant integrations.

        Called during application startup. Queries database for enabled
        integrations, creates MCPClient connections, and registers with
        the global tool registry.
        """
        logger.info("Initializing tenant MCP connections...")

        db = SessionLocal()
        try:
            # Load all enabled integrations
            integrations = db.query(TenantMCPIntegration).filter(
                TenantMCPIntegration.is_enabled == True
            ).all()

            logger.info(f"Found {len(integrations)} enabled tenant integrations")

            # Connect each integration (errors don't block others)
            for integration in integrations:
                try:
                    await self._connect_integration_impl(integration, db)
                except Exception as e:
                    logger.error(
                        f"Failed to connect integration {integration.id} "
                        f"({integration.integration_name}): {e}",
                        exc_info=True,
                        extra={
                            "integration_id": integration.id,
                            "integration_name": integration.integration_name,
                            "tenant_id": integration.tenant_id
                        }
                    )

            logger.info(
                f"Tenant MCP initialization complete: "
                f"{len(self.tenant_clients)}/{len(integrations)} connected"
            )
        finally:
            db.close()

    async def _connect_integration_impl(
        self,
        integration: TenantMCPIntegration,
        db: Session
    ):
        """Internal: connect an integration.

        Args:
            integration: TenantMCPIntegration to connect
            db: Database session

        Raises:
            ValueError: If configuration is invalid
            Exception: If connection fails
        """
        # Detect protocol type first (needed for stdio check)
        protocol = self._detect_protocol_type(integration)
        server_name = f"tenant_{integration.id}_{integration.integration_name}"

        # Stdio protocol uses different initialization path
        if protocol == "stdio":
            # Stdio-based MCP (Playwright, filesystem, etc.)
            command = integration.config.get("command")
            args = integration.config.get("args", [])

            if not command:
                raise ValueError(f"Integration {integration.id} missing 'command' for stdio protocol")

            client = StdioMCPClient(command, args, server_name)
            logger.info(
                f"Using stdio protocol for {server_name}",
                extra={"server": server_name, "protocol": protocol, "command": command}
            )

            # Initialize stdio client (spawns subprocess)
            await client.initialize()

        else:
            # REST/JSON-RPC protocols need credentials and URL

            # Resolve the credential secret: prefer ExternalCredential table (encrypted),
            # fall back to plaintext value stored directly in config["credentials"].
            decrypted_secret: Optional[str] = None

            credential = db.query(ExternalCredential).filter(
                ExternalCredential.integration_id == integration.id
            ).first()

            if credential:
                if not self.encryption:
                    raise RuntimeError("Encryption not initialized - cannot decrypt credentials")
                decrypted_secret = self.encryption.decrypt(credential.secret_enc)
            else:
                # Credentials stored inline in config (used by the AddMCPModal flow)
                decrypted_secret = integration.config.get("credentials") or integration.config.get("api_key")
                if not decrypted_secret:
                    raise ValueError(
                        f"No credential found for integration {integration.id}: "
                        "neither ExternalCredential row nor config.credentials present"
                    )
                logger.info(
                    f"Using inline config credentials for {server_name}",
                    extra={"server": server_name}
                )

            # Build MCPServerConfig
            # URL can be under base_url or server_url (older integrations used server_url)
            base_url = integration.config.get("base_url") or integration.config.get("server_url", "")
            if not base_url:
                raise ValueError(f"Integration {integration.id} missing base_url/server_url in config")

            timeout = integration.config.get("timeout", 30)

            # Create server config
            config = MCPServerConfig(
                name=server_name,
                url=base_url,
                timeout_seconds=timeout
            )

            # Build authentication headers
            auth_headers = {}
            if integration.auth_type in ("api_key", "oauth", "pat"):
                auth_headers["Authorization"] = f"Bearer {decrypted_secret}"
            # For other auth types, headers can be extended as needed

            # Create client based on protocol
            if protocol == "jsonrpc":
                # JSON-RPC 2.0 MCP (Jira, GitHub, etc.)
                client = JsonRpcMCPClient(config, auth_headers=auth_headers)
                logger.info(
                    f"Using JSON-RPC 2.0 protocol for {server_name}",
                    extra={"server": server_name, "protocol": protocol}
                )
            else:
                # REST/HTTP MCP (default, backward compatible)
                client = MCPClient(config, auth_headers=auth_headers)
                logger.info(
                    f"Using REST/HTTP protocol for {server_name}",
                    extra={"server": server_name, "protocol": protocol}
                )

            # Initialize client
            await client.initialize()

        # Verify connection
        is_healthy = await client.health_check()
        if not is_healthy:
            logger.warning(
                f"Integration {server_name} connected but health check failed"
            )

        # Store client
        self.tenant_clients[integration.id] = client

        # Register with global registry and invalidate tool catalog cache
        # so the next agent run rebuilds the catalog including this new client
        self.registry.clients[server_name] = client
        self.registry._discovery_cache = None

        logger.info(
            f"Connected tenant integration: {server_name}",
            extra={
                "integration_id": integration.id,
                "integration_name": integration.integration_name,
                "tenant_id": integration.tenant_id,
                "healthy": is_healthy
            }
        )

    async def connect_integration(self, integration_id: int):
        """Connect a single integration.

        Args:
            integration_id: ID of TenantMCPIntegration to connect

        Raises:
            ValueError: If integration not found
            Exception: If connection fails
        """
        db = SessionLocal()
        try:
            integration = db.query(TenantMCPIntegration).filter(
                TenantMCPIntegration.id == integration_id
            ).first()

            if not integration:
                raise ValueError(f"Integration {integration_id} not found")

            await self._connect_integration_impl(integration, db)
        finally:
            db.close()

    async def disconnect_integration(self, integration_id: int):
        """Disconnect an integration.

        Args:
            integration_id: ID of integration to disconnect
        """
        client = self.tenant_clients.get(integration_id)
        if not client:
            logger.warning(f"Integration {integration_id} not connected")
            return

        # Close client
        try:
            await client.close()
        except Exception as e:
            logger.error(f"Error closing client for integration {integration_id}: {e}")

        # Remove from tracking
        del self.tenant_clients[integration_id]

        # Remove from registry
        server_name = None
        for name, c in list(self.registry.clients.items()):
            if c == client:
                server_name = name
                del self.registry.clients[name]
                break

        logger.info(
            f"Disconnected tenant integration: {server_name or integration_id}",
            extra={"integration_id": integration_id}
        )

    async def reconnect_integration(self, integration_id: int):
        """Reconnect an integration (disconnect then connect).

        Args:
            integration_id: ID of integration to reconnect
        """
        await self.disconnect_integration(integration_id)
        await self.connect_integration(integration_id)

    async def get_connection_status(self, integration_id: int) -> dict:
        """Get connection status for an integration.

        Args:
            integration_id: ID of integration to check

        Returns:
            Dictionary with status:
            - connected: bool - whether client exists
            - healthy: bool - whether health check passes (if connected)
            - error: str - error message (if health check fails)
        """
        client = self.tenant_clients.get(integration_id)

        if not client:
            return {"connected": False}

        # Check health
        try:
            is_healthy = await client.health_check()
            return {
                "connected": True,
                "healthy": is_healthy
            }
        except Exception as e:
            logger.error(
                f"Health check failed for integration {integration_id}: {e}",
                extra={"integration_id": integration_id}
            )
            return {
                "connected": True,
                "healthy": False,
                "error": str(e)
            }

    def list_connected_integrations(self) -> List[int]:
        """List integration IDs that are currently connected.

        Returns:
            List of integration IDs with active connections
        """
        return list(self.tenant_clients.keys())
