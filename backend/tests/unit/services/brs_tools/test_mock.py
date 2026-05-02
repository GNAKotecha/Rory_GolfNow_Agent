import pytest
from app.services.brs_tools.mock import MockBRSToolExecutor
from app.services.brs_tools.registry import BRSToolRegistry
from app.services.brs_tools.schemas import TeesheetInitOutput


@pytest.mark.asyncio
async def test_mock_executor_returns_fake_process():
    """Should return fake process with mocked output."""
    registry = BRSToolRegistry()
    mock_executor = MockBRSToolExecutor(registry)

    result = await mock_executor.execute_tool(
        tool_name="brs_teesheet_init",
        parameters={"club_name": "Test Club", "club_id": "TC001"}
    )

    assert result.returncode == 0
    assert result.stdout_text
    assert "Test Club" in result.stdout_text or "TC001" in result.stdout_text


@pytest.mark.asyncio
async def test_mock_executor_records_call():
    """Should record tool calls for inspection."""
    registry = BRSToolRegistry()
    mock_executor = MockBRSToolExecutor(registry)

    await mock_executor.execute_tool(
        tool_name="brs_teesheet_init",
        parameters={"club_name": "Test Club", "club_id": "TC001"}
    )

    assert len(mock_executor.call_history) == 1
    call = mock_executor.call_history[0]
    assert call["tool_name"] == "brs_teesheet_init"
    assert call["parameters"]["club_name"] == "Test Club"


@pytest.mark.asyncio
async def test_mock_executor_can_simulate_failure():
    """Should simulate failure when configured."""
    registry = BRSToolRegistry()
    mock_executor = MockBRSToolExecutor(registry, simulate_failure=True)

    result = await mock_executor.execute_tool(
        tool_name="brs_teesheet_init",
        parameters={"club_name": "Test Club", "club_id": "TC001"}
    )

    assert result.returncode != 0
    assert result.stderr_text
