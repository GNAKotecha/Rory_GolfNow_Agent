"""
PAT Validation Flow

Handles Personal Access Token validation and storage.
Used for providers like GitHub that support user-pasted PATs.

Flow:
1. User creates PAT at provider's token creation page
2. User pastes PAT into our UI
3. We validate PAT against provider API
4. We extract user info and scopes
5. We store PAT encrypted in database

Security considerations:
- PATs are validated before storage
- PATs are encrypted at rest
- Scope validation ensures minimum required permissions
- Failed validation returns actionable errors
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional

from gateway_mcp.core.credentials.providers.base import (
    PATProvider,
    PATValidationResult,
)
from gateway_mcp.core.credentials.providers.generic import (
    GenericPATProvider,
    create_pat_provider,
)


@dataclass
class PATValidationError:
    """
    Error details for PAT validation failure.
    
    Attributes:
        code: Error code (e.g., "invalid_token", "insufficient_scopes").
        message: Human-readable error message.
        missing_scopes: List of missing scopes (if scope check failed).
        token_creation_url: URL to create a new token with correct scopes.
    """
    code: str
    message: str
    missing_scopes: list[str] = None
    token_creation_url: Optional[str] = None
    
    def __post_init__(self):
        if self.missing_scopes is None:
            self.missing_scopes = []


@dataclass
class PATStorageResult:
    """
    Result of PAT storage operation.
    
    Attributes:
        success: Whether storage succeeded.
        provider: Provider name.
        user_login: User's login name from provider.
        scopes: Scopes the PAT has.
        metadata: Additional metadata from validation.
        error: Error details if storage failed.
    """
    success: bool
    provider: str
    user_login: Optional[str] = None
    scopes: list[str] = None
    metadata: dict[str, Any] = None
    error: Optional[PATValidationError] = None
    
    def __post_init__(self):
        if self.scopes is None:
            self.scopes = []
        if self.metadata is None:
            self.metadata = {}


class PATFlow:
    """
    Orchestrates PAT validation and storage flow.
    
    Handles:
    - PAT validation against provider API
    - Scope checking
    - Error handling with actionable messages
    """
    
    def __init__(
        self,
        providers: Dict[str, PATProvider],
    ):
        """
        Initialize PAT flow handler.
        
        Args:
            providers: Dict mapping provider names to PATProvider instances.
        """
        self._providers = providers
    
    def validate_and_prepare(
        self,
        provider: str,
        pat: str,
        required_scopes: Optional[list[str]] = None,
    ) -> PATStorageResult:
        """
        Validate a PAT and prepare for storage.
        
        Validates the PAT, checks scopes, and returns metadata for storage.
        Does NOT store the PAT - caller should use CredentialStore.
        
        Args:
            provider: Provider name (e.g., "github").
            pat: The personal access token.
            required_scopes: Minimum required scopes (defaults to provider config).
            
        Returns:
            PATStorageResult with validation result and metadata.
        """
        pat_provider = self._providers.get(provider)
        if pat_provider is None:
            return PATStorageResult(
                success=False,
                provider=provider,
                error=PATValidationError(
                    code="unknown_provider",
                    message=f"Unknown PAT provider: {provider}",
                ),
            )
        
        # Validate the token
        validation_result = pat_provider.validate_token(pat)
        
        if not validation_result.valid:
            return PATStorageResult(
                success=False,
                provider=provider,
                error=PATValidationError(
                    code="invalid_token",
                    message=validation_result.error or "Invalid personal access token",
                    token_creation_url=pat_provider.config.token_creation_hint_url,
                ),
            )
        
        # Check scopes
        required = required_scopes or pat_provider.config.required_scopes
        if required:
            has_all, missing = pat_provider.check_scopes(pat, required)
            
            if not has_all:
                return PATStorageResult(
                    success=False,
                    provider=provider,
                    error=PATValidationError(
                        code="insufficient_scopes",
                        message=f"Token is missing required scopes: {', '.join(missing)}",
                        missing_scopes=missing,
                        token_creation_url=pat_provider.config.token_creation_hint_url,
                    ),
                )
        
        # Success - return metadata for storage
        return PATStorageResult(
            success=True,
            provider=provider,
            user_login=validation_result.user_login,
            scopes=validation_result.scopes,
            metadata={
                "user_id": validation_result.user_id,
                "user_login": validation_result.user_login,
                **validation_result.metadata,
            },
        )
    
    def get_token_creation_url(
        self,
        provider: str,
        scopes: Optional[list[str]] = None,
    ) -> Optional[str]:
        """
        Get URL for creating a new PAT.
        
        Args:
            provider: Provider name.
            scopes: Scopes to pre-select (defaults to provider defaults).
            
        Returns:
            Token creation URL, or None if provider not found.
        """
        pat_provider = self._providers.get(provider)
        if pat_provider is None:
            return None
        
        # Use provider's method if available, otherwise return config URL
        if hasattr(pat_provider, "get_token_creation_url"):
            return pat_provider.get_token_creation_url(scopes)
        
        return pat_provider.config.token_creation_hint_url
    
    def get_provider(self, provider: str) -> Optional[PATProvider]:
        """Get provider by name."""
        return self._providers.get(provider)
    
    def list_providers(self) -> list[str]:
        """List available provider names."""
        return list(self._providers.keys())


def create_pat_flow(
    config: dict,
) -> PATFlow:
    """
    Create PATFlow from configuration.
    
    Automatically creates providers for all PAT-type entries in config.
    
    Args:
        config: Credentials configuration with providers section.
        
    Returns:
        Configured PATFlow instance.
    """
    providers = {}
    providers_config = config.get("providers", {})
    
    # Create providers for all PAT entries
    for name, provider_config in providers_config.items():
        if provider_config.get("type") == "pat":
            providers[name] = create_pat_provider(name, provider_config)
    
    return PATFlow(providers=providers)
