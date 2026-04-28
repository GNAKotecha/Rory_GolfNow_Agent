# Approval Workflow and Memory Batching

## Agent Memory Transaction Batching

### Purpose
Provide atomicity for related memory operations while maintaining backward compatibility.

### Implementation
Added `batch()` context manager to `AgentMemory`:

```python
memory = AgentMemory(db)

# Atomic batch: all succeed or all rollback
with memory.batch():
    memory.store_user_preference(user_id, "format", "verbose")
    memory.store_workflow_outcome(user_id, "analysis", "success", context)
    memory.store_domain_knowledge(user_id, "golf", "peak times 7-9am", "analysis")

# Individual commit (default behavior, unchanged)
memory.store_user_preference(user_id, "theme", "dark")
```

### Key Features
- **Opt-in batching** - Default behavior unchanged
- **Single commit** - All operations commit together at context exit
- **Automatic rollback** - Exception triggers rollback of entire batch
- **Flag reset guarantee** - `_batch_mode` flag always resets (even on error)

### When to Use Batching
- Storing related memory updates from single workflow execution
- Recording preference + outcome + knowledge together
- Any scenario requiring all-or-nothing semantics

### When NOT to Use Batching
- Single isolated operations (default is fine)
- Unrelated memory updates
- When partial success is acceptable

### Tests
6 comprehensive tests added to `tests/test_agent_memory.py`:
- Successful batch commit
- Rollback on error
- Mixed operations (preferences + outcomes + knowledge)
- Individual commits outside batch context
- Batch mode flag lifecycle
- Flag reset on error

---

## Fail-Safe Approval Workflow

### Purpose
Enforce tool approval policy with fail-safe design: client requests can make approval **stricter**, never weaker.

### Policy Hierarchy
```
User/Org Setting (stored in DB)
    ↓
Optional Request Override (can only increase strictness)
    ↓
Final Approval Policy (used by agentic service)
```

### Implementation

**Database:**
- Added `require_tool_approval` column to `users` table
- Default: `FALSE` (for MVP)
- Migration: `migrations/add_require_tool_approval.sql`

**API Endpoints:**

**HTTP (`/chat`):**
```json
{
  "session_id": 1,
  "message": "user message",
  "require_approval": true  // Optional: can only make stricter
}
```

**WebSocket (`/ws/chat`):**
```json
{
  "type": "message",
  "session_id": 1,
  "message": "user message",
  "require_approval": true  // Optional: can only make stricter
}
```

**Fail-Safe Logic:**
```python
user_requires_approval = current_user.require_tool_approval
request_requires_approval = request.require_approval

if request_requires_approval is not None:
    if user_requires_approval and not request_requires_approval:
        # FAIL-SAFE: ignore attempt to disable required approval
        logger.warning("Ignoring attempt to disable required approval")
        final_approval_setting = True
    else:
        # Allow client to enable approval
        final_approval_setting = request_requires_approval
else:
    # No override: use user/org setting
    final_approval_setting = user_requires_approval
```

### Security Properties
1. **Fail-safe default** - Client cannot weaken security
2. **Audit trail** - Attempts to disable required approvals are logged
3. **Consistent enforcement** - Same logic in HTTP and WebSocket endpoints
4. **Explicit policy** - User/org setting is source of truth

### Examples

**Scenario 1: User requires approval, client tries to disable**
```
User setting: require_tool_approval = True
Request: require_approval = False
Result: require_approval_for_write = True  ✓ (fail-safe)
Log: "Ignoring attempt to disable required approval"
```

**Scenario 2: User doesn't require approval, client enables it**
```
User setting: require_tool_approval = False
Request: require_approval = True
Result: require_approval_for_write = True  ✓ (allowed)
```

**Scenario 3: User doesn't require approval, no override**
```
User setting: require_tool_approval = False
Request: require_approval = None
Result: require_approval_for_write = False  ✓ (default)
```

**Scenario 4: User requires approval, client also requires**
```
User setting: require_tool_approval = True
Request: require_approval = True
Result: require_approval_for_write = True  ✓ (consistent)
```

### Configuration

**Enable approvals for specific users:**
```sql
UPDATE users
SET require_tool_approval = TRUE
WHERE email IN ('admin@example.com', 'restricted-user@example.com');
```

**Enable approvals for all admins:**
```sql
UPDATE users
SET require_tool_approval = TRUE
WHERE role = 'admin';
```

**Enable approvals organization-wide:**
```sql
UPDATE users SET require_tool_approval = TRUE;
```

### Future Enhancements
- Role-based default approval policies
- Organization-level approval settings
- Per-tool approval granularity (approve database writes but not reads)
- Approval delegation (manager approves on behalf of user)

---

## Files Modified

### Agent Memory Batching
- `app/services/agent_memory.py` - Added `batch()` context manager
- `tests/test_agent_memory.py` - Added 6 batching tests

### Fail-Safe Approval Workflow
- `app/models/models.py` - Added `require_tool_approval` to User model
- `migrations/add_require_tool_approval.sql` - Database migration
- `app/api/chat.py` - Added fail-safe approval logic + `require_approval` parameter
- `app/api/chat_ws.py` - Added fail-safe approval logic + WebSocket parameter

---

## Testing

### Agent Memory Batching Tests
```bash
pytest tests/test_agent_memory.py::test_batch_context_manager_success
pytest tests/test_agent_memory.py::test_batch_context_manager_rollback_on_error
pytest tests/test_agent_memory.py::test_batch_with_mixed_operations
pytest tests/test_agent_memory.py::test_non_batch_operations_still_commit_individually
pytest tests/test_agent_memory.py::test_batch_mode_flag_resets_after_context
pytest tests/test_agent_memory.py::test_batch_mode_resets_even_on_error
```

**Result:** All 6 tests passing ✓

### Approval Workflow Tests
Manual testing required (integration tests not yet implemented):

1. Apply migration: `psql -d rory_agent -f migrations/add_require_tool_approval.sql`
2. Enable approval for test user: `UPDATE users SET require_tool_approval = TRUE WHERE email = 'test@example.com';`
3. Test HTTP endpoint:
   - With override: `{"require_approval": false}` → Logs warning, uses `true`
   - Without override: `{}` → Uses user setting (`true`)
4. Test WebSocket endpoint (same scenarios)
5. Verify logs contain "Ignoring attempt to disable required approval" when fail-safe triggers

---

## Migration Guide

### Applying Database Migration
```bash
# Connect to database
psql -U postgres -d rory_agent

# Run migration
\i backend/migrations/add_require_tool_approval.sql

# Verify
\d users
# Should see: require_tool_approval | boolean | not null | false
```

### Frontend Integration
Update API clients to optionally send `require_approval`:

```javascript
// HTTP
const response = await fetch('/api/chat', {
  method: 'POST',
  body: JSON.stringify({
    session_id: sessionId,
    message: message,
    require_approval: true  // Optional: enable approval for this request
  })
});

// WebSocket
ws.send(JSON.stringify({
  type: 'message',
  session_id: sessionId,
  message: message,
  require_approval: true  // Optional
}));
```

**Important:** Clients should NOT attempt to disable approvals (will be ignored with warning logged).

---

## Best Practices

### Memory Batching
- Use batching when atomicity matters (related operations)
- Don't over-batch unrelated operations
- Expect rollback on any error in batch
- Monitor batch transaction durations

### Approval Workflow
- Set user/org approval policy conservatively
- Rely on fail-safe enforcement (don't trust client)
- Monitor attempts to disable approvals (security signal)
- Document approval requirements clearly for users
