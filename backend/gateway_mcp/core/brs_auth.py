"""
BRS OAuth Token Provider

Handles OAuth token exchange with BRS teesheet API.
Uses client_credentials/api_key flow:
  POST /oauth/v2/token
  {
    "client_id": "...",
    "client_secret": "...",
    "grant_type": "api_key",
    "api_key": "..."
  }

Tokens are cached per-club with TTL based on expires_in from the response.

Two modes of operation:
1. Static API key (env var): Single global API key for all requests
2. Dynamic per-club: API key retrieved from club's fe_users table
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Dict, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class BRSToken:
    """Cached BRS OAuth token."""
    access_token: str
    expires_at: float  # Unix timestamp
    token_type: str = "Bearer"
    club_id: Optional[str] = None  # Club ID this token is for (if per-club)
    
    @property
    def is_expired(self) -> bool:
        """Check if token is expired (with 60s buffer)."""
        return time.time() >= (self.expires_at - 60)
    
    def as_bearer(self) -> str:
        """Return token formatted for Authorization header."""
        return f"{self.token_type} {self.access_token}"


class BRSAuthProvider:
    """
    Provides OAuth tokens for BRS teesheet API.
    
    Configuration via environment variables:
    - BRS_TEESHEET_URL: Base URL for teesheet (e.g., https://api.brs.dev)
    - BRS_CLIENT_ID: OAuth client ID (app-level credential)
    - BRS_CLIENT_SECRET: OAuth client secret (app-level credential)
    - BRS_API_KEY: (Optional) Static superuser API key for single-club setup
    - BRS_GRANT_TYPE: Grant type (default: "api_key")
    
    For multi-club setup, use get_token_for_club() with dynamically retrieved API keys.
    
    Usage (static):
        provider = BRSAuthProvider()
        token = await provider.get_token()
        headers = {"Authorization": token.as_bearer()}
        
    Usage (per-club):
        provider = BRSAuthProvider()
        token = await provider.get_token_for_club(club_id, api_key)
        headers = {"Authorization": token.as_bearer()}
    """
    
    _instance: Optional["BRSAuthProvider"] = None
    
    def __init__(
        self,
        teesheet_url: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        api_key: Optional[str] = None,
        grant_type: Optional[str] = None,
    ):
        """
        Initialize BRS auth provider.
        
        Args:
            teesheet_url: BRS teesheet base URL (or BRS_TEESHEET_URL env)
            client_id: OAuth client ID (or BRS_CLIENT_ID env)
            client_secret: OAuth client secret (or BRS_CLIENT_SECRET env)
            api_key: Static superuser API key (or BRS_API_KEY env) - optional for per-club mode
            grant_type: OAuth grant type (or BRS_GRANT_TYPE env, default "api_key")
        """
        self.teesheet_url = (
            teesheet_url or 
            os.environ.get("BRS_TEESHEET_URL", "")
        ).rstrip("/")
        
        self.client_id = client_id or os.environ.get("BRS_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("BRS_CLIENT_SECRET", "")
        self.static_api_key = api_key or os.environ.get("BRS_API_KEY", "")
        self.grant_type = grant_type or os.environ.get("BRS_GRANT_TYPE", "api_key")
        
        # Token cache: key is club_id (or "static" for env-var API key)
        self._tokens: Dict[str, BRSToken] = {}
        self._lock = asyncio.Lock()
    
    @classmethod
    def get_instance(cls) -> "BRSAuthProvider":
        """Get singleton instance of BRS auth provider."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @property
    def is_configured(self) -> bool:
        """Check if OAuth app credentials are configured (not API key - that's per-club)."""
        return bool(
            self.teesheet_url and
            self.client_id and
            self.client_secret
        )
    
    @property
    def has_static_api_key(self) -> bool:
        """Check if a static API key is configured."""
        return bool(self.static_api_key)
    
    async def get_token(self, force_refresh: bool = False) -> BRSToken:
        """
        Get a valid OAuth token using static API key from env.
        
        Args:
            force_refresh: Force token refresh even if cached token is valid
            
        Returns:
            Valid BRSToken
            
        Raises:
            ValueError: If credentials not configured
            httpx.HTTPError: If token exchange fails
        """
        if not self.static_api_key:
            raise ValueError(
                "No static BRS_API_KEY configured. Use get_token_for_club() "
                "for per-club authentication."
            )
        
        return await self.get_token_for_club("static", self.static_api_key, force_refresh)
    
    async def get_token_for_club(
        self,
        club_id: str,
        api_key: str,
        force_refresh: bool = False,
    ) -> BRSToken:
        """
        Get a valid OAuth token for a specific club.
        
        Args:
            club_id: Club identifier (used as cache key)
            api_key: API key from club's fe_users table
            force_refresh: Force token refresh even if cached token is valid
            
        Returns:
            Valid BRSToken
            
        Raises:
            ValueError: If OAuth credentials not configured
            httpx.HTTPError: If token exchange fails
        """
        if not self.is_configured:
            raise ValueError(
                "BRS OAuth not configured. Set BRS_TEESHEET_URL, "
                "BRS_CLIENT_ID, and BRS_CLIENT_SECRET environment variables."
            )
        
        cache_key = club_id
        
        # Check if we have a valid cached token
        if not force_refresh:
            cached = self._tokens.get(cache_key)
            if cached and not cached.is_expired:
                return cached
        
        # Acquire lock to prevent concurrent refreshes for same club
        async with self._lock:
            # Double-check after acquiring lock
            if not force_refresh:
                cached = self._tokens.get(cache_key)
                if cached and not cached.is_expired:
                    return cached
            
            # Refresh the token
            token = await self._exchange_token(api_key, club_id)
            self._tokens[cache_key] = token
            return token
    
    async def _exchange_token(self, api_key: str, club_id: str = "unknown") -> BRSToken:
        """
        Exchange credentials for OAuth token.
        
        Calls POST /oauth/v2/token with client credentials.
        """
        url = f"{self.teesheet_url}/oauth/v2/token"
        
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": self.grant_type,
            "api_key": api_key,
        }
        
        logger.info(f"Exchanging BRS OAuth token for club: {club_id}")
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                
                response.raise_for_status()
                data = response.json()
                
                access_token = data.get("access_token")
                if not access_token:
                    raise ValueError(f"No access_token in response: {data}")
                
                # Calculate expiry time
                expires_in = data.get("expires_in", 3600)  # Default 1 hour
                expires_at = time.time() + expires_in
                
                token_type = data.get("token_type", "Bearer")
                
                logger.info(
                    f"BRS OAuth token obtained for club {club_id}, expires in {expires_in}s",
                    extra={"expires_in": expires_in, "token_type": token_type, "club_id": club_id}
                )
                
                return BRSToken(
                    access_token=access_token,
                    expires_at=expires_at,
                    token_type=token_type,
                    club_id=club_id,
                )
                
        except httpx.HTTPStatusError as e:
            logger.error(
                f"BRS OAuth token exchange failed for club {club_id}: {e.response.status_code}",
                extra={"status_code": e.response.status_code, "body": e.response.text[:500], "club_id": club_id}
            )
            raise
        except Exception as e:
            logger.error(f"BRS OAuth token exchange error for club {club_id}: {e}", exc_info=True)
            raise
    
    async def get_auth_headers(self, club_id: Optional[str] = None, api_key: Optional[str] = None) -> dict[str, str]:
        """
        Get Authorization header dict for BRS API calls.
        
        Args:
            club_id: Club ID (required for per-club auth)
            api_key: API key (required for per-club auth if no static key)
            
        Returns:
            Dict with Authorization header
        """
        if club_id and api_key:
            token = await self.get_token_for_club(club_id, api_key)
        else:
            token = await self.get_token()
        return {"Authorization": token.as_bearer()}
    
    def get_cached_token(self, club_id: str) -> Optional[BRSToken]:
        """
        Get cached token for a club without requiring API key.
        
        This is used for subsequent requests after authenticate_club has cached a token.
        
        Args:
            club_id: Club ID to look up
            
        Returns:
            Cached BRSToken if exists and not expired, None otherwise
        """
        cached = self._tokens.get(club_id)
        if cached and not cached.is_expired:
            return cached
        return None
    
    def get_cached_auth_headers(self, club_id: str) -> Optional[dict[str, str]]:
        """
        Get cached Authorization headers for a club.
        
        Used by HTTP utilities to inject auth from cached tokens without needing api_key.
        
        Args:
            club_id: Club ID to look up
            
        Returns:
            Dict with Authorization header if cached token exists, None otherwise
        """
        token = self.get_cached_token(club_id)
        if token:
            return {"Authorization": token.as_bearer()}
        return None
    
    def clear_token(self, club_id: Optional[str] = None) -> None:
        """
        Clear cached token (e.g., after receiving 401).
        
        Args:
            club_id: Specific club to clear, or None to clear all
        """
        if club_id:
            self._tokens.pop(club_id, None)
            logger.info(f"BRS OAuth token cache cleared for club: {club_id}")
        else:
            self._tokens.clear()
            logger.info("BRS OAuth token cache cleared (all)")


# Convenience function for getting auth headers
async def get_brs_auth_headers(club_id: Optional[str] = None, api_key: Optional[str] = None) -> dict[str, str]:
    """
    Get BRS authentication headers.
    
    Returns empty dict if BRS not configured (allows graceful degradation).
    
    Priority order for auth:
    1. If club_id + api_key provided: Exchange for new token
    2. If club_id provided (no api_key): Look for cached token from authenticate_club
    3. Fall back to static BRS_API_KEY if configured
    4. Return empty dict if nothing available
    
    Args:
        club_id: Club ID for per-club auth
        api_key: API key for per-club auth (optional if token already cached)
    """
    provider = BRSAuthProvider.get_instance()
    
    if not provider.is_configured:
        logger.debug("BRS OAuth not configured, returning empty headers")
        return {}
    
    # If api_key provided with club_id, use it (new token exchange)
    if club_id and api_key:
        try:
            return await provider.get_auth_headers(club_id, api_key)
        except Exception as e:
            logger.error(f"Failed to get BRS auth headers for club {club_id}: {e}")
            return {}
    
    # If club_id provided without api_key, try to use cached token
    # (from prior authenticate_club call)
    if club_id:
        cached_headers = provider.get_cached_auth_headers(club_id)
        if cached_headers:
            logger.debug(f"Using cached BRS auth for club: {club_id}")
            return cached_headers
        # No cached token for this club - log warning and continue to static fallback
        logger.debug(f"No cached token for club {club_id}, trying static key fallback")
    
    # Fall back to static key if configured
    if not provider.has_static_api_key:
        if club_id:
            logger.warning(
                f"No cached token for club {club_id} and no static BRS_API_KEY. "
                f"Call authenticate_club first or configure BRS_API_KEY."
            )
        else:
            logger.debug("No API key provided and no static BRS_API_KEY, returning empty headers")
        return {}
    
    try:
        return await provider.get_auth_headers(club_id, api_key)
    except Exception as e:
        logger.error(f"Failed to get BRS auth headers: {e}")
        return {}
