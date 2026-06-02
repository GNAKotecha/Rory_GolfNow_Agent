# Workflow Cursor Design

## Purpose
Provide precise workflow execution checkpoints for pause/resume functionality with tenant isolation and replay protection.

---

## Architecture

### Core Component
`WorkflowCursor` dataclass in `backend/app/services/workflow_cursor.py`

### Integration Strategy
1. Cursor embedded in `RunState.metadata['cursor']` (no schema change needed)
2. Persisted automatically via existing `ApprovalRecord.run_state_json` serialization
3. Restored from `RunState` on resume operations

---

## Data Structure

```python
@dataclass
class WorkflowCursor:
    step_number: int          # Last completed workflow step
    message_index: int        # Position in RunState.messages array
    workflow_id: str          # Workflow type identifier
    tenant_id: int            # Tenant context for isolation
    timestamp: datetime       # Checkpoint creation time
    metadata: Dict[str, Any]  # Extensible workflow state
```

---

## Key Features

### 1. Lightweight Tracking
- Tracks step number + message index (not full state duplication)
- Minimal memory overhead (~200 bytes serialized)
- Fast serialization/deserialization

### 2. Tenant Isolation
- Every cursor includes `tenant_id`
- Validation enforces tenant match on resume
- Prevents cross-tenant cursor replay

### 3. Replay Protection
- Timestamp-based age validation (default: 24 hours)
- Compatibility check with `RunState` before resume
- Prevents reuse of stale cursors

### 4. Idempotency Support
- `message_index` prevents duplicate message processing
- Step boundary tracking avoids re-execution
- Compatible with existing `completed_action_keys` pattern

---

## Persistence Points

Cursor should be persisted at:
1. **Before approval pause** - In `request_approval()` flow
2. **After successful step** - In agentic loop after tool execution
3. **On explicit interrupt** - When user cancels/stops workflow
4. **During state transitions** - Status changes (running → paused)

---

## Integration with Existing Code

### RunState Enhancement
```python
# In run_state.py - no schema change needed
# Cursor stored in metadata['cursor']

from app.services.workflow_cursor import (
    create_cursor,
    persist_cursor_in_run_state,
    restore_cursor_from_run_state
)

# Create and persist cursor
cursor = create_cursor(
    run_state=state,
    workflow_id="onboarding",
    tenant_id=tenant_id
)
persist_cursor_in_run_state(state, cursor)

# Restore cursor on resume
cursor = restore_cursor_from_run_state(state)
if cursor:
    cursor.validate(current_tenant_id=user.tenant_id)
```

### Approval Flow Integration
```python
# In agentic_service.py - before requesting approval
from app.services.workflow_cursor import create_cursor, persist_cursor_in_run_state

# Before pausing for approval
cursor = create_cursor(
    run_state=state,
    workflow_id=workflow_type,
    tenant_id=user_tenant_id,
    metadata={'pending_tool': tool_name}
)
persist_cursor_in_run_state(state, cursor)

# Serialize state with embedded cursor
await approval_service.request_approval(
    run_state=state,  # Cursor included in metadata
    tool_name=tool_name,
    # ...
)
```

### Resume Flow Integration
```python
# In chat.py and chat_ws.py resume handlers
from app.services.workflow_cursor import restore_cursor_from_run_state

# Restore RunState from ApprovalRecord
run_state = RunState.from_json(approval_record.run_state_json)

# Extract and validate cursor
cursor = restore_cursor_from_run_state(run_state)
if cursor:
    try:
        cursor.validate(current_tenant_id=current_user.tenant_id)
        
        # Use cursor for precise resume
        logger.info(
            f"Resuming from cursor: step={cursor.step_number}, "
            f"msg_idx={cursor.message_index}, workflow={cursor.workflow_id}"
        )
        
        # Resume from cursor position
        # (existing resume logic continues from run_state.current_step)
        
    except ValueError as e:
        logger.error(f"Cursor validation failed: {e}")
        # Fallback to full state resume or reject
```

---

## Validation Rules

### Pre-Resume Validation
1. **Tenant match**: `cursor.tenant_id == current_user.tenant_id`
2. **Age check**: Cursor timestamp within acceptable window (default 24h)
3. **Bounds check**: `message_index <= len(run_state.messages)`
4. **Step sanity**: `step_number <= run_state.current_step + 1`

### Failure Modes
- **Tenant mismatch** → `ValueError` (security violation)
- **Expired cursor** → `ValueError` (reject resume)
- **Incompatible state** → Log warning, fallback to full state resume

---

## Performance Characteristics

### Space Complexity
- Cursor size: ~200 bytes JSON serialized
- Embedded in existing `RunState.metadata` (no additional storage)
- Total overhead per checkpoint: negligible

### Time Complexity
- Serialization: O(1) - fixed fields, no nested loops
- Deserialization: O(1) - fixed structure parsing
- Validation: O(1) - simple field comparisons

---

## Security Considerations

### Tenant Isolation
- Cursor includes `tenant_id` as first-class field
- Validation enforces tenant match (cannot resume other tenant's work)
- Logged in telemetry for audit trails

### Replay Prevention
- Timestamp-based expiration (configurable)
- Compatibility check with RunState prevents stale cursor use
- No secret material in cursor (safe to log)

### Audit Trail
- All cursor operations logged with context
- Telemetry includes cursor provenance in events
- Resume events show workflow_id and step_number

---

## Testing Strategy

### Unit Tests Required
```python
# In backend/tests/test_workflow_cursor.py

def test_cursor_serialization():
    """Cursor serializes and deserializes correctly."""

def test_cursor_validation_tenant_mismatch():
    """Reject cursor from different tenant."""

def test_cursor_validation_expired():
    """Reject cursor older than max_age_seconds."""

def test_cursor_validation_invalid_bounds():
    """Reject cursor with negative step/message index."""

def test_cursor_compatibility_with_run_state():
    """Cursor compatibility checks work correctly."""

def test_cursor_persistence_in_run_state():
    """Cursor persists in RunState.metadata."""

def test_cursor_restoration_from_run_state():
    """Cursor restores from RunState.metadata."""

def test_cursor_missing_in_run_state():
    """Graceful handling when cursor absent."""
```

### Integration Tests Required
```python
# In backend/tests/test_cursor_resume.py

def test_approval_pause_persists_cursor():
    """Approval pause stores cursor in ApprovalRecord."""

def test_resume_restores_cursor():
    """Resume extracts and validates cursor."""

def test_resume_with_invalid_cursor():
    """Resume handles invalid cursor gracefully."""

def test_cursor_telemetry_in_events():
    """Headless events include cursor metadata."""
```

---

## Migration Path

### Phase 1: Add Cursor Module (This Task)
- ✅ Create `workflow_cursor.py` module
- ✅ Add cursor dataclass with validation
- ✅ Add helper functions for persist/restore

### Phase 2: Integration (Next Task)
- Modify approval flow to persist cursor
- Modify resume handlers to restore cursor
- Add cursor validation to resume paths

### Phase 3: Telemetry (Following Task)
- Add cursor metadata to headless events
- Log cursor provenance in analytics
- Update dashboard to show cursor info

### Phase 4: Testing (Final Task)
- Write unit tests for cursor logic
- Write integration tests for resume flow
- End-to-end validation with tenant isolation

---

## Extensibility

### Workflow-Specific Metadata
Cursor includes extensible `metadata` field for workflow-specific state:

```python
# Example: Browser-heavy workflow tracking
cursor = WorkflowCursor(
    step_number=5,
    message_index=12,
    workflow_id="onboarding",
    tenant_id=1,
    metadata={
        'browser_context_id': 'ctx_abc123',
        'current_page_url': 'https://example.com/step5',
        'form_partial_data': {'club_name': 'Test Club'}
    }
)
```

### Future Enhancements
- Add `resume_count` to track how many times cursor was used
- Add `parent_cursor_id` for nested workflow support
- Add `checkpoint_type` field (approval, interrupt, periodic)

---

## Open Questions / Decisions Needed

1. **Cursor expiration default**: 24 hours reasonable? Or configurable per tenant?
2. **Fallback behavior**: If cursor validation fails, attempt full state resume or reject?
3. **Telemetry format**: Cursor metadata embedded in `workflow_events` table or separate `cursor_events`?
4. **RunState schema change**: Keep cursor in metadata or add dedicated field?
   - **Decision**: Use metadata (no migration needed, backward compatible)

---

## Success Criteria

✅ Cursor persists before approval pause
✅ Cursor validates tenant isolation on resume
✅ Resume preserves `run_id` through pause/resume cycle
✅ No duplicate message processing after resume
✅ Telemetry shows cursor provenance
✅ All unit tests pass
✅ Integration tests demonstrate tenant isolation

---

## Related Files

- `backend/app/services/workflow_cursor.py` - Core cursor implementation
- `backend/app/services/run_state.py` - RunState integration points
- `backend/app/services/agentic_service.py` - Approval pause integration
- `backend/app/api/chat.py` - REST resume handler
- `backend/app/api/chat_ws.py` - WebSocket resume handler
- `backend/app/services/headless_events.py` - Telemetry integration

---

## References

- Phase 5 Plan: `docs/superpowers/plans/2026-05-21-phase-5-harness-productization.md`
- Milestone 3: True Resume Continuity (Task 4)
- Acceptance Gate: Paused run resumes with same `run_id`, no duplicate messages
