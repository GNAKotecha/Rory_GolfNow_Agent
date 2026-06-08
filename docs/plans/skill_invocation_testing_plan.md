# Skill Invocation Testing & Debugging Plan

**Date:** 2026-06-08  
**Objective:** Verify skill invocation works end-to-end and fix semantic detection

---

## Current Status (from SKILL_INVOCATION_HANDOFF.md)

**Working ✅:**
- Slash commands UI (type "/" shows skills)
- Gateway MCP (25 tools accessible)
- Database schema and seeded REINSTATE_USER skill
- Frontend dropdown with keyboard navigation

**Not Working ❌:**
- Semantic detection: "I need to reinstate a deleted user" doesn't trigger skill
- Agent skips skill detection, gives generic response

---

## Phase 1: Verify Current Implementation

### Task 1.1: Confirm Skill Data in Database
**Goal:** Verify REINSTATE_USER skill exists with correct intent patterns

**Actions:**
- [ ] Query database for skill ID 2
- [ ] Verify `intent_patterns` JSON field contains regex patterns
- [ ] Confirm tenant_id = 1, is_active = true

**Expected Result:**
```json
{
  "id": 2,
  "skill_name": "REINSTATE_USER",
  "intent_patterns": [
    "reinstate.*user",
    "restore.*user.*account",
    "reactivate.*member"
  ],
  "tenant_id": 1,
  "is_active": true
}
```

---

### Task 1.2: Test Skill Discovery Service in Isolation
**Goal:** Verify pattern matching logic works

**Actions:**
- [ ] Call `SkillDiscoveryService.match_skill_by_intent()` with test message
- [ ] Test message: "I need to reinstate a deleted user"
- [ ] Verify it returns REINSTATE_USER skill

**Test Script:**
```python
from app.services.skill_discovery import SkillDiscoveryService
from app.core.database import get_db

service = SkillDiscoveryService(next(get_db()))
result = service.match_skill_by_intent("I need to reinstate a deleted user", tenant_id=1)
print(f"Matched skill: {result}")  # Should print REINSTATE_USER
```

**Acceptance:** Returns skill object, not None

---

### Task 1.3: Verify Agent Loads Skills Context
**Goal:** Confirm agent initialization loads skills

**Actions:**
- [ ] Add logging to `AgenticService._load_skills_context()` 
- [ ] Trigger agent initialization (send any message)
- [ ] Check logs for "Loaded N skills for tenant_id=1"
- [ ] Verify `self.skills_context` is not empty

**Expected Log:**
```
INFO: Loaded 1 skills for tenant_id=1
DEBUG: Skills context: [{'id': 2, 'skill_name': 'REINSTATE_USER', ...}]
```

**Acceptance:** Skills context populated at agent init

---

### Task 1.4: Trace Skill Detection Flow
**Goal:** Confirm `_check_skill_match()` is called during message processing

**Actions:**
- [ ] Add debug logging at line ~400 in `agentic_service.py`
- [ ] Log: entry to `_check_skill_match()`, user message, match result
- [ ] Send test message: "I need to reinstate a deleted user"
- [ ] Check logs for skill match attempt

**Expected Log:**
```
DEBUG: Checking skill match for message: "I need to reinstate a deleted user"
DEBUG: Skill match found: REINSTATE_USER (id=2)
INFO: Auto-invoking skill: REINSTATE_USER
```

**Acceptance:** Logs show skill detection runs and matches

---

## Phase 2: Debug Semantic Detection Issue

### Task 2.1: Fix Missing Skill Detection Call
**Hypothesis:** `_check_skill_match()` exists but isn't invoked

**Actions:**
- [ ] Review `AgenticService._execute_internal()` flow
- [ ] Verify skill check happens BEFORE agent prompt construction
- [ ] Ensure check runs for all user messages (not just certain types)

**Fix Pattern:**
```python
async def _execute_internal(self, message: str, ...):
    # BEFORE constructing agent prompt:
    matched_skill = await self._check_skill_match(message)
    if matched_skill:
        return await self._invoke_skill(matched_skill)
    
    # THEN proceed with normal agent flow
    agent_prompt = self._build_prompt(message)
    ...
```

**Acceptance:** Skill check runs before agent invocation

---

### Task 2.2: Fix Regex Pattern Matching
**Hypothesis:** Patterns don't match due to case sensitivity or regex flags

**Actions:**
- [ ] Review `SkillDiscoveryService.match_skill_by_intent()` implementation
- [ ] Ensure case-insensitive matching (`re.IGNORECASE`)
- [ ] Test patterns against example messages
- [ ] Add pattern compilation caching if missing

**Fix Pattern:**
```python
def match_skill_by_intent(self, message: str, tenant_id: int):
    skills = self.skill_repo.get_active_skills(tenant_id)
    for skill in skills:
        for pattern in skill.intent_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return skill
    return None
```

**Acceptance:** Pattern matching works case-insensitively

---

### Task 2.3: Fix Skills Context Loading
**Hypothesis:** Skills not loaded at agent initialization

**Actions:**
- [ ] Verify `_load_skills_context()` is called in `__init__` or before first message
- [ ] Check if context is lost between requests (session issue)
- [ ] Ensure tenant_id is correctly passed to discovery service

**Fix Pattern:**
```python
class AgenticService:
    def __init__(self, tenant_id: int, ...):
        self.tenant_id = tenant_id
        self.skills_context = []
        await self._load_skills_context()  # Load at init
    
    async def _load_skills_context(self):
        discovery = SkillDiscoveryService(self.db)
        self.skills_context = discovery.get_skills(self.tenant_id)
```

**Acceptance:** Skills loaded and persist across messages

---

## Phase 3: End-to-End Testing via Playwright MCP

### Task 3.1: Test Slash Command Flow (Baseline)
**Goal:** Confirm slash commands still work (already working)

**Playwright Actions:**
- [ ] Navigate to `http://localhost:3000/chat`
- [ ] Login as `admin@test.com` / `password`
- [ ] Click chat input field
- [ ] Type `/`
- [ ] Verify dropdown appears with "Reinstate User"
- [ ] Press ArrowDown then Enter
- [ ] Verify skill execution starts
- [ ] Verify response mentions skill result

**Expected Result:** Skill executes via slash command

**Playwright Script:**
```javascript
await page.goto('http://localhost:3000/chat');
await page.fill('input[type="email"]', 'admin@test.com');
await page.fill('input[type="password"]', 'password');
await page.click('button[type="submit"]');

await page.waitForSelector('[data-testid="chat-input"]');
await page.fill('[data-testid="chat-input"]', '/');
await page.waitForSelector('[data-testid="skill-dropdown"]');

const skills = await page.$$('[data-testid="skill-option"]');
console.log(`Found ${skills.length} skills in dropdown`);

await page.keyboard.press('ArrowDown');
await page.keyboard.press('Enter');
await page.waitForSelector('[data-testid="message"]');

const response = await page.textContent('[data-testid="message"]:last-child');
console.log(`Response: ${response}`);
```

---

### Task 3.2: Test Semantic Detection (Primary Goal)
**Goal:** Verify natural language triggers skill automatically

**Playwright Actions:**
- [ ] Navigate to `http://localhost:3000/chat`
- [ ] Login as `admin@test.com` / `password`
- [ ] Type: "I need to reinstate a deleted user"
- [ ] Submit message
- [ ] Wait for response
- [ ] Verify response contains skill execution result (not generic answer)

**Expected Indicators:**
- Response mentions "REINSTATE_USER skill"
- Response contains specific skill output (user ID, status change)
- Response does NOT say "I can help you with that" (generic)

**Playwright Script:**
```javascript
await page.goto('http://localhost:3000/chat');
// Login...

await page.fill('[data-testid="chat-input"]', 'I need to reinstate a deleted user');
await page.click('[data-testid="send-button"]');
await page.waitForSelector('[data-testid="message"]:last-child');

const response = await page.textContent('[data-testid="message"]:last-child');
console.log(`Response: ${response}`);

// Check for skill execution indicators
const hasSkillResult = response.includes('REINSTATE_USER') || 
                      response.includes('User reinstated') ||
                      response.includes('skill executed');

console.log(`Skill detected: ${hasSkillResult}`);
```

**Acceptance Criteria:**
- Skill automatically invoked
- Response contains skill-specific output
- No generic "I can help" response

---

### Task 3.3: Test Multiple Intent Patterns
**Goal:** Verify all intent patterns trigger skill

**Test Messages:**
- [ ] "I need to reinstate a deleted user"
- [ ] "Can you restore a user account?"
- [ ] "Reactivate a member please"
- [ ] "Bring back a disabled user"

**Playwright Script:**
```javascript
const testMessages = [
  "I need to reinstate a deleted user",
  "Can you restore a user account?",
  "Reactivate a member please",
  "Bring back a disabled user"
];

for (const msg of testMessages) {
  await page.fill('[data-testid="chat-input"]', msg);
  await page.click('[data-testid="send-button"]');
  await page.waitForSelector('[data-testid="message"]:last-child');
  
  const response = await page.textContent('[data-testid="message"]:last-child');
  const matched = response.includes('REINSTATE_USER') || 
                 response.includes('skill executed');
  
  console.log(`"${msg}" -> Skill matched: ${matched}`);
}
```

**Acceptance:** All patterns trigger skill invocation

---

### Task 3.4: Test Negative Cases
**Goal:** Verify non-matching messages don't trigger skill

**Test Messages:**
- [ ] "What's the weather today?"
- [ ] "List all users"
- [ ] "Create a new booking"

**Expected:** Generic agent response, NO skill invocation

**Acceptance:** Only matching patterns trigger skill

---

## Phase 4: Performance & Edge Cases

### Task 4.1: Test Skill Not Found Gracefully
**Goal:** Agent handles missing skill gracefully

**Actions:**
- [ ] Temporarily disable REINSTATE_USER skill (set is_active=false)
- [ ] Send matching message
- [ ] Verify agent responds generically (no crash)

**Acceptance:** No errors, graceful fallback

---

### Task 4.2: Test Multiple Skills
**Goal:** Agent selects correct skill when multiple exist

**Actions:**
- [ ] Add second skill (e.g., "CREATE_BOOKING") with different patterns
- [ ] Send message matching REINSTATE_USER
- [ ] Send message matching CREATE_BOOKING
- [ ] Verify correct skill invoked each time

**Acceptance:** Correct skill selected based on intent

---

### Task 4.3: Test Concurrent Skill Invocations
**Goal:** System handles multiple users invoking skills

**Actions:**
- [ ] Use Playwright to open 2 browser contexts
- [ ] Login as different users (admin@test.com, user@test.com)
- [ ] Send skill-triggering messages simultaneously
- [ ] Verify both execute correctly without interference

**Acceptance:** No race conditions or cross-user contamination

---

## Phase 5: Logging & Observability

### Task 5.1: Add Comprehensive Logging
**Goal:** Make skill invocation traceable

**Log Points:**
- [ ] Agent init: "Loaded N skills"
- [ ] Message received: "Checking skill match for: {message}"
- [ ] Match found: "Matched skill: {skill_name}"
- [ ] Invocation start: "Invoking skill {skill_name}"
- [ ] Invocation complete: "Skill {skill_name} executed in {duration}ms"

**Acceptance:** Full skill flow visible in logs

---

### Task 5.2: Add Metrics
**Goal:** Track skill invocation rates

**Metrics:**
- [ ] skill_invocations_total (counter by skill_name)
- [ ] skill_execution_duration (histogram)
- [ ] skill_match_attempts (counter)

**Acceptance:** Prometheus metrics exposed

---

## Success Criteria

### Must Pass:
1. ✅ Database contains REINSTATE_USER skill with correct patterns
2. ✅ `SkillDiscoveryService.match_skill_by_intent()` returns skill for test message
3. ✅ Agent loads skills context at initialization
4. ✅ `_check_skill_match()` is called for user messages
5. ✅ Playwright test: Natural language "reinstate deleted user" triggers skill
6. ✅ Slash command flow still works

### Nice to Have:
- ✅ All intent patterns tested
- ✅ Negative cases verified
- ✅ Logging comprehensive
- ✅ Metrics exposed

---

## Risk Mitigation

**Risk:** Breaking existing slash command functionality  
**Mitigation:** Test slash commands FIRST as baseline before debugging semantic detection

**Risk:** Database queries slow down agent initialization  
**Mitigation:** Cache skills context, refresh periodically

**Risk:** Regex patterns too broad, trigger incorrectly  
**Mitigation:** Test negative cases thoroughly

---

## Execution Order

1. **Phase 1 (Verify)** - Confirm current state, no code changes
2. **Phase 2 (Debug)** - Fix semantic detection issue
3. **Phase 3 (Test E2E)** - Playwright tests to validate
4. **Phase 4 (Edge Cases)** - Harden against failures
5. **Phase 5 (Observability)** - Production readiness

**Estimated Time:** 4-6 hours
