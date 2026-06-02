"""
Generic Credential Providers

Configuration-driven OAuth and PAT provider implementations.
Providers are defined via config rather than requiring separate code files.

This allows adding new external MCP integrations by updating configuration
rather than writing new provider classes.
"""
import base64
import hashlib
import os
import secrets
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Union
from urllib.parse import urlencode

import httpx

from gateway_mcp.core.credentials.providers.base import (
    AuthorizationResult,
    OAuthProviderConfig,
    PATProviderConfig,
    PATValidationResult,
    ProviderType,
    TokenExchangeResult,
)


@dataclass
class MetadataEndpoint:
    """
    Configuration for fetching provider-specific metadata.
    
    Attributes:
        url: URL to fetch metadata from (can contain {access_token} placeholder).
        method: HTTP method (GET or POST).
        headers: Additional headers to send.
        extract: Dict mapping output keys to JSONPath-like expressions.
    """
    url: str
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    extract: dict[str, str] = field(default_factory=dict)


@dataclass
class ExtendedOAuthConfig(OAuthProviderConfig):
    """
    Extended OAuth configuration with metadata fetching.
    
    Attributes:
        metadata_endpoint: Optional endpoint for fetching resource metadata.
        scope_separator: Separator for scope strings (default: space).
    """
    metadata_endpoint: Optional[MetadataEndpoint] = None
    scope_separator: str = " "


@dataclass 
class ExtendedPATConfig(PATProviderConfig):
    """
    Extended PAT configuration with validation details.
    
    Attributes:
        validate_method: HTTP method for validation (default: GET).
        validate_headers: Headers to send for validation.
        user_id_path: JSONPath to extract user ID from validation response.
        user_login_path: JSONPath to extract username from validation response.
        metadata_paths: Dict of metadata keys to JSONPaths.
        scope_parse_mode: How to parse scopes ("header", "response_field", "none").
        scope_field: Field name or header for scopes.
    """
    validate_method: str = "GET"
    validate_headers: dict[str, str] = field(default_factory=dict)
    user_id_path: str = "id"
    user_login_path: str = "login"
    metadata_paths: dict[str, str] = field(default_factory=dict)
    scope_parse_mode: str = "header"  # "header", "response_field", "none"
    scope_field: str = "x-oauth-scopes"


class GenericOAuthProvider:
    """
    Generic OAuth 2.0 provider implementation.
    
    Works with any OAuth 2.0 authorization code flow provider
    via configuration rather than custom code.
    """
    
    def __init__(
        self,
        config: ExtendedOAuthConfig,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ):
        """
        Initialize generic OAuth provider.
        
        Args:
            config: Provider configuration.
            client_id: OAuth client ID (or read from env via config.client_id_env).
            client_secret: OAuth client secret (or read from env).
        """
        self._config = config
        self._client_id = client_id or os.environ.get(config.client_id_env, "")
        self._client_secret = client_secret or os.environ.get(config.client_secret_env, "")
        self._http_client = httpx.Client(timeout=30.0)
    
    @property
    def config(self) -> ExtendedOAuthConfig:
        """Get provider configuration."""
        return self._config
    
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
            AuthorizationResult with URL, state, and code_verifier (if PKCE).
        """
        code_verifier = None
        code_challenge = None
        
        if self._config.use_pkce:
            code_verifier = self._generate_code_verifier()
            code_challenge = self._generate_code_challenge(code_verifier)
        
        if state is None:
            state = secrets.token_urlsafe(32)
        
        scope_str = self._config.scope_separator.join(
            scopes or self._config.default_scopes
        )
        
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._config.redirect_uri,
            "response_type": "code",
            "scope": scope_str,
            "state": state,
            **self._config.additional_params,
        }
        
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        
        authorization_url = f"{self._config.authz_url}?{urlencode(params)}"
        
        return AuthorizationResult(
            authorization_url=authorization_url,
            state=state,
            code_verifier=code_verifier,
        )
    
    def exchange_code(
        self,
        code: str,
        code_verifier: Optional[str] = None,
    ) -> TokenExchangeResult:
        """
        Exchange authorization code for tokens.
        
        Args:
            code: Authorization code from callback.
            code_verifier: PKCE code verifier.
            
        Returns:
            TokenExchangeResult with access token, refresh token, etc.
        """
        data = {
            "grant_type": "authorization_code",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "code": code,
            "redirect_uri": self._config.redirect_uri,
        }
        
        if code_verifier:
            data["code_verifier"] = code_verifier
        
        response = self._http_client.post(
            self._config.token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        
        token_data = response.json()
        
        return TokenExchangeResult(
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            expires_in=token_data.get("expires_in", 3600),
            scope=token_data.get("scope", ""),
            token_type=token_data.get("token_type", "Bearer"),
        )
    
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
        """
        data = {
            "grant_type": "refresh_token",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "refresh_token": refresh_token,
        }
        
        response = self._http_client.post(
            self._config.token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        
        token_data = response.json()
        
        return TokenExchangeResult(
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token", refresh_token),
            expires_in=token_data.get("expires_in", 3600),
            scope=token_data.get("scope", ""),
            token_type=token_data.get("token_type", "Bearer"),
        )
    
    def get_resource_metadata(
        self,
        access_token: str,
    ) -> dict[str, Any]:
        """
        Fetch provider-specific resource metadata.
        
        Args:
            access_token: Valid access token.
            
        Returns:
            Provider-specific metadata dict.
        """
        if not self._config.metadata_endpoint:
            return {}
        
        endpoint = self._config.metadata_endpoint
        url = endpoint.url.format(access_token=access_token)
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            **endpoint.headers,
        }
        
        response = self._http_client.request(
            method=endpoint.method,
            url=url,
            headers=headers,
        )
        response.raise_for_status()
        
        data = response.json()
        
        # Extract configured fields
        metadata = {}
        for key, path in endpoint.extract.items():
            metadata[key] = self._extract_path(data, path)
        
        # Include raw response for reference
        metadata["_raw"] = data
        
        return metadata
    
    def _extract_path(self, data: Any, path: str) -> Any:
        """
        Extract value from nested dict/list using dot notation.
        
        Args:
            data: Data to extract from.
            path: Dot-separated path (e.g., "user.id" or "[0].id").
            
        Returns:
            Extracted value or None.
        """
        current = data
        
        for part in path.split("."):
            if current is None:
                return None
            
            # Handle array index
            if part.startswith("[") and part.endswith("]"):
                try:
                    idx = int(part[1:-1])
                    current = current[idx] if isinstance(current, list) else None
                except (ValueError, IndexError):
                    return None
            else:
                current = current.get(part) if isinstance(current, dict) else None
        
        return current
    
    def _generate_code_verifier(self, length: int = 64) -> str:
        """Generate PKCE code verifier."""
        return secrets.token_urlsafe(length)[:length]
    
    def _generate_code_challenge(self, code_verifier: str) -> str:
        """Generate PKCE code challenge from verifier."""
        digest = hashlib.sha256(code_verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")
    
    def __del__(self):
        """Clean up HTTP client."""
        if hasattr(self, "_http_client"):
            self._http_client.close()


class GenericPATProvider:
    """
    Generic PAT (Personal Access Token) provider implementation.
    
    Works with any PAT-based authentication provider via configuration.
    """
    
    def __init__(
        self,
        config: ExtendedPATConfig,
    ):
        """
        Initialize generic PAT provider.
        
        Args:
            config: Provider configuration.
        """
        self._config = config
        self._http_client = httpx.Client(timeout=30.0)
    
    @property
    def config(self) -> ExtendedPATConfig:
        """Get provider configuration."""
        return self._config
    
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
        try:
            headers = {
                "Authorization": f"Bearer {pat}",
                "Accept": "application/json",
                **self._config.validate_headers,
            }
            
            response = self._http_client.request(
                method=self._config.validate_method,
                url=self._config.validate_url,
                headers=headers,
            )
            
            if response.status_code == 401:
                return PATValidationResult(
                    valid=False,
                    error="Invalid or expired personal access token",
                )
            
            if response.status_code == 403:
                return PATValidationResult(
                    valid=False,
                    error="Access forbidden - token may lack required permissions",
                )
            
            response.raise_for_status()
            
            data = response.json()
            
            # Extract user info using configured paths
            user_id = self._extract_path(data, self._config.user_id_path)
            user_login = self._extract_path(data, self._config.user_login_path)
            
            # Extract scopes based on mode
            scopes = self._extract_scopes(response, data)
            
            # Extract additional metadata
            metadata = {}
            for key, path in self._config.metadata_paths.items():
                metadata[key] = self._extract_path(data, path)
            
            return PATValidationResult(
                valid=True,
                user_id=str(user_id) if user_id else None,
                user_login=str(user_login) if user_login else None,
                scopes=scopes,
                metadata=metadata,
            )
            
        except httpx.TimeoutException:
            return PATValidationResult(
                valid=False,
                error="Request timed out while validating token",
            )
        except httpx.HTTPStatusError as e:
            return PATValidationResult(
                valid=False,
                error=f"API error: {e.response.status_code}",
            )
        except Exception as e:
            return PATValidationResult(
                valid=False,
                error=f"Validation failed: {str(e)}",
            )
    
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
        required = required_scopes or self._config.required_scopes
        
        result = self.validate_token(pat)
        
        if not result.valid:
            return False, required
        
        token_scopes = set(result.scopes)
        missing = [s for s in required if not self._scope_matches(s, token_scopes)]
        
        return len(missing) == 0, missing
    
    def get_token_creation_url(
        self,
        scopes: Optional[list[str]] = None,
        description: str = "External Integration",
    ) -> str:
        """
        Get URL for creating a new PAT.
        
        Args:
            scopes: Scopes to pre-select.
            description: Token description.
            
        Returns:
            Token creation URL.
        """
        base_url = self._config.token_creation_hint_url
        
        if not base_url:
            return ""
        
        scopes = scopes or self._config.required_scopes
        
        # Most providers support scopes query param
        params = {}
        if scopes:
            params["scopes"] = ",".join(scopes)
        if description:
            params["description"] = description
        
        if params:
            return f"{base_url}?{urlencode(params)}"
        return base_url
    
    def _extract_scopes(
        self,
        response: httpx.Response,
        data: dict,
    ) -> list[str]:
        """
        Extract scopes from response based on config.
        
        Args:
            response: HTTP response object.
            data: Parsed JSON response body.
            
        Returns:
            List of scope strings.
        """
        if self._config.scope_parse_mode == "header":
            header_value = response.headers.get(self._config.scope_field, "")
            return [s.strip() for s in header_value.split(",") if s.strip()]
        
        elif self._config.scope_parse_mode == "response_field":
            scopes = self._extract_path(data, self._config.scope_field)
            if isinstance(scopes, list):
                return scopes
            elif isinstance(scopes, str):
                return scopes.split()
            return []
        
        return []
    
    def _scope_matches(self, required: str, available: set[str]) -> bool:
        """
        Check if a required scope is satisfied.
        
        Handles common scope hierarchies (e.g., "repo" includes "repo:status").
        """
        if required in available:
            return True
        
        # Check parent scopes
        if ":" in required:
            parent = required.split(":")[0]
            if parent in available:
                return True
        
        return False
    
    def _extract_path(self, data: Any, path: str) -> Any:
        """Extract value from nested dict using dot notation."""
        current = data
        
        for part in path.split("."):
            if current is None:
                return None
            
            if part.startswith("[") and part.endswith("]"):
                try:
                    idx = int(part[1:-1])
                    current = current[idx] if isinstance(current, list) else None
                except (ValueError, IndexError):
                    return None
            else:
                current = current.get(part) if isinstance(current, dict) else None
        
        return current
    
    def __del__(self):
        """Clean up HTTP client."""
        if hasattr(self, "_http_client"):
            self._http_client.close()


# --- Provider Factory ---

# Pre-defined configurations for common providers
PROVIDER_PRESETS: dict[str, dict] = {
    "atlassian": {
        "type": "oauth",
        "display_name": "Atlassian (Jira/Confluence)",
        "authz_url": "https://auth.atlassian.com/authorize",
        "token_url": "https://auth.atlassian.com/oauth/token",
        "default_scopes": ["read:jira-work", "write:jira-work"],
        "use_pkce": True,
        "additional_params": {
            "audience": "api.atlassian.com",
            "prompt": "consent",
        },
        "metadata_endpoint": {
            "url": "https://api.atlassian.com/oauth/token/accessible-resources",
            "method": "GET",
            "extract": {
                "cloud_id": "[0].id",
                "cloud_name": "[0].name",
                "cloud_url": "[0].url",
            },
        },
        "icon_url": "https://wac-cdn.atlassian.com/assets/img/favicons/atlassian/favicon.png",
    },
    "github": {
        "type": "pat",
        "display_name": "GitHub",
        "validate_url": "https://api.github.com/user",
        "validate_headers": {
            "X-GitHub-Api-Version": "2022-11-28",
        },
        "token_creation_hint_url": "https://github.com/settings/tokens/new",
        "required_scopes": ["repo", "read:user"],
        "scope_parse_mode": "header",
        "scope_field": "x-oauth-scopes",
        "user_id_path": "id",
        "user_login_path": "login",
        "metadata_paths": {
            "name": "name",
            "email": "email",
            "avatar_url": "avatar_url",
            "html_url": "html_url",
        },
        "icon_url": "https://github.githubassets.com/favicons/favicon.png",
    },
}


def create_oauth_provider(
    name: str,
    config: Optional[dict] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
) -> GenericOAuthProvider:
    """
    Create an OAuth provider from config.
    
    Args:
        name: Provider name (e.g., "atlassian").
        config: Provider configuration (merged with preset if exists).
        client_id: OAuth client ID.
        client_secret: OAuth client secret.
        
    Returns:
        Configured GenericOAuthProvider.
    """
    # Start with preset if available
    preset = PROVIDER_PRESETS.get(name, {}).copy()
    
    # Merge with provided config
    if config:
        preset.update(config)
    
    # Build metadata endpoint if configured
    metadata_endpoint = None
    if "metadata_endpoint" in preset:
        me = preset["metadata_endpoint"]
        metadata_endpoint = MetadataEndpoint(
            url=me.get("url", ""),
            method=me.get("method", "GET"),
            headers=me.get("headers", {}),
            extract=me.get("extract", {}),
        )
    
    provider_config = ExtendedOAuthConfig(
        name=name,
        type=ProviderType.OAUTH,
        display_name=preset.get("display_name", name.title()),
        default_scopes=preset.get("default_scopes", []),
        icon_url=preset.get("icon_url"),
        authz_url=preset.get("authz_url", ""),
        token_url=preset.get("token_url", ""),
        client_id_env=preset.get("client_id_env", f"{name.upper()}_CLIENT_ID"),
        client_secret_env=preset.get("client_secret_env", f"{name.upper()}_CLIENT_SECRET"),
        redirect_uri=preset.get("redirect_uri", ""),
        use_pkce=preset.get("use_pkce", True),
        additional_params=preset.get("additional_params", {}),
        metadata_endpoint=metadata_endpoint,
        scope_separator=preset.get("scope_separator", " "),
    )
    
    return GenericOAuthProvider(
        config=provider_config,
        client_id=client_id,
        client_secret=client_secret,
    )


def create_pat_provider(
    name: str,
    config: Optional[dict] = None,
) -> GenericPATProvider:
    """
    Create a PAT provider from config.
    
    Args:
        name: Provider name (e.g., "github").
        config: Provider configuration (merged with preset if exists).
        
    Returns:
        Configured GenericPATProvider.
    """
    # Start with preset if available
    preset = PROVIDER_PRESETS.get(name, {}).copy()
    
    # Merge with provided config
    if config:
        preset.update(config)
    
    provider_config = ExtendedPATConfig(
        name=name,
        type=ProviderType.PAT,
        display_name=preset.get("display_name", name.title()),
        default_scopes=preset.get("default_scopes", []),
        icon_url=preset.get("icon_url"),
        validate_url=preset.get("validate_url", ""),
        token_creation_hint_url=preset.get("token_creation_hint_url", ""),
        required_scopes=preset.get("required_scopes", []),
        scope_header=preset.get("scope_header", "x-oauth-scopes"),
        validate_method=preset.get("validate_method", "GET"),
        validate_headers=preset.get("validate_headers", {}),
        user_id_path=preset.get("user_id_path", "id"),
        user_login_path=preset.get("user_login_path", "login"),
        metadata_paths=preset.get("metadata_paths", {}),
        scope_parse_mode=preset.get("scope_parse_mode", "header"),
        scope_field=preset.get("scope_field", "x-oauth-scopes"),
    )
    
    return GenericPATProvider(config=provider_config)


def create_provider_from_config(
    name: str,
    config: dict,
) -> Union[GenericOAuthProvider, GenericPATProvider]:
    """
    Create appropriate provider based on config type.
    
    Args:
        name: Provider name.
        config: Provider configuration with "type" field.
        
    Returns:
        OAuth or PAT provider instance.
        
    Raises:
        ValueError: If provider type is unknown.
    """
    provider_type = config.get("type", "").lower()
    
    if provider_type == "oauth":
        return create_oauth_provider(name, config)
    elif provider_type == "pat":
        return create_pat_provider(name, config)
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")
