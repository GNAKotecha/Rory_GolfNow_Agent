"""
OAuth Authorization Flow

Handles OAuth 2.0 authorization code flow with PKCE support.
Orchestrates the flow between providers and credential storage.

Flow:
1. Start authorization (generate URL + store state/verifier in session)
2. Handle callback (validate state, exchange code, get metadata)
3. Store credential (encrypt and persist)
4. Refresh token (when token expires)

Session Management:
State and code_verifier are stored in a session cache keyed by state.
This cache should be backed by Redis in production for multi-instance support.
"""
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Union

from gateway_mcp.core.credentials.providers.base import (
    AuthorizationResult,
    OAuthProvider,
    TokenExchangeResult,
)
from gateway_mcp.core.credentials.providers.generic import (
    GenericOAuthProvider,
    create_oauth_provider,
)


class OAuthStateStore:
    """
    Stores OAuth state parameters during authorization flow.
    
    In-memory implementation for single-instance deployments.
    For production, this should be backed by Redis.
    """
    
    # State entries expire after 10 minutes
    STATE_TTL_SECONDS = 600
    
    def __init__(self):
        self._states: Dict[str, dict] = {}
    
    def store(
        self,
        state: str,
        code_verifier: Optional[str] = None,
        provider: str = "",
        user_id: Optional[int] = None,
        redirect_after: Optional[str] = None,
    ) -> None:
        """
        Store state parameters for OAuth callback.
        
        Args:
            state: State parameter (CSRF token).
            code_verifier: PKCE code verifier.
            provider: Provider name.
            user_id: User ID initiating the flow.
            redirect_after: URL to redirect after completion.
        """
        self._states[state] = {
            "code_verifier": code_verifier,
            "provider": provider,
            "user_id": user_id,
            "redirect_after": redirect_after,
            "created_at": datetime.utcnow(),
        }
        
        # Clean up expired states
        self._cleanup()
    
    def get(self, state: str) -> Optional[dict]:
        """
        Retrieve and consume state parameters.
        
        Args:
            state: State parameter to look up.
            
        Returns:
            State data dict, or None if not found/expired.
        """
        data = self._states.pop(state, None)
        
        if data is None:
            return None
        
        # Check if expired
        created_at = data.get("created_at")
        if created_at and (datetime.utcnow() - created_at).seconds > self.STATE_TTL_SECONDS:
            return None
        
        return data
    
    def _cleanup(self) -> None:
        """Remove expired states."""
        now = datetime.utcnow()
        expired = [
            state
            for state, data in self._states.items()
            if (now - data.get("created_at", now)).seconds > self.STATE_TTL_SECONDS
        ]
        for state in expired:
            self._states.pop(state, None)


class OAuthFlow:
    """
    Orchestrates OAuth authorization flow.
    
    Handles:
    - Authorization URL generation
    - Callback validation and token exchange
    - Token refresh
    - Provider metadata fetching
    """
    
    def __init__(
        self,
        providers: Dict[str, OAuthProvider],
        state_store: Optional[OAuthStateStore] = None,
    ):
        """
        Initialize OAuth flow handler.
        
        Args:
            providers: Dict mapping provider names to OAuthProvider instances.
            state_store: State store for CSRF/PKCE parameters.
        """
        self._providers = providers
        self._state_store = state_store or OAuthStateStore()
    
    def start_authorization(
        self,
        provider: str,
        user_id: int,
        scopes: Optional[list[str]] = None,
        redirect_after: Optional[str] = None,
    ) -> AuthorizationResult:
        """
        Start OAuth authorization flow.
        
        Generates authorization URL and stores state for callback validation.
        
        Args:
            provider: Provider name (e.g., "atlassian").
            user_id: ID of user initiating authorization.
            scopes: Scopes to request (defaults to provider defaults).
            redirect_after: URL to redirect user after OAuth completes.
            
        Returns:
            AuthorizationResult with authorization URL.
            
        Raises:
            ValueError: If provider not found.
        """
        oauth_provider = self._providers.get(provider)
        if oauth_provider is None:
            raise ValueError(f"Unknown OAuth provider: {provider}")
        
        # Generate authorization URL with PKCE
        result = oauth_provider.get_authorization_url(scopes=scopes)
        
        # Store state for callback validation
        self._state_store.store(
            state=result.state,
            code_verifier=result.code_verifier,
            provider=provider,
            user_id=user_id,
            redirect_after=redirect_after,
        )
        
        return result
    
    def handle_callback(
        self,
        code: str,
        state: str,
    ) -> tuple[TokenExchangeResult, dict[str, Any], dict]:
        """
        Handle OAuth callback.
        
        Validates state, exchanges code for tokens, and fetches provider metadata.
        
        Args:
            code: Authorization code from callback.
            state: State parameter from callback.
            
        Returns:
            Tuple of (TokenExchangeResult, provider_metadata, state_data).
            
        Raises:
            ValueError: If state is invalid or exchange fails.
        """
        # Validate state
        state_data = self._state_store.get(state)
        if state_data is None:
            raise ValueError("Invalid or expired OAuth state")
        
        provider_name = state_data.get("provider")
        code_verifier = state_data.get("code_verifier")
        
        oauth_provider = self._providers.get(provider_name)
        if oauth_provider is None:
            raise ValueError(f"Unknown OAuth provider: {provider_name}")
        
        # Exchange code for tokens
        token_result = oauth_provider.exchange_code(
            code=code,
            code_verifier=code_verifier,
        )
        
        # Get provider-specific metadata (e.g., Atlassian cloud_id)
        metadata = {}
        try:
            metadata = oauth_provider.get_resource_metadata(token_result.access_token)
        except Exception:
            # Metadata fetch is optional, don't fail the flow
            pass
        
        return token_result, metadata, state_data
    
    def refresh_token(
        self,
        provider: str,
        refresh_token: str,
    ) -> dict[str, Any]:
        """
        Refresh an access token.
        
        Args:
            provider: Provider name.
            refresh_token: The refresh token.
            
        Returns:
            Dict with new access_token, refresh_token, expires_in, scope.
            
        Raises:
            ValueError: If provider not found.
            Exception: If refresh fails.
        """
        oauth_provider = self._providers.get(provider)
        if oauth_provider is None:
            raise ValueError(f"Unknown OAuth provider: {provider}")
        
        result = oauth_provider.refresh_token(refresh_token)
        
        return {
            "access_token": result.access_token,
            "refresh_token": result.refresh_token,
            "expires_in": result.expires_in,
            "scope": result.scope,
        }
    
    def get_provider(self, provider: str) -> Optional[OAuthProvider]:
        """Get provider by name."""
        return self._providers.get(provider)
    
    def list_providers(self) -> list[str]:
        """List available provider names."""
        return list(self._providers.keys())


def create_oauth_flow(
    config: dict,
) -> OAuthFlow:
    """
    Create OAuthFlow from configuration.
    
    Automatically creates providers for all OAuth-type entries in config.
    
    Args:
        config: Credentials configuration with providers section.
        
    Returns:
        Configured OAuthFlow instance.
    """
    providers = {}
    providers_config = config.get("providers", {})
    
    # Create providers for all OAuth entries
    for name, provider_config in providers_config.items():
        if provider_config.get("type") == "oauth":
            providers[name] = create_oauth_provider(name, provider_config)
    
    return OAuthFlow(providers=providers)
