"""
Gateway MCP Output Parser

Parses executor results (CLI output, HTTP responses, DB query results)
into structured Gateway schemas.

This module adapts the Phase 2 BRSToolOutputParser pattern for the Gateway:
- Uses Instructor/LLM for intelligent CLI output parsing when available
- Provides fallback parsing for common patterns
- Translates raw executor output to typed Pydantic models

The Gateway tools layer uses this to convert raw execution results
into the contract-defined output schemas.
"""

from datetime import datetime
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from gateway_mcp.core.executors.base import ExecResult, HTTPResult


T = TypeVar("T", bound=BaseModel)


class OutputParser:
    """
    Parses executor results into Gateway output schemas.
    
    Supports multiple parsing strategies:
    1. JSON parsing (for HTTP responses)
    2. Key-value parsing (for structured CLI output)
    3. LLM-assisted parsing (when Instructor client is available)
    4. Fallback minimal parsing
    
    Usage:
        parser = OutputParser()
        
        # Parse CLI output
        result = ExecResult(exit_code=0, stdout="...", stderr="", duration_ms=100)
        output = parser.parse_exec_result(result, CreateClubOutput, "create_club")
        
        # Parse HTTP response
        http_result = HTTPResult(status_code=200, body={...}, headers={})
        output = parser.parse_http_result(http_result, GetClubConfigOutput)
    """
    
    def __init__(self, instructor_client: Optional[Any] = None):
        """
        Initialize parser.
        
        Args:
            instructor_client: Optional Instructor client for LLM-based parsing.
                               If provided, uses intelligent parsing for ambiguous output.
        """
        self._instructor = instructor_client
    
    async def parse_exec_result(
        self,
        result: ExecResult,
        output_schema: Type[T],
        tool_name: str,
    ) -> T:
        """
        Parse command execution result into output schema.
        
        Attempts parsing strategies in order:
        1. JSON in stdout (if present)
        2. Key-value pairs in stdout
        3. LLM-assisted parsing (if instructor available)
        4. Fallback minimal output
        
        Args:
            result: Execution result with exit_code, stdout, stderr
            output_schema: Pydantic model to parse into
            tool_name: Name of tool (for context in LLM parsing)
            
        Returns:
            Parsed output model instance
            
        Raises:
            ValidationError: If parsing fails completely
        """
        stdout = result.stdout.strip()
        
        # Try JSON parsing first (BRS CLI may output JSON)
        if stdout.startswith("{") or stdout.startswith("["):
            try:
                import json
                data = json.loads(stdout)
                return output_schema.model_validate(data)
            except (json.JSONDecodeError, ValidationError):
                pass
        
        # Try key-value parsing
        parsed = self._parse_key_value(stdout)
        if parsed:
            try:
                # Add success flag based on exit code
                if "success" not in parsed:
                    parsed["success"] = result.success
                return output_schema.model_validate(parsed)
            except ValidationError:
                pass
        
        # Try LLM-assisted parsing if available
        if self._instructor:
            try:
                return await self._llm_parse(
                    stdout=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.exit_code,
                    output_schema=output_schema,
                    tool_name=tool_name,
                )
            except Exception:
                pass
        
        # Fallback to minimal parsing
        return self._fallback_parse(
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            output_schema=output_schema,
        )
    
    def parse_http_result(
        self,
        result: HTTPResult,
        output_schema: Type[T],
    ) -> T:
        """
        Parse HTTP response into output schema.
        
        Args:
            result: HTTP result with status_code, body, headers
            output_schema: Pydantic model to parse into
            
        Returns:
            Parsed output model instance
            
        Raises:
            ValidationError: If body doesn't match schema
        """
        if result.body is None:
            return output_schema.model_validate({})
        
        if isinstance(result.body, dict):
            return output_schema.model_validate(result.body)
        
        if isinstance(result.body, str):
            import json
            data = json.loads(result.body)
            return output_schema.model_validate(data)
        
        return output_schema.model_validate({"data": result.body})
    
    def parse_db_result(
        self,
        rows: list[dict[str, Any]],
        output_schema: Type[T],
        single: bool = True,
    ) -> T:
        """
        Parse database query result into output schema.
        
        Args:
            rows: Query result rows
            output_schema: Pydantic model to parse into
            single: If True, expects single row and returns found=False if empty
            
        Returns:
            Parsed output model instance
        """
        if single:
            if not rows:
                # Return "not found" output with found=False
                return output_schema.model_validate({"found": False})
            return output_schema.model_validate({**rows[0], "found": True})
        
        # Multiple rows - schema should expect a list field
        return output_schema.model_validate({"items": rows, "count": len(rows)})
    
    def _parse_key_value(self, text: str) -> dict[str, Any]:
        """
        Parse key-value pairs from text.
        
        Handles formats like:
            key: value
            key=value
            KEY: value
        
        Returns:
            Dict of parsed key-value pairs
        """
        result: dict[str, Any] = {}
        
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            
            # Try "key: value" format
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip().lower().replace(" ", "_")
                value = value.strip()
                if key and value:
                    result[key] = self._coerce_value(value)
                continue
            
            # Try "key=value" format
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip().lower().replace(" ", "_")
                value = value.strip()
                if key and value:
                    result[key] = self._coerce_value(value)
        
        return result
    
    def _coerce_value(self, value: str) -> Any:
        """Coerce string value to appropriate type."""
        # Boolean
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False
        
        # Integer
        try:
            return int(value)
        except ValueError:
            pass
        
        # Float
        try:
            return float(value)
        except ValueError:
            pass
        
        # Datetime (ISO format)
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass
        
        # String
        return value
    
    async def _llm_parse(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        output_schema: Type[T],
        tool_name: str,
    ) -> T:
        """
        Use LLM to parse CLI output.
        
        Delegates to the Instructor client for intelligent parsing.
        """
        prompt = f"""Parse the output from the '{tool_name}' CLI command.

Return code: {exit_code}

Standard output:
{stdout}

Standard error:
{stderr}

Extract structured information according to the schema. If the command succeeded (returncode 0), set success=True. Extract any relevant IDs, names, or messages from the output."""

        result = await self._instructor.generate_structured(
            prompt=prompt,
            response_model=output_schema,
            temperature=0.0,
            max_retries=2,
        )
        return result
    
    def _fallback_parse(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        output_schema: Type[T],
    ) -> T:
        """
        Fallback parsing when other methods fail.
        
        Creates minimal valid output based on exit code and schema fields.
        """
        data: dict[str, Any] = {}
        
        # Get schema fields
        fields = output_schema.model_fields
        
        # Set success based on exit code
        if "success" in fields:
            data["success"] = exit_code == 0
        
        # Set found based on output content
        if "found" in fields:
            data["found"] = bool(stdout.strip()) and exit_code == 0
        
        # Set stdout/error if schema expects them
        if "stdout" in fields:
            data["stdout"] = stdout
        if "error" in fields:
            data["error"] = stderr if exit_code != 0 else None
        
        # Set empty collections
        for name, field in fields.items():
            annotation = field.annotation
            if annotation is not None:
                origin = getattr(annotation, "__origin__", None)
                if origin is list:
                    data.setdefault(name, [])
                elif origin is dict:
                    data.setdefault(name, {})
        
        try:
            return output_schema.model_validate(data)
        except ValidationError:
            # Last resort: try with model_construct to skip validation
            # This may produce an invalid object but won't raise
            return output_schema.model_construct(**data)


# ============================================================================
# Phase 2 Parser Adapter
# ============================================================================

# Try to import and adapt Phase 2 parser for backward compatibility
try:
    from app.services.brs_tools.parser import BRSToolOutputParser
    
    class Phase2ParserAdapter(OutputParser):
        """
        Adapter that wraps Phase 2 BRSToolOutputParser.
        
        Use this when you want to maintain compatibility with existing
        Phase 2 parsing logic while using Gateway schemas.
        """
        
        def __init__(self, brs_parser: Optional[BRSToolOutputParser] = None):
            super().__init__(instructor_client=None)
            self._brs_parser = brs_parser
        
        async def parse_exec_result(
            self,
            result: ExecResult,
            output_schema: Type[T],
            tool_name: str,
        ) -> T:
            """
            Parse using Phase 2 parser if available, else fallback.
            """
            if self._brs_parser:
                # Adapt ExecResult to ProcessResult protocol expected by Phase 2
                class ProcessResultAdapter:
                    def __init__(self, exec_result: ExecResult):
                        self.returncode = exec_result.exit_code
                        self.stdout_text = exec_result.stdout
                        self.stderr_text = exec_result.stderr
                
                adapted = ProcessResultAdapter(result)
                return await self._brs_parser.parse_output(
                    process=adapted,
                    output_schema=output_schema,
                    tool_name=tool_name,
                )
            
            return await super().parse_exec_result(result, output_schema, tool_name)

except ImportError:
    # Phase 2 parser not available - this is fine, use OutputParser directly
    Phase2ParserAdapter = None


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    "OutputParser",
    "Phase2ParserAdapter",
]
