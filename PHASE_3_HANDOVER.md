# Phase 3 Handover: Onboarding Workflow + Testing + Analytics

**Last Updated:** 2026-05-06  
**Branch:** `phase-3-onboarding-testing-analytics`  
**Status:** Task 2 complete — ready for Task 3

---

## Completed Work

### Task 1: Teesheet Onboarding Workflow Template ✅ (with review feedback)

**What was implemented:**
- Created `backend/app/workflows/teesheet_onboarding.py` with complete 5-step workflow template:
  1. `init_database` - BRS tool call (brs_teesheet_init)
  2. `create_superuser` - BRS tool call (brs_create_superuser)
  3. `config_setup` - LLM decision (config generation)
  4. `approval_gate_config` - Approval gate (human review)
  5. `validate_config` - BRS tool call (brs_config_validate)
- Created `backend/app/workflows/__init__.py`
- Created `backend/tests/integration/test_teesheet_onboarding_e2e.py` with 2 E2E tests
- Added `validate_onboarding_input()` function with jsonschema validation

**Files changed:**
- `backend/app/workflows/teesheet_onboarding.py` (created)
- `backend/app/workflows/__init__.py` (created)
- `backend/tests/integration/test_teesheet_onboarding_e2e.py` (created)

**Tests:**
- ✅ `test_teesheet_onboarding_workflow_e2e` - Tests full workflow execution
- ✅ `test_teesheet_onboarding_workflow_validates_input` - Tests input validation through orchestrator
- All tests passing (2/2)

**Commits:**
- `cabc50c` - feat: add teesheet onboarding workflow template
- `b0ed300` - fix: correct test names and validation approach for spec compliance
- `bdde3db` - fix: validate input through orchestrator.create_workflow_run()

**Code Review Feedback (Important Issues to Address):**

1. **Critical: Weak input validation in orchestrator**
   - Location: `backend/app/services/workflow_orchestrator.py:132-137`
   - Issue: `_validate_input_data()` only checks field presence, not types/formats/enum constraints
   - Risk: Invalid data (wrong types, bad email formats, invalid enums) can pass validation
   - Fix needed: Use `jsonschema.validate()` for complete schema validation

2. **Critical: Duplicate validation logic**
   - Locations: `workflow_orchestrator.py` (weak validation) vs `teesheet_onboarding.py:140-157` (proper jsonschema validation)
   - Issue: Two different validation implementations - orchestrator uses weaker version in production
   - Fix needed: Consolidate to single validation point using jsonschema

3. **Important: Missing type validation test coverage**
   - Tests only verify missing fields, not invalid types/formats
   - Needed: Tests for invalid email format, wrong facility_type enum, wrong data types

**Decision resolved:** Task 1 critical validation issues were fixed in commit `8171c50` (jsonschema used for full input validation in `workflow_orchestrator._validate_input_data`). Task 1 fully closed.

---

### Task 2: Approval Gate Implementation ✅

**What was implemented:**
- Added `WAITING_APPROVAL = "waiting_approval"` to `WorkflowRunStatus` enum (matches existing lowercase convention)
- Added 5 approval fields to `WorkflowRun` model:
  - `approval_data` (JSON)
  - `approval_prompt` (Text)
  - `approved_by` (Integer, FK → users.id)
  - `approved_at` (DateTime)
  - `approval_notes` (Text)
- Created `ApprovalService` with 4 methods:
  - `request_approval(workflow_run_id, approval_data, approval_prompt)` — sets status=WAITING_APPROVAL
  - `process_approval(workflow_run_id, approved, user_id, notes)` — validates current status, sets approved_by/at/notes, flips to RUNNING or FAILED (sets `error_message` on rejection)
  - `get_pending_approvals(user_id=None)` — ordered by `created_at`
  - `get_approval_history(workflow_run_id)` — returns 7-key dict with ISO-formatted timestamp
- Created `ApprovalStatus` constants class (APPROVED/REJECTED/PENDING)
- Created Alembic migration `a1b2c3d4e5f6_add_approval_fields_to_workflow_runs.py`:
  - 5 `op.add_column` calls
  - FK `fk_workflow_runs_approved_by_users`
  - Postgres-gated `ALTER TYPE workflowrunstatus ADD VALUE IF NOT EXISTS 'waiting_approval'` inside `autocommit_block()` (no-op on SQLite)
  - Documented limitation: Postgres cannot DROP VALUE on downgrade
- Added `workflow_run_factory` fixture to `backend/tests/fixtures/workflow_fixtures.py`

**Files changed:**
- `backend/app/models/workflow.py` (+8 lines)
- `backend/app/services/approval_service.py` (new, ~120 lines)
- `backend/tests/unit/services/test_approval_service.py` (new, 7 tests)
- `backend/tests/unit/__init__.py`, `backend/tests/unit/services/__init__.py` (new, empty)
- `backend/tests/fixtures/workflow_fixtures.py` (+41 lines)
- `backend/alembic/versions/a1b2c3d4e5f6_add_approval_fields_to_workflow_runs.py` (new, 76 lines)

**Tests:**
- ✅ `test_request_approval_updates_workflow_run`
- ✅ `test_approve_workflow_run_updates_status`
- ✅ `test_reject_workflow_run_updates_status`
- ✅ `test_get_pending_approvals_returns_waiting_workflows`
- ✅ `test_process_approval_rejects_wrong_status` (regression for spec fix)
- ✅ `test_reject_sets_error_message` (regression for spec fix)
- ✅ `test_get_approval_history_returns_audit_fields` (regression for spec fix)
- All unit tests passing (7/7)
- Task 1 E2E regression: 2/2 still passing

**Commits:**
- `2e84f31` - feat: add approval gate implementation for workflows
- `a643702` - fix: address spec compliance issues in approval service (status guard, error_message, dict-shape history, ordering + 3 regression tests)
- `81e82ca` - refactor: normalize WAITING_APPROVAL enum value to lowercase

**Review Flow:**
- Spec review iteration 1: 4 deviations found (missing status guard, missing error_message, wrong return type on history, missing ordering) → fixed in `a643702`
- Spec review iteration 2: ✅ compliant
- Code quality review iteration 1: ⚠️ Approved with follow-ups (0 Critical, 4 Important) → enum casing fixed in `81e82ca`, remaining deferred below

**Deferred follow-ups (not blocking merge):**
1. **Concurrency in `process_approval`** — no row-level locking; two concurrent approvers can both pass the status check and the second overwrites the first's audit trail. Not data corruption (state ends as RUNNING/FAILED) but lost audit info. Suggested fix: `.with_for_update()` on the select, or optimistic concurrency on an `updated_at` column.
2. **`error_message` format not documented** — rejection reason is embedded as `"Rejected by user {user_id}: {notes}"`. Format is stable but should be documented in the method docstring for downstream consumers.
3. **Orchestrator integration** — the plan's Task 2 header listed `workflow_orchestrator.py` as a modified file, but no Step edits it. Orchestrator integration (actually calling `ApprovalService.request_approval` from an `approval_gate` step) is out of scope for Task 2 per the step breakdown. Likely needed before the end-to-end onboarding workflow can pause at the approval gate — confirm scope of later task (probably Task 4 or dedicated follow-up).

---

## In Progress

None — Task 2 complete, awaiting approval to start Task 3

---

## Next Tasks

- **Task 3:** DeepEval Integration (add dependency, config, smoke test)
- **Task 4:** Workflow Test Suite with DeepEval (correctness, hallucination, toxicity tests)
- **Task 5:** Prompt Template Versioning (database models, migration, metrics)
- **Task 6:** Analytics Dashboard Backend API (analytics service, REST endpoints)
- **Task 7:** Analytics Dashboard Frontend (React components, dashboard page)
- **Task 8:** Documentation (phase-3-complete.md, README updates)

**Also deferred from Task 2 (file as follow-up tickets):**
- Wire `approval_gate` workflow step type in `workflow_orchestrator` to actually call `ApprovalService.request_approval` (needed for onboarding E2E to actually pause at the approval step rather than skip it)
- Row-level locking in `ApprovalService.process_approval` for concurrent approvers
- Document `error_message` format in `process_approval` docstring

---

## Blockers

None

---

## Assumptions

- BRS tools run in mock mode (BRS_MOCK_MODE=true by default)
- Phase 2 BRS Tool Gateway is functional
- Workflow orchestrator from Phase 1 is operational
- Input validation will be addressed (decision pending)

---

## Key Learnings

1. **Validation layer consistency matters:** Having multiple validation implementations (orchestrator vs template) creates confusion about which is authoritative
2. **Jsonschema is essential:** Field presence checks aren't sufficient - need type/format/enum validation
3. **E2E tests need real execution:** Mock-heavy tests are fine for MVP but don't catch integration issues
4. **Match existing enum casing:** When adding a new enum value, follow the existing convention (lowercase values here) to avoid mixed-case status strings leaking into DB/APIs/logs. The first-pass `WAITING_APPROVAL = "WAITING_APPROVAL"` had to be normalized to `"waiting_approval"`.
5. **Spec review caught 4 real deviations that passing tests missed:** The initial 4 unit tests asserted happy-path behavior but didn't exercise status guards, error_message on reject, dict-shape return values, or ordering. Regression tests added post-review now cover all of these. Lesson: write tests against the spec's *stated behavior*, not only the happy path.
6. **Postgres enum ALTER requires autocommit:** `ALTER TYPE ... ADD VALUE` cannot run inside a transaction block; use Alembic's `op.get_context().autocommit_block()` and gate on `dialect.name == 'postgresql'`.

---

## Testing Notes

**How to run Phase 3 tests:**

```bash
cd backend

# Task 1: onboarding workflow tests
pytest tests/integration/test_teesheet_onboarding_e2e.py -v

# Task 2: approval service tests
pytest tests/unit/services/test_approval_service.py -v

# Run all integration tests
pytest tests/integration/ -v
```

**Expected behavior:**
- Tests run in mock mode by default
- Workflow creates 5 step executions
- Input validation catches missing required fields AND invalid types/formats (jsonschema)
- Approval service: 7 tests covering request/approve/reject/pending/status-guard/error_message/history-dict

---

## Next Steps

1. Start Task 3 (DeepEval Integration) after user approval
2. File follow-up tickets for the 3 deferred Task 2 items (orchestrator wiring, row-level locking, docstring)
3. Follow TDD: Test → Fail → Implement → Pass → Review → Fix → Re-review (max 2 iterations per review stage)
