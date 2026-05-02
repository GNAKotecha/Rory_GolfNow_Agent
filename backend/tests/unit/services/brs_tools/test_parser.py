import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.brs_tools.parser import BRSToolOutputParser
from app.services.brs_tools.schemas import TeesheetInitOutput
from app.core.instructor_client import InstructorOllamaClient


@pytest.mark.asyncio
async def test_parse_output_with_instructor():
    """Should parse CLI output into structured schema."""
    # Mock Instructor client
    mock_instructor = AsyncMock(spec=InstructorOllamaClient)
    mock_instructor.generate_structured.return_value = TeesheetInitOutput(
        success=True,
        database_name="test_club_db",
        stdout="Database initialized successfully\nCreated database: test_club_db",
        error=None
    )

    parser = BRSToolOutputParser(mock_instructor)

    # Mock process result
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stdout_text = "Database initialized successfully\nCreated database: test_club_db"
    mock_process.stderr_text = ""

    result = await parser.parse_output(
        process=mock_process,
        output_schema=TeesheetInitOutput,
        tool_name="brs_teesheet_init"
    )

    assert isinstance(result, TeesheetInitOutput)
    assert result.success is True
    assert result.database_name == "test_club_db"


@pytest.mark.asyncio
async def test_parse_output_fallback_on_instructor_failure():
    """Should fallback to best-effort parsing if Instructor fails."""
    # Mock Instructor client that fails
    mock_instructor = AsyncMock(spec=InstructorOllamaClient)
    mock_instructor.generate_structured.side_effect = Exception("LLM error")

    parser = BRSToolOutputParser(mock_instructor)

    # Mock process result
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stdout_text = "Some output"
    mock_process.stderr_text = ""

    result = await parser.parse_output(
        process=mock_process,
        output_schema=TeesheetInitOutput,
        tool_name="brs_teesheet_init"
    )

    # Should return schema with success based on returncode
    assert isinstance(result, TeesheetInitOutput)
    assert result.success is True  # returncode 0
    assert result.stdout == "Some output"


def test_build_parsing_prompt():
    """Should build prompt for Instructor."""
    parser = BRSToolOutputParser(None)

    prompt = parser._build_parsing_prompt(
        stdout="Database created: test_db",
        stderr="",
        returncode=0,
        tool_name="brs_teesheet_init"
    )

    assert "brs_teesheet_init" in prompt
    assert "Database created: test_db" in prompt
    assert "0" in prompt and ("return code" in prompt.lower() or "returncode" in prompt.lower())
