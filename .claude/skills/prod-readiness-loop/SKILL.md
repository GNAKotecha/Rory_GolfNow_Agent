---
name: prod-readiness-loop
version: 1.0.0
type: meta
description: Continuous E2E testing, bug fixing, and validation loop until production ready
triggers:
  - make this prod ready
  - test until production ready
  - continuous qa loop
  - validate for production
  - /prod-readiness-loop
---

# Production Readiness Loop

## Purpose
Orchestrate continuous E2E testing, bug fixing, and validation using specialized subagents until system is production ready.

## Inputs
**Required:**
- `test_plan_path`: Path to E2E test plan (default: docs/superpowers/plans/e2e-test-plan.md)

**Optional:**
- `max_iterations`: Maximum loop cycles (default: 10)
- `skip_phases`: List of test phases to skip
- `focus_tests`: Specific tests to focus on

## Workflow
1. Dispatch e2e-test-executor subagent to run Playwright tests from plan
2. Analyze test results, parse logs, identify failures and root causes
3. If bugs found: dispatch bug-analyzer subagent to create detailed report
4. Dispatch plan-writer subagent to create fix plan for identified bugs
5. Dispatch implementer subagents (parallel) to execute fixes per plan
6. Dispatch code-reviewer subagent to validate all fixes
7. Dispatch documentation-writer subagent to update docs with changes
8. Re-run E2E tests on fixed code, update progress tracker
9. If all critical tests pass: validate MCP servers and skills
10. If validation passes: dispatch final-doc-reviewer subagent, mark PROD_READY
11. Max iterations reached: generate final status report and blockers

## Tools
- Agent (subagent dispatch)
- Read (test plans, logs, code)
- Write (bug reports, fix plans, status)
- Edit (code fixes)
- Bash (start services, check logs)
- mcp__playwright__browser_* (E2E browser testing)
- TodoWrite (iteration progress tracking)

## Subagents

### e2e-test-executor
- **Role**: Execute E2E tests via Playwright MCP
- **Inputs**: Test plan path, browser state
- **Outputs**: Test results, screenshots, logs
- **Location**: .claude/agents/e2e-test-executor.md

### bug-analyzer
- **Role**: Analyze test failures and identify root causes
- **Inputs**: Test results, backend logs
- **Outputs**: Bug report with severity, impact, root cause
- **Location**: .claude/agents/bug-analyzer.md

### plan-writer
- **Role**: Create implementation plan to fix bugs
- **Inputs**: Bug report, codebase context
- **Outputs**: Fix plan with tasks, files, acceptance criteria

### implementer
- **Role**: Execute specific fix from plan
- **Inputs**: Fix task, code context
- **Outputs**: Code changes, tests updated

### code-reviewer
- **Role**: Review fixes for correctness and completeness
- **Inputs**: Changed files, fix plan
- **Outputs**: Review result (approve/request changes)

### documentation-writer
- **Role**: Update documentation after fixes applied
- **Inputs**: Bug report, fix plan, code changes
- **Outputs**: Updated PHASE_*_HANDOVER.md, E2E_TEST_RESULTS.md, bug reports
- **Location**: .claude/agents/documentation-writer.md

### final-doc-reviewer
- **Role**: Validate all documentation is complete and accurate
- **Inputs**: All docs created during loop
- **Outputs**: Documentation checklist (missing sections, outdated info)
- **Location**: .claude/agents/final-doc-reviewer.md

## Error Handling
1. Test execution fails → Capture screenshots/logs, create bug report, continue
2. Fix implementation blocked → Document blocker, add to known issues, skip
3. Max iterations reached → Generate final report with remaining blockers
4. Subagent error → Retry with more context, fallback to manual intervention
5. Playwright browser 'already in use' → Run 'pkill -f playwright-mcp' to kill all processes, wait 2s, retry test
6. Agent tool API error (thinking.type) → Fall back to direct tool execution instead of subagent dispatch

## Validation Criteria

### Critical Tests
- REINSTATE_USER workflow completes without loops
- State machine transitions correctly
- HTTP method validation works
- MCP tools execute successfully
- Skills invokable via '\' and semantic matching

### MCP Servers
- brs-admin MCP server connected
- Playwright MCP server functional
- Tools discoverable via frontend

### Skills
- REINSTATE_USER skill works
- At least one other skill works

## Output Format
```
=== ITERATION N/M ===
Tests Run: X/Y passed (Z failed)
New Bugs: [list with IDs]
Fixes Applied: [list with file paths]
Status: IN_PROGRESS / BLOCKED / READY

=== FINAL STATUS ===
Production Ready: YES/NO
Critical Tests: X/Y passing
Known Blockers: [list]
Next Steps: [recommendations]
```

## Notes
- Uses Playwright MCP for real browser testing
- Delegates each phase to specialized subagents for isolation
- Tracks progress across iterations with TodoWrite
- Updates documentation after each iteration (PHASE_5_HANDOVER.md, E2E_TEST_RESULTS.md, bug reports)
- Validates MCP servers, skills, and core workflows
- Final documentation review before production approval
- Generates comprehensive status reports per iteration
- Stops when all critical tests pass AND documentation validated
- All changes traceable from bug → fix → verification → docs
