# REINSTATE_USER Skill - Execution Blocker

**Date:** 2026-06-08  
**Status:** ⚠️ BLOCKED - LLM ignores skill execution instructions

---

## Summary

The REINSTATE_USER skill successfully matches via semantic intent patterns and injects execution instructions into the LLM conversation, but the LLM **ignores the instructions** and asks clarifying questions instead of executing the workflow.

---

## What Works ✅

### 1. Skill Matching
- ✅ Intent pattern matching works correctly
- ✅ `SkillDiscoveryService.match_skill_by_intent()` detects "reinstate user" requests
- ✅ `_check_skill_match()` method identifies the correct skill

### 2. Instruction Injection
- ✅ Skill instructions are built via `_build_skill_instructions()`
- ✅ Instructions are injected as system message: `messages.insert(-1, {...})`
- ✅ Logs confirm: "✅ Injected skill instructions for: Reinstate User"
- ✅ Instructions contain detailed workflow steps with MCP tool usage

### 3. Backend Infrastructure
- ✅ Backend restarts successfully after code changes
- ✅ Health check passes
- ✅ WebSocket connection established
- ✅ MCP tools available (run_sql, call_api, call_internal_api)

---

## The Problem ❌

### LLM Behavior
**Expected:** LLM reads skill instructions and immediately begins executing workflow steps using MCP tools

**Actual:** LLM asks clarifying questions like:
- "What should the password be for the reinstated testadmin account?"
- "Are there any other details you'd like to include (email, full name, role, etc.)?"

### Evidence
From backend logs:
```
2026-06-08 10:59:49,105 - app.services.agentic_service - INFO - ✅ Injected skill instructions for: Reinstate User
2026-06-08 10:59:49,105 - app.services.agentic_service - INFO - Starting agentic workflow
2026-06-08 10:59:52,065 - httpx - INFO - HTTP Request: POST https://golfnow-keystone.vdpv.ai/v1/chat/completions "HTTP/1.1 200 OK"
2026-06-08 10:59:52,065 - app.services.agentic_service - INFO - Agentic workflow completed
```

The workflow completes successfully (HTTP 200), but the LLM's response doesn't execute the skill - it asks questions.

---

## Root Cause Analysis

### Architecture Issue
The current implementation:
1. Injects skill instructions as an additional system message in the conversation
2. Returns `None` from `_check_skill_match()` to continue normal LLM flow
3. Lets the LLM decide how to respond

**Problem:** The LLM has autonomy to interpret the instructions as "guidance" rather than "mandatory execution"

### Why Directive Language Doesn't Help
Even with strong directive language in instructions:
- ⚠️ **CRITICAL**: You MUST execute this skill immediately
- ⚠️ Do NOT ask clarifying questions first
- 🚀 IMMEDIATE EXECUTION REQUIRED
- 🎯 START EXECUTION NOW

...the LLM still chooses to ask clarifying questions because:
1. The instructions are just ONE system message among many in the conversation
2. The LLM's base behavior is to be helpful and thorough (asking for clarification)
3. No mechanism enforces execution over questioning

---

## Attempted Fixes ⚙️

### Fix 1: Add Directive Language
**Status:** ❌ Failed  
**Approach:** Made skill instructions more forceful with warnings and emojis  
**Result:** LLM still asks clarifying questions

### Fix 2: Fixed AttributeError
**Status:** ✅ Successful  
**Approach:** Changed `self.messages.insert()` to `messages.insert()`  
**Result:** Instructions are now injected without errors  
**Impact:** Doesn't solve the core problem - LLM still ignores execution

### Fix 3: Improved Instruction Template
**Status:** ❌ Failed  
**Approach:** Added detailed step-by-step workflow with SQL/API examples  
**Result:** LLM sees the instructions but doesn't follow them  

---

## Possible Solutions 🔧

### Option 1: Force Execution Mode
**Approach:** Don't return `None` - instead, construct a specialized prompt that ONLY contains:
- The skill instructions
- The user's original message
- No other conversation history

**Implementation:**
```python
# In _check_skill_match():
skill_instructions = self._build_skill_instructions(matched_skill, execution_context)

# Create a minimal context with ONLY skill execution instructions
skill_execution_messages = [
    {"role": "system", "content": skill_instructions},
    {"role": "user", "content": last_user_message}
]

# Call LLM with this specialized context (bypass normal flow)
skill_result = await self.ollama.chat(
    messages=skill_execution_messages,
    tools=available_tools,
    stream=False
)

# Return the result as a completed skill execution
return {
    "success": True,
    "skill_name": matched_skill.skill_name,
    "message": skill_result["message"]["content"],
    "tool_calls": skill_result.get("tool_calls", [])
}
```

**Pros:**
- LLM has no conversation context to fall back on
- Instructions are the PRIMARY context
- Forces execution path

**Cons:**
- Loses conversation history (might need it for context)
- Requires handling tool calls within skill execution
- More complex error handling

### Option 2: Use Tool-Use-Only Mode
**Approach:** Configure LLM call to REQUIRE tool use (no text-only response allowed)

**Implementation:**
```python
skill_result = await self.ollama.chat(
    messages=skill_execution_messages,
    tools=available_tools,
    tool_choice="required",  # Force tool use
    stream=False
)
```

**Pros:**
- Guarantees LLM will call tools
- Simpler than Option 1

**Cons:**
- Not all Ollama models support tool_choice="required"
- Might need fallback handling

### Option 3: Pre-Execute Workflow Steps
**Approach:** Don't rely on LLM to execute - parse the skill_data and execute steps programmatically

**Implementation:**
```python
# In skill_data JSON:
{
  "workflow_steps": [
    {"type": "sql_query", "query": "SELECT ..."},
    {"type": "api_call", "method": "PATCH", "path": "..."},
    {"type": "sql_query", "query": "SELECT ..."}
  ]
}

# In _check_skill_match():
for step in skill_data["workflow_steps"]:
    if step["type"] == "sql_query":
        result = await self.mcp.call_tool("run_sql", {"query": step["query"]})
    elif step["type"] == "api_call":
        result = await self.mcp.call_tool("call_api", {...})
    # etc.
```

**Pros:**
- Deterministic execution
- No LLM decision-making involved
- Fast and reliable

**Cons:**
- Skills become rigid, hardcoded workflows
- Loses flexibility/intelligence of LLM-driven execution
- Requires complex workflow DSL in skill_data

### Option 4: Multi-Turn Forced Execution
**Approach:** Add a follow-up check - if LLM asks questions, inject a stronger system message forcing execution

**Implementation:**
```python
# After LLM response, check if it's asking questions
if is_asking_questions(llm_response):
    # Inject stronger directive
    messages.append({
        "role": "system",
        "content": "STOP. You MUST execute the workflow steps NOW. Do not ask ANY questions. Begin with Step 1 immediately."
    })
    # Re-call LLM
    result = await self.ollama.chat(messages=messages, tools=tools)
```

**Pros:**
- Preserves conversation context
- Corrects LLM behavior dynamically

**Cons:**
- Adds latency (2x LLM calls)
- Might still fail if LLM is stubborn
- Hacky solution

---

## Recommended Solution ✅

**Option 1: Force Execution Mode** is the cleanest solution because:
1. It removes ambiguity - the LLM has ONE job: execute the skill
2. Skills become true "function calls" with predictable behavior
3. Aligns with the original intent: "skills are instructions to execute workflows"

**Implementation Plan:**
1. Modify `_check_skill_match()` to call LLM with isolated skill context
2. Handle tool calls within skill execution loop
3. Return skill result directly (don't continue to normal flow)
4. Add error handling for tool call failures

---

## Testing Checklist

Once solution is implemented:
- [ ] Skill matches user intent
- [ ] Skill instructions are built correctly
- [ ] LLM receives ONLY skill context (no conversation history)
- [ ] LLM calls `run_sql` tool to query user details
- [ ] LLM calls `call_api` tool to rename user (add _deleted suffix)
- [ ] LLM calls `call_api` tool to create new user
- [ ] LLM verifies restoration with `run_sql`
- [ ] Skill returns success with user details
- [ ] Frontend displays skill execution results

---

## Files Modified

### This Session (2026-06-08)
- ✅ `backend/app/services/agentic_service.py` (line 2255) - Fixed `self.messages` → `messages`
- ✅ `backend/app/services/agentic_service.py` (lines 2281-2383) - Updated `_build_skill_instructions()` with directive language
- ✅ `REINSTATE_USER_EXECUTION_BLOCKER.md` - Created this document

### Previous Session (2026-06-05)
- ✅ `backend/app/services/agentic_service.py` - Added skill invocation logic
- ✅ `backend/app/services/skill_discovery.py` - Intent pattern matching
- ✅ `backend/app/utils/skill_invoker.py` - Mock skill executor (reverted)

---

## Next Steps

1. **Implement Option 1** - Force execution mode with isolated context
2. **Test end-to-end** - Verify LLM actually executes workflow
3. **Verify database changes** - Check that user was renamed and recreated
4. **Document success** - Update PHASE_5_HANDOVER.md with working solution

---

## Key Learnings

1. **Injecting instructions ≠ forcing execution** - The LLM will still make autonomous decisions
2. **Directive language alone doesn't work** - Need architectural enforcement
3. **Skills must be deterministic** - If execution is optional, they're not reliable
4. **Test with actual tool calls** - Backend logs show success, but actual behavior differs

---

## References

- **Phase 5 Handover:** `backend/PHASE_5_HANDOVER.md`
- **Skill Implementation Status:** `REINSTATE_USER_SKILL_IMPLEMENTATION_STATUS.md`
- **Architecture Doc:** `SKILL_TOOL_ARCHITECTURE.md`
- **Backend Logs:** `/tmp/backend.log`
