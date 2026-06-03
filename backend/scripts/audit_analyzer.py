"""Audit Analyzer - Analyze QA test results and identify issues.

This module provides the AuditAnalyzer class to analyze QA test results,
identify root causes in failures, and detect anomalies in passed tests.
It generates structured audit reports using the AuditReportFormatter.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.scripts.audit_report_formatter import (
    AuditFinding,
    AuditReportFormatter,
    Severity,
)


class AuditAnalyzer:
    """Analyze QA test results to identify failures, anomalies, and patterns.

    This analyzer:
    1. Loads QA results from JSON file
    2. Analyzes failures to find root causes
    3. Detects anomalies in passed tests (e.g., slow tests)
    4. Generates a comprehensive audit report
    """

    def __init__(self, qa_results_file: str, logs_file: str = "") -> None:
        """Initialize the audit analyzer.

        Args:
            qa_results_file: Path to QA results JSON file
            logs_file: Optional path to logs file for additional context
        """
        self.qa_results_file = qa_results_file
        self.logs_file = logs_file
        self.qa_results: Dict[str, Any] = {}
        self.findings: List[AuditFinding] = []
        self._load_qa_results()

    def _load_qa_results(self) -> None:
        """Load QA results from JSON file.

        Raises:
            FileNotFoundError: If qa_results_file doesn't exist
            json.JSONDecodeError: If file is not valid JSON
        """
        qa_file = Path(self.qa_results_file)
        if not qa_file.exists():
            raise FileNotFoundError(f"QA results file not found: {self.qa_results_file}")

        with open(qa_file, "r") as f:
            self.qa_results = json.load(f)

    def analyze(self) -> str:
        """Main analysis method.

        Executes full analysis pipeline:
        1. Analyzes failures to find root causes
        2. Analyzes anomalies in passed tests
        3. Generates and writes report

        Returns:
            Path to written audit report file
        """
        # Analyze failures
        self._analyze_failures()

        # Analyze anomalies in passed tests
        self._analyze_anomalies()

        # Generate report using formatter
        qa_run_id = self.qa_results.get("run_id", "unknown")
        formatter = AuditReportFormatter(qa_run_id)

        for finding in self.findings:
            formatter.add_finding(finding)

        # Write report to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"backend/results/audit_report_{timestamp}.md"
        report_path = formatter.write_to_file(output_path)

        return report_path

    def _analyze_failures(self) -> None:
        """Analyze failed tests to find root causes.

        Loops through test_results where status=="failed":
        - Checks tool_calls for failures
        - Creates CRITICAL findings for tool failures
        - Includes tool name, error message, trace ID, code path
        """
        test_results = self.qa_results.get("test_results", [])

        for result in test_results:
            if result.get("status") == "failed":
                scenario_name = result.get("scenario_name", "unknown")
                error_msg = result.get("error", "No error message")
                trace_id = result.get("langfuse_trace_id", "")
                tool_calls = result.get("tool_calls", 0)

                # Create finding for failed test
                finding = self._categorize_failure(
                    scenario_name=scenario_name,
                    error_msg=error_msg,
                    trace_id=trace_id,
                    tool_calls=tool_calls,
                    result=result,
                )

                if finding:
                    self.findings.append(finding)

    def _categorize_failure(
        self,
        scenario_name: str,
        error_msg: str,
        trace_id: str,
        tool_calls: int,
        result: Dict[str, Any],
    ) -> Optional[AuditFinding]:
        """Categorize a failed test and create audit finding.

        Args:
            scenario_name: Name of the scenario that failed
            error_msg: Error message from the failure
            trace_id: Trace ID for observability
            tool_calls: Number of tool calls made
            result: Full result dict for context

        Returns:
            AuditFinding with CRITICAL severity
        """
        # Build title based on error type
        title = f"Failed Scenario: {scenario_name}"

        # Build root cause explanation
        root_cause = f"Test scenario failed during execution. Error: {error_msg}"

        # Determine code path (use scenario name as proxy)
        code_path = f"tests/scenarios/{scenario_name}"

        # Build suggested fix
        suggested_fix = (
            f"Review test scenario logic and verify tool calls are executing correctly. "
            f"Check observability traces (ID: {trace_id}) for detailed execution flow."
        )

        # Build details dict
        details = {
            "tool_calls": tool_calls,
            "duration_ms": result.get("duration_ms", 0),
        }

        # Add response snippet if available
        if result.get("response_snippet"):
            details["response_snippet"] = result.get("response_snippet")

        # Add db state if available
        if result.get("db_state"):
            details["db_state"] = result.get("db_state")

        trace_ids = [trace_id] if trace_id else []

        finding = AuditFinding(
            title=title,
            severity=Severity.CRITICAL,
            affected_tests=[scenario_name],
            root_cause=root_cause,
            trace_ids=trace_ids,
            affected_code_path=code_path,
            suggested_fix=suggested_fix,
            details=details,
        )

        return finding

    def _analyze_anomalies(self) -> None:
        """Analyze passed tests for anomalies.

        Loops through test_results where status=="passed":
        - If duration_ms > 2000, creates WARNING finding for slow test
        - Includes tool call durations and suggested investigation
        """
        test_results = self.qa_results.get("test_results", [])
        slow_test_threshold_ms = 2000

        for result in test_results:
            if result.get("status") == "passed":
                duration_ms = result.get("duration_ms", 0)

                # Check for slow tests
                if duration_ms > slow_test_threshold_ms:
                    scenario_name = result.get("scenario_name", "unknown")
                    trace_id = result.get("langfuse_trace_id", "")
                    tool_calls = result.get("tool_calls", 0)

                    # Create WARNING finding for slow test
                    title = f"Slow Test: {scenario_name}"

                    root_cause = (
                        f"Test scenario completed successfully but took {duration_ms}ms, "
                        f"exceeding the {slow_test_threshold_ms}ms threshold."
                    )

                    code_path = f"tests/scenarios/{scenario_name}"

                    suggested_fix = (
                        f"Investigate performance bottlenecks in test execution. "
                        f"Review tool call durations and consider optimizing setup/teardown steps. "
                        f"Check traces (ID: {trace_id}) for slow operations."
                    )

                    details = {
                        "duration_ms": duration_ms,
                        "threshold_ms": slow_test_threshold_ms,
                        "tool_calls": tool_calls,
                        "assertions": result.get("assertions", 0),
                    }

                    trace_ids = [trace_id] if trace_id else []

                    finding = AuditFinding(
                        title=title,
                        severity=Severity.WARNING,
                        affected_tests=[scenario_name],
                        root_cause=root_cause,
                        trace_ids=trace_ids,
                        affected_code_path=code_path,
                        suggested_fix=suggested_fix,
                        details=details,
                    )

                    self.findings.append(finding)
