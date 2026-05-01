import pytest
from app.services.brs_tools.registry import BRSToolRegistry, ToolDefinition
from app.services.brs_tools.schemas import TeesheetInitOutput

def test_registry_get_all_tools():
    """Should return all registered tools."""
    registry = BRSToolRegistry()
    tools = registry.get_all_tools()

    assert len(tools) > 0
    assert all(isinstance(tool, ToolDefinition) for tool in tools)

def test_registry_get_tool_by_name():
    """Should retrieve tool by name."""
    registry = BRSToolRegistry()
    tool = registry.get_tool("brs_teesheet_init")

    assert tool is not None
    assert tool.name == "brs_teesheet_init"
    assert tool.description
    assert len(tool.parameters) > 0
    assert tool.cli_template
    assert tool.output_schema == TeesheetInitOutput

def test_registry_get_nonexistent_tool_returns_none():
    """Should return None for unknown tool."""
    registry = BRSToolRegistry()
    tool = registry.get_tool("nonexistent_tool")

    assert tool is None

def test_tool_definition_cli_template_has_placeholders():
    """CLI template should use {param_name} placeholders."""
    registry = BRSToolRegistry()
    tool = registry.get_tool("brs_teesheet_init")

    assert "{club_name}" in tool.cli_template
    assert "{club_id}" in tool.cli_template