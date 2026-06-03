# Test QA-Audit-Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Execute each task with review checkpoints. Max 2 review iterations per task.

**Goal:** Build reusable `/test-qa-audit-loop` skill for automated testing, audit analysis, and fix implementation with user approval gates.

**Architecture:** Skill orchestrates three agents (QA, Audit, Planning) with pauses between stages. QA runs scenarios → writes results JSON. Audit correlates results + traces + logs → writes severity-ranked report. Planning + subagent-driven-development implements fixes.

**Tech Stack:** Python (QA/Audit scripts), Skill definition (Markdown), superpowers orchestration

---

### Task 1: Create QA Results Formatter ✅

**Files:**
- Create: `backend/scripts/qa_results_formatter.py`

- [x] Write formatter module with `QAResultsFormatter` class
- [x] Methods: `add_result()`, `to_dict()`, `write_to_file()`
- [x] Test imports work
- [x] Commit

---

### Task 2: Create QA Test Runner

**Files:**
- Create: `backend/scripts/qa_test_runner.py`

- [ ] Write runner with `QATestRunner` class
- [ ] Methods: `get_scenarios()` (return list based on scope), `run_scenario()`, `run_all()`
- [ ] Scenarios: all/critical/custom filtering
- [ ] Write results to `backend/results/qa_run_<timestamp>.json`
- [ ] Test imports, verify results dir exists
- [ ] Commit

---

### Task 3: Create Audit Report Formatter

**Files:**
- Create: `backend/scripts/audit_report_formatter.py`

- [ ] Write `AuditFinding` class with severity levels
- [ ] Write `AuditReportFormatter` class
- [ ] Methods: `add_finding()`, `to_markdown()`, `write_to_file()`
- [ ] Format: Critical failures first, then warnings, then info
- [ ] Test imports
- [ ] Commit

---

### Task 4: Create Audit Analyzer

**Files:**
- Create: `backend/scripts/audit_analyzer.py`

- [ ] Write `AuditAnalyzer` class
- [ ] Methods: `analyze()`, `_analyze_failures()`, `_categorize_failure()`, `_analyze_anomalies()`
- [ ] Load QA results JSON
- [ ] Identify tool failures as CRITICAL
- [ ] Identify slow tests (>2s) as WARNING
- [ ] Write report to `backend/results/audit_report_<timestamp>.md`
- [ ] Test imports
- [ ] Commit

---

### Task 5: Create Main Skill Definition

**Files:**
- Create: `~/.claude/skills/test-qa-audit-loop.md`

- [ ] Write skill frontmatter (name, description)
- [ ] Document workflow phases (QA → Audit → Plan → Fix → Loop)
- [ ] Document scope choices (critical/all/custom)
- [ ] Include usage examples
- [ ] Document limitations and next steps
- [ ] Commit

---

### Task 6: Update Project Handover

**Files:**
- Modify: `backend/PHASE_5_HANDOVER.md`

- [ ] Append "Test Infrastructure: Automated QA-Audit-Loop" section
- [ ] Document files created, how to use, workflow, benefits, next steps
- [ ] Commit
