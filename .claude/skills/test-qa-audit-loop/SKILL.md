---
name: test-qa-audit-loop
version: 1.0.0
type: workflow
description: Orchestrate automated QA testing, audit analysis, planning, and fix implementation with user approval gates
---

# Test QA Audit Loop Skill

## Overview

This skill orchestrates a complete quality assurance workflow with five phases:

1. **Scenario Scope Selection** - Choose test scope (critical/all/custom)
2. **QA Execution** - Run tests and generate results JSON
3. **Audit Analysis** - Correlate traces/logs, rank findings by severity
4. **Planning** - Create implementation plan for identified issues
5. **Implementation** - Execute fixes via subagent-driven-development with user approval

Each phase includes user approval gates before proceeding to the next.

## Getting Started

### Quick Start: Critical Tests Only
```
/test-qa-audit-loop --scope critical
```

### Full QA Cycle: All Scenarios
```
/test-qa-audit-loop --scope all
```

### Custom Scenario Selection
```
/test-qa-audit-loop --scope custom --scenarios "auth,payment,onboarding"
```

### Dry-Run (Analysis Only, No Implementation)
```
/test-qa-audit-loop --scope all --dry-run
```

## Workflow: Five Phases

### Phase 1: Scenario Scope Selection

**User Control:** Select test scenarios to run

**Options:**
- `critical` - Run minimum viable set (login, payment, core flows)
- `all` - Run complete test suite for all features
- `custom` - Select specific scenarios by name

**Output:**
- Selected scenario list
- Estimated test runtime
- Request for user confirmation

**Decision Point:** Proceed to Phase 2 or abort

---

### Phase 2: QA Execution

**Automation:** Runs selected test scenarios, captures results

**Process:**
1. Load scenario definitions from `~/.claude/qa/scenarios/`
2. Execute each scenario in isolated test environment
3. Capture:
   - Test pass/fail status
   - Execution time per test
   - Error messages and stack traces
   - Browser traces (if Playwright-based)
   - API request/response logs
4. Write results to JSON: `qa_results_TIMESTAMP.json`

**Output Format:**
```json
{
  "execution_id": "qa_20260603_143022",
  "timestamp": "2026-06-03T14:30:22Z",
  "scope": "critical",
  "scenarios": [
    {
      "name": "auth_login",
      "status": "FAILED",
      "duration_ms": 2500,
      "tests": [
        {
          "id": "auth_login_001",
          "name": "Valid credentials login",
          "status": "PASSED",
          "duration_ms": 800
        },
        {
          "id": "auth_login_002",
          "name": "Invalid password rejection",
          "status": "FAILED",
          "duration_ms": 1200,
          "error": "Timeout waiting for error message",
          "stack": "..."
        }
      ],
      "artifacts": {
        "traces": ["traces/auth_login_trace_001.zip"],
        "screenshots": ["screenshots/auth_login_002_failure.png"],
        "logs": ["logs/auth_login_api.log"]
      }
    }
  ],
  "summary": {
    "total_tests": 24,
    "passed": 22,
    "failed": 2,
    "skipped": 0,
    "pass_rate": 91.7
  }
}
```

**Decision Point:** Review results before proceeding to audit

---

### Phase 3: Audit Analysis

**Automation:** Analyze traces, logs, and correlate failures

**Process:**
1. Load test results JSON from Phase 2
2. For each failed test:
   - Extract stack traces and error messages
   - Correlate with API logs (if available)
   - Check browser traces for DOM/rendering issues
   - Query for related passing/failing tests
   - Determine root cause (frontend/backend/infrastructure)
3. Rank findings by:
   - Impact severity (CRITICAL/HIGH/MEDIUM/LOW)
   - Frequency (one-off vs. pattern)
   - User-facing vs. internal
4. Generate audit report with categorized findings

**Output Format:**
```json
{
  "audit_id": "audit_20260603_143022",
  "execution_id": "qa_20260603_143022",
  "findings": [
    {
      "id": "FINDING_001",
      "severity": "HIGH",
      "category": "performance",
      "title": "Login form timeout after invalid password",
      "affected_tests": ["auth_login_002"],
      "root_cause": "API endpoint /api/auth/validate returns 504 after 2 failed attempts",
      "evidence": [
        "Stack trace: Timeout in cy.get('[data-testid=error-message]')",
        "API logs: POST /api/auth/validate returns 504 at 14:30:15",
        "Pattern: Occurs when invalid password submitted within 1 second of first failure"
      ],
      "impact": "Users cannot retry login after single failed attempt",
      "suggested_fix": "Add retry logic with exponential backoff in auth service"
    }
  ],
  "summary": {
    "total_findings": 2,
    "critical": 0,
    "high": 1,
    "medium": 1,
    "low": 0
  }
}
```

**Decision Point:** Review findings and approve planning or request adjustments

---

### Phase 4: Planning

**Automation:** Create implementation plan for approved fixes

**Process:**
1. Load audit findings from Phase 3
2. For each approved finding:
   - Define acceptance criteria
   - Estimate effort (XS/S/M/L)
   - Identify files to modify
   - Suggest test cases to add
3. Order fixes by:
   - Dependency graph (fixes with no dependencies first)
   - Severity (high-impact first)
   - Effort (quick wins before complex)
4. Generate implementation plan document

**Output Format:**
```markdown
# Implementation Plan - QA Audit 20260603_143022

## Summary
- Total fixes: 2
- Estimated effort: 6 hours (3 + 3)
- Dependencies: None
- Risk level: MEDIUM

## Fix 1: Auth Service Retry Logic
- **Severity:** HIGH
- **Effort:** 3 hours
- **Files:** backend/app/services/auth_service.py
- **Acceptance Criteria:**
  1. Invalid login followed by retry within 1s succeeds
  2. After 3 failed attempts, 30s cooldown enforced
  3. Error message displayed immediately (no timeout)
- **Test Cases to Add:**
  - test_retry_after_failed_attempt
  - test_cooldown_period_enforced
  - test_error_message_immediate

## Fix 2: Payment Form Validation
- **Severity:** MEDIUM
- **Effort:** 3 hours
- **Files:** frontend/components/PaymentForm.tsx
- **Acceptance Criteria:**
  1. Card number field validates format in real-time
  2. Expiry date field allows MM/YY format only
  3. CVC validation enforced (3-4 digits)
- **Test Cases to Add:**
  - test_card_validation_format
  - test_expiry_format_enforcement
  - test_cvc_digit_validation

## Execution Order
1. Fix auth service retry logic (unblocks payment testing)
2. Fix payment form validation (no dependencies)
```

**Decision Point:** Review plan, request adjustments, or approve implementation

---

### Phase 5: Implementation

**Automation:** Execute fixes via subagent-driven-development

**Process:**
1. Load implementation plan from Phase 4
2. For each approved fix:
   - Create feature branch (auto-named from fix)
   - Delegate implementation to engineer-agent via subagent-driven-development
   - Agent implements fix following plan acceptance criteria
   - Agent creates tests for fix
   - Agent submits for code review
3. After all fixes complete:
   - Run Phase 2 (QA Execution) again with same scope
   - Verify all previously failing tests now pass
   - Report regression analysis

**Subagent Invocation:**
```
runSubagent(
  agentName: "engineer-agent",
  prompt: "Implement fix for [FINDING_ID]: [title]\n\nAcceptance Criteria:\n- [criterion 1]\n- [criterion 2]\n\nFiles to modify: [file list]\n\nAfter implementation:\n1. Create/update tests for acceptance criteria\n2. Run tests locally\n3. Submit for code review",
  description: "Implement QA fix"
)
```

**Output:**
```
## Implementation Results

### Fix 1: Auth Service Retry Logic
- Status: IMPLEMENTED
- Commit: abc1234
- Tests Created: 3
- Tests Passing: 3/3
- Code Review: APPROVED

### Fix 2: Payment Form Validation
- Status: IMPLEMENTED
- Commit: def5678
- Tests Created: 3
- Tests Passing: 3/3
- Code Review: APPROVED

### Regression Testing
- Previous failures: 2
- Retested: 24 total
- New failures: 0
- Pass rate improved: 91.7% → 100%

### Summary
All fixes implemented and verified. No regressions detected.
```

---

## Example Session

### User Initiates QA Cycle
```
$ /test-qa-audit-loop --scope critical

Scenario Scope Selection
========================

Selected scenarios (critical):
- auth_login (1 scenario, 4 tests)
- payment_checkout (1 scenario, 6 tests)
- booking_create (1 scenario, 5 tests)

Total: 15 tests
Estimated runtime: 8 minutes

Ready to execute? [yes/no]
```

### User Confirms → Phase 2 Executes
```
Running QA Execution
====================

Scenario 1: auth_login
  ✓ Valid credentials login (0.8s)
  ✗ Invalid password rejection (1.2s) - Timeout
  ✓ Forgot password flow (1.1s)
  ✓ 2FA code validation (0.9s)

Scenario 2: payment_checkout
  ✓ Valid card processing (2.1s)
  ✓ Invalid card rejection (0.7s)
  ✓ 3D Secure verification (3.2s)
  ✓ Receipt generation (0.6s)
  ✓ Refund processing (1.1s)
  ✓ Invoice email delivery (2.5s)

Scenario 3: booking_create
  ✓ Basic booking (1.8s)
  ✓ Booking with addons (2.3s)
  ✓ Booking confirmation email (1.5s)
  ✓ Booking cancellation (0.9s)
  ✓ Refund on cancellation (1.2s)

Results: 14 passed, 1 failed (93.3% pass rate)
Artifacts: qa_results_20260603_143022.json

Ready for audit analysis? [yes/no]
```

### User Confirms → Phase 3 Analyzes
```
Audit Analysis
==============

Finding 1: HIGH - Auth timeout after invalid password
  Root Cause: POST /api/auth/validate returns 504 after retry
  Impact: Users cannot retry login
  Tests affected: auth_login_002

Finding 2: MEDIUM - Payment form validation timing
  Root Cause: DOM not updated immediately after card number entry
  Impact: User experience (validation appears delayed)
  Tests affected: None yet (but observed in traces)

Total findings: 2 (1 high, 1 medium)

Review findings and approve planning? [yes/no]
```

### User Approves → Phase 4 Plans
```
Planning Implementation Fixes
=============================

Fix 1: Auth Service Retry Logic (HIGH)
  Files: backend/app/services/auth_service.py
  Effort: 3 hours
  Acceptance criteria: 3 criteria defined

Fix 2: Payment Form Validation (MEDIUM)
  Files: frontend/components/PaymentForm.tsx
  Effort: 3 hours
  Acceptance criteria: 3 criteria defined

Total effort: 6 hours
Order: Fix auth first (blocks payment), then payment form

Ready to implement? [yes/no]
```

### User Approves → Phase 5 Implements
```
Implementing Fixes
==================

Implementing Fix 1: Auth Service Retry Logic
  Branch: gni-fix-auth-retry-logic
  Status: In Progress
  Agent: engineer-agent
  
  [Agent implements fix, creates tests, runs verification]
  
  Completed: 3 tests passing
  Code review: APPROVED ✓

Implementing Fix 2: Payment Form Validation
  Branch: gni-fix-payment-form-validation
  Status: In Progress
  Agent: engineer-agent
  
  [Agent implements fix, creates tests, runs verification]
  
  Completed: 3 tests passing
  Code review: APPROVED ✓

Regression Testing
==================

Running Phase 2 again (critical scope)...

Results: 15 passed, 0 failed (100% pass rate) ✓

All previously failing tests now pass.
No regressions detected.

QA Audit Loop Complete
======================
Scope: critical
Duration: 47 minutes
Fixes: 2 implemented
Tests passing: 15/15 (100%)
Status: SUCCESS
```

---

## Implementation Notes

### Scenario Definitions

Scenarios are stored in `~/.claude/qa/scenarios/` as YAML files:

```yaml
# ~/.claude/qa/scenarios/auth_login.yaml
name: auth_login
description: Authentication login flow tests
priority: critical
tests:
  - id: auth_login_001
    name: Valid credentials login
    steps:
      - navigate: http://localhost:3000/login
      - fill: "[data-testid=username]" value: "test@example.com"
      - fill: "[data-testid=password]" value: "password123"
      - click: "[data-testid=submit]"
      - wait_for: "[data-testid=dashboard]"
    timeout: 5000
```

### Result File Format

All results stored as JSON for programmatic analysis:
- `qa_results_TIMESTAMP.json` - Test execution results
- `qa_audit_TIMESTAMP.json` - Audit findings
- `qa_plan_TIMESTAMP.md` - Implementation plan

### Approval Gates

User must explicitly approve at each phase:
1. Phase 1 → 2: Confirm scenario selection
2. Phase 2 → 3: Review test results
3. Phase 3 → 4: Approve findings for planning
4. Phase 4 → 5: Approve implementation plan
5. Phase 5: Review fixes before committing

### Dry-Run Mode

Use `--dry-run` to skip implementation phase:
```
/test-qa-audit-loop --scope all --dry-run
```

Executes phases 1-4, generates plan, but does NOT implement fixes. Useful for:
- Planning future sprint work
- Estimating effort
- Impact analysis
- Risk assessment

---

## Limitations

1. **Scenario Coverage** - Only predefined scenarios can be selected (custom scenario creation not yet supported)
2. **Parallel Execution** - Phases execute sequentially (no parallelization between scenarios)
3. **Result Retention** - Audit results stored locally only (not yet integrated into database)
4. **Flaky Test Handling** - Flaky tests not yet automatically retried (manual review required)
5. **Performance Baselines** - No historical trending (each audit standalone)

---

## See Also

- **Test Execution:** `/run-tests` - Run test suite directly
- **Code Review:** `/code-review` - Review implementation changes
- **Debug Workflow:** `/run-debug` - Investigate test failures
- **Subagent Development:** `/superpowers:subagent-driven-development` - Agent implementation orchestration
