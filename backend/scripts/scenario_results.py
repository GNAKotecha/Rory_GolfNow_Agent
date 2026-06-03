#!/usr/bin/env python3
"""
Test result persistence and export utilities.

Handles formatting, saving, and loading E2E test results to/from JSON.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from statistics import mean


@dataclass
class TestRunSummary:
    """Summary statistics for a test run."""
    timestamp: str
    environment: str
    total: int
    passed: int
    failed: int
    pass_rate: float
    duration_seconds: float
    failed_scenarios: List[str]

    @staticmethod
    def from_result(result: Dict) -> "TestRunSummary":
        """Create summary from result dict."""
        failed = [s["scenario_name"] for s in result.get("scenarios", []) if not s.get("success", False)]
        total = result.get("total_scenarios", 0)
        passed = result.get("passed", 0)
        pass_rate = (passed / total * 100) if total > 0 else 0.0

        return TestRunSummary(
            timestamp=result.get("timestamp", ""),
            environment=result.get("environment", "unknown"),
            total=total,
            passed=passed,
            failed=result.get("failed", 0),
            pass_rate=pass_rate,
            duration_seconds=result.get("duration_seconds", 0.0),
            failed_scenarios=failed
        )


class ResultExporter:
    """Handles test result formatting and export."""

    @staticmethod
    def format_scenario_result(
        scenario_name: str,
        success: bool,
        turns: List[Dict],
        tool_calls_count: int,
        error: Optional[str] = None
    ) -> Dict:
        """Format a single scenario result."""
        return {
            "scenario_name": scenario_name,
            "success": success,
            "turn_count": len(turns),
            "tool_calls_count": tool_calls_count,
            "error_message": error,
            "turn_results": [
                {
                    "turn": t.get("turn", i + 1),
                    "success": t.get("success", True),
                    "keywords_matched": t.get("keywords_matched", None),
                    "tool_used": t.get("tool_used", False)
                }
                for i, t in enumerate(turns)
            ]
        }

    @staticmethod
    def format_test_run(
        timestamp: str,
        environment: str,
        scenarios: List[Dict],
        duration_seconds: float,
        tags: Optional[List[str]] = None
    ) -> Dict:
        """Format a complete test run."""
        passed = sum(1 for s in scenarios if s.get("success", False))
        failed = len(scenarios) - passed

        return {
            "timestamp": timestamp,
            "environment": environment,
            "total_scenarios": len(scenarios),
            "passed": passed,
            "failed": failed,
            "duration_seconds": duration_seconds,
            "tags": tags or [],
            "scenarios": scenarios
        }

    @staticmethod
    def save_to_json(result: Dict, output_dir: str = "test-results") -> str:
        """Save result to JSON file, return full path."""
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # Generate filename with timestamp and microseconds for uniqueness
        now = datetime.utcnow()
        timestamp = now.strftime("%Y_%m_%d_%H_%M_%S_%f")
        filename = f"test_run_{timestamp}.json"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "w") as f:
            json.dump(result, f, indent=2)

        return filepath

    @staticmethod
    def read_from_json(filepath: str) -> Dict:
        """Read and parse result JSON file."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Result file not found: {filepath}")

        with open(filepath, "r") as f:
            data = json.load(f)

        # Validate structure
        required_fields = ["timestamp", "environment", "total_scenarios", "passed", "failed", "scenarios"]
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Invalid result format: missing field '{field}'")

        return data


def aggregate_runs(result_files: List[str]) -> Dict:
    """Aggregate multiple result files for trend analysis."""
    if not result_files:
        return {
            "total_runs": 0,
            "date_range": None,
            "avg_pass_rate": 0.0,
            "trend": "unknown",
            "by_scenario": {}
        }

    runs = []
    for filepath in result_files:
        try:
            result = ResultExporter.read_from_json(filepath)
            runs.append(result)
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            continue

    if not runs:
        return {
            "total_runs": 0,
            "date_range": None,
            "avg_pass_rate": 0.0,
            "trend": "unknown",
            "by_scenario": {}
        }

    # Calculate overall stats
    pass_rates = []
    by_scenario = {}

    for run in runs:
        total = run.get("total_scenarios", 0)
        passed = run.get("passed", 0)
        if total > 0:
            pass_rates.append(passed / total * 100)

        for scenario in run.get("scenarios", []):
            name = scenario.get("scenario_name", "unknown")
            if name not in by_scenario:
                by_scenario[name] = {"runs": 0, "passes": 0, "pass_rate": 0.0}

            by_scenario[name]["runs"] += 1
            if scenario.get("success", False):
                by_scenario[name]["passes"] += 1
            by_scenario[name]["pass_rate"] = by_scenario[name]["passes"] / by_scenario[name]["runs"] * 100

    # Determine trend
    avg_pass_rate = mean(pass_rates) if pass_rates else 0.0
    if len(pass_rates) >= 2:
        recent_avg = mean(pass_rates[-3:]) if len(pass_rates) >= 3 else pass_rates[-1]
        old_avg = mean(pass_rates[:-3]) if len(pass_rates) > 3 else pass_rates[0]
        if recent_avg > old_avg + 5:
            trend = "improving"
        elif recent_avg < old_avg - 5:
            trend = "declining"
        else:
            trend = "stable"
    else:
        trend = "insufficient_data"

    # Date range
    timestamps = [r.get("timestamp", "") for r in runs if r.get("timestamp")]
    date_range = f"{min(timestamps)} to {max(timestamps)}" if timestamps else None

    return {
        "total_runs": len(runs),
        "date_range": date_range,
        "avg_pass_rate": round(avg_pass_rate, 2),
        "trend": trend,
        "by_scenario": by_scenario
    }
