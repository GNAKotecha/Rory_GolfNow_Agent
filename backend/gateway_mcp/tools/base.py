"""
Tool Definition Base

Defines the Tool dataclass with all metadata required by the middleware chain:
- name, description: tool identity
- input_schema, output_schema: Pydantic models for validation
- risk_level: determines permission requirements
- allowed_environments: list of envs where tool can run
- requires_approval: if True, middleware calls ApprovalService
- timeout_seconds: max execution time
- required_scopes: OAuth scopes for external tools
- handler: async function that executes the tool
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Optional, Type, TypeVar

from pydantic import BaseModel


class RiskLevel(str, Enum):
    """
    Risk levels determining permission requirements.
    
    - read: any authenticated caller
    - low_write: operator allowlist
    - medium_write: operator allowlist (approval in future for staging/prod)
    - high_write: operator + explicit approval required
    """
    READ = "read"
    LOW_WRITE = "low_write"
    MEDIUM_WRITE = "medium_write"
    HIGH_WRITE = "high_write"


class Environment(str, Enum):
    """Deployment environments."""
    LOCAL = "local"
    DEV = "dev"
    QA = "qa"
    PROD = "prod"


# Type alias for tool handler function
# Handler receives input model instance, returns output model instance
InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)

ToolHandler = Callable[
    [InputT, "ToolContext"],
    Awaitable[OutputT],
]


@dataclass
class ToolContext:
    """
    Context passed to tool handlers.
    
    Provides access to user identity, executor backend, and credentials
    without exposing raw secrets.
    """
    user_id: int
    correlation_id: str
    audit_id: str
    environment: Environment
    
    # Injected by middleware - tool handlers call these, never access tokens directly
    _executor: Any = None  # ExecutorBackend, set by middleware
    _credential_fetcher: Optional[Callable[[str], Awaitable[str]]] = None
    
    async def get_executor(self) -> Any:
        """Get the executor backend for this request."""
        if self._executor is None:
            raise RuntimeError("Executor not set on context")
        return self._executor
    
    async def get_credential(self, provider: str) -> str:
        """
        Get OAuth token or PAT for the given provider.
        
        Transparently handles refresh for OAuth tokens.
        
        Args:
            provider: Provider name (e.g., "atlassian", "github")
            
        Returns:
            Bearer token string ready for Authorization header
            
        Raises:
            CredentialMissingError: User hasn't connected this provider
            TokenRefreshFailedError: OAuth refresh failed
        """
        if self._credential_fetcher is None:
            raise RuntimeError("Credential fetcher not set on context")
        return await self._credential_fetcher(provider)


@dataclass
class Tool:
    """
    Complete definition of a Gateway tool.
    
    Tools are the atomic unit of work exposed to the agent.
    Each tool declares its metadata for the middleware chain:
    - Validation (input/output schemas)
    - Permissions (risk level, env restrictions)
    - Approval (requires_approval flag)
    - Execution (handler, timeout)
    - External integration (required_scopes)
    
    Example:
        create_club_tool = Tool(
            name="create_club",
            description="Create a new golf club in the BRS system",
            input_schema=CreateClubInput,
            output_schema=CreateClubOutput,
            risk_level=RiskLevel.LOW_WRITE,
            allowed_environments=[Environment.LOCAL, Environment.DEV],
            requires_approval=False,
            timeout_seconds=120,
            handler=create_club_handler,
        )
    """
    
    # Identity
    name: str
    description: str
    
    # Schemas - Pydantic models for input/output validation
    input_schema: Type[BaseModel]
    output_schema: Type[BaseModel]
    
    # Risk & permissions
    risk_level: RiskLevel = RiskLevel.READ
    allowed_environments: list[Environment] = field(
        default_factory=lambda: list(Environment)
    )
    requires_approval: bool = False
    
    # Execution
    timeout_seconds: int = 30
    handler: Optional[ToolHandler] = None
    
    # External integrations (OAuth scopes)
    # Empty for BRS tools, populated for Atlassian/Github tools
    required_scopes: list[str] = field(default_factory=list)
    
    # Audit metadata - extra fields to include in audit records
    # e.g., {"category": "brs", "executor": "docker_exec"}
    audit_metadata: dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate tool definition."""
        if not self.name:
            raise ValueError("Tool name is required")
        if not self.description:
            raise ValueError("Tool description is required")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
    
    def to_mcp_schema(self) -> dict[str, Any]:
        """
        Convert to MCP tool schema format.
        
        Used by the MCP HTTP transport to expose tools to clients.
        
        Returns:
            Dict compatible with MCP tools/list response
        """
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema.model_json_schema(),
        }
    
    def is_allowed_in(self, env: Environment) -> bool:
        """Check if tool is allowed in the given environment."""
        return env in self.allowed_environments
    
    def is_external(self) -> bool:
        """Check if this tool requires external credentials."""
        return len(self.required_scopes) > 0


# Schemas for tools with no input/output (rare but possible)

class EmptyInput(BaseModel):
    """Empty input schema for tools that take no parameters."""
    pass


class EmptyOutput(BaseModel):
    """Empty output schema for tools that return no data."""
    pass
