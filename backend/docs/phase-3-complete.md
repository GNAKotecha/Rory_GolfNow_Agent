# Phase 3: Onboarding Workflow + Testing + Analytics - COMPLETE ✅

## Overview

Phase 3 adds complete teesheet onboarding workflow with approval gates, DeepEval testing suite, prompt versioning, and analytics dashboard.

## What Was Built

### 1. Teesheet Onboarding Workflow

**Purpose**: Automate club onboarding with human approval gates

**Components**:
- `app/workflows/teesheet_onboarding.py` - Complete workflow template
- 5-step workflow: init → superuser → config → approval → validate

**Workflow Steps**:
```
1. init_database (BRS tool)
   └─ Creates club-specific database

2. create_superuser (BRS tool)
   └─ Creates admin account

3. config_setup (LLM decision)
   └─ Generates club configuration

4. approval_gate_config (Human approval)
   └─ Reviews generated config before deployment

5. validate_config (BRS tool)
   └─ Validates configuration is correct
```

**Usage**:
```python
from app.workflows.teesheet_onboarding import create_teesheet_onboarding_template

template = create_teesheet_onboarding_template(db_session)

orchestrator = WorkflowOrchestrator(db_session, None)
workflow_run = orchestrator.create_workflow_run(
    template=template,
    session_id=session.id,
    input_data={
        "club_name": "Pebble Beach Golf Links",
        "club_id": "PB001",
        "contact_email": "admin@pebblebeach.com",
        "contact_name": "John Smith",
        "facility_type": "golf_course",
        "modules": ["member", "sms"]
    },
    user_id=1
)

result = await orchestrator.execute_workflow(workflow_run.id)
```

### 2. Approval Gate System

**Purpose**: Human-in-the-loop for business decisions

**Components**:
- `app/services/approval_service.py` - Approval orchestration
- `WAITING_APPROVAL` status in WorkflowRun
- Approval fields: approval_data, approval_prompt, approved_by, approved_at

**Usage**:
```python
from app.services.approval_service import ApprovalService

service = ApprovalService(db_session)

service.request_approval(
    workflow_run_id=123,
    approval_data={"config": {...}},
    approval_prompt="Please review the generated configuration"
)

service.process_approval(
    workflow_run_id=123,
    approved=True,
    user_id=1,
    notes="Config looks good"
)

pending = service.get_pending_approvals()
```

**Known limitation (tracked as follow-up):** The `approval_gate` step type in `workflow_orchestrator` is not yet wired to call `ApprovalService.request_approval`, so real end-to-end pause behavior is not active. The service is fully implemented and unit-tested; orchestrator wiring is a Phase 4 item.

### 3. DeepEval Testing Suite

**Purpose**: Test workflow correctness, hallucination, and toxicity

**Components**:
- `tests/deepeval/test_workflow_correctness.py`
- `tests/deepeval/test_workflow_hallucination.py`
- `tests/deepeval/test_workflow_toxicity.py`

**Running Tests**:
```bash
export OPENAI_API_KEY=your_key   # DeepEval uses OpenAI as judge by default
pytest tests/deepeval/ -v -m deepeval
```

**Test Coverage**:
- Config generation correctness
- Input validation
- No hallucinated modules
- Correct email usage
- Non-toxic outputs
- Unbiased approval prompts (test active once orchestrator approval-gate wiring lands)

### 4. Prompt Template Versioning

**Purpose**: A/B test prompts and track performance

**Components**:
- `app/models/prompt_template.py` - PromptTemplate + PromptTemplateVersion models
- Database tables: `prompt_templates`, `prompt_template_versions`

**Usage**:
```python
from app.models.prompt_template import PromptTemplate, PromptTemplateVersion

template = PromptTemplate(
    name="teesheet_config_generation",
    description="Generate club configuration"
)
db.add(template)
db.commit()

v1 = PromptTemplateVersion(
    template_id=template.id,
    version_number=1,
    prompt_text="Generate config for {{club_name}}",
    variables={"club_name": "string"},
    is_active=True
)
db.add(v1)
db.commit()

v1.update_metrics(success=True, latency_ms=250.5)
db.commit()

success_rate = v1.calculate_success_rate()
```

**Metrics Tracked**: usage_count, success_count, success rate (computed), avg_latency_ms, is_active.

### 5. Analytics Dashboard

**Purpose**: Monitor workflow performance and optimize prompts

**Components (backend)**:
- `app/services/analytics_service.py`
- `app/api/analytics.py`
- `app/schemas/analytics.py`

**Components (frontend — Next.js 16 App Router)**:
- `frontend/components/analytics/WorkflowSuccessRate.tsx`
- `frontend/components/analytics/StepFailureAnalysis.tsx`
- `frontend/components/analytics/PromptVersionComparison.tsx`
- `frontend/app/analytics/dashboard/page.tsx`
- `frontend/lib/analytics.ts`

**API Endpoints**:
```
GET /analytics/workflows/{id}/success-rate
GET /analytics/workflows/{id}/step-failures
GET /analytics/prompts/{id}/version-comparison
GET /analytics/dashboard/{id}
```

**Dashboard Features**:
- Workflow success rate
- Average workflow duration
- Step-by-step failure analysis
- Prompt version performance comparison

**Accessing Dashboard**:
```
http://localhost:3000/analytics/dashboard?templateId=1
```

## System Capabilities After Phase 3

- Complete onboarding workflow automation
- Human approval gates for business decisions
- LLM output testing (correctness, hallucination, toxicity)
- Prompt versioning with A/B testing
- Analytics dashboard for performance monitoring
- Step failure analysis for troubleshooting

## Database Schema Updates

**New Tables**: `prompt_templates`, `prompt_template_versions` (see `app/models/prompt_template.py` and the Alembic migration from Task 5).

**Modified Tables**: `workflow_runs` gained `approval_data`, `approval_prompt`, `approved_by`, `approved_at`, `approval_notes`, plus the `WAITING_APPROVAL` enum value on status.

**Note:** Task 5's migration has not yet been applied to the dev Postgres DB (`db` hostname unreachable during development). Run `alembic upgrade head` when a reachable Postgres environment is available.

## Test Coverage

- Unit tests: 16 (test_approval_service: 7, test_analytics_service: 4, test_prompt_template: 5)
- Integration tests: 2 (test_teesheet_onboarding_e2e)
- DeepEval tests: 6 (correctness: 2, hallucination: 2, toxicity: 2; require `OPENAI_API_KEY` to actually run)
- **Total: 24 collected test functions** (pytest `--collect-only` verified)

## Environment Variables

```bash
# DeepEval (uses OpenAI judge by default)
OPENAI_API_KEY=your_key
```

## Next Steps (Phase 4 candidates)

- Wire `approval_gate` step type in `workflow_orchestrator` → `ApprovalService.request_approval`
- Row-level locking in `ApprovalService.process_approval` for concurrent approvers
- Add Guardrails AI for content filtering
- Implement A/B testing framework
- Build reinforcement loop for prompt optimization
- Production deployment configuration

## Critical Learnings

1. Approval gates are first-class workflow steps (status: `WAITING_APPROVAL`)
2. DeepEval needs real executions — mocks pass trivially
3. Analytics drives prompt optimization — track metrics from day 1
4. Prompt versioning is essential before rolling out new prompts
5. Plan-to-implementation path drift is common; always verify the layout before documenting

## How to Verify Phase 3

```bash
cd backend
pytest tests/ -v                      # run all backend tests
export OPENAI_API_KEY=your_key
pytest tests/deepeval/ -v -m deepeval # run DeepEval judge tests
uvicorn app.main:app --reload         # start backend

cd ../frontend
npm run dev                           # start frontend (port 3000)
open http://localhost:3000/analytics/dashboard?templateId=1
```

## Files Modified/Created in Phase 3

**Created (backend)**:
- `backend/app/workflows/teesheet_onboarding.py`
- `backend/app/workflows/__init__.py`
- `backend/app/services/approval_service.py`
- `backend/app/services/analytics_service.py`
- `backend/app/models/prompt_template.py`
- `backend/app/api/analytics.py`
- `backend/app/schemas/analytics.py`
- `backend/tests/deepeval/` (correctness, hallucination, toxicity + conftest if present)
- `backend/tests/unit/services/test_approval_service.py`
- `backend/tests/unit/services/test_analytics_service.py`
- `backend/tests/unit/models/test_prompt_template.py`
- `backend/tests/integration/test_teesheet_onboarding_e2e.py`
- Alembic migration for prompt template tables (Task 5)

**Created (frontend, Next.js 16 App Router — no `src/`)**:
- `frontend/components/analytics/WorkflowSuccessRate.tsx`
- `frontend/components/analytics/StepFailureAnalysis.tsx`
- `frontend/components/analytics/PromptVersionComparison.tsx`
- `frontend/app/analytics/dashboard/page.tsx`
- `frontend/lib/analytics.ts`

**Modified**:
- `backend/app/models/workflow.py` (approval fields + `WAITING_APPROVAL` status)
- `backend/app/services/workflow_orchestrator.py` (jsonschema input validation)
- `backend/requirements.txt` (added `deepeval`)
- `.env.example` (added `OPENAI_API_KEY` / DeepEval note)
- `frontend/lib/api.ts` (TS7053 fix — Task 8)
