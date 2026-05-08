# Phase 3: Onboarding Workflow + Testing + Analytics - Handover Document

## Phase Overview

**Goal**: Implement teesheet onboarding workflow with human-in-the-loop approval, add DeepEval testing for LLM outputs, implement prompt versioning system, and build analytics dashboard.

**Plan**: `docs/superpowers/plans/2026-05-01-phase-3-onboarding-testing-analytics.md`

**Branch**: `phase-3-onboarding-testing-analytics`

---

## Current Status

**Phase**: Starting Phase 3  
**Last Completed**: Phase 2 (BRS Tools + Core Observability)  
**Ready to start**: Task 1 (Teesheet Onboarding Workflow Template)

---

## Phase 3 Tasks (0/8 Complete)

### Task 1: Teesheet Onboarding Workflow Template ⏳
- **Status**: Not started
- **Files**: 
  - Create: `backend/app/workflows/teesheet_onboarding.py`
  - Create: `backend/tests/unit/workflows/test_teesheet_onboarding.py`
- **Goal**: Create workflow template with sequential dependencies (init → superuser → config → approval → validate)

### Task 2: Approval Gate Implementation ⏳
- **Status**: Not started
- **Files**:
  - Modify: `backend/app/models/workflow.py`
  - Create: `backend/app/services/approval_service.py`
  - Create: `backend/app/api/approvals.py`
- **Goal**: Add WAITING_APPROVAL status and approval workflow

### Task 3: DeepEval Integration ⏳
- **Status**: Not started
- **Files**:
  - Modify: `backend/requirements.txt`
  - Create: `backend/tests/conftest.py` (pytest fixtures)
- **Goal**: Add DeepEval dependency and pytest configuration

### Task 4: Workflow Test Suite with DeepEval ⏳
- **Status**: Not started
- **Files**:
  - Create: `backend/tests/deepeval/test_workflow_correctness.py`
  - Create: `backend/tests/deepeval/test_workflow_hallucination.py`
  - Create: `backend/tests/deepeval/test_workflow_toxicity.py`
- **Goal**: Test LLM outputs for correctness, hallucination, toxicity

### Task 5: Prompt Template Versioning ⏳
- **Status**: Not started
- **Files**:
  - Create: `backend/alembic/versions/xxx_add_prompt_versioning.py`
  - Create: `backend/app/models/prompt.py`
  - Create: `backend/app/services/prompt_service.py`
- **Goal**: Track prompt versions with usage metrics

### Task 6: Analytics Dashboard (Backend API) ⏳
- **Status**: Not started
- **Files**:
  - Create: `backend/app/services/analytics_service.py`
  - Create: `backend/app/api/analytics.py`
- **Goal**: API endpoints for workflow metrics and prompt performance

### Task 7: Analytics Dashboard (Frontend Components) ⏳
- **Status**: Not started
- **Files**:
  - Create: `frontend/src/pages/analytics/dashboard.tsx`
  - Create: `frontend/src/components/analytics/WorkflowSuccessRate.tsx`
  - Create: `frontend/src/components/analytics/StepFailureAnalysis.tsx`
  - Create: `frontend/src/components/analytics/PromptVersionComparison.tsx`
- **Goal**: React components for real-time analytics

### Task 8: Documentation ⏳
- **Status**: Not started
- **Files**:
  - Create: `docs/phase-3-complete.md`
  - Modify: `README.md`
- **Goal**: Complete Phase 3 documentation

---

## Dependencies (Phase 2 Complete)

✅ **From Phase 2**:
- Langfuse for tracing
- Instructor for structured outputs
- BRS Tool Gateway
- Mock BRS tool executor

---

## Key Architectural Decisions

*To be documented as implementation progresses*

---

## Known Blockers

None currently

---

## Test Commands

```bash
# Unit tests
cd backend
pytest tests/unit/ -v

# DeepEval tests (requires DEEPEVAL_API_KEY)
pytest tests/deepeval/ -v

# Integration tests
pytest tests/integration/ -v

# All tests
pytest tests/ -v
```

---

## Notes for Next Session

- Start with Task 1: Teesheet Onboarding Workflow Template
- Follow TDD: write failing test → implement → verify pass → commit
- Use `/subagent-driven-development` for task execution
- Update this handover after each task completion

---

## Session Handoff Template

After completing a task, add:

```markdown
### Task X: [Name] ✅
- **Status**: Complete
- **Completed**: YYYY-MM-DD
- **Commits**: [commit SHA]
- **Files Changed**: [list]
- **Tests**: [test results]
- **Key Changes**: [brief description]
- **Blockers Resolved**: [if any]
- **Next Task**: Task X+1
```
