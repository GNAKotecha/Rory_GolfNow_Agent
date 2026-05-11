"""
Credential Providers

Generic provider implementations for OAuth and PAT authentication.
Providers are configured via YAML/dict config rather than requiring
separate code files for each external service.
"""
from gateway_mcp.core.credentials.providers.base import (
    AuthorizationResult,
    OAuthProvider,
    OAuthProviderConfig,
    PATProvider,
    PATProviderConfig,
    PATValidationResult,
    ProviderConfig,
    ProviderType,
    TokenExchangeResult,
)
from gateway_mcp.core.credentials.providers.generic import (
    ExtendedOAuthConfig,
    ExtendedPATConfig,
    GenericOAuthProvider,
    GenericPATProvider,
    MetadataEndpoint,
    PROVIDER_PRESETS,
    create_oauth_provider,
    create_pat_provider,
    create_provider_from_config,
)

__all__ = [
    # Base types
    "AuthorizationResult",
    "OAuthProvider",
    "OAuthProviderConfig",
    "PATProvider",
    "PATProviderConfig",
    "PATValidationResult",
    "ProviderConfig",
    "ProviderType",
    "TokenExchangeResult",
    # Extended config types
    "ExtendedOAuthConfig",
    "ExtendedPATConfig",
    "MetadataEndpoint",
    # Generic implementations
    "GenericOAuthProvider",
    "GenericPATProvider",
    "PROVIDER_PRESETS",
    # Factory functions
    "create_oauth_provider",
    "create_pat_provider",
    "create_provider_from_config",
]


