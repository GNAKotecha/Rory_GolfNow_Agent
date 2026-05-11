"""
Authentication Module

Validates service tokens and extracts user identity from requests.

Authentication flow:
1. Check Authorization header for Bearer token
2. Validate token against configured service tokens
3. Extract X-User-Id header for user identity
4. Return AuthResult with user_id and any scopes from token

Service tokens are configured per-environment in YAML config.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class AuthResult:
    """Result of authentication check."""
    
    user_id: int
    token_scopes: list[str]
    is_service_token: bool = True  # vs user OAuth token, future
    
    @property
    def is_operator(self) -> bool:
        """Check if caller has operator role (can invoke low_write tools)."""
        return "operator" in self.token_scopes or "admin" in self.token_scopes
    
    @property
    def is_admin(self) -> bool:
        """Check if caller has admin role."""
        return "admin" in self.token_scopes


class AuthError(Exception):
    """Authentication failed."""
    
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class AuthService:
    """
    Service token and user identity validation.
    
    Validates service tokens from Authorization header and extracts
    user identity from X-User-Id header.
    
    Configuration (from settings):
    - service_tokens: dict mapping token -> scopes list
    - require_user_id: whether X-User-Id is mandatory
    """
    
    def __init__(
        self,
        service_tokens: dict[str, list[str]],
        require_user_id: bool = True,
    ):
        """
        Initialize auth service.
        
        Args:
            service_tokens: Map of token value -> list of scopes.
                           Example: {"secret-123": ["operator"], "admin-456": ["admin"]}
            require_user_id: If True, X-User-Id header is mandatory.
        """
        self._service_tokens = service_tokens
        self._require_user_id = require_user_id
    
    def authenticate(
        self,
        authorization_header: Optional[str],
        user_id_header: Optional[str],
    ) -> AuthResult:
        """
        Validate request authentication.
        
        Args:
            authorization_header: Value of Authorization header
            user_id_header: Value of X-User-Id header
            
        Returns:
            AuthResult with user identity and scopes
            
        Raises:
            AuthError: If authentication fails
        """
        # Validate Authorization header
        if not authorization_header:
            raise AuthError("Missing Authorization header")
        
        if not authorization_header.startswith("Bearer "):
            raise AuthError("Invalid Authorization header format (expected 'Bearer <token>')")
        
        token = authorization_header[7:]  # Strip "Bearer "
        
        if not token:
            raise AuthError("Empty bearer token")
        
        # Look up token scopes
        scopes = self._service_tokens.get(token)
        if scopes is None:
            raise AuthError("Invalid service token")
        
        # Validate X-User-Id header
        if self._require_user_id:
            if not user_id_header:
                raise AuthError("Missing X-User-Id header")
        
        user_id = self._parse_user_id(user_id_header)
        
        return AuthResult(
            user_id=user_id,
            token_scopes=list(scopes),
            is_service_token=True,
        )
    
    def _parse_user_id(self, user_id_header: Optional[str]) -> int:
        """Parse and validate X-User-Id header value."""
        if not user_id_header:
            # Return default user_id if not required
            return 0
        
        try:
            user_id = int(user_id_header)
            if user_id < 0:
                raise AuthError("X-User-Id must be non-negative")
            return user_id
        except ValueError:
            raise AuthError("X-User-Id must be a valid integer")


def create_auth_service_from_settings(settings) -> AuthService:
    """
    Factory to create AuthService from gateway settings.
    
    Args:
        settings: Gateway settings object with service_tokens dict
        
    Returns:
        Configured AuthService
    """
    # Preferred format: explicit token->scopes map.
    service_tokens = getattr(settings, "service_tokens", {}) or {}

    # Backward-compatible fallback for single-token config via GATEWAY_SERVICE_TOKEN.
    # This keeps local/dev Gateway usable without requiring a token map file.
    if not service_tokens:
        single_token = getattr(settings, "service_token", "")
        if single_token:
            service_tokens = {single_token: ["operator", "admin"]}

    require_user_id = getattr(settings, "require_user_id", True)
    
    return AuthService(
        service_tokens=service_tokens,
        require_user_id=require_user_id,
    )
