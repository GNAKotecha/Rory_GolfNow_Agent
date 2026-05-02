import os
import asyncio
import shlex
from typing import Dict, Any, List
from dataclasses import dataclass
from app.services.brs_tools.registry import BRSToolRegistry, ToolDefinition


class CommandBuildError(Exception):
    """Raised when command cannot be built from template."""
    pass


class ExecutionError(Exception):
    """Raised when tool execution fails."""
    pass


@dataclass
class ToolExecutionResult:
    """Result of a tool execution.

    Attributes:
        returncode: Process exit code
        stdout_bytes: Raw stdout bytes
        stderr_bytes: Raw stderr bytes
        stdout_text: Decoded stdout text
        stderr_text: Decoded stderr text
    """
    returncode: int
    stdout_bytes: bytes
    stderr_bytes: bytes
    stdout_text: str
    stderr_text: str


class BRSToolExecutor:
    """Executes BRS tools via subprocess with timeout and error handling.

    Usage:
        registry = BRSToolRegistry()
        executor = BRSToolExecutor(registry, brs_teesheet_path="/path/to/brs-teesheet")

        result = await executor.execute_tool(
            tool_name="brs_teesheet_init",
            parameters={"club_name": "Test Club", "club_id": "TC001"}
        )

        print(result.returncode)
        print(result.stdout)
    """

    def __init__(
        self,
        registry: BRSToolRegistry,
        brs_teesheet_path: str,
        brs_config_path: str = "",
        timeout_multiplier: float = 1.0
    ):
        """Initialize executor with registry and paths.

        Args:
            registry: Tool registry for definitions
            brs_teesheet_path: Path to brs-teesheet repository
            brs_config_path: Path to brs-config-api repository
            timeout_multiplier: Multiplier for tool timeouts (for slower systems)
        """
        self.registry = registry
        self.brs_teesheet_path = brs_teesheet_path
        self.brs_config_path = brs_config_path
        self.timeout_multiplier = timeout_multiplier

    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> ToolExecutionResult:
        """Execute a BRS tool with given parameters.

        Args:
            tool_name: Name of tool to execute
            parameters: Parameter dictionary matching tool definition

        Returns:
            ToolExecutionResult with process output

        Raises:
            CommandBuildError: If command cannot be built
            ExecutionError: If execution fails or times out
        """
        # Get tool definition
        tool = self.registry.get_tool(tool_name)
        if tool is None:
            raise CommandBuildError(f"Tool not found: {tool_name}")

        # Validate parameters
        self._validate_parameters(tool, parameters)

        # Build command
        command = self._build_command(tool, parameters)

        # Determine working directory
        cwd = self._get_working_directory(tool)

        # Calculate timeout
        timeout = tool.timeout_seconds * self.timeout_multiplier

        # Execute with timeout
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )

            return ToolExecutionResult(
                returncode=process.returncode,
                stdout_bytes=stdout,
                stderr_bytes=stderr,
                stdout_text=stdout.decode('utf-8', errors='replace'),
                stderr_text=stderr.decode('utf-8', errors='replace')
            )

        except asyncio.TimeoutError:
            # Kill the subprocess to prevent resource leaks
            try:
                process.kill()
                await process.wait()
            except ProcessLookupError:
                pass  # Process already terminated
            raise ExecutionError(
                f"Tool execution timed out after {timeout}s: {tool_name}"
            )
        except Exception as e:
            raise ExecutionError(f"Tool execution failed: {tool_name}: {e}")

    def _validate_parameters(
        self,
        tool: ToolDefinition,
        parameters: Dict[str, Any]
    ):
        """Validate parameters against tool definition.

        Args:
            tool: Tool definition
            parameters: Parameter dictionary

        Raises:
            CommandBuildError: If validation fails
        """
        # Check required parameters
        for param in tool.parameters:
            if param.required and param.name not in parameters:
                raise CommandBuildError(
                    f"Missing required parameter '{param.name}' for tool '{tool.name}'"
                )

    def _build_command(
        self,
        tool: ToolDefinition,
        parameters: Dict[str, Any]
    ) -> List[str]:
        """Build CLI command from template and parameters.

        Args:
            tool: Tool definition with CLI template
            parameters: Parameter dictionary

        Returns:
            Command as list of strings for subprocess

        Raises:
            CommandBuildError: If command cannot be built
        """
        try:
            # Replace placeholders in template with quoted values
            command_str = tool.cli_template
            for param_name, param_value in parameters.items():
                placeholder = f"{{{param_name}}}"
                # Quote the value to preserve spaces
                quoted_value = shlex.quote(str(param_value))
                command_str = command_str.replace(placeholder, quoted_value)

            # Check for unreplaced placeholders
            if "{" in command_str and "}" in command_str:
                raise CommandBuildError(
                    f"Unreplaced placeholders in command: {command_str}"
                )

            # Split into list for subprocess (shlex handles quoted strings)
            command_parts = shlex.split(command_str)
            return command_parts

        except Exception as e:
            raise CommandBuildError(f"Failed to build command: {e}")

    def _get_working_directory(self, tool: ToolDefinition) -> str:
        """Get working directory for tool execution.

        Args:
            tool: Tool definition

        Returns:
            Absolute path to working directory

        Raises:
            CommandBuildError: If working directory cannot be determined
        """
        # Determine repo based on tool name
        if "teesheet" in tool.name.lower():
            if not self.brs_teesheet_path:
                raise CommandBuildError(
                    f"Tool '{tool.name}' requires brs_teesheet_path but it is not configured"
                )
            return self.brs_teesheet_path
        elif "config" in tool.name.lower():
            if not self.brs_config_path:
                raise CommandBuildError(
                    f"Tool '{tool.name}' requires brs_config_path but it is not configured"
                )
            return self.brs_config_path
        else:
            raise CommandBuildError(
                f"Cannot determine working directory for tool '{tool.name}' - "
                f"tool name must contain 'teesheet' or 'config'"
            )
