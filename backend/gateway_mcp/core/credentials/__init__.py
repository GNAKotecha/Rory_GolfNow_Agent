"""
Credential Subsystem

Handles OAuth tokens and user-pasted PATs with unified encrypted storage.

Components:
- store.py: Encrypted DB-backed credential store
- oauth_flow.py: OAuth 2.0 authorization flow with PKCE
- pat_flow.py: PAT validation and storage
- providers/: Generic provider implementations (config-driven)
"""
from gateway_mcp.core.credentials.store import (
    Credential,
    CredentialEncryption,
    CredentialStore,
    create_credential_store,
    generate_encryption_key,
)
from gateway_mcp.core.credentials.oauth_flow import (
    OAuthFlow,
    OAuthStateStore,
    create_oauth_flow,
)
from gateway_mcp.core.credentials.pat_flow import (
    PATFlow,
    PATStorageResult,
    PATValidationError,
    create_pat_flow,
)
from gateway_mcp.core.credentials.providers import (
    AuthorizationResult,
    ExtendedOAuthConfig,
    ExtendedPATConfig,
    GenericOAuthProvider,
    GenericPATProvider,
    MetadataEndpoint,
    OAuthProvider,
    OAuthProviderConfig,
    PATProvider,
    PATProviderConfig,
    PATValidationResult,
    ProviderConfig,
    ProviderType,
    PROVIDER_PRESETS,
    TokenExchangeResult,
    create_oauth_provider,
    create_pat_provider,
    create_provider_from_config,
)

__all__ = [
    # Store
    "Credential",
    "CredentialEncryption",
    "CredentialStore",
    "create_credential_store",
    "generate_encryption_key",
    # OAuth Flow
    "OAuthFlow",
    "OAuthStateStore",
    "create_oauth_flow",
    # PAT Flow
    "PATFlow",
    "PATStorageResult",
    "PATValidationError",
    "create_pat_flow",
    # Providers - Base types
    "AuthorizationResult",
    "OAuthProvider",
    "OAuthProviderConfig",
    "PATProvider",
    "PATProviderConfig",
    "PATValidationResult",
    "ProviderConfig",
    "ProviderType",
    "TokenExchangeResult",
    # Providers - Extended config
    "ExtendedOAuthConfig",
    "ExtendedPATConfig",
    "MetadataEndpoint",
    # Providers - Generic implementations
    "GenericOAuthProvider",
    "GenericPATProvider",
    "PROVIDER_PRESETS",
    # Providers - Factory functions
    "create_oauth_provider",
    "create_pat_provider",
    "create_provider_from_config",
]
