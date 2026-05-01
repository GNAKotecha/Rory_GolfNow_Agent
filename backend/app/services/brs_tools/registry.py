from typing import Dict, List, Optional, Type
from dataclasses import dataclass
from pydantic import BaseModel
from app.services.brs_tools.schemas import (
    TeesheetInitOutput,
    SuperuserCreateOutput,
    ConfigValidateOutput
)


@dataclass
class ToolParameter:
    """Definition of a tool parameter."""
    name: str
    type: str  # "string", "integer", "boolean"
    description: str
    required: bool = True
    default: Optional[str] = None


@dataclass
class ToolDefinition:
    """Complete definition of a BRS tool.

    Attributes:
        name: Tool identifier (e.g., "brs_teesheet_init")
        description: Human-readable description
        parameters: List of input parameters
        cli_template: Template string for CLI command (uses {param_name} placeholders)
        output_schema: Pydantic model for parsing output
        timeout_seconds: Maximum execution time
    """
    name: str
    description: str
    parameters: List[ToolParameter]
    cli_template: str
    output_schema: Type[BaseModel]
    timeout_seconds: int = 300


class BRSToolRegistry:
    """Registry of all BRS tools with their definitions.

    Usage:
        registry = BRSToolRegistry()
        tool = registry.get_tool("brs_teesheet_init")

        print(tool.description)
        print(tool.cli_template)
        print(tool.output_schema)
    """

    def __init__(self):
        """Initialize registry with tool definitions."""
        self._tools: Dict[str, ToolDefinition] = {}
        self._register_tools()

    def _register_tools(self):
        """Register all BRS tools."""

        # Tool 1: Teesheet Initialization
        self._tools["brs_teesheet_init"] = ToolDefinition(
            name="brs_teesheet_init",
            description="Initialize a new teesheet database for a golf club",
            parameters=[
                ToolParameter(
                    name="club_name",
                    type="string",
                    description="Name of the golf club (e.g., 'Pebble Beach')",
                    required=True
                ),
                ToolParameter(
                    name="club_id",
                    type="string",
                    description="Unique club identifier (e.g., 'PB001')",
                    required=True
                )
            ],
            cli_template="./bin/teesheet init {club_name} {club_id}",
            output_schema=TeesheetInitOutput,
            timeout_seconds=120
        )

        # Tool 2: Superuser Creation
        self._tools["brs_create_superuser"] = ToolDefinition(
            name="brs_create_superuser",
            description="Create a superuser account for club administration",
            parameters=[
                ToolParameter(
                    name="club_name",
                    type="string",
                    description="Name of the golf club",
                    required=True
                ),
                ToolParameter(
                    name="email",
                    type="string",
                    description="Superuser email address",
                    required=True
                ),
                ToolParameter(
                    name="name",
                    type="string",
                    description="Superuser full name",
                    required=True
                )
            ],
            cli_template="./bin/teesheet update-superusers {club_name} --email {email} --name {name}",
            output_schema=SuperuserCreateOutput,
            timeout_seconds=60
        )

        # Tool 3: Configuration Validation
        self._tools["brs_config_validate"] = ToolDefinition(
            name="brs_config_validate",
            description="Validate club configuration before deployment",
            parameters=[
                ToolParameter(
                    name="club_id",
                    type="string",
                    description="Unique club identifier",
                    required=True
                )
            ],
            cli_template="./bin/config validate {club_id}",
            output_schema=ConfigValidateOutput,
            timeout_seconds=30
        )

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Get tool definition by name.

        Args:
            name: Tool name (e.g., "brs_teesheet_init")

        Returns:
            ToolDefinition if found, None otherwise
        """
        return self._tools.get(name)

    def get_all_tools(self) -> List[ToolDefinition]:
        """Get all registered tools.

        Returns:
            List of all tool definitions
        """
        return list(self._tools.values())

    def list_tool_names(self) -> List[str]:
        """Get list of all tool names.

        Returns:
            List of tool names
        """
        return list(self._tools.keys())
