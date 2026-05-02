import pytest
from app.services.brs_tools.executor import BRSToolExecutor, CommandBuildError
from app.services.brs_tools.registry import BRSToolRegistry


def test_build_command_from_template():
    """Should build CLI command from template and parameters."""
    registry = BRSToolRegistry()
    executor = BRSToolExecutor(registry, brs_teesheet_path="/fake/path")

    tool = registry.get_tool("brs_teesheet_init")
    params = {"club_name": "Test Club", "club_id": "TC001"}

    command = executor._build_command(tool, params)

    assert command == ["./bin/teesheet", "init", "Test Club", "TC001"]


def test_build_command_with_unreplaced_placeholders_raises_error():
    """Should raise error if command has unreplaced placeholders."""
    registry = BRSToolRegistry()
    executor = BRSToolExecutor(registry, brs_teesheet_path="/fake/path")

    tool = registry.get_tool("brs_teesheet_init")
    params = {"club_name": "Test Club"}  # Missing club_id

    with pytest.raises(CommandBuildError) as exc_info:
        executor._build_command(tool, params)

    assert "unreplaced placeholders" in str(exc_info.value).lower()


def test_validate_parameters_success():
    """Should validate parameters successfully."""
    registry = BRSToolRegistry()
    executor = BRSToolExecutor(registry, brs_teesheet_path="/fake/path")

    tool = registry.get_tool("brs_teesheet_init")
    params = {"club_name": "Test Club", "club_id": "TC001"}

    # Should not raise
    executor._validate_parameters(tool, params)


def test_validate_parameters_missing_required():
    """Should raise error for missing required parameters."""
    registry = BRSToolRegistry()
    executor = BRSToolExecutor(registry, brs_teesheet_path="/fake/path")

    tool = registry.get_tool("brs_teesheet_init")
    params = {}

    with pytest.raises(CommandBuildError):
        executor._validate_parameters(tool, params)


@pytest.mark.asyncio
async def test_execute_tool_integration_skipped():
    """Integration test for actual subprocess execution (skipped in unit tests)."""
    pytest.skip("Integration test - requires actual BRS CLI")
