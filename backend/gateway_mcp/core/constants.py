"""
Gateway MCP Constants

Canonical service names and other constants used across the gateway.
All service references should use these constants to prevent drift.
"""

# ============================================================================
# Service Names (must match configs/*.yaml)
# ============================================================================

# BRS Services - local containers or remote APIs
class Services:
    """Canonical service names matching config files."""
    
    # BRS Teesheet container (docker exec)
    TEESHEET = "teesheet"
    
    # Admin API - HTTP service for internal operations
    ADMIN_API = "admin_api"
    
    # Config API - HTTP service for club configuration
    CONFIG_API = "config_api"
    
    # MySQL database container
    MYSQL = "mysql"
    
    # MongoDB container
    MONGO = "mongo"


# ============================================================================
# Upstream MCP Providers
# ============================================================================

class UpstreamProviders:
    """Upstream MCP provider names."""
    
    ATLASSIAN = "atlassian"
    GITHUB = "github"


# ============================================================================
# Environment Names
# ============================================================================

class Environments:
    """Deployment environment names."""
    
    LOCAL = "local"
    DEV = "dev"
    QA = "qa"
    PROD = "prod"


# ============================================================================
# Executor Backend Types
# ============================================================================

class ExecutorBackends:
    """Executor backend type names."""
    
    DOCKER_EXEC = "docker_exec"
    K8S_EXEC = "k8s_exec"
    JOB_RUNNER = "job_runner"
    MOCK = "mock"
