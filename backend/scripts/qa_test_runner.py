"""QA Test Runner - Execute QA test scenarios with filtering and result collection."""

import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from qa_results_formatter import QAResultsFormatter


# Define all 15 QA scenarios with categorization
ALL_SCENARIOS = [
    # Core scenarios (10)
    {"name": "basic_greeting", "type": "core", "description": "Test basic agent greeting"},
    {"name": "club_setup", "type": "core", "description": "Test club setup workflow"},
    {"name": "member_lookup", "type": "core", "description": "Test member lookup functionality"},
    {"name": "booking_query", "type": "core", "description": "Test booking query"},
    {"name": "context_retention", "type": "core", "description": "Test context memory across turns"},
    {"name": "error_recovery", "type": "core", "description": "Test error handling and recovery"},
    {"name": "approval_flow", "type": "core", "description": "Test approval workflow"},
    {"name": "analytics_query", "type": "core", "description": "Test analytics queries"},
    {"name": "help_documentation", "type": "core", "description": "Test help documentation"},
    {"name": "stress_test_long_conversation", "type": "core", "description": "Test long conversation handling"},
    # Infrastructure scenarios (2)
    {"name": "mcp_health_check", "type": "infrastructure", "description": "Test MCP health check"},
    {"name": "integration_discovery", "type": "infrastructure", "description": "Test integration discovery"},
    # Cross-MCP scenarios (3)
    {"name": "jira_ticket_escalation", "type": "cross_mcp", "description": "Test JIRA ticket escalation"},
    {"name": "jira_status_check", "type": "cross_mcp", "description": "Test JIRA status check"},
    {"name": "cross_system_audit_trail", "type": "cross_mcp", "description": "Test cross-system audit trail"},
]


class QATestRunner:
    """Run QA test scenarios with filtering and result tracking."""

    def __init__(self, scope: str = "critical") -> None:
        """Initialize QA test runner.

        Args:
            scope: Test scope filtering
                - "all": Run all 15 scenarios
                - "critical": Run 10 core scenarios only
                - "custom:name1,name2": Run specific scenarios by name
                Default: "critical"
        """
        self.scope = scope
        self.formatter = QAResultsFormatter(scope)
        self._scenarios = self._filter_scenarios()

    def _filter_scenarios(self) -> List[Dict[str, str]]:
        """Filter scenarios based on scope.

        Returns:
            List of scenarios to run
        """
        if self.scope == "all":
            return ALL_SCENARIOS.copy()
        elif self.scope == "critical":
            return [s for s in ALL_SCENARIOS if s["type"] == "core"]
        elif self.scope.startswith("custom:"):
            names = [n.strip() for n in self.scope[7:].split(",")]
            return [s for s in ALL_SCENARIOS if s["name"] in names]
        else:
            # Default to critical if unknown scope
            return [s for s in ALL_SCENARIOS if s["type"] == "core"]

    def get_scenarios(self) -> List[Dict[str, str]]:
        """Get list of scenarios filtered by scope.

        Returns:
            List of scenario definitions
        """
        return self._scenarios

    async def run_scenario(self, scenario_name: str) -> Dict[str, Any]:
        """Run a single QA scenario.

        Args:
            scenario_name: Name of scenario to run

        Returns:
            Dictionary with scenario results:
                - scenario_name: Name of the scenario
                - status: "passed", "failed", or "skipped"
                - duration_ms: Execution duration in milliseconds
                - tool_calls: Number of tool calls made
                - langfuse_trace_id: Trace ID for observability
                - assertions: Number of assertions
                - error: Error message if failed
                - response_snippet: LLM response snippet
        """
        # Mock implementation - placeholder for actual scenario execution
        # In production, this would execute the actual test scenario
        start_time = time.time()

        # Simulate scenario execution
        await asyncio.sleep(0.1)

        duration_ms = (time.time() - start_time) * 1000

        # Mock result
        result = {
            "scenario_name": scenario_name,
            "status": "passed",
            "duration_ms": duration_ms,
            "tool_calls": 2,
            "langfuse_trace_id": f"trace_{scenario_name}_{int(time.time() * 1000)}",
            "assertions": 5,
            "error": None,
            "response_snippet": f"Mock response for {scenario_name}",
        }

        return result

    async def run_all(self) -> str:
        """Run all filtered scenarios and write results to JSON.

        Returns:
            Path to results JSON file
        """
        scenarios = self.get_scenarios()
        total_scenarios = len(scenarios)

        print(f"Running {total_scenarios} scenarios with scope: {self.scope}")

        # Run all scenarios
        for i, scenario in enumerate(scenarios):
            scenario_name = scenario["name"]
            print(f"  [{i+1}/{total_scenarios}] Running {scenario_name}...", end=" ", flush=True)

            try:
                result = await self.run_scenario(scenario_name)
                self.formatter.add_result(
                    scenario_name=result["scenario_name"],
                    status=result["status"],
                    duration_ms=result["duration_ms"],
                    tool_calls=result["tool_calls"],
                    langfuse_trace_id=result["langfuse_trace_id"],
                    assertions=result["assertions"],
                    error=result["error"],
                    response_snippet=result["response_snippet"],
                )
                print(f"✓ {result['status']}")
            except Exception as e:
                self.formatter.add_result(
                    scenario_name=scenario_name,
                    status="failed",
                    duration_ms=0,
                    error=str(e),
                )
                print(f"✗ failed")

        # Write results to file
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        output_path = f"backend/results/qa_run_{timestamp}.json"
        result_file = self.formatter.write_to_file(output_path)

        print(f"\nResults written to: {result_file}")
        return result_file


async def main():
    """Example usage of QATestRunner."""
    runner = QATestRunner(scope="critical")
    await runner.run_all()


if __name__ == "__main__":
    asyncio.run(main())
