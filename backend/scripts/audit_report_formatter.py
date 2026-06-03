"""Audit Report Formatter - Generate structured markdown audit reports.

This module provides classes to build and format audit findings into structured
markdown reports with severity levels, affected tests, root causes, and fixes.
"""

from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path


class Severity(Enum):
    """Severity levels for audit findings."""
    CRITICAL = 1  # Highest priority
    WARNING = 2
    INFO = 3


@dataclass
class AuditFinding:
    """Represents a single audit finding with severity, impact, and remediation.

    Attributes:
        title: Short descriptive title of the finding
        severity: Severity level (CRITICAL, WARNING, INFO)
        affected_tests: List of test names/identifiers impacted by this finding
        root_cause: Explanation of the underlying cause
        trace_ids: List of trace IDs from observability system for correlation
        affected_code_path: File path or code location affected by this issue
        suggested_fix: Recommended solution or remediation step
        details: Additional details as dict (e.g., metrics, error messages, context)
    """
    title: str
    severity: Severity
    affected_tests: List[str]
    root_cause: str
    trace_ids: List[str]
    affected_code_path: str
    suggested_fix: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_markdown(self) -> str:
        """Convert finding to markdown format.

        Returns:
            Markdown string with finding details formatted for readability
        """
        lines = []

        # Title with severity indicator
        severity_indicator = {
            Severity.CRITICAL: "🔴 CRITICAL",
            Severity.WARNING: "🟡 WARNING",
            Severity.INFO: "ℹ️ INFO",
        }
        lines.append(f"### {severity_indicator[self.severity]} - {self.title}")
        lines.append("")

        # Affected tests
        if self.affected_tests:
            lines.append("**Affected Tests:**")
            for test in self.affected_tests:
                lines.append(f"- {test}")
            lines.append("")

        # Root cause
        lines.append("**Root Cause:**")
        lines.append(self.root_cause)
        lines.append("")

        # Trace IDs for correlation
        if self.trace_ids:
            lines.append("**Trace IDs:**")
            for trace_id in self.trace_ids:
                lines.append(f"- `{trace_id}`")
            lines.append("")

        # Affected code path
        lines.append("**Affected Code Path:**")
        lines.append(f"`{self.affected_code_path}`")
        lines.append("")

        # Suggested fix
        lines.append("**Suggested Fix:**")
        lines.append(self.suggested_fix)
        lines.append("")

        # Additional details
        if self.details:
            lines.append("**Details:**")
            for key, value in self.details.items():
                # Format value based on type
                if isinstance(value, (list, dict)):
                    lines.append(f"- **{key}:**")
                    lines.append(f"  ```json")
                    lines.append(f"  {value}")
                    lines.append(f"  ```")
                else:
                    lines.append(f"- **{key}:** {value}")
            lines.append("")

        return "\n".join(lines)


class AuditReportFormatter:
    """Generate structured markdown audit reports with findings organized by severity.

    This formatter collects audit findings and generates a comprehensive markdown report
    with summary statistics, findings grouped by severity level, and prioritized
    recommendations for remediation.
    """

    def __init__(self, qa_run_id: str):
        """Initialize the audit report formatter.

        Args:
            qa_run_id: Identifier for the QA run this audit is analyzing
        """
        self.qa_run_id = qa_run_id
        self.timestamp = datetime.now()
        self.findings: List[AuditFinding] = []

    def add_finding(self, finding: AuditFinding) -> None:
        """Add a finding to the report.

        Args:
            finding: AuditFinding instance to add to report
        """
        self.findings.append(finding)

    def _count_by_severity(self) -> Dict[Severity, int]:
        """Count findings by severity level.

        Returns:
            Dict mapping severity to count of findings at that level
        """
        counts = {Severity.CRITICAL: 0, Severity.WARNING: 0, Severity.INFO: 0}
        for finding in self.findings:
            counts[finding.severity] += 1
        return counts

    def to_markdown(self) -> str:
        """Generate complete markdown report.

        Returns:
            Full markdown string with header, summary, findings organized by severity,
            and recommendations section
        """
        lines = []

        # Header
        lines.append("# Audit Report")
        lines.append("")
        lines.append(f"**QA Run ID:** `{self.qa_run_id}`")
        lines.append(f"**Generated:** {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # Summary section
        counts = self._count_by_severity()
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Critical Issues:** {counts[Severity.CRITICAL]}")
        lines.append(f"- **Warnings:** {counts[Severity.WARNING]}")
        lines.append(f"- **Info Items:** {counts[Severity.INFO]}")
        lines.append(f"- **Total Findings:** {len(self.findings)}")
        lines.append("")

        # Critical failures section
        critical_findings = [f for f in self.findings if f.severity == Severity.CRITICAL]
        if critical_findings:
            lines.append("## Critical Failures")
            lines.append("")
            for finding in critical_findings:
                lines.append(finding.to_markdown())
            lines.append("")

        # Warnings section
        warning_findings = [f for f in self.findings if f.severity == Severity.WARNING]
        if warning_findings:
            lines.append("## Warnings")
            lines.append("")
            for finding in warning_findings:
                lines.append(finding.to_markdown())
            lines.append("")

        # Info section
        info_findings = [f for f in self.findings if f.severity == Severity.INFO]
        if info_findings:
            lines.append("## Info")
            lines.append("")
            for finding in info_findings:
                lines.append(finding.to_markdown())
            lines.append("")

        # Recommendations section listing critical items by priority
        if critical_findings:
            lines.append("## Recommendations")
            lines.append("")
            lines.append("**Priority Order (address in this order):**")
            lines.append("")
            for idx, finding in enumerate(critical_findings, 1):
                lines.append(f"{idx}. **{finding.title}**")
                lines.append(f"   - Fix: {finding.suggested_fix[:100]}...")
                lines.append(f"   - Code: `{finding.affected_code_path}`")
            lines.append("")

        return "\n".join(lines)

    def write_to_file(self, output_path: str) -> str:
        """Write report to markdown file.

        Args:
            output_path: File path where report should be written

        Returns:
            Absolute path to the written file
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        report_content = self.to_markdown()
        output_file.write_text(report_content, encoding='utf-8')

        return str(output_file.absolute())
