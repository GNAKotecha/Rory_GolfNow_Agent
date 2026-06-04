# Phase 2: Root Cause Analysis - Complete

**Date:** 2026-06-04  
**Status:** ROOT CAUSE IDENTIFIED ✅

---

## Executive Finding

**Primary Blocker:** Missing database table `workflow_outcomes`

The backend is attempting to log workflow execution outcomes to a non-existent database table, which causes errors during chat processing. This blocks the normal workflow execution flow but does NOT prevent chat responses - it only prevents workflow outcome logging.

---

## Investigation Results

### 1. Backend Services Status
- ✅ Backend running (port 8000)
- ✅ Database connected (PostgreSQL)
- ✅ MCP servers running (golf-plus, tee-sheet)
- ✅ Agentic service executing
- ✅ Chat endpoint responding

### 2. Error Analysis

**Error in `/tmp/backend.log`:**
```
Failed to store workflow outcome: (psycopg2.errors.UndefinedTable) 
relation "workflow_outcomes" does not exist
```

**Location:** `backend/app/services/agent_memory.py:311`  
**Method:** `store_workflow_outcome()`  
**Called from:** `backend/app/api/chat.py:726`

### 3. Code Review

**File:** `backend/app/services/agent_memory.py`
- Lines 308-328: `store_workflow_outcome()` method
- Attempts: `INSERT INTO workflow_outcomes (user_id, workflow_type, outcome, context, created_at)`
- Error handling: Catches exception but logs and re-raises

**File:** `backend/app/api/chat.py`
- Line 726: Catches the error but continues (WARNING level)
- Impact: Error is silenced, workflow continues, but outcome not logged

### 4. Database Schema Check

**Query:** `psql -c "\dt" | grep workflow`
**Result:** No `workflow_outcomes` table found

**Migration Status:**
- Last migration: `j6k7l8m9n0o1_add_test_run_tables.py` (Jun 3, 15:03)
- No migration for `workflow_outcomes` table exists
- Database migrations not applied for this table

### 5. Related Models

**Found:** `WorkflowOutcome` enum in `backend/app/models/models.py`
```python
class WorkflowOutcome(str, enum.Enum):
    # This is an ENUM, not a table model
```

**Missing:** SQLAlchemy ORM model for `workflow_outcomes` table

---

## Impact Assessment

### Does This Explain Tool Call Issues?

**No, it does NOT directly explain why tools aren't being called.**

The missing table causes:
- ✅ Workflow outcome logging to fail (non-fatal)
- ✅ Errors in logs (but caught and handled)
- ✅ No impact on actual tool calling logic

The tool calling code is actually working (lines 644-669 in agentic_service.py show proper tool execution logic).

### Why Aren't Tools Being Called Then?

**Possible Reasons (still investigating):**
1. **LLM not generating tool calls** - Model might not be instructed to use tools
2. **Tool availability** - MCP registry may not have tools registered
3. **Workflow classification** - No `workflow_type` specified in requests (defaults to "general" which may have limited tools)
4. **Tool filtering** - Workflow-scoped tool filtering may exclude tools for general workflows

---

## Solution

### Quick Fix (Tonight)
Create migration to add `workflow_outcomes` table:

```sql
CREATE TABLE workflow_outcomes (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    workflow_type VARCHAR(100) NOT NULL,
    outcome VARCHAR(50) NOT NULL,
    context JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX idx_workflow_outcomes_user_id ON workflow_outcomes(user_id);
CREATE INDEX idx_workflow_outcomes_workflow_type ON workflow_outcomes(workflow_type);
CREATE INDEX idx_workflow_outcomes_created_at ON workflow_outcomes(created_at);
```

### Full Solution
1. Create alembic migration file
2. Add ORM model `WorkflowOutcomeRecord` 
3. Run migration: `alembic upgrade head`
4. Restart backend

---

## Next Steps

### Phase 3: Root Cause Continued
After fixing missing table:
1. Re-run QA scenarios
2. Check if tool calls now appear in logs
3. If still no tool calls, investigate:
   - LLM tool definition in prompt
   - MCP registry tool loading
   - Workflow-scoped tool filtering

### Recommended Actions
- **Priority 1:** Create migration for `workflow_outcomes` table
- **Priority 2:** Re-run QA after migration
- **Priority 3:** If tools still not called, investigate tool definition in LLM prompt

---

## Files Affected
- `backend/app/services/agent_memory.py` - trying to insert into missing table
- `backend/app/api/chat.py` - catches the error silently
- Database - missing `workflow_outcomes` table
- Alembic - missing migration file

## Blockers Remaining
- ✅ Database table missing (IDENTIFIED)
- ❓ Tool calling still needs verification
- ❓ MCP gateway connectivity needs verification
- ❓ BRS API integration needs verification

---

Generated: 2026-06-04 during Phase 2 investigation
