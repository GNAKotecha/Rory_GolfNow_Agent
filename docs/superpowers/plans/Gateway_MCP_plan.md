# Gateway MCP Implementation Plan

**Spec:** [2026-05-08-gateway-mcp-design.md](../specs/2026-05-08-gateway-mcp-design.md)  
**Phase:** 4  
**Status:** In Progress

---

## Overview

Build a Gateway MCP server exposing business-level tools with unified policy, auth, audit, and credential handling. The gateway wraps Phase 2 BRS tools and adds Atlassian/Jira integration via OAuth.

---

## Milestone 1: Package Foundation ✅

- [x] **1.1** Create `backend/gateway_mcp/` package structure with `__init__.py` and `pyproject.toml`
- [x] **1.2** Create `backend/gateway_mcp/main.py` with FastAPI app skeleton (port 8090) + `/health` endpoint
- [x] **1.3** Create config loader (`core/config.py`) with env-based YAML loading (`GATEWAY_ENV`)
- [x] **1.4** Create config files: `configs/local.yaml`, `configs/qa.yaml`, `configs/prod.yaml`
- [x] **1.5** Add `GatewayError` hierarchy in `core/errors.py` with all error codes from spec
- [x] **1.6** Verify gateway starts locally and `/health` returns 200

---

## Milestone 2: Executor Backends

- [x] **2.1** Define `ExecutorBackend` protocol in `core/executors/base.py` with `run_command`, `submit_command`, `query_db`, `call_http`
- [x] **2.2** Implement `docker_exec.py` backend (shells out to `docker exec`)
- [x] **2.3** Implement `mock.py` executor backend for tests
- [x] **2.4** Stub `k8s_exec.py` backend (interface only, raises NotImplemented for now)
- [x] **2.5** Stub `job_runner.py` backend (interface only)
- [x] **2.6** Unit tests for `docker_exec` with mocked subprocess
- [x] **2.7** Unit tests for `mock` executor

---

## Milestone 3: Tool Registry & Base

- [x] **3.1** Create `tools/base.py` with `Tool` dataclass (name, description, input_schema, output_schema, risk_level, allowed_environments, requires_approval, timeout_seconds, required_scopes, handler)
- [x] **3.2** Create `tools/__init__.py` with `ToolRegistry` class
- [x] **3.3** Import and adapt Phase 2 schemas from `app.services.brs_tools.schemas`
- [x] **3.4** Import and adapt Phase 2 parser from `app.services.brs_tools.parser`
- [x] **3.5** Unit tests for `ToolRegistry`

---

## Milestone 4: Core Middleware Chain

- [ ] **4.1** Create `core/auth.py` — service token + X-User-Id validation
- [ ] **4.2** Create `core/permissions.py` — risk_level vs env/role gate
- [ ] **4.3** Create `core/scopes.py` — required_scopes vs token scope check (stub for external tools)
- [ ] **4.4** Create `core/approval.py` — bridge to Phase 3 `ApprovalService`
- [ ] **4.5** Create `core/audit.py` — structured JSON logger + Langfuse span creation
- [ ] **4.6** Create `core/middleware.py` — assemble request pipeline (start audit → auth → schema validate → env gate → permission check → scope check → approval check → handler → finish audit)
- [ ] **4.7** Unit tests for each middleware stage (auth fail, env denial, permission deny, etc.)
- [ ] **4.8** Integration test verifying middleware order and audit records

---

## Milestone 5: BRS Tools (6)

- [ ] **5.1** Implement `tools/clubs.py` — `create_club` handler
- [ ] **5.2** Implement `tools/clubs.py` — `get_club_by_name` handler
- [ ] **5.3** Implement `tools/clubs.py` — `verify_club_setup` handler
- [ ] **5.4** Implement `tools/config.py` — `get_club_config` handler
- [ ] **5.5** Implement `tools/users.py` — `create_admin_user` handler
- [ ] **5.6** Implement `tools/api.py` — `call_internal_api` handler (research `enable_required_features` body first)
- [ ] **5.7** Register all 6 BRS tools in `ToolRegistry`
- [ ] **5.8** Unit tests for each BRS tool with mock executor
- [ ] **5.9** Integration test: full club-setup workflow replay (`create_club` → `get_club_by_name` → `create_admin_user` → `call_internal_api` → `verify_club_setup`)

---

## Milestone 6: MCP Protocol Transport

- [ ] **6.1** Add MCP HTTP/SSE transport to `main.py` (FastAPI routes for `tools/list`, `tools/call`)
- [ ] **6.2** Implement `/tools` debugging endpoint
- [ ] **6.3** Implement `/ready` health check (executor + service URL reachability)
- [ ] **6.4** Unit tests for MCP protocol compliance
- [ ] **6.5** Integration test: MCP client can list and call tools

---

## Milestone 7: Credential Subsystem

- [ ] **7.1** Create Alembic migration for `external_credentials` table
- [ ] **7.2** Create `core/credentials/store.py` — encrypted DB-backed credential store
- [ ] **7.3** Create `core/credentials/providers/base.py` — `CredentialProvider` protocol
- [ ] **7.4** Create `core/credentials/providers/atlassian.py` — OAuth provider config
- [ ] **7.5** Create `core/credentials/providers/github.py` — PAT provider config (infra only)
- [ ] **7.6** Create `core/credentials/oauth_flow.py` — authz code + PKCE, exchange, refresh
- [ ] **7.7** Create `core/credentials/pat_flow.py` — PAT validation + storage
- [ ] **7.8** Add OAuth/PAT routes to main backend (`app/api/credentials.py`): `/api/credentials/atlassian/authorize`, `/api/credentials/atlassian/callback`, `/api/credentials/github/pat`, `DELETE /api/credentials/{provider}`, `GET /api/credentials`
- [ ] **7.9** Unit tests: encryption roundtrip, refresh logic, concurrent refresh serialization
- [ ] **7.10** Unit tests: PAT validation success/failure, revocation handling
- [ ] **7.11** Integration test: OAuth authz redirect → callback → token stored

---

## Milestone 8: External Executor Backends

- [ ] **8.1** Implement `core/executors/mcp_proxy.py` — upstream MCP client with credential injection
- [ ] **8.2** Implement `core/executors/http_rest.py` — direct REST fallback with allowlist
- [ ] **8.3** Add upstream MCP config to YAML files (`upstream_mcps` section)
- [ ] **8.4** Unit tests for `mcp_proxy` with mocked upstream
- [ ] **8.5** Unit tests for `http_rest` with mocked HTTP

---

## Milestone 9: Atlassian Tools (3)

- [ ] **9.1** Implement `tools/jira.py` — `create_ticket` handler
- [ ] **9.2** Implement `tools/jira.py` — `get_ticket_status` handler
- [ ] **9.3** Implement `tools/jira.py` — `add_comment` handler
- [ ] **9.4** Register all 3 Atlassian tools in `ToolRegistry`
- [ ] **9.5** Unit tests for each Atlassian tool with mocked `mcp_proxy`
- [ ] **9.6** Integration test: `create_ticket` → `get_ticket_status` → `add_comment` with mocked upstream

---

## Milestone 10: System Integration

- [ ] **10.1** Register Gateway MCP in `backend/app/config/mcp_config.py` allowlist (per env)
- [ ] **10.2** Update `WorkflowOrchestrator` routing to prefer Gateway MCP tools
- [ ] **10.3** Update onboarding template to use `create_club` instead of raw BRS names
- [ ] **10.4** Verify `MCPToolRegistry` picks up Gateway tools automatically
- [ ] **10.5** Integration test: existing onboarding workflow passes with Gateway routing

---

## Milestone 11: E2E & Smoke Tests

- [ ] **11.1** Create `infrastructure/docker-compose.brs.yml` for local BRS stack
- [ ] **11.2** Document BRS repo prerequisites and dev Dockerfile requirements
- [ ] **11.3** Create `scripts/smoke_setup_club.py` — BRS workflow smoke test
- [ ] **11.4** Create `scripts/smoke_jira.py` — Atlassian tools smoke test
- [ ] **11.5** E2E test: full club-setup against real BRS containers (`GATEWAY_E2E=1`)
- [ ] **11.6** Optional E2E: Atlassian against real test instance (`GATEWAY_E2E_ATLASSIAN=1`)

---

## Milestone 12: Documentation & Cleanup

- [ ] **12.1** Update `GATEWAY_MCP.md` (root) with final architecture and usage
- [ ] **12.2** Document local dev setup in `backend/gateway_mcp/README.md`
- [ ] **12.3** Document credential setup flow (OAuth + PAT) for operators
- [ ] **12.4** Create `PHASE_4_HANDOVER.md` with completion status
- [ ] **12.5** Final acceptance criteria checklist verification

---

## Open Questions (Resolve During Implementation)

1. [ ] Research: exact body shape for `call_internal_api(operation=enable_required_features)`
2. [ ] Research: do BRS repos have dev Dockerfiles or need local overrides?
3. [ ] Spike: `docker` Python SDK vs shell-out for `docker_exec` backend
4. [ ] Prerequisite: register Atlassian OAuth app in GolfNow tenant
5. [ ] Research: Github PAT scope query-string parameters for pre-selection

---

## Risk Register

| Risk | Status | Mitigation |
|------|--------|------------|
| BRS repos lack dev Dockerfiles | Open | Add minimal overrides in `infrastructure/dockerfiles/` |
| k8s_exec/job_runner untestable before infra | Accepted | Unit test only; placeholders |
| Atlassian MCP API stability | Open | Pin version header; smoke test in CI |
| Credential leakage via logs | Mitigated | Strict redaction; unit test assertions |

---

## Progress Log

| Date | Milestone | Tasks Completed | Notes |
|------|-----------|-----------------|-------|
| 2026-05-10 | 1 | 1.1-1.6 | Milestone 1 complete: Package structure, main.py with /health /ready /tools endpoints, config loader with YAML, GatewayError hierarchy, gateway verified running on :8090 |
| 2026-05-10 | 2 | 2.1-2.7 | Milestone 2 complete: ExecutorBackend protocol, docker_exec, mock, k8s_exec, job_runner. Code review fixes: SQL injection removed from query_db (now raises NotImplementedError), added MockJobHandle.stream(), created http_utils.py for shared HTTP logic. 20 tests passing. |
| 2026-05-10 | 3 | 3.1-3.5 | Milestone 3 complete: Tool dataclass with all metadata (RiskLevel, Environment enums, ToolContext), ToolRegistry class with filtering/MCP schema generation, Gateway schemas for 9 tools (6 BRS + 3 Atlassian), OutputParser adapting Phase 2 parser pattern. 47 tests passing (20 executor + 27 tool registry). |
