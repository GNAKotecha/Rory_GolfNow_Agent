# Plan: Production-Ready E2E Testing Suite

## Context

Bug #10 (HTTP method selection) is now resolved with runtime validation. Before declaring the system production-ready, we need comprehensive end-to-end tests that stress-test the entire stack through the **frontend UI** using Playwright MCP.

**Why this testing approach:**
- Validates the full user journey (UI → API → LLM → MCP → Database)
- Tests real browser interactions, not just API calls
- Catches frontend/backend integration issues
- Validates skill execution, MCP tools, and workflow state machines
- Proves the HTTP method fix works in production scenarios

**Current State:**
- Backend has pytest infrastructure (`tests/conftest.py`, `pytest.ini`)
- Backend has async test fixtures and DeepEval markers
- **No frontend E2E tests exist**
- No comprehensive stress tests or edge case coverage
- User already has Playwright MCP browser running and logged in at localhost:3000

**Goal:**
Create a comprehensive E2E test suite executed via Playwright MCP that validates production readiness across:
1. General chat interactions
2. Multi-turn conversations with context
3. Error handling and recovery
4. MCP tool creation and usage
5. Skill creation and execution
6. Workflow state machine correctness (especially REINSTATE_USER)

---

## Test Strategy

### Test Execution Method
**Use Playwright MCP tools directly** (not writing test files) to:
1. Navigate browser to localhost:3000/chat
2. Send messages via chat input
3. Verify responses appear
4. Check backend logs for expected behavior
5. Query database for expected state changes
6. AT THE END of each test close the playwright browser

**Why not write test files:**
- User wants immediate validation
- Playwright MCP is already running and authenticated
- Can iterate quickly with real browser
- Covers the exact user flow
- Backend logs provide detailed validation

### Test Categories

#### 1. **Baseline Functionality Tests**
Verify system handles normal operations:
- Simple question-answer flow
- Multi-turn conversation with context retention
- Request for tool list
- Request for skill list

#### 2. **Error Handling Tests**
Verify graceful degradation:
- Invalid skill invocation
- MCP tool errors (network timeout, invalid params)
- Database connection failures (simulated via query errors)
- LLM timeout/rate limiting
- Malformed user input

#### 3. **MCP Tool Tests**
Validate BRS tool integration:
- Query existing data (run_sql on users)
- Read configuration (get_config)
- API calls (call_api to BRS endpoints)
- Tool parameter validation
- Tool error recovery

#### 4. **Skill Execution Tests**
Validate skill orchestration:
- Simple skill execution (e.g., "list tools")
- Complex workflow skill (REINSTATE_USER)
- Skill with missing parameters
- Skill that fails mid-execution
- Multiple skills in conversation

#### 5. **Workflow State Machine Tests** (CRITICAL)
Validate Bug #10 fix and state progression:
- REINSTATE_USER workflow:
  - Verify GET rejection in after_read state
  - Verify LLM switches to POST/PATCH
  - Verify state transitions: initial → after_read → after_write → complete
  - Verify tool sequence: run_sql → call_api(POST) → run_sql
- Edge cases:
  - User doesn't exist (should fail gracefully)
  - User already exists (should detect conflict)
  - Database error during workflow

#### 6. **Stress Tests**
Validate system under load:
- Rapid message sending (10 messages in 10 seconds)
- Long conversation (20+ turns)
- Large response handling (tool returns 1000+ rows)
- Concurrent sessions (if possible via multiple browser tabs)
- Memory leak detection (repeat workflow 5x, check backend memory)

---

## Implementation Plan

### Phase 1: Setup and Baseline Tests (15-20 minutes)

**1.1 Browser Setup**
- Already done: Browser at localhost:3000/chat, user logged in
- Verify: Take snapshot, confirm chat interface visible

**1.2 Simple Message Flow Test**
```
Action: Send "Hello, what tools do you have?"
Expected Response: List of MCP tools (run_sql, call_api, get_config, etc.)
Verification: 
  - Response appears in UI within 10 seconds
  - Backend log shows tool list generated
  - No errors in browser console
```

**1.3 Multi-Turn Context Test**
```
Turn 1: "What's the name of the test club?"
Turn 2: "What's its club ID?"
Turn 3: "Can you query the database for users in that club?"

Verification:
  - LLM remembers context from previous turns
  - Uses club name/ID from earlier in conversation
  - Backend logs show correct SQL query with club filter
```

**1.4 Tool List Verification**
```
Action: Send "List all available tools"
Expected: LLM calls list_tools or describes available MCP tools
Verification:
  - Response includes run_sql, call_api, get_config, etc.
  - Backend log shows list_tools execution
```

### Phase 2: Error Handling Tests (10-15 minutes)

**2.1 Invalid SQL Query**
```
Action: "Run this SQL: SELECT * FROM nonexistent_table"
Expected: Error message explaining table doesn't exist
Verification:
  - LLM returns user-friendly error (not raw SQL error)
  - Backend logs show MCPToolResult with success=False
  - UI displays error gracefully (not crash)
```

**2.2 Invalid API Endpoint**
```
Action: "Call the BRS API endpoint /api/v3/fake/endpoint"
Expected: 404 error handled gracefully
Verification:
  - Error message explains endpoint not found
  - Suggests valid endpoints
  - Workflow doesn't crash or loop
```

**2.3 Malformed User Input**
```
Action: Send empty message or very long message (5000+ chars)
Expected: Validation error or truncation
Verification:
  - No backend crash
  - User-friendly error message
  - System remains responsive
```

**2.4 Network Timeout Simulation**
```
Action: (If possible) Disconnect from BRS API and send "Get club info"
Expected: Timeout error with retry suggestion
Verification:
  - Error message explains timeout
  - System doesn't hang indefinitely
  - Logs show timeout detection
```

### Phase 3: MCP Tool Integration Tests (15-20 minutes)

**3.1 run_sql Tool**
```
Action: "Query the database for all users with username containing 'test'"
Expected: SQL query executed, results returned
Verification:
  - Backend log shows: Calling tool: run_sql with query containing LIKE '%test%'
  - Response shows user records or "No results found"
  - No SQL injection (check query is parameterized)
```

**3.2 get_config Tool**
```
Action: "What's the BRS API base URL configured?"
Expected: Config value returned
Verification:
  - Backend log shows: Calling tool: get_config
  - Response shows localhost:8056 or similar
  - No sensitive secrets exposed (password/keys masked)
```

**3.3 call_api Tool (GET)**
```
Action: "Get the list of clubs from BRS"
Expected: API call executed, club list returned
Verification:
  - Backend log shows: call_api with method='GET', path='/api/v3/clubs'
  - Response shows club names/IDs
  - Proper error handling if API down
```

**3.4 call_api Tool (POST) - Test HTTP Method Fix**
```
Action: "Create a test user in BRS" (if safe, otherwise skip)
Expected: POST request sent
Verification:
  - Backend log shows: call_api with method='POST'
  - NOT method='GET' (Bug #10 regression check)
  - Proper request body included
```

**3.5 Tool Parameter Validation**
```
Action: "Run SQL without specifying a query"
Expected: Error explaining missing required parameter
Verification:
  - Parameter validation triggered before tool execution
  - Clear error message about what's missing
  - No backend crash
```

### Phase 4: Skill Execution Tests (20-25 minutes)

**4.1 Simple Skill Invocation**
```
Action: Type "/" to trigger skill autocomplete
Expected: Skill list appears in UI
Verification:
  - UI shows available skills
  - Can select skill from list
  - Skill executes when selected
```

**4.2 REINSTATE_USER Skill (Happy Path)**
```
Action: "Reinstate user testuser123"
Expected: Skill executes workflow
Verification:
  - Backend log shows: ✅ Skill matched: Reinstate User
  - State transitions: initial → after_read → after_write → complete
  - Tool sequence: run_sql → call_api → run_sql
  - NO infinite loops
  - Completes within 30 seconds
```

**4.3 REINSTATE_USER Skill (HTTP Method Fix Validation) - CRITICAL**
```
Action: "Reinstate user 98765432"
Expected: GET method rejected, LLM switches to POST/PATCH
Verification Checklist:
  ✅ Backend log shows: 🔒 Restricted call_api to write methods only
  ✅ Backend log shows: ❌ Invalid method 'GET' in after_read state
  ✅ LLM retries with method='POST' or 'PATCH'
  ✅ State transition: after_read → after_write occurs
  ✅ Workflow completes successfully
  ❌ NO method='GET' calls after initial rejection
  ❌ NO infinite loops of run_sql
  
Backend log grep commands:
  tail -100 /tmp/backend.log | grep "🔒 Restricted"
  tail -100 /tmp/backend.log | grep "❌ Invalid method"
  tail -100 /tmp/backend.log | grep "Calling tool: call_api" | grep -oE "'method':\s*'[A-Z]+'"
```

**4.4 Skill with Missing Parameters**
```
Action: "Reinstate user" (no username provided)
Expected: Skill asks for missing parameter or fails gracefully
Verification:
  - LLM requests username
  - OR returns error: "Username required"
  - No backend crash
```

**4.5 Skill Execution Failure Recovery**
```
Action: "Reinstate user nonexistent123"
Expected: Skill detects user doesn't exist and reports error
Verification:
  - Backend log shows: run_sql returns empty result
  - Skill execution stops gracefully
  - User-friendly error message
  - System remains responsive for next message
```

### Phase 5: Workflow State Machine Deep Dive (15-20 minutes)

**5.1 State Transition Logging**
```
Action: Execute REINSTATE_USER skill
Verification in logs:
  Line 1: Skill execution iteration 1/10, workflow_state=initial
  Line 2: 📖 State transition: initial → after_read
  Line 3: Skill execution iteration 2/10, workflow_state=after_read
  Line 4: 🔒 Restricted call_api to write methods only
  Line 5: ❌ Invalid method 'GET' in after_read state (may appear 1-2x)
  Line 6: Calling tool: call_api with method='POST' (or PATCH)
  Line 7: ✏️ State transition: after_read → after_write
  Line 8: Skill execution iteration N/10, workflow_state=after_write
  Line 9: ✅ State transition: after_write → complete
  Line 10: ✅ Skill execution complete
```

**5.2 Tool Filtering Verification**
```
Action: Check which tools are available in each state
Verification:
  Initial state: All tools available (run_sql, get_config, call_api, etc.)
  After_read state: Only write tools (call_api, update_config, no run_sql/get_schema)
  After_write state: All tools available again
  Complete state: All tools available

Backend log check:
  grep "Filtered to write tools only" /tmp/backend.log
  grep "removed read-only tools" /tmp/backend.log
```

**5.3 HTTP Method Constraint Enforcement**
```
Action: Trigger workflow, watch for GET rejection
Verification:
  1. Schema modification logged: 🔒 Restricted call_api to write methods only: ['PATCH', 'POST', 'PUT', 'DELETE']
  2. GET attempt detected: ❌ Invalid method 'GET' in after_read state
  3. Error message instructs LLM: "You must use PATCH to rename the user..."
  4. LLM receives error in conversation context
  5. Next tool call uses POST or PATCH
  6. Workflow progresses (doesn't get stuck)
```

**5.4 Edge Case: Max Iterations**
```
Action: (Hard to trigger intentionally) Force workflow to hit max iterations
Expected: Workflow stops after 10 iterations, returns partial result
Verification:
  - Backend log shows: Skill execution iteration 10/10
  - Workflow returns error: "Max iterations reached"
  - System doesn't hang indefinitely
```

### Phase 6: Stress Tests (15-20 minutes)

**6.1 Rapid Message Sending**
```
Action: Send 10 messages rapidly (1 per second)
Messages: "Message 1", "Message 2", ... "Message 10"
Expected: All messages processed in order
Verification:
  - All 10 responses appear in UI
  - Responses are in correct order
  - No dropped messages
  - No backend crashes
  - Check backend memory: ps aux | grep uvicorn (RSS should not spike excessively)
```

**6.2 Long Conversation Test**
```
Action: Have 20+ turn conversation with context
Example flow:
  Turn 1-5: Ask about clubs
  Turn 6-10: Query users
  Turn 11-15: Discuss bookings
  Turn 16-20: Ask for summaries

Expected: Context maintained throughout
Verification:
  - LLM remembers details from early turns
  - Conversation doesn't hit memory limits
  - Response times remain consistent
  - Backend logs show conversation history growing
```

**6.3 Large Response Handling**
```
Action: "Query all users in the database" (if safe, limit to 100 rows)
Expected: Large result set handled gracefully
Verification:
  - Response appears within reasonable time (30 seconds)
  - UI doesn't freeze
  - Data displayed correctly (not truncated mid-record)
  - Backend logs show result processing
```

**6.4 Repeated Workflow Execution**
```
Action: Execute REINSTATE_USER skill 5 times in a row
Expected: All executions complete successfully
Verification:
  - All 5 workflows progress through states correctly
  - HTTP method validation works every time
  - No memory leaks (check backend RSS before/after)
  - No performance degradation (execution time consistent)
  
Check memory:
  ps aux | grep uvicorn | awk '{print $2, $6}' (PID and RSS)
```

**6.5 Concurrent Sessions (if possible)**
```
Action: Open 2 browser tabs, send messages in both
Expected: Sessions remain isolated
Verification:
  - Tab 1 messages don't appear in Tab 2
  - Backend logs show different session IDs
  - No session data leakage
```

---

## Test Execution Protocol

### Pre-Test Setup
```bash
# 1. Ensure backend is running
ps aux | grep uvicorn | grep -v grep || echo "Backend not running!"

# 2. Clear previous logs
> /tmp/backend.log

# 3. Verify Playwright browser connected
# (Already done - browser at localhost:3000/chat)

# 4. Start fresh session (optional)
# Click "New chat" in UI
```

### During Tests
**For each test:**
1. **Document starting state** (take browser snapshot)
2. **Execute action** (send message via Playwright)
3. **Wait for response** (10-30 seconds)
4. **Capture evidence:**
   - Browser snapshot showing response
   - Backend log excerpt
   - Database query result (if applicable)
5. **Verify against expected behavior**
6. **Log outcome** (Pass/Fail/Blocked)

### Log Analysis Commands
```bash
# General workflow execution
tail -200 /tmp/backend.log | grep -E "(Skill execution|State transition|Calling tool)"

# HTTP method validation (Bug #10)
tail -200 /tmp/backend.log | grep -E "(🔒 Restricted|❌ Invalid method|method.*GET|method.*POST)"

# Tool execution sequence
tail -200 /tmp/backend.log | grep "Calling tool:" | awk '{print $NF}'

# Error detection
tail -200 /tmp/backend.log | grep -i "error\|exception\|failed"

# Performance (execution time per iteration)
tail -200 /tmp/backend.log | grep "Skill execution iteration" | awk '{print $1, $2, $NF}'
```

### Test Result Tracking
Create a simple markdown checklist:

```markdown
## E2E Test Results (2026-06-08)

### Baseline Functionality
- [ ] Simple question-answer: ___________
- [ ] Multi-turn context: ___________
- [ ] Tool list request: ___________

### Error Handling
- [ ] Invalid SQL query: ___________
- [ ] Invalid API endpoint: ___________
- [ ] Malformed input: ___________

### MCP Tools
- [ ] run_sql execution: ___________
- [ ] get_config execution: ___________
- [ ] call_api GET: ___________
- [ ] call_api POST: ___________

### Skills
- [ ] REINSTATE_USER happy path: ___________
- [ ] HTTP method constraint (Bug #10): ___________
- [ ] Skill with missing params: ___________
- [ ] Skill failure recovery: ___________

### Workflow State Machine
- [ ] State transitions correct: ___________
- [ ] Tool filtering in after_read: ___________
- [ ] HTTP method validation: ___________

### Stress Tests
- [ ] Rapid messages (10 in 10s): ___________
- [ ] Long conversation (20+ turns): ___________
- [ ] Large response handling: ___________
- [ ] Repeated execution (5x): ___________
- [ ] Memory leak check: ___________

### Production Readiness
- [ ] All critical tests passed: ___________
- [ ] No blockers found: ___________
- [ ] Performance acceptable: ___________
- [ ] Ready for deployment: ___________
```

---

## Success Criteria

### Must Pass (Blockers)
1. ✅ REINSTATE_USER skill completes without infinite loops
2. ✅ HTTP method constraint enforced (GET rejected in after_read state)
3. ✅ State machine transitions correctly
4. ✅ Tool filtering works (no run_sql in after_read state)
5. ✅ Error handling doesn't crash system
6. ✅ Multi-turn conversations maintain context

### Should Pass (High Priority)
1. All MCP tools execute successfully
2. Skill parameter validation works
3. Large responses handled gracefully
4. No memory leaks after repeated execution
5. Rapid messages processed in order

### Nice to Have (Lower Priority)
1. Concurrent session isolation
2. Network timeout recovery
3. Performance under sustained load
4. Browser console has no errors

---

## Risk Mitigation

### Known Issues to Watch For
1. **User 98765432 doesn't exist in BRS** - Skill will fail at SQL query stage (expected)
   - Mitigation: Test with real user or mock the query result
2. **BRS API may be unstable** - API calls may timeout or fail
   - Mitigation: Test during stable periods, have retry logic
3. **Playwright browser may disconnect** - Long test runs may lose browser connection
   - Mitigation: Restart browser if needed, take checkpoints
4. **Backend may accumulate memory** - Long test runs may expose leaks
   - Mitigation: Monitor RSS, restart backend between test phases

### Rollback Plan
If tests reveal critical bugs:
1. Document issue in PHASE_5_HANDOVER.md
2. Create GitHub issue with reproduction steps
3. Revert problematic code if blocking
4. Re-run tests after fix

---

## Deliverables

### Test Execution Summary
```markdown
# E2E Test Execution Report

**Date:** 2026-06-08
**Tester:** Claude (via Playwright MCP)
**Environment:** localhost:3000 + localhost:8000
**Backend PID:** 46432
**Browser:** Chrome (Playwright MCP)

## Tests Executed: X/Y passed

### Critical Findings
- Bug #10 HTTP method fix: WORKING / BROKEN
- Workflow state machine: STABLE / UNSTABLE
- Error handling: ROBUST / FRAGILE

### Blockers
(List any blockers found)

### Recommendations
(Next steps for production readiness)
```

### Updated Handover Document
Add test results to `PHASE_5_HANDOVER.md`:
```markdown
## Production Readiness Testing (2026-06-08)

**Status:** ✅ PRODUCTION READY / ⚠️ ISSUES FOUND / ❌ BLOCKED

### Test Coverage
- Baseline functionality: X/Y passed
- Error handling: X/Y passed
- MCP tools: X/Y passed
- Skills: X/Y passed
- Workflow state machine: X/Y passed
- Stress tests: X/Y passed

### Critical Validations
- ✅ Bug #10 fix verified working
- ✅ No infinite loops detected
- ✅ HTTP method constraint enforced
- ✅ State machine stable

### Known Limitations
(List any limitations discovered)

### Next Steps
(Recommendations for deployment or further work)
```

---

## Timeline Estimate

**Total Time:** 90-120 minutes

- Phase 1 (Baseline): 15-20 min
- Phase 2 (Errors): 10-15 min
- Phase 3 (MCP Tools): 15-20 min
- Phase 4 (Skills): 20-25 min
- Phase 5 (State Machine): 15-20 min
- Phase 6 (Stress): 15-20 min
- Documentation: 10-15 min

Can be parallelized or broken into multiple sessions if needed.

---

## Notes

- All tests executed via Playwright MCP tools (browser_type, browser_snapshot, etc.)
- Backend logs are the source of truth for validation
- Database queries run via MCP run_sql tool for verification
- No test files written - all tests are interactive via browser
- Results documented in handover file for future reference
