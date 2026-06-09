# Bug #11: LLM Request Timeout in REINSTATE_USER Workflow

**Status:** 🔴 OPEN  
**Severity:** P0 - Critical (Blocks Production)  
**Discovered:** 2026-06-08 23:30 UTC  
**Reporter:** Production Readiness Loop (Iteration 1)  
**Component:** `app.services.ollama`  
**Affects:** All skill-based workflows (REINSTATE_USER confirmed)

---

## Summary

REINSTATE_USER skill execution fails with "LLM request timed out" error after 60 seconds. This prevents the workflow from executing any tools or progressing through states, making the core workflow completely unusable.

---

## Impact

### User Impact
- ✅ Simple chat works (tool listing, questions)
- ✅ Multi-turn conversations work
- ✅ Database queries work
- ❌ **REINSTATE_USER skill completely broken**
- ⚠️ All complex workflows likely affected

### Production Readiness
- **Deployment:** BLOCKED (critical workflow unusable)
- **Bug #10 Validation:** BLOCKED (cannot test HTTP method validation)
- **E2E Testing:** BLOCKED (Phase 4, 5, 6 cannot proceed)

---

## Reproduction Steps

1. **Setup:**
   - Backend running at localhost:8000
   - Frontend at localhost:3000/chat
   - User logged in as admin

2. **Execute:**
   ```
   User message: "Reinstate user 98765432"
   ```

3. **Observe:**
   - Skill matches correctly
   - Workflow starts (iteration 1/10, state=initial)
   - After 60 seconds: timeout error
   - UI shows: "❌ Skill execution failed: Reinstate User"

4. **Expected:**
   - Workflow should execute tools (run_sql, call_api)
   - State should transition (initial → after_read → after_write → complete)
   - Workflow should complete within 60 seconds OR have configurable timeout

---

## Evidence

### Backend Log
```
2026-06-08 23:30:04,266 - app.services.agentic_service - INFO - ✅ Skill matched: Reinstate User (id=2)
2026-06-08 23:30:04,266 - app.services.agentic_service - INFO - Skill execution with 23 available tools
2026-06-08 23:30:04,266 - app.services.agentic_service - INFO - 🚀 Starting skill execution: Reinstate User (isolated context)
2026-06-08 23:30:04,266 - app.services.agentic_service - INFO - Skill execution iteration 1/10, workflow_state=initial
2026-06-08 23:31:04,270 - app.services.agentic_service - ERROR - Error in skill execution loop: LLM request timed out
Traceback (most recent call last):
  ...
  raise OllamaError("LLM request timed out")
app.services.ollama.OllamaError: LLM request timed out
2026-06-08 23:31:04,282 - app.services.agentic_service - INFO - ✅ Skill execution completed: Reinstate User
2026-06-08 23:31:04,282 - app.services.agentic_service - INFO - Skill 'Reinstate User' matched and executed
2026-06-08 23:31:04,287 - app.api.chat - INFO - Agentic workflow completed for session 175
```

### Frontend UI Error
```
❌ Skill execution failed: Reinstate User
Skill execution error: LLM request timed out
```

### What Didn't Happen (Expected)
```
# No tool calls logged:
✗ Calling tool: run_sql
✗ Calling tool: call_api

# No state transitions logged:
✗ 📖 State transition: initial → after_read
✗ ✏️ State transition: after_read → after_write
✗ ✅ State transition: after_write → complete

# No HTTP method validation logged:
✗ 🔒 Restricted call_api to write methods only
✗ ❌ Invalid method 'GET' in after_read state
```

---

## Root Cause Analysis

### Hypothesis 1: LLM Endpoint Slow/Unreachable
**Evidence:**
- Timeout occurs at exactly 60 seconds (suggests hard timeout)
- No tool calls executed (LLM never responded)
- Simple chat works (suggests endpoint reachable for simple requests)

**Likely Cause:**
- LLM endpoint overloaded or slow for complex skill prompts
- Network latency not accounted for
- REINSTATE_USER skill prompt too large for 60s timeout

### Hypothesis 2: Timeout Threshold Too Aggressive
**Evidence:**
- Simple chat: ~4 seconds (PASS)
- Database query: ~3 seconds (PASS)
- Skill execution: >60 seconds (FAIL)

**Likely Cause:**
- 60-second timeout appropriate for simple requests
- Complex workflows need 120-180 seconds
- No per-skill timeout configuration

### Hypothesis 3: Missing Retry Logic
**Evidence:**
- Single timeout error raised, no retry attempts logged
- No fallback or recovery mechanism

**Likely Cause:**
- OllamaError raised immediately on timeout
- No exponential backoff retry implemented

---

## Proposed Solutions

### Solution 1: Increase Timeout Threshold (Quick Fix)
**Priority:** 🔴 P0 - Immediate  
**Effort:** 1 hour  
**Risk:** Low

**Implementation:**
```python
# In app/services/ollama.py
class OllamaService:
    def __init__(self):
        self.timeout = 180  # Increase from 60 to 180 seconds
```

**Pros:**
- Simple change, low risk
- Allows more time for complex workflows

**Cons:**
- Doesn't address underlying latency issue
- User still waits 3 minutes on actual timeout

### Solution 2: Add Retry Logic with Exponential Backoff (Robust Fix)
**Priority:** 🟡 P1 - High  
**Effort:** 2-3 hours  
**Risk:** Medium

**Implementation:**
```python
# In app/services/ollama.py
async def call_llm_with_retry(self, prompt, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await self.call_llm(prompt)
        except OllamaError as e:
            if "timeout" in str(e) and attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                await asyncio.sleep(wait_time)
                continue
            raise
```

**Pros:**
- Handles transient failures
- Exponential backoff prevents overwhelming endpoint
- Resilient to network issues

**Cons:**
- More complex implementation
- Longer total wait time on repeated failures

### Solution 3: Per-Skill Timeout Configuration (Best Long-Term)
**Priority:** 🟢 P2 - Medium  
**Effort:** 2-3 hours  
**Risk:** Low

**Implementation:**
```python
# In app/models/skill.py
class Skill(BaseModel):
    timeout_seconds: Optional[int] = 60  # Default 60s
    
# In skills/reinstate_user.yaml
timeout_seconds: 180  # Override for complex workflow
```

**Pros:**
- Flexible per-skill configuration
- Simple skills stay fast (60s)
- Complex workflows get more time (180s)

**Cons:**
- Requires skill definition updates
- More configuration to maintain

### Solution 4: Add LLM Health Check (Proactive)
**Priority:** 🟢 P2 - Medium  
**Effort:** 1-2 hours  
**Risk:** Low

**Implementation:**
```python
# In app/services/agentic_service.py
async def execute_skill(self, skill):
    # Check LLM health before skill execution
    if not await self.check_llm_health():
        raise LLMUnavailableError("LLM endpoint unreachable")
    
    # Proceed with skill execution
    ...
```

**Pros:**
- Fail fast if LLM down
- Better user experience (immediate error vs 60s wait)
- Can show LLM status in UI

**Cons:**
- Adds latency to every skill execution
- False positives if health check too strict

---

## Recommended Fix Plan

### Phase 1: Immediate Mitigation (Today)
1. **Increase timeout to 180 seconds** (Solution 1)
2. **Re-test REINSTATE_USER workflow**
3. **Document results in E2E_TEST_RESULTS.md**

**Estimated Time:** 1-2 hours  
**Risk:** Low  
**Success Criteria:** REINSTATE_USER completes without timeout

### Phase 2: Robust Solution (This Week)
1. **Implement retry logic** (Solution 2)
2. **Add per-skill timeout configuration** (Solution 3)
3. **Update REINSTATE_USER skill timeout to 180s**
4. **Re-test all workflows**

**Estimated Time:** 4-6 hours  
**Risk:** Medium  
**Success Criteria:** All workflows handle transient failures, no false timeouts

### Phase 3: Proactive Monitoring (Next Sprint)
1. **Add LLM health check** (Solution 4)
2. **Dashboard widget for LLM response time**
3. **Alert on sustained high latency**

**Estimated Time:** 2-3 hours  
**Risk:** Low  
**Success Criteria:** LLM issues detected proactively

---

## Files to Change

### Priority 1 (Immediate)
- `backend/app/services/ollama.py` - Increase timeout from 60s to 180s
- `backend/tests/test_ollama.py` - Update test timeout expectations

### Priority 2 (Robust Fix)
- `backend/app/services/ollama.py` - Add retry logic
- `backend/app/models/skill.py` - Add timeout_seconds field
- `backend/skills/reinstate_user.yaml` - Set timeout_seconds: 180

### Priority 3 (Monitoring)
- `backend/app/services/agentic_service.py` - Add LLM health check
- `backend/app/api/health.py` - Expose LLM status endpoint

---

## Testing Checklist

### After Fix Applied
- [ ] REINSTATE_USER workflow completes without timeout
- [ ] Workflow executes expected tools (run_sql, call_api)
- [ ] State transitions logged correctly
- [ ] HTTP method validation enforced (Bug #10)
- [ ] Workflow completes within new timeout (180s)
- [ ] No infinite loops
- [ ] Error handling graceful on actual timeout
- [ ] Retry logic works (if implemented)
- [ ] LLM health check works (if implemented)

### Regression Tests
- [ ] Simple chat still works (~4s)
- [ ] Multi-turn context still works (~3s)
- [ ] Database queries still work (~3s)
- [ ] Tool listing still works (~4s)

---

## Related Issues

- **Bug #10:** HTTP method validation fix - INCONCLUSIVE (blocked by this bug)
- **Production Readiness:** BLOCKED (cannot validate core workflow)
- **E2E Testing:** BLOCKED (Phase 4, 5, 6 cannot proceed)

---

## Status Updates

### 2026-06-08 23:30 UTC - Bug Discovered
- **Who:** Production Readiness Loop (Iteration 1)
- **What:** REINSTATE_USER workflow timeout discovered during E2E testing
- **Impact:** Critical blocker for production deployment
- **Next:** Investigate LLM endpoint, increase timeout, re-test

---

## Notes

- Simple chat and tool queries work reliably (3-4 second response times)
- Timeout appears to be hard 60-second limit in ollama.py
- No tool calls executed before timeout (LLM never responded)
- REINSTATE_USER skill has complex prompt with 23 tools + workflow state
- Bug #10 validation blocked until this is fixed

---

## References

- **Test Results:** `docs/E2E_TEST_RESULTS.md`
- **Handover Doc:** `backend/PHASE_5_HANDOVER.md`
- **Iteration Summary:** `docs/PROD_READINESS_ITERATION_1.md`
- **LLM Endpoint:** https://golfnow-keystone.vdpv.ai/v1/chat/completions
