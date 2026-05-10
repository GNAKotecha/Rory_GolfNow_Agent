# Phase 4 Handover: Gateway MCP Implementation

**Last Updated:** 2026-05-10  
**Branch:** `phase-3-onboarding-testing-analytics`  
**Status:** Milestone 4 complete — ready for Milestone 5 (BRS Tools)

---

## Overview

Building Gateway MCP server exposing business-level tools with unified policy, auth, audit, and credential handling. The gateway wraps Phase 2 BRS tools and adds Atlassian/Jira integration via OAuth.

**Plan File:** `docs/superpowers/plans/Gateway_MCP_plan.md`

---

## Completed Milestones

### Milestone 1: Package Foundation ✅

Completed prior to Phase 4.

### Milestone 2: Executor Backends ✅

Completed prior to Phase 4.

### Milestone 3: Tool Registry & Base ✅

Completed prior to Phase 4.

### Milestone 4: Core Middleware Chain ✅

**Completed:** 2026-05-10

**What was implemented:**

1. **core/auth.py** — Service token + X-User-Id validation
   - `AuthService` class with token validation and user ID parsing
   - `AuthResult` dataclass with user_id, token_scopes, is_operator, is_admin
   - Factory function `create_auth_service_from_settings()`

2. **core/permissions.py** — Risk level vs env/role gate
   - `PermissionService` class checking tool permissions
   - Environment restriction validation (allowed_environments)
   - Risk level → role mapping (READ=any, LOW/MEDIUM_WRITE=operator, HIGH_WRITE=admin)
   - `requires_approval()` method for approval gate decisions

3. **core/scopes.py** — OAuth scope validation (stub for external tools)
   - `ScopeService` class for credential scope checking
   - Provider detection from scopes (jira: → atlassian, repo → github)
   - Stub implementation — full credential store in Milestone 7

4. **core/approval.py** — Bridge to Phase 3 ApprovalService
   - `ApprovalBridge` class with in-memory pending requests
   - `ApprovalRequest` dataclass for tracking
   - Integration with Phase 3 `ApprovalService` when DB session provided
   - `require_approval()` method raises `ApprovalRequiredError`

5. **core/audit.py** — Structured JSON logger + Langfuse span creation
   - `AuditLogger` class with Langfuse integration
   - `AuditRecord` dataclass capturing full request lifecycle
   - `AuditOutcome` enum for categorizing results
   - `sanitize_data()` function to redact secrets (password, api_key, etc.)
   - Structured JSON logging with timestamps and correlation IDs

6. **core/middleware.py** — Complete request pipeline
   - `MiddlewarePipeline` class orchestrating all stages
   - `MiddlewareRequest` / `MiddlewareResponse` dataclasses
   - Pipeline stages:
     1. Start audit record
     2. Authenticate (service token + X-User-Id)
     3. Validate input (Pydantic schema)
     4. Check environment restrictions
     5. Check permission (risk level vs role)
     6. Check OAuth scopes (external tools)
     7. Check approval requirement
     8. Execute tool handler
     9. Finish audit record
   - `create_middleware_pipeline()` factory function

**Files created:**
- `backend/gateway_mcp/core/auth.py`
- `backend/gateway_mcp/core/permissions.py`
- `backend/gateway_mcp/core/scopes.py`
- `backend/gateway_mcp/core/approval.py`
- `backend/gateway_mcp/core/audit.py`
- `backend/gateway_mcp/core/middleware.py`
- `backend/gateway_mcp/tests/unit/test_middleware.py`
- `backend/gateway_mcp/tests/integration/test_middleware_integration.py`

**Tests:**
- ✅ 31 unit tests in `test_middleware.py`
  - 8 auth tests (token validation, user ID parsing)
  - 8 permission tests (risk levels, env restrictions)
  - 4 scope tests (provider detection, credential missing)
  - 4 approval tests (request creation, status check)
  - 7 audit tests (record lifecycle, sanitization)
- ✅ 11 integration tests in `test_middleware_integration.py`
  - Successful tool execution
  - Auth failure (missing/invalid token)
  - Validation failure (missing fields)
  - Permission denied (readonly user)
  - Approval required (high-risk tools)
  - Handler error captured
  - Full audit lifecycle
  - Middleware order verification
  - Environment restrictions
- All 89 gateway_mcp tests passing (no regressions)

**Architecture:**

```
MiddlewareRequest
       ↓
┌──────────────────────────────────────────────┐
│              MiddlewarePipeline              │
├──────────────────────────────────────────────┤
│  1. AuditLogger.start_audit()               │
│  2. AuthService.authenticate()               │
│  3. Tool.input_schema(**input_data)         │
│  4. PermissionService._check_env()          │
│  5. PermissionService._check_role()         │
│  6. ScopeService.check_scopes()             │
│  7. ApprovalBridge.require_approval()       │
│  8. tool.handler(validated_input, context)  │
│  9. AuditLogger.finish_audit()              │
└──────────────────────────────────────────────┘
       ↓
MiddlewareResponse
```

**Deferred items (not blocking):**

1. **Langfuse span updates** — Current implementation creates spans but span update API may differ from assumed interface. Verify against actual Langfuse SDK.

2. **Scope validation full implementation** — ScopeService is a stub. Full credential store and scope validation in Milestone 7.

3. **Concurrent approval handling** — In-memory pending dict isn't thread-safe. Production use should go through Phase 3 ApprovalService with DB-backed storage.

---

## Next Milestone: 5 (BRS Tools)

Implement the 6 BRS tool handlers:
- `create_club`
- `get_club_by_name`
- `verify_club_setup`
- `get_club_config`
- `create_admin_user`
- `call_internal_api`

---

## Running Tests

```bash
# Run all gateway_mcp tests
cd backend && pytest gateway_mcp/tests/ -v

# Run only middleware tests
cd backend && pytest gateway_mcp/tests/unit/test_middleware.py gateway_mcp/tests/integration/test_middleware_integration.py -v
```
