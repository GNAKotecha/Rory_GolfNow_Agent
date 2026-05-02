from typing import Dict, Any, List
from datetime import datetime, timezone
from app.services.brs_tools.registry import BRSToolRegistry


class MockProcess:
    """Mock subprocess.Process for testing."""

    def __init__(
        self,
        returncode: int,
        stdout_text: str,
        stderr_text: str = ""
    ):
        self.returncode = returncode
        self.stdout_text = stdout_text
        self.stderr_text = stderr_text
        self.stdout_bytes = stdout_text.encode('utf-8')
        self.stderr_bytes = stderr_text.encode('utf-8')


class MockBRSToolExecutor:
    """Mock executor for BRS tools (no real CLI execution).

    Usage:
        registry = BRSToolRegistry()
        mock_executor = MockBRSToolExecutor(registry)

        result = await mock_executor.execute_tool(
            tool_name="brs_teesheet_init",
            parameters={"club_name": "Test Club", "club_id": "TC001"}
        )

        print(result.stdout_text)  # Fake output
        print(mock_executor.call_history)  # Inspect calls
    """

    def __init__(
        self,
        registry: BRSToolRegistry,
        simulate_failure: bool = False,
        failure_rate: float = 0.0
    ):
        """Initialize mock executor.

        Args:
            registry: Tool registry for definitions
            simulate_failure: Always simulate failures if True
            failure_rate: Random failure rate (0.0-1.0)
        """
        self.registry = registry
        self.simulate_failure = simulate_failure
        self.failure_rate = failure_rate
        self.call_history: List[Dict[str, Any]] = []

    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> MockProcess:
        """Execute tool in mock mode (no real CLI).

        Args:
            tool_name: Name of tool to execute
            parameters: Parameter dictionary

        Returns:
            MockProcess with fake output
        """
        # Record call
        self.call_history.append({
            "tool_name": tool_name,
            "parameters": parameters.copy(),
            "timestamp": datetime.now(timezone.utc)
        })

        # Get tool definition
        tool = self.registry.get_tool(tool_name)
        if tool is None:
            return MockProcess(
                returncode=1,
                stdout_text="",
                stderr_text=f"Error: Tool not found: {tool_name}"
            )

        # Simulate failure if configured
        if self.simulate_failure:
            return self._generate_failure_output(tool_name, parameters)

        # Generate success output
        return self._generate_success_output(tool_name, parameters)

    def _generate_success_output(
        self,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> MockProcess:
        """Generate fake success output for tool.

        Args:
            tool_name: Name of tool
            parameters: Parameters passed to tool

        Returns:
            MockProcess with success output
        """
        if tool_name == "brs_teesheet_init":
            club_name = parameters.get("club_name", "Unknown")
            club_id = parameters.get("club_id", "UNK")
            database_name = f"{club_name.lower().replace(' ', '_')}_db"

            stdout = f"""Initializing teesheet for {club_name} ({club_id})
Creating database: {database_name}
Running migrations...
Database initialized successfully
"""
            return MockProcess(returncode=0, stdout_text=stdout)

        elif tool_name == "brs_create_superuser":
            email = parameters.get("email", "admin@example.com")
            name = parameters.get("name", "Admin User")

            stdout = f"""Creating superuser account
Email: {email}
Name: {name}
Superuser created successfully
User ID: 12345
"""
            return MockProcess(returncode=0, stdout_text=stdout)

        elif tool_name == "brs_config_validate":
            club_id = parameters.get("club_id", "UNK")

            stdout = f"""Validating configuration for {club_id}
✓ Database connection valid
✓ Teesheet settings valid
✓ Booking rules valid
Configuration is valid
"""
            return MockProcess(returncode=0, stdout_text=stdout)

        else:
            # Generic success
            stdout = f"Mock execution of {tool_name} completed successfully\n"
            return MockProcess(returncode=0, stdout_text=stdout)

    def _generate_failure_output(
        self,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> MockProcess:
        """Generate fake failure output for tool.

        Args:
            tool_name: Name of tool
            parameters: Parameters passed to tool

        Returns:
            MockProcess with failure output
        """
        stderr = f"Error: Mock failure for {tool_name}\n"
        return MockProcess(returncode=1, stdout_text="", stderr_text=stderr)

    def clear_history(self):
        """Clear call history."""
        self.call_history.clear()

    def get_calls_for_tool(self, tool_name: str) -> List[Dict[str, Any]]:
        """Get all recorded calls for a specific tool.

        Args:
            tool_name: Tool name to filter by

        Returns:
            List of call records
        """
        return [
            call for call in self.call_history
            if call["tool_name"] == tool_name
        ]
