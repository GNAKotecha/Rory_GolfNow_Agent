"""OAuth service for managing OAuth flows and state tokens."""
import secrets
import time
from datetime import datetime, timedelta
from typing import Dict, Optional
from urllib.parse import urlencode
import requests


class StateTokenStore:
    """In-memory state token storage with expiry and tenant isolation.

    In production, this should be replaced with Redis for persistence
    and multi-instance support.
    """

    def __init__(self, expiry_seconds: int = 600):
        """Initialize state token store.

        Args:
            expiry_seconds: Token expiry time in seconds (default 10 minutes)
        """
        self._store: Dict[str, Dict] = {}
        self._expiry_seconds = expiry_seconds

    def store(self, state: str, data: dict, tenant_id: int) -> None:
        """Store state token with metadata.

        Args:
            state: State token string
            data: Metadata to store (integration_id, tenant_id, user_id, etc.)
            tenant_id: Tenant ID for isolation
        """
        self._store[state] = {
            "data": data,
            "tenant_id": tenant_id,
            "expires_at": time.time() + self._expiry_seconds
        }

    def retrieve(self, state: str, tenant_id: int) -> Optional[dict]:
        """Retrieve state token data.

        Args:
            state: State token string
            tenant_id: Tenant ID for isolation

        Returns:
            Stored data dict or None if not found/expired/wrong tenant
        """
        entry = self._store.get(state)
        if not entry:
            return None

        # Check expiry
        if time.time() > entry["expires_at"]:
            del self._store[state]
            return None

        # Check tenant isolation
        if entry["tenant_id"] != tenant_id:
            return None

        return entry["data"]

    def cleanup(self) -> None:
        """Remove expired state tokens."""
        current_time = time.time()
        expired_keys = [
            key for key, entry in self._store.items()
            if current_time > entry["expires_at"]
        ]
        for key in expired_keys:
            del self._store[key]


# Global state store instance (replace with Redis in production)
_state_store = StateTokenStore()


class OAuthService:
    """Service for OAuth authorization flows."""

    @staticmethod
    def generate_state_token() -> str:
        """Generate a cryptographically secure state token.

        Returns:
            URL-safe random token string
        """
        return secrets.token_urlsafe(32)

    @staticmethod
    def build_authorize_url(
        integration_name: str,
        config: dict,
        state: str,
        base_url: str
    ) -> str:
        """Build OAuth authorization URL for a provider.

        Args:
            integration_name: Name of integration (e.g., "github", "gitlab")
            config: Integration config containing client_id, scopes, etc.
            state: CSRF state token
            base_url: Base URL for OAuth callback redirect

        Returns:
            Full authorization URL

        Raises:
            ValueError: If integration_name is not supported
        """
        if integration_name == "github":
            return OAuthService._build_github_authorize_url(config, state, base_url)
        elif integration_name == "gitlab":
            return OAuthService._build_gitlab_authorize_url(config, state, base_url)
        else:
            raise ValueError(f"Unsupported integration: {integration_name}")

    @staticmethod
    def _build_github_authorize_url(config: dict, state: str, base_url: str) -> str:
        """Build GitHub OAuth authorization URL."""
        params = {
            "client_id": config["client_id"],
            "redirect_uri": base_url,
            "state": state,
            "scope": " ".join(config.get("scopes", []))
        }
        return f"https://github.com/login/oauth/authorize?{urlencode(params)}"

    @staticmethod
    def _build_gitlab_authorize_url(config: dict, state: str, base_url: str) -> str:
        """Build GitLab OAuth authorization URL."""
        params = {
            "client_id": config["client_id"],
            "redirect_uri": base_url,
            "state": state,
            "scope": " ".join(config.get("scopes", [])),
            "response_type": "code"
        }
        return f"https://gitlab.com/oauth/authorize?{urlencode(params)}"

    @staticmethod
    def exchange_code_for_token(
        integration_name: str,
        config: dict,
        code: str
    ) -> dict:
        """Exchange authorization code for access token.

        Args:
            integration_name: Name of integration (e.g., "github")
            config: Integration config containing client_id, client_secret
            code: Authorization code from OAuth callback

        Returns:
            Token response dict with access_token, token_type, scope, etc.

        Raises:
            ValueError: If token exchange fails
        """
        if integration_name == "github":
            return OAuthService._exchange_github_token(config, code)
        elif integration_name == "gitlab":
            return OAuthService._exchange_gitlab_token(config, code)
        else:
            raise ValueError(f"Unsupported integration: {integration_name}")

    @staticmethod
    def _exchange_github_token(config: dict, code: str) -> dict:
        """Exchange GitHub authorization code for access token."""
        try:
            response = requests.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": config["client_id"],
                    "client_secret": config["client_secret"],
                    "code": code
                },
                timeout=10
            )

            if response.status_code != 200:
                raise ValueError(f"Token exchange failed: HTTP {response.status_code}")

            data = response.json()
            if "error" in data:
                raise ValueError(f"Token exchange failed: {data.get('error_description', data['error'])}")

            return data

        except Exception as e:
            raise ValueError(f"Token exchange failed: {str(e)}")

    @staticmethod
    def _exchange_gitlab_token(config: dict, code: str) -> dict:
        """Exchange GitLab authorization code for access token."""
        try:
            response = requests.post(
                "https://gitlab.com/oauth/token",
                data={
                    "client_id": config["client_id"],
                    "client_secret": config["client_secret"],
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": config.get("redirect_uri", "")
                },
                timeout=10
            )

            if response.status_code != 200:
                raise ValueError(f"Token exchange failed: HTTP {response.status_code}")

            data = response.json()
            if "error" in data:
                raise ValueError(f"Token exchange failed: {data.get('error_description', data['error'])}")

            return data

        except Exception as e:
            raise ValueError(f"Token exchange failed: {str(e)}")

    @staticmethod
    def validate_state_token(stored: Optional[str], received: Optional[str]) -> bool:
        """Validate that state tokens match.

        Args:
            stored: State token stored when initiating OAuth
            received: State token received in callback

        Returns:
            True if tokens match, False otherwise
        """
        if stored is None or received is None:
            return False
        return stored == received

    @staticmethod
    def get_state_store() -> StateTokenStore:
        """Get the global state token store instance.

        Returns:
            StateTokenStore instance
        """
        return _state_store
