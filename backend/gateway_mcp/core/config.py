"""
Gateway MCP Configuration

Loads environment-specific config from YAML files based on GATEWAY_ENV.
Secrets are referenced by env var names, never stored in config.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


# Environment types
Environment = Literal["local", "dev", "qa", "prod"]
ExecutorBackend = Literal["docker_exec", "k8s_exec", "job_runner", "mock"]


class ServiceConfig(BaseModel):
    """Configuration for a single service target."""
    
    # Docker exec (local)
    container: str | None = None
    
    # K8s exec (qa)
    k8s_namespace: str | None = None
    pod_selector: str | None = None
    
    # HTTP services
    url: str | None = None
    
    # Job runner (prod)
    job_template: str | None = None
    
    # Database
    db: str | None = None


class AuditConfig(BaseModel):
    """Audit sink configuration."""
    
    stdout: bool = True
    langfuse: bool = True


class OAuthProviderConfig(BaseModel):
    """OAuth provider configuration."""
    
    type: Literal["oauth"] = "oauth"
    client_id_env: str
    client_secret_env: str
    authz_url: str
    token_url: str
    default_scopes: list[str] = Field(default_factory=list)
    redirect_uri: str


class PATProviderConfig(BaseModel):
    """PAT provider configuration."""
    
    type: Literal["pat"] = "pat"
    validate_url: str
    default_required_scopes: list[str] = Field(default_factory=list)
    token_creation_hint_url: str


class CredentialsConfig(BaseModel):
    """Credentials subsystem configuration."""
    
    providers: dict[str, OAuthProviderConfig | PATProviderConfig] = Field(default_factory=dict)


class UpstreamMCPConfig(BaseModel):
    """Upstream MCP server configuration."""
    
    url: str
    auth_mode: Literal["oauth", "pat"]
    provider: str


class Settings(BaseSettings):
    """Gateway MCP settings loaded from env + YAML."""
    
    # Core
    env: Environment = "local"
    executor_backend: ExecutorBackend = "docker_exec"
    
    # Service map
    services: dict[str, ServiceConfig] = Field(default_factory=dict)
    
    # Audit
    audit: AuditConfig = Field(default_factory=AuditConfig)
    
    # Credentials
    credentials: CredentialsConfig = Field(default_factory=CredentialsConfig)
    
    # Upstream MCP servers
    upstream_mcps: dict[str, UpstreamMCPConfig] = Field(default_factory=dict)
    
    # Auth (from env vars)
    service_token: str = Field(default="", alias="GATEWAY_SERVICE_TOKEN")
    operator_user_ids: list[str] = Field(default_factory=list)
    credential_encryption_key: str = Field(default="", alias="GATEWAY_CREDENTIAL_ENCRYPTION_KEY")
    
    class Config:
        env_prefix = "GATEWAY_"
        extra = "ignore"


def load_yaml_config(env: Environment) -> dict[str, Any]:
    """Load YAML config file for the given environment."""
    config_dir = Path(__file__).parent.parent / "configs"
    config_file = config_dir / f"{env}.yaml"
    
    if not config_file.exists():
        # Return minimal defaults if config file doesn't exist
        return {
            "env": env,
            "executor_backend": "mock" if env == "local" else "docker_exec",
            "services": {},
            "audit": {"stdout": True, "langfuse": True},
        }
    
    with open(config_file) as f:
        return yaml.safe_load(f) or {}


def parse_operator_ids(env_value: str | None) -> list[str]:
    """Parse GATEWAY_OPERATOR_USER_IDS from comma-separated string."""
    if not env_value:
        return []
    return [uid.strip() for uid in env_value.split(",") if uid.strip()]


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Settings are loaded from:
    1. YAML config file based on GATEWAY_ENV
    2. Environment variables (override YAML)
    """
    env = os.environ.get("GATEWAY_ENV", "local")
    if env not in ("local", "dev", "qa", "prod"):
        env = "local"
    
    yaml_config = load_yaml_config(env)  # type: ignore
    
    # Parse operator IDs from env
    operator_ids = parse_operator_ids(os.environ.get("GATEWAY_OPERATOR_USER_IDS"))
    
    # Merge YAML config with env overrides
    return Settings(
        **yaml_config,
        operator_user_ids=operator_ids,
    )


def clear_settings_cache():
    """Clear the settings cache (for testing)."""
    get_settings.cache_clear()
