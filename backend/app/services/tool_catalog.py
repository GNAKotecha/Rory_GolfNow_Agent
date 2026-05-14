"""Tool Catalog Abstraction (Task D1)

Provides enhanced tool metadata, risk classification, and filtering capabilities
for workflow-scoped tool exposure. This module introduces a clean abstraction
between raw MCP tool discovery and the agent's tool consumption.

Key abstractions:
- ToolMetadata: Rich tool metadata including risk, scopes, provider
- EnhancedToolCatalog: Filtered view of tools with workflow-aware filtering
- ToolProvider: Classification of tool sources (BRS, Atlassian, Internal, etc.)

The agent consumes filtered catalogs instead of ad-hoc flattened tool lists,
reducing context overload and enabling workflow-specific tool exposure.
"""
import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any, Set
import logging

from app.services.mcp_client import MCPTool

logger = logging.getLogger(__name__)


# ==============================================================================
# Enums for Tool Classification
# ==============================================================================

class ToolRiskLevel(str, Enum):
    """Risk level for tools, determining permission requirements.
    
    Maps to gateway_mcp RiskLevel but lives in backend for decoupling.
    """
    READ = "read"  # Any authenticated caller
    LOW_WRITE = "low_write"  # Operator allowlist
    MEDIUM_WRITE = "medium_write"  # Operator + approval in staging/prod
    HIGH_WRITE = "high_write"  # Admin + explicit approval


class ToolProvider(str, Enum):
    """Classification of tool providers/sources."""
    BRS = "brs"  # BRS business tools (create_club, etc.)
    ATLASSIAN = "atlassian"  # Jira/Confluence tools
    INTERNAL = "internal"  # Internal backend tools
    BUILTIN = "builtin"  # Simple built-in tools (get_current_time, etc.)
    EXTERNAL = "external"  # External third-party integrations


class WorkflowType(str, Enum):
    """Types of workflows with distinct tool requirements."""
    CLUB_SETUP = "club_setup"  # Club onboarding workflow
    TICKET_MANAGEMENT = "ticket_management"  # Jira ticket workflows
    GENERAL = "general"  # General chat/queries
    ADMIN = "admin"  # Administrative operations


# ==============================================================================
# Tool Metadata
# ==============================================================================

@dataclass
class ToolMetadata:
    """Enhanced metadata for a single tool.
    
    Task D1: Provides rich information about a tool beyond just name/schema:
    - Risk level for permission decisions
    - Provider for tool grouping
    - Required scopes for external integrations
    - Health status for availability tracking
    - Workflow tags for exposure filtering
    """
    # Core identity (from MCPTool)
    name: str
    description: str
    input_schema: Dict[str, Any]
    server_name: str
    
    # Risk & permissions
    risk_level: ToolRiskLevel = ToolRiskLevel.READ
    requires_approval: bool = False
    
    # Provider classification
    provider: ToolProvider = ToolProvider.INTERNAL
    
    # External integration (empty for internal tools)
    required_scopes: List[str] = field(default_factory=list)
    
    # Workflow tags - which workflows can use this tool
    workflow_tags: Set[WorkflowType] = field(default_factory=lambda: {WorkflowType.GENERAL})
    
    # Availability
    is_healthy: bool = True
    
    @classmethod
    def from_mcp_tool(
        cls,
        tool: MCPTool,
        metadata_registry: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> "ToolMetadata":
        """Create ToolMetadata from an MCPTool with optional enrichment.
        
        Args:
            tool: Base MCPTool from discovery
            metadata_registry: Optional dict mapping tool names to extra metadata
            
        Returns:
            Enriched ToolMetadata instance
        """
        # Start with defaults from tool
        meta = cls(
            name=tool.name,
            description=tool.description,
            input_schema=tool.input_schema,
            server_name=tool.server_name or "",
        )
        
        # Apply enrichment from registry if available
        if metadata_registry and tool.name in metadata_registry:
            enrichment = metadata_registry[tool.name]
            
            if "risk_level" in enrichment:
                meta.risk_level = ToolRiskLevel(enrichment["risk_level"])
            if "requires_approval" in enrichment:
                meta.requires_approval = enrichment["requires_approval"]
            if "provider" in enrichment:
                meta.provider = ToolProvider(enrichment["provider"])
            if "required_scopes" in enrichment:
                meta.required_scopes = enrichment["required_scopes"]
            if "workflow_tags" in enrichment:
                meta.workflow_tags = {WorkflowType(t) for t in enrichment["workflow_tags"]}
        else:
            # Infer metadata from tool name/server patterns
            meta = cls._infer_metadata(meta)
        
        return meta
    
    @staticmethod
    def _infer_metadata(meta: "ToolMetadata") -> "ToolMetadata":
        """Infer metadata from naming conventions when not explicitly provided."""
        name_lower = meta.name.lower()
        server_lower = meta.server_name.lower()
        
        # Provider inference
        if "brs" in server_lower or "gateway" in server_lower:
            meta.provider = ToolProvider.BRS
        elif "atlassian" in server_lower or "jira" in server_lower:
            meta.provider = ToolProvider.ATLASSIAN
        
        # Risk level inference from naming patterns
        if name_lower.startswith(("get_", "list_", "search_", "verify_")):
            meta.risk_level = ToolRiskLevel.READ
        elif name_lower.startswith(("create_", "update_", "add_")):
            if "admin" in name_lower or "user" in name_lower:
                meta.risk_level = ToolRiskLevel.MEDIUM_WRITE
            else:
                meta.risk_level = ToolRiskLevel.LOW_WRITE
        elif name_lower.startswith(("delete_", "remove_")):
            meta.risk_level = ToolRiskLevel.HIGH_WRITE
            meta.requires_approval = True
        
        # Workflow tags inference
        workflow_tags = {WorkflowType.GENERAL}
        
        if "club" in name_lower:
            workflow_tags.add(WorkflowType.CLUB_SETUP)
        if "ticket" in name_lower or "jira" in name_lower or "comment" in name_lower:
            workflow_tags.add(WorkflowType.TICKET_MANAGEMENT)
        if "admin" in name_lower:
            workflow_tags.add(WorkflowType.ADMIN)
        
        meta.workflow_tags = workflow_tags
        
        return meta
    
    def to_mcp_tool(self) -> MCPTool:
        """Convert back to MCPTool for compatibility."""
        return MCPTool(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
            server_name=self.server_name,
        )
    
    def to_ollama_format(self) -> Dict[str, Any]:
        """Convert to Ollama tool definition format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            }
        }
    
    def is_write_operation(self) -> bool:
        """Check if this tool performs write operations."""
        return self.risk_level != ToolRiskLevel.READ
    
    def is_external(self) -> bool:
        """Check if this tool requires external credentials."""
        return len(self.required_scopes) > 0
    
    def matches_workflow(self, workflow: WorkflowType) -> bool:
        """Check if this tool is tagged for a specific workflow."""
        return workflow in self.workflow_tags or WorkflowType.GENERAL in self.workflow_tags


# ==============================================================================
# Enhanced Tool Catalog
# ==============================================================================

@dataclass
class EnhancedToolCatalog:
    """Enhanced tool catalog with filtering and metadata.
    
    Task D1: Provides a filtered view of available tools with:
    - Rich metadata per tool
    - Filtering by workflow, risk, provider
    - Health-aware availability
    - Context-reducing tool selection
    
    Usage:
        catalog = EnhancedToolCatalog.from_mcp_tools(mcp_tools)
        
        # Filter for club setup workflow
        club_tools = catalog.filter_by_workflow(WorkflowType.CLUB_SETUP)
        
        # Get only read-only tools
        read_tools = catalog.filter_by_risk(ToolRiskLevel.READ)
        
        # Get tools for Ollama
        definitions = catalog.to_ollama_format()
    """
    # All tool metadata
    tools: List[ToolMetadata] = field(default_factory=list)
    
    # Quick lookup indices
    _by_name: Dict[str, ToolMetadata] = field(default_factory=dict)
    _by_provider: Dict[ToolProvider, List[ToolMetadata]] = field(default_factory=dict)
    _by_workflow: Dict[WorkflowType, List[ToolMetadata]] = field(default_factory=dict)
    
    # Catalog metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source_catalog_id: Optional[str] = None
    filter_description: Optional[str] = None
    
    def __post_init__(self):
        """Build indices after initialization."""
        self._rebuild_indices()
    
    def _rebuild_indices(self):
        """Rebuild lookup indices from tools list."""
        self._by_name = {}
        self._by_provider = {}
        self._by_workflow = {}
        
        for tool in self.tools:
            # Name index
            self._by_name[tool.name] = tool
            
            # Provider index
            if tool.provider not in self._by_provider:
                self._by_provider[tool.provider] = []
            self._by_provider[tool.provider].append(tool)
            
            # Workflow index
            for workflow in tool.workflow_tags:
                if workflow not in self._by_workflow:
                    self._by_workflow[workflow] = []
                self._by_workflow[workflow].append(tool)
    
    @classmethod
    def from_mcp_tools(
        cls,
        mcp_tools: List[MCPTool],
        metadata_registry: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> "EnhancedToolCatalog":
        """Create catalog from MCP tools with optional metadata enrichment.
        
        Args:
            mcp_tools: List of MCPTool from discovery
            metadata_registry: Optional dict mapping tool names to extra metadata
            
        Returns:
            EnhancedToolCatalog with enriched metadata
        """
        tools = [
            ToolMetadata.from_mcp_tool(tool, metadata_registry)
            for tool in mcp_tools
        ]
        return cls(tools=tools)
    
    def get_tool(self, name: str) -> Optional[ToolMetadata]:
        """Get tool by name."""
        return self._by_name.get(name)
    
    def has_tool(self, name: str) -> bool:
        """Check if tool exists in catalog."""
        return name in self._by_name
    
    @property
    def tool_count(self) -> int:
        """Get total number of tools."""
        return len(self.tools)
    
    @property
    def tool_names(self) -> List[str]:
        """Get list of all tool names."""
        return list(self._by_name.keys())
    
    # ==========================================================================
    # Filtering Methods
    # ==========================================================================
    
    def filter_by_workflow(
        self,
        workflow: WorkflowType,
        include_general: bool = True,
    ) -> "EnhancedToolCatalog":
        """Get tools tagged for a specific workflow.
        
        Args:
            workflow: Workflow type to filter for
            include_general: Include tools tagged with GENERAL (default True)
            
        Returns:
            New catalog containing only matching tools
        """
        filtered = []
        seen = set()
        
        # Add workflow-specific tools
        for tool in self._by_workflow.get(workflow, []):
            if tool.name not in seen:
                filtered.append(tool)
                seen.add(tool.name)
        
        # Optionally add general tools
        if include_general and workflow != WorkflowType.GENERAL:
            for tool in self._by_workflow.get(WorkflowType.GENERAL, []):
                if tool.name not in seen:
                    filtered.append(tool)
                    seen.add(tool.name)
        
        result = EnhancedToolCatalog(tools=filtered)
        result.source_catalog_id = str(id(self))
        result.filter_description = f"workflow={workflow.value}"
        return result
    
    def filter_by_risk(
        self,
        max_risk: ToolRiskLevel,
    ) -> "EnhancedToolCatalog":
        """Get tools up to a maximum risk level.
        
        Args:
            max_risk: Maximum risk level to include
            
        Returns:
            New catalog with only tools at or below risk level
        """
        risk_order = [
            ToolRiskLevel.READ,
            ToolRiskLevel.LOW_WRITE,
            ToolRiskLevel.MEDIUM_WRITE,
            ToolRiskLevel.HIGH_WRITE,
        ]
        max_idx = risk_order.index(max_risk)
        
        filtered = [
            tool for tool in self.tools
            if risk_order.index(tool.risk_level) <= max_idx
        ]
        
        result = EnhancedToolCatalog(tools=filtered)
        result.source_catalog_id = str(id(self))
        result.filter_description = f"max_risk={max_risk.value}"
        return result
    
    def filter_by_provider(
        self,
        providers: List[ToolProvider],
    ) -> "EnhancedToolCatalog":
        """Get tools from specific providers.
        
        Args:
            providers: List of providers to include
            
        Returns:
            New catalog with only tools from specified providers
        """
        filtered = []
        seen = set()
        
        for provider in providers:
            for tool in self._by_provider.get(provider, []):
                if tool.name not in seen:
                    filtered.append(tool)
                    seen.add(tool.name)
        
        result = EnhancedToolCatalog(tools=filtered)
        result.source_catalog_id = str(id(self))
        result.filter_description = f"providers={[p.value for p in providers]}"
        return result
    
    def filter_healthy(self) -> "EnhancedToolCatalog":
        """Get only healthy (available) tools.
        
        Returns:
            New catalog with only healthy tools
        """
        filtered = [tool for tool in self.tools if tool.is_healthy]
        
        result = EnhancedToolCatalog(tools=filtered)
        result.source_catalog_id = str(id(self))
        result.filter_description = "healthy_only"
        return result
    
    def filter_read_only(self) -> "EnhancedToolCatalog":
        """Get only read-only tools (no write operations).
        
        Returns:
            New catalog with only read tools
        """
        return self.filter_by_risk(ToolRiskLevel.READ)
    
    def exclude_tools(self, tool_names: List[str]) -> "EnhancedToolCatalog":
        """Exclude specific tools by name.
        
        Args:
            tool_names: Tool names to exclude
            
        Returns:
            New catalog without excluded tools
        """
        excluded = set(tool_names)
        filtered = [tool for tool in self.tools if tool.name not in excluded]
        
        result = EnhancedToolCatalog(tools=filtered)
        result.source_catalog_id = str(id(self))
        result.filter_description = f"excluded={tool_names}"
        return result
    
    def include_only(self, tool_names: List[str]) -> "EnhancedToolCatalog":
        """Include only specific tools by name.
        
        Args:
            tool_names: Tool names to include
            
        Returns:
            New catalog with only specified tools
        """
        included = set(tool_names)
        filtered = [tool for tool in self.tools if tool.name in included]
        
        result = EnhancedToolCatalog(tools=filtered)
        result.source_catalog_id = str(id(self))
        result.filter_description = f"include_only={tool_names}"
        return result
    
    # ==========================================================================
    # Conversion Methods
    # ==========================================================================
    
    def to_ollama_format(self) -> List[Dict[str, Any]]:
        """Convert all tools to Ollama/OpenAI format.
        
        Returns:
            List of tool definitions for LLM consumption
        """
        return [tool.to_ollama_format() for tool in self.tools]
    
    def to_mcp_tools(self) -> List[MCPTool]:
        """Convert back to MCPTool list for compatibility.
        
        Returns:
            List of MCPTool objects
        """
        return [tool.to_mcp_tool() for tool in self.tools]
    
    def to_summary_dict(self) -> Dict[str, Any]:
        """Get catalog summary for logging/metrics."""
        provider_counts = {
            provider.value: len(tools)
            for provider, tools in self._by_provider.items()
        }
        risk_counts = {}
        for tool in self.tools:
            risk_counts[tool.risk_level.value] = risk_counts.get(tool.risk_level.value, 0) + 1
        
        return {
            "total_tools": len(self.tools),
            "by_provider": provider_counts,
            "by_risk": risk_counts,
            "filter_description": self.filter_description,
            "created_at": self.created_at.isoformat(),
        }


# ==============================================================================
# Tool Metadata Registry (Default Enrichment)
# ==============================================================================

# Default metadata registry for known tools
# This provides explicit metadata when tool names match
DEFAULT_TOOL_METADATA_REGISTRY: Dict[str, Dict[str, Any]] = {
    # BRS Tools
    "create_club": {
        "risk_level": "low_write",
        "provider": "brs",
        "workflow_tags": ["club_setup", "general"],
        "requires_approval": False,
    },
    "get_club_by_name": {
        "risk_level": "read",
        "provider": "brs",
        "workflow_tags": ["club_setup", "general"],
    },
    "get_club_config": {
        "risk_level": "read",
        "provider": "brs",
        "workflow_tags": ["club_setup", "general"],
    },
    "create_admin_user": {
        "risk_level": "medium_write",
        "provider": "brs",
        "workflow_tags": ["club_setup", "admin"],
        "requires_approval": True,
    },
    "call_internal_api": {
        "risk_level": "medium_write",
        "provider": "brs",
        "workflow_tags": ["admin"],
    },
    "verify_club_setup": {
        "risk_level": "read",
        "provider": "brs",
        "workflow_tags": ["club_setup", "general"],
    },
    # Atlassian Tools
    "create_ticket": {
        "risk_level": "low_write",
        "provider": "atlassian",
        "workflow_tags": ["ticket_management", "general"],
        "required_scopes": ["jira:write"],
    },
    "get_ticket_status": {
        "risk_level": "read",
        "provider": "atlassian",
        "workflow_tags": ["ticket_management", "general"],
        "required_scopes": ["jira:read"],
    },
    "add_comment": {
        "risk_level": "low_write",
        "provider": "atlassian",
        "workflow_tags": ["ticket_management"],
        "required_scopes": ["jira:write"],
    },
    # Built-in Tools
    "get_current_time": {
        "risk_level": "read",
        "provider": "builtin",
        "workflow_tags": ["general"],
    },
}


def get_default_metadata_registry() -> Dict[str, Dict[str, Any]]:
    """Get the default tool metadata registry.
    
    Returns a deep copy to prevent mutation of the default.
    """
    return copy.deepcopy(DEFAULT_TOOL_METADATA_REGISTRY)


# ==============================================================================
# Task D2: Workflow-Scoped Tool Exposure Policy
# ==============================================================================

@dataclass
class ToolExposurePolicyConfig:
    """Configuration for tool exposure policy.
    
    Defines which tools and risk levels are allowed per workflow type.
    """
    # Maximum risk level allowed for this workflow
    max_risk_level: ToolRiskLevel = ToolRiskLevel.LOW_WRITE
    
    # Allowed providers (empty = all providers)
    allowed_providers: List[ToolProvider] = field(default_factory=list)
    
    # Explicit tool allowlist (empty = use workflow tags)
    allowed_tools: List[str] = field(default_factory=list)
    
    # Explicit tool blocklist (always excluded)
    blocked_tools: List[str] = field(default_factory=list)
    
    # Whether to include GENERAL-tagged tools
    include_general_tools: bool = True
    
    # Whether to include built-in tools (get_current_time, etc.)
    include_builtin_tools: bool = True


# Default policy configurations per workflow
DEFAULT_WORKFLOW_POLICIES: Dict[WorkflowType, ToolExposurePolicyConfig] = {
    WorkflowType.GENERAL: ToolExposurePolicyConfig(
        max_risk_level=ToolRiskLevel.LOW_WRITE,
        include_general_tools=True,
        include_builtin_tools=True,
    ),
    WorkflowType.CLUB_SETUP: ToolExposurePolicyConfig(
        max_risk_level=ToolRiskLevel.MEDIUM_WRITE,
        allowed_providers=[ToolProvider.BRS, ToolProvider.BUILTIN],
        include_general_tools=True,
        include_builtin_tools=True,
    ),
    WorkflowType.TICKET_MANAGEMENT: ToolExposurePolicyConfig(
        max_risk_level=ToolRiskLevel.LOW_WRITE,
        allowed_providers=[ToolProvider.ATLASSIAN, ToolProvider.BUILTIN],
        include_general_tools=True,
        include_builtin_tools=True,
    ),
    WorkflowType.ADMIN: ToolExposurePolicyConfig(
        max_risk_level=ToolRiskLevel.HIGH_WRITE,
        include_general_tools=True,
        include_builtin_tools=True,
    ),
}


class ToolExposurePolicy:
    """Workflow-scoped tool exposure policy (Task D2).
    
    Determines which tools are exposed to the model based on:
    - Workflow type (club_setup, ticket_management, etc.)
    - Risk level restrictions
    - Provider allowlists
    - Explicit tool allowlists/blocklists
    
    Usage:
        policy = ToolExposurePolicy(WorkflowType.CLUB_SETUP)
        filtered_catalog = policy.apply(full_catalog)
        
        # Or with custom config
        policy = ToolExposurePolicy(
            workflow=WorkflowType.CLUB_SETUP,
            config_overrides={"max_risk_level": "read"},
        )
    """
    
    def __init__(
        self,
        workflow: WorkflowType,
        config_overrides: Optional[Dict[str, Any]] = None,
        custom_config: Optional[ToolExposurePolicyConfig] = None,
    ):
        """Initialize policy for a workflow.
        
        Args:
            workflow: Workflow type to apply
            config_overrides: Dict of config fields to override
            custom_config: Completely custom config (ignores defaults)
        """
        self.workflow = workflow
        
        if custom_config:
            self.config = custom_config
        else:
            # Start with default for workflow
            default = DEFAULT_WORKFLOW_POLICIES.get(
                workflow,
                DEFAULT_WORKFLOW_POLICIES[WorkflowType.GENERAL]
            )
            
            # Apply overrides if provided
            if config_overrides:
                self.config = self._apply_overrides(default, config_overrides)
            else:
                self.config = default
    
    @staticmethod
    def _apply_overrides(
        base: ToolExposurePolicyConfig,
        overrides: Dict[str, Any],
    ) -> ToolExposurePolicyConfig:
        """Apply override dict to a base config."""
        # Create a copy with overrides
        config_dict = {
            "max_risk_level": base.max_risk_level,
            "allowed_providers": list(base.allowed_providers),
            "allowed_tools": list(base.allowed_tools),
            "blocked_tools": list(base.blocked_tools),
            "include_general_tools": base.include_general_tools,
            "include_builtin_tools": base.include_builtin_tools,
        }
        
        for key, value in overrides.items():
            if key == "max_risk_level" and isinstance(value, str):
                config_dict[key] = ToolRiskLevel(value)
            elif key == "allowed_providers":
                config_dict[key] = [
                    ToolProvider(p) if isinstance(p, str) else p
                    for p in value
                ]
            elif key in config_dict:
                config_dict[key] = value
        
        return ToolExposurePolicyConfig(**config_dict)
    
    def apply(self, catalog: EnhancedToolCatalog) -> EnhancedToolCatalog:
        """Apply this policy to a catalog, returning a filtered catalog.
        
        Args:
            catalog: Full catalog to filter
            
        Returns:
            Filtered catalog with only allowed tools
        """
        result = catalog
        
        # 1. Filter by workflow tags
        result = result.filter_by_workflow(
            self.workflow,
            include_general=self.config.include_general_tools,
        )
        
        # 2. Filter by risk level
        result = result.filter_by_risk(self.config.max_risk_level)
        
        # 3. Filter by provider if specified
        if self.config.allowed_providers:
            result = result.filter_by_provider(self.config.allowed_providers)
        
        # 4. Apply explicit allowlist if specified
        if self.config.allowed_tools:
            # Keep only tools that are both in current result AND allowlist
            allowed = set(self.config.allowed_tools)
            current_names = set(result.tool_names)
            keep = allowed & current_names
            # Always enforce allowlist - even if intersection is empty
            result = result.include_only(list(keep))
        
        # 5. Apply blocklist
        if self.config.blocked_tools:
            result = result.exclude_tools(self.config.blocked_tools)
        
        # 6. Optionally add builtin tools back (respecting blocklist and allowlist)
        if self.config.include_builtin_tools:
            builtin_tools = catalog.filter_by_provider([ToolProvider.BUILTIN])
            # Merge builtin tools that aren't already included AND pass policy constraints
            existing_names = set(result.tool_names)
            blocked = set(self.config.blocked_tools) if self.config.blocked_tools else set()
            allowed = set(self.config.allowed_tools) if self.config.allowed_tools else None
            
            for tool in builtin_tools.tools:
                # Skip if already present
                if tool.name in existing_names:
                    continue
                # Skip if explicitly blocked
                if tool.name in blocked:
                    continue
                # Skip if allowlist exists and tool not in it
                if allowed is not None and tool.name not in allowed:
                    continue
                result.tools.append(tool)
            result._rebuild_indices()
        
        # Update filter description
        result.filter_description = f"policy(workflow={self.workflow.value})"
        
        logger.info(
            f"Applied exposure policy: {catalog.tool_count} -> {result.tool_count} tools",
            extra={
                "workflow": self.workflow.value,
                "original_count": catalog.tool_count,
                "filtered_count": result.tool_count,
                "max_risk": self.config.max_risk_level.value,
            }
        )
        
        return result
    
    def is_tool_allowed(self, tool: ToolMetadata) -> bool:
        """Check if a specific tool would be allowed by this policy.
        
        Args:
            tool: Tool metadata to check
            
        Returns:
            True if tool would be allowed
        """
        # Check blocklist first
        if tool.name in self.config.blocked_tools:
            return False
        
        # Check explicit allowlist if specified
        if self.config.allowed_tools and tool.name not in self.config.allowed_tools:
            return False
        
        # Check workflow match
        if not tool.matches_workflow(self.workflow):
            if not (self.config.include_general_tools and 
                    WorkflowType.GENERAL in tool.workflow_tags):
                return False
        
        # Check risk level
        risk_order = [
            ToolRiskLevel.READ,
            ToolRiskLevel.LOW_WRITE,
            ToolRiskLevel.MEDIUM_WRITE,
            ToolRiskLevel.HIGH_WRITE,
        ]
        if risk_order.index(tool.risk_level) > risk_order.index(self.config.max_risk_level):
            return False
        
        # Check provider
        if self.config.allowed_providers:
            if tool.provider not in self.config.allowed_providers:
                # Exception for builtin tools
                if not (self.config.include_builtin_tools and 
                        tool.provider == ToolProvider.BUILTIN):
                    return False
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize policy for logging/debugging."""
        return {
            "workflow": self.workflow.value,
            "max_risk_level": self.config.max_risk_level.value,
            "allowed_providers": [p.value for p in self.config.allowed_providers],
            "allowed_tools": self.config.allowed_tools,
            "blocked_tools": self.config.blocked_tools,
            "include_general_tools": self.config.include_general_tools,
            "include_builtin_tools": self.config.include_builtin_tools,
        }


def get_policy_for_workflow(
    workflow: WorkflowType,
    overrides: Optional[Dict[str, Any]] = None,
) -> ToolExposurePolicy:
    """Get the exposure policy for a workflow type.
    
    Convenience function for creating policies with optional overrides.
    
    Args:
        workflow: Workflow type
        overrides: Optional config overrides
        
    Returns:
        Configured ToolExposurePolicy
    """
    return ToolExposurePolicy(workflow, config_overrides=overrides)
