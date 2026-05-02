import pytest
from app.services.brs_tools.registry import BRSToolRegistry
from app.services.brs_tools.mock import MockBRSToolExecutor
from app.services.brs_tools.parser import BRSToolOutputParser
from app.services.brs_tools.schemas import TeesheetInitOutput, SuperuserCreateOutput


@pytest.fixture
def brs_setup():
    """Fixture providing registry, executor, and parser."""
    registry = BRSToolRegistry()
    executor = MockBRSToolExecutor(registry)
    parser = BRSToolOutputParser(instructor_client=None)  # Fallback mode
    return registry, executor, parser


@pytest.mark.asyncio
async def test_brs_tool_gateway_e2e_teesheet_init(brs_setup):
    """Test complete flow: registry → mock executor → parser."""
    # Setup
    registry, executor, parser = brs_setup

    # Get tool
    tool = registry.get_tool("brs_teesheet_init")
    assert tool is not None

    # Execute
    parameters = {"club_name": "Pebble Beach", "club_id": "PB001"}
    process = await executor.execute_tool("brs_teesheet_init", parameters)

    # Parse
    result = await parser.parse_output(
        process=process,
        output_schema=TeesheetInitOutput,
        tool_name="brs_teesheet_init"
    )

    # Verify
    assert isinstance(result, TeesheetInitOutput)
    assert result.success is True
    # Fallback parser extracts database_name from stdout
    assert "pebble_beach_db" in result.stdout.lower()
    assert "Pebble Beach" in result.stdout or "PB001" in result.stdout

    # Verify call was recorded
    assert len(executor.call_history) == 1
    assert executor.call_history[0]["tool_name"] == "brs_teesheet_init"


@pytest.mark.asyncio
async def test_brs_tool_gateway_e2e_superuser_create(brs_setup):
    """Test complete flow for superuser creation."""
    # Setup
    registry, executor, parser = brs_setup

    # Execute
    parameters = {
        "club_name": "Pebble Beach",
        "email": "admin@pebblebeach.com",
        "name": "John Admin"
    }
    process = await executor.execute_tool("brs_create_superuser", parameters)

    # Parse
    result = await parser.parse_output(
        process=process,
        output_schema=SuperuserCreateOutput,
        tool_name="brs_create_superuser"
    )

    # Verify
    assert isinstance(result, SuperuserCreateOutput)
    assert result.success is True
    # Fallback parser doesn't extract email from stdout (only from params if passed explicitly)
    assert result.email == ""
    assert "admin@pebblebeach.com" in result.stdout
    assert "John Admin" in result.stdout


@pytest.mark.asyncio
async def test_brs_tool_gateway_e2e_failure_handling():
    """Test failure handling through the pipeline."""
    # Setup with failure simulation
    registry = BRSToolRegistry()
    executor = MockBRSToolExecutor(registry, simulate_failure=True)
    parser = BRSToolOutputParser(instructor_client=None)

    # Execute (will fail)
    parameters = {"club_name": "Test Club", "club_id": "TC001"}
    process = await executor.execute_tool("brs_teesheet_init", parameters)

    # Parse
    result = await parser.parse_output(
        process=process,
        output_schema=TeesheetInitOutput,
        tool_name="brs_teesheet_init"
    )

    # Verify failure was captured
    assert isinstance(result, TeesheetInitOutput)
    assert result.success is False
    assert result.error is not None
    assert len(result.error) > 0
    assert "mock failure" in result.error.lower() or "error" in result.error.lower()


@pytest.mark.asyncio
async def test_brs_tool_gateway_e2e_workflow_integration(brs_setup):
    """Test BRS tools in a workflow-like sequence."""
    # Setup
    registry, executor, parser = brs_setup

    # Step 1: Initialize teesheet
    init_result = await parser.parse_output(
        process=await executor.execute_tool(
            "brs_teesheet_init",
            {"club_name": "Test Club", "club_id": "TC001"}
        ),
        output_schema=TeesheetInitOutput,
        tool_name="brs_teesheet_init"
    )
    assert init_result.success is True

    # Step 2: Create superuser
    superuser_result = await parser.parse_output(
        process=await executor.execute_tool(
            "brs_create_superuser",
            {
                "club_name": "Test Club",
                "email": "admin@test.com",
                "name": "Admin User"
            }
        ),
        output_schema=SuperuserCreateOutput,
        tool_name="brs_create_superuser"
    )
    assert superuser_result.success is True

    # Verify call sequence
    assert len(executor.call_history) == 2
    assert executor.call_history[0]["tool_name"] == "brs_teesheet_init"
    assert executor.call_history[1]["tool_name"] == "brs_create_superuser"
