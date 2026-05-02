import pytest
from pydantic import BaseModel, Field
from app.core.instructor_client import InstructorOllamaClient

class SampleOutput(BaseModel):
    """Sample structured output for testing."""
    club_name: str = Field(description="Name of the golf club")
    club_id: str = Field(description="Unique club identifier")
    database_name: str = Field(description="Database name")

@pytest.mark.skip(reason="Integration test - requires Ollama running")
@pytest.mark.asyncio
async def test_instructor_client_generates_structured_output():
    """Integration test - requires Ollama running, will be skipped."""
    client = InstructorOllamaClient()

    prompt = "Extract: Club Name: Test Golf Club, ID: TGC123"

    result = await client.generate_structured(
        prompt=prompt,
        response_model=SampleOutput,
        temperature=0.0
    )

    assert isinstance(result, SampleOutput)
    assert result.club_name == "Test Golf Club"
    assert result.club_id == "TGC123"

def test_instructor_client_can_be_instantiated():
    """Smoke test - can create client."""
    client = InstructorOllamaClient()
    assert client is not None
    assert hasattr(client, 'generate_structured')