"""QA Results Formatter - Structures and persists test results for analysis."""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class QAResultsFormatter:
    """Format and persist QA test results with structured metadata."""

    def __init__(self, scope: str) -> None:
        """Initialize formatter with run metadata.

        Args:
            scope: Test scope (e.g., 'critical', 'all', 'custom')
        """
        self.run_id = f"qa_run_{int(time.time() * 1000)}"
        self.timestamp = datetime.utcnow().isoformat()
        self.scope = scope
        self.test_results: List[Dict[str, Any]] = []
        self.scenarios_passed = 0
        self.scenarios_failed = 0

    def add_result(
        self,
        scenario_name: str,
        status: str,
        duration_ms: float,
        tool_calls: int = 0,
        langfuse_trace_id: Optional[str] = None,
        assertions: Optional[int] = None,
        error: Optional[str] = None,
        db_state: Optional[Dict[str, Any]] = None,
        response_snippet: Optional[str] = None,
    ) -> None:
        """Add a test result to the formatter.

        Args:
            scenario_name: Name of the test scenario
            status: Test status ('passed', 'failed', 'skipped')
            duration_ms: Test execution duration in milliseconds
            tool_calls: Number of tool calls made during test
            langfuse_trace_id: Optional trace ID for observability
            assertions: Number of assertions checked
            error: Optional error message if test failed
            db_state: Optional database state snapshot
            response_snippet: Optional LLM response snippet
        """
        result = {
            "scenario_name": scenario_name,
            "status": status,
            "duration_ms": duration_ms,
            "tool_calls": tool_calls,
            "langfuse_trace_id": langfuse_trace_id,
            "assertions": assertions,
            "error": error,
            "db_state": db_state,
            "response_snippet": response_snippet,
        }

        self.test_results.append(result)

        # Track pass/fail counts
        if status == "passed":
            self.scenarios_passed += 1
        elif status == "failed":
            self.scenarios_failed += 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert results to dictionary format.

        Returns:
            Dictionary with run metadata and test results
        """
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "scope": self.scope,
            "scenarios_run": len(self.test_results),
            "scenarios_passed": self.scenarios_passed,
            "scenarios_failed": self.scenarios_failed,
            "test_results": self.test_results,
        }

    def write_to_file(self, output_path: str) -> str:
        """Write results to JSON file.

        Args:
            output_path: File path to write results to

        Returns:
            Path to written file
        """
        # Ensure parent directory exists
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Write JSON to file
        with open(output_file, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

        return str(output_file)
