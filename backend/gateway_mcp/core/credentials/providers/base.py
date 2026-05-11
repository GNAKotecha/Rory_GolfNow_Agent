"""
Credential Provider Protocol

Defines the interface for external credential providers (OAuth and PAT).
Each provider implements this protocol to handle:
- Authorization URL generation
- Token exchange
- Token refresh
- Token validation
- Scope management
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable


class ProviderType(str, Enum):
    """Type of credential provider."""
    OAUTH = "oauth"
    PAT = "pat"


@dataclass
class ProviderConfig:
    """
    Base configuration for a credential provider.
    
    Attributes:
        name: Provider identifier (e.g., "atlassian", "github").
        type: Provider type (oauth or pat).
        display_name: Human-readable name for UI.
        default_scopes: Default scopes to request.
        icon_url: Optional icon URL for UI.
    """
    name: str
    type: ProviderType
    display_name: str
    default_scopes: list[str] = field(default_factory=list)
    icon_url: Optional[str] = None


@dataclass
class OAuthProviderConfig(ProviderConfig):
    """
    Configuration for an OAuth provider.
    
    Attributes:
        authz_url: Authorization endpoint URL.
        token_url: Token exchange endpoint URL.
        client_id_env: Environment variable name for client ID.
        client_secret_env: Environment variable name for client secret.
        redirect_uri: OAuth callback URI.
        use_pkce: Whether to use PKCE (recommended).
        additional_params: Extra parameters for authorization request.
    """
    authz_url: str = ""
    token_url: str = ""
    client_id_env: str = ""
    client_secret_env: str = ""
    redirect_uri: str = ""
    use_pkce: bool = True
    additional_params: dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        self.type = ProviderType.OAUTH


@dataclass
class PATProviderConfig(ProviderConfig):
    """
    Configuration for a PAT provider.
    
    Attributes:
        validate_url: URL to validate the PAT (e.g., GET /user).
        token_creation_hint_url: URL to help users create a token.
        required_scopes: Minimum required scopes for the PAT.
        scope_header: HTTP header containing scope info (for validation).
    """
    validate_url: str = ""
    token_creation_hint_url: str = ""
    required_scopes: list[str] = field(default_factory=list)
    scope_header: str = "x-oauth-scopes"
    
    def __post_init__(self):
        self.type = ProviderType.PAT


@dataclass
class AuthorizationResult:
    """
    Result of authorization URL generation.
    
    Attributes:
        authorization_url: Full URL to redirect user to.
        state: State parameter for CSRF protection.
        code_verifier: PKCE code verifier (if using PKCE).
    """
    authorization_url: str
    state: str
    code_verifier: Optional[str] = None


@dataclass
class TokenExchangeResult:
    """
    Result of OAuth token exchange.
    
    Attributes:
        access_token: The access token.
        refresh_token: The refresh token (if provided).
        expires_in: Token lifetime in seconds.
        scope: Space-separated scope string.
        token_type: Token type (usually "Bearer").
        metadata: Provider-specific metadata.
    """
    access_token: str
    refresh_token: Optional[str] = None
    expires_in: int = 3600
    scope: str = ""
    token_type: str = "Bearer"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PATValidationResult:
    """
    Result of PAT validation.
    
    Attributes:
        valid: Whether the PAT is valid.
        user_id: User identifier from the provider.
        user_login: Username/login from the provider.
        scopes: List of scopes the PAT has.
        metadata: Additional metadata from validation.
        error: Error message if validation failed.
    """
    valid: bool
    user_id: Optional[str] = None
    user_login: Optional[str] = None
    scopes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@runtime_checkable
class OAuthProvider(Protocol):
    """
    Protocol for OAuth credential providers.
    
    Implementations handle OAuth 2.0 authorization code flow with optional PKCE.
    """
    
    @property
    def config(self) -> OAuthProviderConfig:
        """Get provider configuration."""
        ...
    
    def get_authorization_url(
        self,
        scopes: Optional[list[str]] = None,
        state: Optional[str] = None,
    ) -> AuthorizationResult:
        """
        Generate OAuth authorization URL.
        
        Args:
            scopes: Scopes to request (defaults to config.default_scopes).
            state: Optional state parameter (generated if not provided).
            
        Returns:
            AuthorizationResult with URL, state, and optional code_verifier.
        """
        ...
    
    def exchange_code(
        self,
        code: str,
        code_verifier: Optional[str] = None,
    ) -> TokenExchangeResult:
        """
        Exchange authorization code for tokens.
        
        Args:
            code: Authorization code from callback.
            code_verifier: PKCE code verifier (if PKCE was used).
            
        Returns:
            TokenExchangeResult with access token, refresh token, etc.
            
        Raises:
            Exception: If token exchange fails.
        """
        ...
    
    def refresh_token(
        self,
        refresh_token: str,
    ) -> TokenExchangeResult:
        """
        Refresh an access token.
        
        Args:
            refresh_token: The refresh token.
            
        Returns:
            TokenExchangeResult with new access token.
            
        Raises:
            Exception: If refresh fails.
        """
        ...
    
    def get_resource_metadata(
        self,
        access_token: str,
    ) -> dict[str, Any]:
        """
        Get provider-specific resource metadata.
        
        For example, Atlassian needs cloud_id for API calls.
        
        Args:
            access_token: Valid access token.
            
        Returns:
            Provider-specific metadata dict.
        """
        ...


@runtime_checkable
class PATProvider(Protocol):
    """
    Protocol for PAT (Personal Access Token) credential providers.
    
    Implementations handle PAT validation and scope checking.
    """
    
    @property
    def config(self) -> PATProviderConfig:
        """Get provider configuration."""
        ...
    
    def validate_token(
        self,
        pat: str,
    ) -> PATValidationResult:
        """
        Validate a PAT and extract user info.
        
        Args:
            pat: The personal access token.
            
        Returns:
            PATValidationResult with validation status and user info.
        """
        ...
    
    def check_scopes(
        self,
        pat: str,
        required_scopes: Optional[list[str]] = None,
    ) -> tuple[bool, list[str]]:
        """
        Check if PAT has required scopes.
        
        Args:
            pat: The personal access token.
            required_scopes: Scopes to check for (defaults to config.required_scopes).
            
        Returns:
            Tuple of (has_all_scopes, missing_scopes).
        """
        ...
