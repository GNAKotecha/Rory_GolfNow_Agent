"""
Gateway MCP Tools

Business-level tools exposed to the agent:

BRS Tools (6):
- create_club
- get_club_by_name
- get_club_config
- create_admin_user
- call_internal_api
- verify_club_setup

Atlassian Tools (3):
- create_ticket
- get_ticket_status
- add_comment
"""

from typing import Any, Optional

from gateway_mcp.tools.base import (
    EmptyInput,
    EmptyOutput,
    Environment,
    RiskLevel,
    Tool,
    ToolContext,
)


class ToolRegistry:
    """
    Registry of all Gateway MCP tools.
    
    Provides tool lookup for the middleware chain and MCP protocol transport.
    Tools are registered at startup and cannot be modified at runtime.
    
    Usage:
        registry = ToolRegistry()
        registry.register(create_club_tool)
        registry.register(get_club_by_name_tool)
        
        tool = registry.get("create_club")
        all_tools = registry.get_all()
        mcp_schemas = registry.to_mcp_list()
    """
    
    def __init__(self):
        """Initialize empty registry."""
        self._tools: dict[str, Tool] = {}
    
    def register(self, tool: Tool) -> None:
        """
        Register a tool.
        
        Args:
            tool: Tool to register
            
        Raises:
            ValueError: If tool with same name already registered
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool
    
    def register_all(self, tools: list[Tool]) -> None:
        """
        Register multiple tools.
        
        Args:
            tools: List of tools to register
            
        Raises:
            ValueError: If any tool name conflicts with existing registration
        """
        for tool in tools:
            self.register(tool)
    
    def get(self, name: str) -> Optional[Tool]:
        """
        Get a tool by name.
        
        Args:
            name: Tool name (e.g., "create_club")
            
        Returns:
            Tool if found, None otherwise
        """
        return self._tools.get(name)
    
    def get_all(self) -> list[Tool]:
        """
        Get all registered tools.
        
        Returns:
            List of all tools (order not guaranteed)
        """
        return list(self._tools.values())
    
    def list_names(self) -> list[str]:
        """
        Get list of all tool names.
        
        Returns:
            List of tool names (order not guaranteed)
        """
        return list(self._tools.keys())
    
    def get_by_risk_level(self, risk_level: RiskLevel) -> list[Tool]:
        """
        Get all tools with a specific risk level.
        
        Args:
            risk_level: Risk level to filter by
            
        Returns:
            List of matching tools
        """
        return [t for t in self._tools.values() if t.risk_level == risk_level]
    
    def get_for_environment(self, env: Environment) -> list[Tool]:
        """
        Get all tools allowed in a specific environment.
        
        Args:
            env: Environment to filter by
            
        Returns:
            List of tools allowed in that environment
        """
        return [t for t in self._tools.values() if t.is_allowed_in(env)]
    
    def get_external_tools(self) -> list[Tool]:
        """
        Get all tools that require external credentials.
        
        Returns:
            List of tools with required_scopes set
        """
        return [t for t in self._tools.values() if t.is_external()]
    
    def to_mcp_list(self) -> list[dict[str, Any]]:
        """
        Convert all tools to MCP protocol format.
        
        Used by the /tools endpoint.
        
        Returns:
            List of tool schemas in MCP format
        """
        return [tool.to_mcp_schema() for tool in self._tools.values()]
    
    def __len__(self) -> int:
        """Return number of registered tools."""
        return len(self._tools)
    
    def __contains__(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools
    
    def __iter__(self):
        """Iterate over tools."""
        return iter(self._tools.values())


# Exports
__all__ = [
    # Registry
    "ToolRegistry",
    # Base types
    "Tool",
    "ToolContext",
    "RiskLevel",
    "Environment",
    "EmptyInput",
    "EmptyOutput",
]
