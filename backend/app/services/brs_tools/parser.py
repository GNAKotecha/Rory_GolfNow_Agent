from typing import Type, TypeVar, Optional, Protocol, runtime_checkable, Union
import asyncio
from pydantic import BaseModel, ValidationError
from app.core.instructor_client import InstructorOllamaClient

T = TypeVar('T', bound=BaseModel)


@runtime_checkable
class ProcessResult(Protocol):
    """Protocol for process-like results with returncode and output text.
    
    Supports asyncio.subprocess.Process, ToolExecutionResult, and MockProcess.
    """
    returncode: int
    stdout_text: str
    stderr_text: str


class BRSToolOutputParser:
    """Parses BRS tool output into structured Pydantic schemas using Instructor.

    Usage:
        instructor = InstructorOllamaClient()
        parser = BRSToolOutputParser(instructor)

        process = await executor.execute_tool("brs_teesheet_init", {...})
        result = await parser.parse_output(
            process=process,
            output_schema=TeesheetInitOutput,
            tool_name="brs_teesheet_init"
        )

        assert isinstance(result, TeesheetInitOutput)
        print(result.database_name)
    """

    def __init__(self, instructor_client: Optional[InstructorOllamaClient] = None):
        """Initialize parser with Instructor client.

        Args:
            instructor_client: Instructor client for LLM-based parsing (optional)
        """
        self.instructor_client = instructor_client

    async def parse_output(
        self,
        process: ProcessResult,
        output_schema: Type[T],
        tool_name: str
    ) -> T:
        """Parse process output into structured schema.

        Args:
            process: Process result with returncode, stdout_text, stderr_text.
                     Accepts ToolExecutionResult, MockProcess, or any object
                     implementing the ProcessResult protocol.
            output_schema: Pydantic model for output structure
            tool_name: Name of tool (for prompt context)

        Returns:
            Instance of output_schema with parsed data

        Raises:
            ValidationError: If parsing fails and fallback also fails
        """
        stdout = getattr(process, 'stdout_text', '')
        stderr = getattr(process, 'stderr_text', '')
        returncode = process.returncode

        # Try Instructor-based parsing if available
        if self.instructor_client:
            try:
                prompt = self._build_parsing_prompt(
                    stdout=stdout,
                    stderr=stderr,
                    returncode=returncode,
                    tool_name=tool_name
                )

                result = await self.instructor_client.generate_structured(
                    prompt=prompt,
                    response_model=output_schema,
                    temperature=0.0,  # Deterministic parsing
                    max_retries=2
                )

                return result

            except Exception as e:
                # Fallback to best-effort parsing
                pass

        # Fallback: create schema with minimal data
        return self._fallback_parse(
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
            output_schema=output_schema
        )

    def _build_parsing_prompt(
        self,
        stdout: str,
        stderr: str,
        returncode: int,
        tool_name: str
    ) -> str:
        """Build prompt for Instructor to parse CLI output.

        Args:
            stdout: Standard output from CLI
            stderr: Standard error from CLI
            returncode: Process exit code
            tool_name: Name of tool

        Returns:
            Prompt for LLM
        """
        return f"""Parse the output from the '{tool_name}' CLI command.

Return code: {returncode}

Standard output:
{stdout}

Standard error:
{stderr}

Extract structured information according to the schema. If the command succeeded (returncode 0), set success=True. Extract any relevant IDs, names, or messages from the output."""

    def _fallback_parse(
        self,
        stdout: str,
        stderr: str,
        returncode: int,
        output_schema: Type[T]
    ) -> T:
        """Best-effort parsing without LLM.

        Args:
            stdout: Standard output
            stderr: Standard error
            returncode: Exit code
            output_schema: Output schema to populate

        Returns:
            Schema instance with minimal data
        """
        # Build minimal data based on returncode
        data = {
            "success": returncode == 0,
            "stdout": stdout,
            "error": stderr if returncode != 0 else None
        }

        # Try to create schema (may fail if required fields missing)
        try:
            return output_schema(**data)
        except ValidationError:
            # Last resort: add empty/default values for required fields
            # This is hacky but ensures we always return something
            schema_fields = output_schema.model_fields
            for field_name, field_info in schema_fields.items():
                if field_name not in data:
                    # Add default based on type
                    if field_info.annotation == str:
                        data[field_name] = ""
                    elif field_info.annotation == int:
                        data[field_name] = 0
                    elif field_info.annotation == bool:
                        data[field_name] = False

            return output_schema(**data)
