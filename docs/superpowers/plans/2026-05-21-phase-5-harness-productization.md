# Phase 5 Plan: Harness Productization for Multi-Client Deployment

## Summary

Create a reusable, headless harness that supports multi-client deployment with:
1. Policy-driven loop budgets for tool-heavy workflows (replacing hardcoded limits).
2. Durable pause/resume continuity with true run cursor persistence.
3. Frontend-managed MCP integrations (OAuth + API-key auth, dynamic onboarding).
4. Frontend-managed skills/workflows (tenant-scoped registries with versioning).
5. Multi-tenant memory architecture (working + historical retrieval).
6. Sanitized export track for platform-core distribution.

**Current State:**
- ✅ Session-scoped tool approval cache exists (`SessionToolApproval` model, `session_approval_cache.py`)
- ✅ Basic pause/resume with `RunState` serialization exists (`run_state.py`)
- ✅ MCP registry with health checks exists (`mcp_registry.py`, `mcp_health.py`)
- ✅ Headless event contract exists (`headless_events.py`)
- ⚠️ No tenant isolation — single-user deployment model
- ⚠️ Hardcoded loop limits in `agentic_service.py` (no policy layer)
- ⚠️ No frontend APIs for MCP/skill/workflow management
- ⚠️ Resume uses serialized state but doesn't preserve `run_id` through interruptions
- ⚠️ Agent memory exists but no two-layer working/historical architecture

**Target plan file:**
`docs/superpowers/plans/2026-05-21-phase-5-harness-productization.md`

**Locked defaults:**
1. Browser-heavy loop budget default: 90 steps (policy-configurable).
2. Approval behavior: auto-resume on approve (already implemented, needs unification).
3. Product strategy: keep current repo as primary, add sanitized export track.

## Milestones and Tasks

## Task Completion Status

**Progress:** 4 of 9 tasks complete (44%) - Milestones 1 & 2 COMPLETE ✅, Milestone 3 IN PROGRESS

- [x] **Task 1**: Define tenant boundary and ownership model (database + service layer) ✅
- [x] **Task 2**: Implement policy-driven loop budget system (replace hardcoded limits) ✅
- [x] **Task 3**: Add budget-pressure warning events to headless contract ✅
- [x] **Task 4**: Implement true resume continuity - RunState cursor persistence COMPLETE ✅
- [ ] **Task 5**: Build frontend-manageable MCP integration registry (OAuth + API-key support)
- [ ] **Task 6**: Build frontend-manageable skill/workflow registries (tenant-scoped, versioned)
- [ ] **Task 7**: Implement two-layer memory architecture (working + historical retrieval)
- [ ] **Task 8**: Add sanitized export track for platform-core distribution
- [ ] **Task 9**: End-to-end validation (browser-heavy workflow + tenant isolation + resume continuity)

### Milestone 1: Tenant Isolation Foundation
**Tasks:** Task 1  
**Goals:**
- Add `tenant_id` to core models (`User`, `Session`, `ExternalCredential`, workflow tables)
- Add tenant-scoped service layer filtering (repos, queries, MCP client isolation)
- Add seed migration for default tenant and admin user assignment

**Acceptance gate:** All database queries respect tenant boundaries. Cross-tenant access is impossible at service layer.

**Dependencies:** None (foundational work)

---

### Milestone 2: Policy-Driven Loop Budgets
**Tasks:** Task 2, Task 3  
**Goals:**
- Extract hardcoded loop limits from `agentic_service.py` into `LoopBudgetPolicy` class
- Support workflow profiles: `default`, `browser-heavy`, `api-heavy`, `custom`
- Default browser-heavy profile: 90 steps
- Emit `budget_warning` events at 80% threshold via headless contract
- Preserve explicit hard-stop telemetry with `stopped_reason: "budget_exhausted"`

**Acceptance gate:** Browser automation workflow runs under 90-step profile. Warning event fires at step 72. Service stops cleanly at step 90 with correct telemetry.

**Dependencies:** None (independent runtime improvement)

---

### Milestone 3: True Resume Continuity
**Tasks:** Task 4  
**Goals:**
- Preserve `run_id` through ask-user, approval, and interruption flows (REST + WebSocket)
- Add `run_cursor` field to `RunState` for safe boundary tracking
- Persist cursor before approval pause, after step completion, on interrupt
- Unify resume paths: `/chat/resume/{session_id}` and WebSocket reconnect both restore from cursor
- Auto-resume behavior already exists — ensure it works with cursor-based resume

**Acceptance gate:** Paused run (approval or interrupt) resumes post-restart with same `run_id`. No duplicate messages. Telemetry shows cursor provenance.

**Dependencies:** Milestone 1 (tenant-scoped sessions required for isolation)

---

### Milestone 4: Frontend-Managed MCP Integrations
**Tasks:** Task 5  
**Goals:**
- Add tenant-scoped MCP integration registry (`TenantMCPIntegration` model)
- Add REST APIs under `/api/integrations/*` (CRUD, test, health, enable/disable)
- Support OAuth flow (initiate, callback, token storage in `ExternalCredential`)
- Support API-key/PAT auth with encrypted storage
- Integrate with existing `mcp_registry.py` for runtime tool resolution
- Gateway layer enforces credential isolation (no changes to gateway MCP itself)

**Acceptance gate:** Tenant admin can onboard GitHub MCP integration via frontend. OAuth flow completes. Tools appear in catalog. Agent can execute GitHub tools. Credentials are tenant-isolated.

**Dependencies:** Milestone 1 (tenant model required), Milestone 3 (resume continuity ensures safe OAuth flows)

---

### Milestone 5: Frontend-Managed Skills and Workflows
**Tasks:** Task 6  
**Goals:**
- Add tenant-scoped skill/workflow registries (`TenantSkill`, `TenantWorkflow` models)
- Add REST APIs under `/api/skills/*` and `/api/workflows/*` (CRUD, version, activate)
- Runtime resolves active tenant config at execution time (merge with global skills)
- Support versioning and rollback (active_version pointer)
- Workflow execution logs tenant provenance for analytics

**Acceptance gate:** Tenant admin can publish "club creation workflow" via frontend. Workflow activates. Agent executes workflow with tenant-configured approval gates. Analytics show tenant attribution.

**Dependencies:** Milestone 1 (tenant model required), Milestone 4 (workflows may reference tenant MCP integrations)

---

### Milestone 6: Two-Layer Memory Architecture
**Tasks:** Task 7  
**Goals:**
- Implement "working memory" (always-injected, <2KB, session-scoped key facts)
- Implement "historical retrieval" (semantic search over prior session summaries, tenant-scoped)
- Add `session_working_memory` JSONB field to `Session` model
- Add retrieval API for agent to pull relevant historical context on-demand
- Agent memory service (`agent_memory.py`) updated to use two-layer approach

**Acceptance gate:** Agent maintains compact working memory across turns. Agent retrieves relevant historical context when user references prior work. Memory is tenant-isolated.

**Dependencies:** Milestone 1 (tenant-scoped sessions), Milestone 3 (resume continuity preserves working memory)

---

### Milestone 7: Sanitized Export Track
**Tasks:** Task 8  
**Goals:**
- Add `.exportignore` file listing BRS-specific modules and configs
- Add `scripts/export_platform_core.sh` that creates clean distribution
- Exclude: `brs_tools/`, `gateway_mcp/tools/clubs.py|users.py|teesheet/`, BRS-specific migrations, BRS env vars from `.env.example`
- Include: core harness, generic gateway MCP, database models, API layer, sanitization docs
- Add validation script to ensure no BRS leakage in export

**Acceptance gate:** Export script runs. Output tarball contains only generic harness components. Validation script passes (no BRS references). Export can be deployed to clean environment with only tenant config changes.

**Dependencies:** All prior milestones (export represents complete, production-ready harness)

---

### Milestone 8: End-to-End Validation
**Tasks:** Task 9  
**Goals:**
- Integration test: browser-heavy workflow (Playwright-driven club creation) runs under 90-step policy, emits budget warning, completes successfully
- Integration test: pause/resume with approval preserves `run_id` and cursor across restart
- Integration test: tenant isolation — two tenants with separate MCP integrations and skills, no cross-tenant data leakage
- Load test: 10 concurrent sessions, different tenants, verify isolation and performance
- Security audit: cross-tenant access denial, credential isolation, sanitized export validation

**Acceptance gate:** All integration tests pass. Load test shows stable performance. Security audit passes. Phase 5 handover document updated with test evidence.

**Dependencies:** All prior milestones (validates complete system)

## Public Interfaces and Contracts

### New REST API Endpoints

#### Tenant Management (admin only)
- `POST /api/admin/tenants` — Create new tenant
- `GET /api/admin/tenants` — List all tenants
- `GET /api/admin/tenants/{tenant_id}` — Get tenant details
- `PATCH /api/admin/tenants/{tenant_id}` — Update tenant config

#### MCP Integrations (tenant-scoped)
- `GET /api/integrations` — List tenant's MCP integrations
- `POST /api/integrations` — Register new MCP integration
- `GET /api/integrations/{integration_id}` — Get integration details
- `PATCH /api/integrations/{integration_id}` — Update integration config
- `DELETE /api/integrations/{integration_id}` — Remove integration
- `POST /api/integrations/{integration_id}/test` — Test connection/auth
- `GET /api/integrations/{integration_id}/health` — Health check
- `POST /api/integrations/{integration_id}/oauth/initiate` — Start OAuth flow
- `GET /api/integrations/{integration_id}/oauth/callback` — OAuth callback handler

#### Skills (tenant-scoped)
- `GET /api/skills` — List tenant's skills
- `POST /api/skills` — Create/upload skill
- `GET /api/skills/{skill_id}` — Get skill details
- `PATCH /api/skills/{skill_id}` — Update skill
- `DELETE /api/skills/{skill_id}` — Remove skill
- `POST /api/skills/{skill_id}/activate` — Set as active version

#### Workflows (tenant-scoped)
- `GET /api/workflows` — List tenant's workflows
- `POST /api/workflows` — Create workflow
- `GET /api/workflows/{workflow_id}` — Get workflow details
- `PATCH /api/workflows/{workflow_id}` — Update workflow
- `DELETE /api/workflows/{workflow_id}` — Remove workflow
- `POST /api/workflows/{workflow_id}/activate` — Set as active version

### Extended Headless Event Contract

**New event types:**
- `budget_warning` — Emitted at 80% of loop budget threshold
  ```json
  {
    "type": "budget_warning",
    "current_step": 72,
    "budget_limit": 90,
    "remaining": 18,
    "profile": "browser-heavy"
  }
  ```

- `budget_exhausted` — Emitted when loop stops due to budget limit
  ```json
  {
    "type": "budget_exhausted",
    "total_steps": 90,
    "stopped_reason": "budget_exhausted",
    "profile": "browser-heavy"
  }
  ```

- `resume_from_cursor` — Emitted when run resumes from saved cursor
  ```json
  {
    "type": "resume_from_cursor",
    "run_id": "abc-123",
    "cursor": {"step": 42, "message_index": 15},
    "resumed_at": "2026-05-28T12:00:00Z",
    "provenance": "approval" | "interrupt" | "ask_user"
  }
  ```

### Credential Isolation Contract

**Gateway layer responsibility:**
- All credential access goes through gateway MCP server
- Gateway validates tenant ownership before credential use
- Backend MCP client never sees raw credentials
- Frontend receives only integration metadata (no secrets)

**Backend responsibility:**
- Store encrypted credentials in `ExternalCredential` table with `tenant_id`
- Provide credential ID to gateway MCP for resolution
- Enforce tenant boundaries in all credential queries

## Test Plan

### Unit Tests (per milestone)

**Milestone 1 (Tenant Isolation):**
- `test_tenant_scoped_session_query()` — Sessions filtered by tenant_id
- `test_tenant_scoped_credential_query()` — Credentials isolated by tenant
- `test_cross_tenant_access_denial()` — Queries with wrong tenant_id return empty
- `test_default_tenant_seed_migration()` — Migration creates default tenant and assigns existing users

**Milestone 2 (Loop Budget Policy):**
- `test_loop_budget_policy_resolution()` — Policy resolves correct limits for workflow profiles
- `test_budget_warning_emission()` — Warning event fires at 80% threshold
- `test_budget_exhausted_telemetry()` — Stopped reason correct when limit hit
- `test_default_browser_heavy_profile()` — Default is 90 steps for browser workflows

**Milestone 3 (Resume Continuity):**
- `test_run_cursor_persistence()` — Cursor saved before approval pause
- `test_resume_preserves_run_id()` — Same run_id after resume
- `test_resume_from_cursor_rest()` — REST `/chat/resume` uses cursor
- `test_resume_from_cursor_ws()` — WebSocket reconnect uses cursor
- `test_resume_provenance_metadata()` — Event shows approval/interrupt/ask_user provenance

**Milestone 4 (MCP Integrations):**
- `test_tenant_mcp_integration_crud()` — CRUD operations respect tenant boundaries
- `test_oauth_flow_credential_storage()` — OAuth tokens stored encrypted with tenant_id
- `test_api_key_integration_creation()` — API-key integrations work
- `test_mcp_health_check()` — Health endpoint returns integration status
- `test_mcp_tool_resolution()` — Runtime resolves tenant-specific tools

**Milestone 5 (Skills/Workflows):**
- `test_tenant_skill_registry_crud()` — Skills are tenant-scoped
- `test_skill_versioning()` — Multiple versions, active_version pointer works
- `test_workflow_activation()` — Runtime loads active tenant workflow
- `test_workflow_tenant_attribution()` — Analytics show tenant provenance

**Milestone 6 (Memory):**
- `test_working_memory_size_limit()` — Working memory stays under 2KB
- `test_historical_retrieval_tenant_scoped()` — Retrieval only finds tenant's history
- `test_working_memory_persistence()` — Survives session resume
- `test_memory_semantic_search()` — Retrieval returns relevant prior context

**Milestone 7 (Sanitized Export):**
- `test_export_excludes_brs_modules()` — Export has no BRS-specific code
- `test_export_includes_core_harness()` — Export has all generic components
- `test_export_validation_script()` — Validation detects BRS leakage
- `test_export_deployable_standalone()` — Export can start with only tenant config

---

### Integration Tests (Milestone 8)

**Browser-Heavy Workflow Test:**
```python
def test_browser_heavy_workflow_with_budget():
    """
    Playwright-driven club creation workflow:
    - Runs under 90-step budget policy
    - Emits budget_warning at step 72
    - Completes successfully before exhaustion
    - Telemetry shows correct profile
    """
```

**Pause/Resume Continuity Test:**
```python
def test_pause_resume_with_run_id_continuity():
    """
    Multi-step workflow:
    - Pause for approval at step 5
    - Restart backend
    - Resume from approval
    - Verify same run_id, cursor restored, no duplicate messages
    """
```

**Tenant Isolation Test:**
```python
def test_multi_tenant_isolation():
    """
    Two tenants with separate configs:
    - Tenant A: GitHub MCP integration, "club workflow" skill
    - Tenant B: Jira MCP integration, "ticket workflow" skill
    - Run concurrent sessions
    - Verify no cross-tenant data leakage (tools, credentials, memory)
    """
```

**Load Test:**
```python
def test_concurrent_multi_tenant_sessions():
    """
    10 concurrent sessions across 3 tenants:
    - Each session runs different workflow
    - Verify isolation under load
    - Measure performance metrics (latency, throughput)
    """
```

---

### Security Tests (Milestone 8)

**Cross-Tenant Access Denial:**
- `test_cross_tenant_session_access()` — User can't access other tenant's sessions
- `test_cross_tenant_credential_access()` — MCP integration can't use other tenant's creds
- `test_cross_tenant_skill_access()` — Tenant can't execute other tenant's skills

**Credential Isolation:**
- `test_oauth_token_encryption()` — Tokens stored encrypted at rest
- `test_credential_revocation_handling()` — Revoked tokens trigger re-auth flow
- `test_gateway_credential_validation()` — Gateway enforces tenant ownership

**Approval/Resume Safety:**
- `test_approval_idempotency()` — Duplicate approval requests handled safely
- `test_resume_replay_safety()` — Can't replay old cursor to skip steps

**Sanitized Export Validation:**
- `test_export_no_brs_references()` — Grep export for BRS-specific strings (fail if found)
- `test_export_no_client_secrets()` — No hardcoded credentials or client-specific env vars

## Implementation Dependency Graph

```
Milestone 1 (Tenant Isolation)
    ├─→ Milestone 3 (Resume Continuity) — needs tenant-scoped sessions
    ├─→ Milestone 4 (MCP Integrations) — needs tenant model
    ├─→ Milestone 5 (Skills/Workflows) — needs tenant model
    └─→ Milestone 6 (Memory) — needs tenant-scoped sessions

Milestone 2 (Loop Budget Policy) — Independent, can run parallel to M1

Milestone 3 (Resume Continuity)
    └─→ Milestone 4 (MCP Integrations) — safe OAuth flows need resume

Milestone 4 (MCP Integrations)
    └─→ Milestone 5 (Skills/Workflows) — workflows reference integrations

Milestone 5 (Skills/Workflows)
    └─→ Milestone 7 (Sanitized Export) — export needs registries

Milestone 6 (Memory)
    └─→ Milestone 7 (Sanitized Export) — export needs memory layer

Milestone 7 (Sanitized Export) — Depends on all functional milestones

Milestone 8 (End-to-End Validation) — Depends on all milestones
```

**Critical path:** M1 → M3 → M4 → M5 → M7 → M8  
**Parallel track:** M2 can start immediately alongside M1

---

## Assumptions and Implementation Defaults

### Execution Order
- Milestones executed sequentially (1 → 8)
- Each milestone's acceptance gate must pass before proceeding
- Tasks within a milestone can be parallelized if independent
- Use `/subagent-driven-development` workflow per task (implement → review → fix → re-review, max 2 review iterations)

### Technical Constraints
- **TDD/contract-first:** Write tests before implementation where feasible
- **Minimal changes:** One concern per PR, no scope creep
- **Backward compatibility:** Existing single-tenant deployments must continue to work (default tenant auto-assigned)
- **Gateway isolation preserved:** Credential access remains gateway-layer responsibility
- **Extend, don't replace:** Build on existing `run_state.py`, `headless_events.py`, `mcp_registry.py` primitives

### Database Migration Strategy
- Milestone 1 adds `tenant_id` columns with default value (non-breaking)
- Seed migration creates "default" tenant and assigns all existing users/sessions
- Foreign key constraints added after data migration completes
- Alembic migration tests verify backward compatibility

### Sanitized Export Strategy
- Export is a **build artifact**, not a repository fork
- `scripts/export_platform_core.sh` runs as part of CI/CD for release validation
- Export tarball includes: core harness, generic gateway MCP, database schema, API docs
- Export excludes: BRS-specific tools, client-specific migrations, hardcoded configs
- Validation script (`scripts/validate_export.sh`) enforces exclusion rules

### Multi-Tenant Security Model
- **Tenant isolation at service layer:** All queries include `tenant_id` filter
- **No shared resources:** Each tenant has isolated MCP integrations, skills, workflows, credentials
- **Admin-only tenant management:** Only `role=admin` users can create/manage tenants
- **Frontend receives tenant context from JWT:** Auth token includes `tenant_id` claim

### Memory Architecture Constraints
- **Working memory:** Max 2KB JSONB, always injected into prompt
- **Historical retrieval:** On-demand semantic search, max 5 results per query
- **Tenant-scoped:** Both working and historical memory filtered by `tenant_id`
- **Session-scoped working memory:** Resets per session, persisted for resume

### Loop Budget Policy Defaults
- `default`: 50 steps (general-purpose workflows)
- `browser-heavy`: 90 steps (Playwright, Selenium automation)
- `api-heavy`: 70 steps (multi-step API orchestration)
- `custom`: Admin-configurable per tenant
- Warning threshold: 80% of limit (e.g., step 72 for 90-step budget)

---

## Known Gaps and Future Work (Out of Scope for Phase 5)

### Not Included in This Phase

**Billing and Usage Metering:**
- No tenant billing/quotas implemented
- No usage-based rate limiting per tenant
- Manual tenant provisioning only (no self-service signup)

**Advanced Multi-Tenancy Features:**
- No tenant-level role-based access control (RBAC) beyond admin/user
- No sub-tenant or organization hierarchy
- No tenant-level audit logs (only system-wide logging)

**Skill/Workflow Marketplace:**
- No public skill sharing or marketplace
- No skill discovery beyond tenant's own registry
- No versioned skill dependencies or compatibility matrix

**Advanced Memory Features:**
- No cross-session memory consolidation/summarization
- No user-level memory preferences (e.g., "always remember my preferred format")
- No vector embeddings for semantic search (using keyword-based retrieval only)

**Production Operations:**
- No blue/green deployment strategy for tenant migrations
- No automated tenant backup/restore
- No tenant data export API (for GDPR compliance)
- No disaster recovery plan beyond standard database backups

**Advanced Resume Features:**
- No partial rollback (resume must continue from cursor, can't restart arbitrary steps)
- No cursor branching (can't fork a run from a prior state)
- No cursor expiration policy (old cursors remain indefinitely)

### When to Address These Gaps

- **Billing/metering:** Phase 6 (commercialization)
- **Advanced RBAC:** Phase 6 (enterprise features)
- **Skill marketplace:** Phase 7 (ecosystem expansion)
- **Advanced memory:** Phase 6 (optimization)
- **Production ops:** Phase 6 (scale and reliability)
- **Advanced resume:** Phase 6 (power user features)

### Design Decisions That Enable Future Work

- Tenant model is extensible (can add `quota_limits`, `billing_tier` columns later)
- Skill/workflow registries support versioning (marketplace readiness)
- Memory architecture is two-layer (can add vector search to historical layer)
- Resume cursor is opaque (can change internal structure without breaking contract)
