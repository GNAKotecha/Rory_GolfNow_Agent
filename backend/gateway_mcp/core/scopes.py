"""
Scope Validation for External Tools

Validates that the user's OAuth token has the required scopes
for external tool invocations (Atlassian, GitHub, etc.).

BRS tools have empty required_scopes and skip this check.
External tools declare required scopes in their Tool definition.
"""

from typing import Optional, TYPE_CHECKING

from gateway_mcp.core.errors import InsufficientScopeError, CredentialMissingError
from gateway_mcp.tools.base import Tool

if TYPE_CHECKING:
    from gateway_mcp.core.credentials.store import CredentialStore, Credential


class ScopeService:
    """
    OAuth scope validation for external tools.
    
    Checks that the user has connected the required provider
    and the credential has sufficient scopes.
    """
    
    def __init__(
        self,
        credential_store: Optional["CredentialStore"] = None,
        oauth_base_url: str = "/api/credentials",
    ):
        """
        Initialize scope service.
        
        Args:
            credential_store: Credential storage backend.
            oauth_base_url: Base URL for OAuth connect endpoints.
        """
        self._credential_store = credential_store
        self._oauth_base_url = oauth_base_url
    
    def check_scopes(
        self,
        tool: Tool,
        user_id: int,
        audit_id: Optional[str] = None,
    ) -> Optional["Credential"]:
        """
        Check if user has required scopes for tool.
        
        For BRS tools (empty required_scopes), this is a no-op.
        For external tools, validates credential exists and has scopes.
        
        Args:
            tool: Tool being invoked
            user_id: ID of calling user
            audit_id: Correlation ID for error responses
            
        Returns:
            Credential object if external tool, None for BRS tools.
            
        Raises:
            CredentialMissingError: User hasn't connected provider
            InsufficientScopeError: Token lacks required scopes
        """
        if not tool.required_scopes:
            # BRS tools - no external credential needed
            return
        
        # Determine provider from scopes (e.g., "jira:read" -> "atlassian")
        provider = self._get_provider_from_scopes(tool.required_scopes)
        
        # Get user's credential for this provider
        credential = self._get_user_credential(user_id, provider)
        
        if credential is None:
            reconnect_url = f"{self._oauth_base_url}/{provider}/authorize"
            raise CredentialMissingError(
                provider=provider,
                reconnect_url=reconnect_url,
                audit_id=audit_id,
            )
        
        # Check if credential has all required scopes
        missing_scopes = self._get_missing_scopes(
            credential_scopes=credential.get("scopes", []),
            required_scopes=tool.required_scopes,
        )
        
        if missing_scopes:
            reconnect_url = f"{self._oauth_base_url}/{provider}/authorize?scopes={','.join(tool.required_scopes)}"
            raise InsufficientScopeError(
                provider=provider,
                required_scopes=missing_scopes,
                reconnect_url=reconnect_url,
                audit_id=audit_id,
            )
    
    def _get_provider_from_scopes(self, scopes: list[str]) -> str:
        """
        Determine provider from scope prefixes.
        
        Examples:
            ["jira:read", "jira:write"] -> "atlassian"
            ["repo", "read:user"] -> "github"
        """
        if not scopes:
            return "unknown"
        
        first_scope = scopes[0].lower()
        
        if first_scope.startswith("jira:") or first_scope.startswith("confluence:"):
            return "atlassian"
        
        # GitHub scopes don't have a prefix
        if first_scope in ("repo", "read:user", "write:repo_hook", "admin:org"):
            return "github"
        
        if first_scope.startswith("github:"):
            return "github"
        
        # Default: use first part before colon or whole string
        if ":" in first_scope:
            return first_scope.split(":")[0]
        
        return "unknown"
    
    def _get_user_credential(
        self,
        user_id: int,
        provider: str,
        audit_id: Optional[str] = None,
    ) -> Optional["Credential"]:
        """
        Get user's credential for a provider.
        
        Integrates with Milestone 7 credential store when available.
        
        Args:
            user_id: ID of the user
            provider: Provider name (e.g., "atlassian", "github")
            audit_id: Correlation ID for errors
            
        Returns:
            Credential object if found, None otherwise
        """
        if self._credential_store is None:
            # Credential store not configured - external tools unavailable
            return None
        
        try:
            credential = self._credential_store.get_credential(
                user_id=user_id,
                provider=provider,
                audit_id=audit_id,
            )
            # Convert Credential to dict for backwards compatibility
            return {
                "scopes": credential.scopes,
                "access_token": credential.access_token,
                "provider": credential.provider,
                "credential_type": credential.credential_type,
            }
        except Exception:
            # Credential not found or error - will be raised properly by caller
            return None
    
    def _get_missing_scopes(
        self,
        credential_scopes: list[str],
        required_scopes: list[str],
    ) -> list[str]:
        """Return list of required scopes not present in credential."""
        credential_set = set(credential_scopes)
        return [s for s in required_scopes if s not in credential_set]


def create_scope_service_from_settings(
    settings,
    credential_store: Optional["CredentialStore"] = None,
) -> ScopeService:
    """
    Factory to create ScopeService from gateway settings.
    
    Args:
        settings: Gateway settings object
        credential_store: Optional credential store (Milestone 7)
        
    Returns:
        Configured ScopeService
    """
    oauth_base_url = getattr(settings, "oauth_base_url", "/api/credentials")
    
    return ScopeService(
        credential_store=credential_store,
        oauth_base_url=oauth_base_url,
    )
