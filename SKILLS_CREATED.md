# Skills and Agents Created for Production Readiness

**Date:** 2026-06-08
**Purpose:** Enable continuous E2E testing, bug fixing, and validation loop

---

## 1. Production Readiness Loop Skill

**File:** `.claude/skills/prod-readiness-loop/SKILL.md`

**Type:** Meta-skill (orchestration)

**Purpose:** Continuous loop that tests, finds bugs, creates fix plans, implements fixes, and validates until production ready.

**Key Features:**
- Orchestrates specialized subagents for each phase
- Uses Playwright MCP for real browser testing
- Tracks progress across iterations
- Validates MCP servers, skills, and workflows
- Stops when all critical tests pass or max iterations reached

**Workflow:**
1. Execute E2E tests via Playwright
2. Analyze failures and create bug reports
3. Generate fix plans for identified bugs
4. Implement fixes in parallel
5. Review all changes
6. Re-test and validate
7. Loop until production ready

**Usage:**
```
make this prod ready
test until production ready
continuous qa loop
```

**Validation Criteria:**
- ✅ REINSTATE_USER workflow completes without loops
- ✅ State machine transitions correctly
- ✅ HTTP method validation works
- ✅ MCP tools execute successfully
- ✅ Skills invokable via '\' and semantic matching

---

## 2. Documentation Writer Agent

**File:** `.claude/agents/documentation-writer.md`

**Type:** Specialized subagent

**Purpose:** Update project documentation after bug fixes and code changes throughout the production readiness loop.

**Responsibilities:**
- Update PROD_READINESS_HANDOVER.md with iteration results
- Maintain E2E_TEST_RESULTS.md with latest test data
- Create/update bug reports (BUG_*.md files)
- Update SKILLS_CREATED.md with new skills
- Track bug status (OPEN → FIXED)

**Documentation Updated:**
- docs/PROD_READINESS_HANDOVER.md (iteration results, blockers, status)
- backend/E2E_TEST_RESULTS.md (test results, bugs found/fixed)
- backend/BUG_*.md (individual bug reports)
- SKILLS_CREATED.md (skill validation results)

**Output:** Comprehensive documentation updates after each iteration with clear traceability from bug → fix → verification.

---

## 3. Final Documentation Reviewer Agent

**File:** `.claude/agents/final-doc-reviewer.md`

**Type:** Specialized subagent

**Purpose:** Validate all documentation is complete, accurate, and production-ready before final approval.

**Responsibilities:**
- Completeness check (all bugs documented, all fixes recorded)
- Accuracy validation (status matches tests, claims verified)
- Traceability verification (bugs link to fixes, fixes link to tests)
- Production readiness assessment (CRITICAL bugs resolved, no false claims)

**Validation Criteria:**
- All CRITICAL bugs resolved and documented
- Test results support completion status
- Cross-references between docs accurate
- File paths and code locations verified
- No outdated information from previous iterations

**Output:** Final documentation review report with READY/NOT READY decision and specific approval criteria checklist.

---

## 4. E2E Test Executor Agent

**File:** `.claude/agents/e2e-test-executor.md`

**Type:** Specialized subagent

**Purpose:** Execute end-to-end tests using Playwright MCP, following test plans and capturing detailed results.

**Responsibilities:**
- Read and parse E2E test plans
- Navigate browser and interact with UI
- Monitor backend logs during tests
- Capture screenshots and snapshots
- Document failures with evidence

**Tools Used:**
- All Playwright MCP browser tools
- Bash for log analysis
- Read for test plans

**Output:** Structured test results with PASS/FAIL status, evidence (screenshots, logs), and failure analysis.

---

## 5. Bug Analyzer Agent

**File:** `.claude/agents/bug-analyzer.md`

**Type:** Specialized subagent

**Purpose:** Deep-dive analysis of test failures to identify root causes and assess impact.

**Responsibilities:**
- Parse test results and identify failures
- Extract and analyze backend logs
- Trace error flow from symptom to source
- Classify severity (CRITICAL/HIGH/MEDIUM/LOW)
- Assess user-facing impact

**Analysis Protocol:**
1. Gather evidence (logs, errors, traces)
2. Root cause analysis (follow error backward)
3. Impact classification (severity + user impact)

**Output:** Structured bug reports with:
- Severity classification
- Root cause with code location
- Impact assessment
- Reproduction steps
- Recommended fix approach

---

## 6. Validate MCP Integration Skill

**File:** `.claude/skills/validate-mcp-integration/SKILL.md`

**Type:** Task skill

**Purpose:** Validate both internal (brs-admin) and external (playwright) MCP servers are properly integrated in frontend.

**Workflow:**
1. Check frontend MCP configuration
2. Verify server processes running
3. Test tool discovery via API
4. Execute sample tool calls
5. Validate error handling

**Validates:**
- brs-admin MCP (run_sql, call_api, get_config)
- playwright MCP (browser tools)

**Usage:**
```
validate mcp integration
test mcp servers
check mcp connections
```

---

## 7. Query Club Members Skill

**File:** `.claude/skills/query-club-members/SKILL.md`

**Type:** Task skill

**Purpose:** Search and display club members from BRS database with flexible filters.

**Features:**
- Search by club name or ID
- Filter by name, email, usergroup
- Returns formatted table
- Handles partial matches

**Workflow:**
1. Parse query for club identifier and filters
2. Query database for club ID
3. Build SQL query with filters
4. Execute run_sql tool
5. Format results in readable table

**Usage:**
```
find members in brsgolfclubsales
search for members with email @test.com
list members in club testclub1779893558
show club members where name contains John
```

---

## Integration Architecture

### Production Readiness Loop Flow

```
┌──────────────────────────────────────────────────────────────┐
│                    PROD-READINESS-LOOP                       │
│                    (Main Orchestrator)                       │
└────────────────┬─────────────────────────────────────────────┘
                 │
    ┌────────────┼────────────┬──────────────┬─────────────┐
    ▼            ▼            ▼              ▼             ▼
┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│  E2E    │ │   BUG    │ │   PLAN   │ │IMPLEMENT │ │CODE      │
│  TEST   │ │ ANALYZER │ │  WRITER  │ │ (parallel│ │REVIEWER  │
│EXECUTOR │ │          │ │          │ │)         │ │          │
└─────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
     │            │            │             │            │
     ▼            ▼            ▼             ▼            ▼
┌──────────────────────────────────────────────────────────────┐
│  TEST RESULTS → BUG REPORTS → FIX PLANS → CODE CHANGES →    │
│                     CODE REVIEW → DOCUMENTATION              │
└────────────────────────────┬─────────────────────────────────┘
                             ▼
                    ┌────────────────┐
                    │ DOCUMENTATION  │
                    │    WRITER      │
                    └────────┬───────┘
                             ▼
                    ┌────────────────┐
                    │   FINAL DOC    │
                    │    REVIEWER    │
                    └────────┬───────┘
                             ▼
                    ┌────────────────┐
                    │  PROD READY?   │
                    │  YES → STOP    │
                    │  NO  → LOOP    │
                    └────────────────┘
```

### MCP Server Integration

The system validates two MCP servers:

1. **Internal: brs-admin MCP**
   - Path: `/Users/206887576@bwt3.com/Documents/GitHub/mcp_servers/brs-admin_mcp_server`
   - Tools: run_sql, call_api, get_config
   - Purpose: Database queries and BRS API calls

2. **External: playwright MCP**
   - Connection: Remote MCP server
   - Tools: browser_navigate, browser_type, browser_snapshot, etc.
   - Purpose: E2E browser automation

### Skills Integration

The system includes two production skills:

1. **REINSTATE_USER** (existing)
   - Already in database
   - Should work via '\' (slash command)
   - Should work semantically (e.g., "reinstate user 98765432")
   - Currently has infinite loop bug (being fixed by prod-readiness-loop)

2. **QUERY_CLUB_MEMBERS** (new)
   - Created for this system
   - Provides useful query functionality
   - Tests skill matching and execution
   - Example: "find members in brsgolfclubsales"

---

## Usage Instructions

### Starting the Production Readiness Loop

```bash
# In Claude Code chat:
make this prod ready

# Or be more specific:
test until production ready using e2e-test-plan.md

# With options:
continuous qa loop with max 5 iterations
```

### What the Loop Does

**Iteration 1:**
1. Runs all E2E tests from test plan
2. Finds bugs (e.g., REINSTATE_USER infinite loop)
3. Creates detailed bug report
4. Generates fix plan
5. Implements fixes
6. Reviews changes
7. Re-tests

**Iteration 2+:**
- Verifies previous fixes work
- Runs remaining tests
- Finds any new bugs
- Repeats fix cycle
- Updates documentation after each iteration

**Documentation Phase (After Each Iteration):**
- documentation-writer updates:
  - PROD_READINESS_HANDOVER.md with iteration results
  - E2E_TEST_RESULTS.md with test data
  - BUG_*.md files (create new, update existing)
  - SKILLS_CREATED.md with skill validation

**Final Validation:**
- Tests MCP server integration
- Validates REINSTATE_USER skill
- Validates QUERY_CLUB_MEMBERS skill
- Confirms all critical tests pass
- final-doc-reviewer validates all documentation
- Produces final production readiness report

### Expected Outcome

After loop completes:
- ✅ All critical E2E tests passing
- ✅ State machine works correctly
- ✅ No infinite loops
- ✅ MCP servers integrated
- ✅ Skills functional (slash + semantic)
- ✅ System marked PROD_READY

---

## Files Structure

```
.claude/
├── skills/
│   ├── prod-readiness-loop/
│   │   └── SKILL.md                    (Main orchestrator)
│   ├── validate-mcp-integration/
│   │   └── SKILL.md                    (MCP validation)
│   └── query-club-members/
│       └── SKILL.md                    (New production skill)
└── agents/
    ├── e2e-test-executor.md            (Test execution)
    ├── bug-analyzer.md                 (Failure analysis)
    ├── documentation-writer.md         (Doc updates)
    └── final-doc-reviewer.md           (Doc validation)
```

---

## Testing the Skills

### Test prod-readiness-loop:
```
make this prod ready
```

### Test validate-mcp-integration:
```
validate mcp integration
```

### Test query-club-members:
```
find members in brsgolfclubsales
search for members with username test
list members where email contains @example.com
```

---

## Next Steps

1. **Seed query-club-members skill into database**
   ```bash
   cd backend
   python scripts/seed_skill.py query-club-members
   ```

2. **Run the production readiness loop**
   ```
   make this prod ready
   ```

3. **Monitor progress**
   - Loop will report after each iteration
   - Bug reports saved to `backend/BUG_*.md`
   - Fix plans saved to `docs/superpowers/plans/fix-*.md`
   - Iteration results in `docs/PROD_READINESS_HANDOVER.md`
   - Test results in `backend/E2E_TEST_RESULTS.md`
   - Final status in `backend/PROD_READINESS_REPORT.md`

4. **Documentation tracking**
   - After each iteration, documentation-writer updates all docs
   - Bugs tracked from discovery → fix → verification
   - Test results archived per iteration
   - Before final approval, final-doc-reviewer validates docs

---

## Success Criteria

System is production ready when:
- ✅ 100% of critical E2E tests pass
- ✅ No infinite loops or stuck states
- ✅ State machine transitions work
- ✅ HTTP method validation enforced
- ✅ brs-admin MCP fully functional
- ✅ playwright MCP fully functional
- ✅ REINSTATE_USER skill works (slash + semantic)
- ✅ QUERY_CLUB_MEMBERS skill works (slash + semantic)
- ✅ Error handling graceful
- ✅ No false completion reports
- ✅ Documentation complete and accurate
- ✅ All bugs traceable (test → bug → fix → verification)
- ✅ Status claims verified (no false COMPLETE)

When all criteria met: **SHIP TO PRODUCTION** 🚀

---

## Documentation Standards

All documentation must follow these standards (enforced by final-doc-reviewer):

### Traceability Chain
Every bug must have:
1. Test failure that discovered it
2. Bug report with root cause analysis
3. Fix plan with implementation tasks
4. Code changes with file paths
5. Verification test results

### Status Accuracy
- "COMPLETE" only when ALL critical tests pass
- "FIXED" only when verification tests pass
- "IN_PROGRESS" when work remains
- "BLOCKED" when stuck on external dependency

### Evidence Requirements
- Screenshots for UI failures
- Log excerpts for backend errors
- Git commits for code changes
- Test results for verification

### Update Frequency
- After every iteration (not just at the end)
- When bugs discovered
- When fixes applied
- When tests re-run
