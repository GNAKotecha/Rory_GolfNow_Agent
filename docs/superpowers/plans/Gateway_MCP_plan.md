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

## Milestone 4: Core Middleware Chain ✅

- [x] **4.1** Create `core/auth.py` — service token + X-User-Id validation
- [x] **4.2** Create `core/permissions.py` — risk_level vs env/role gate
- [x] **4.3** Create `core/scopes.py` — required_scopes vs token scope check (stub for external tools)
- [x] **4.4** Create `core/approval.py` — bridge to Phase 3 `ApprovalService`
- [x] **4.5** Create `core/audit.py` — structured JSON logger + Langfuse span creation
- [x] **4.6** Create `core/middleware.py` — assemble request pipeline (start audit → auth → schema validate → env gate → permission check → scope check → approval check → handler → finish audit)
- [x] **4.7** Unit tests for each middleware stage (auth fail, env denial, permission deny, etc.)
- [x] **4.8** Integration test verifying middleware order and audit records

---

## Milestone 5: BRS Tools (6) ✅

- [x] **5.1** Implement `tools/clubs.py` — `create_club` handler
- [x] **5.2** Implement `tools/clubs.py` — `get_club_by_name` handler
- [x] **5.3** Implement `tools/clubs.py` — `verify_club_setup` handler
- [x] **5.4** Implement `tools/config.py` — `get_club_config` handler
- [x] **5.5** Implement `tools/users.py` — `create_admin_user` handler
- [x] **5.6** Implement `tools/api.py` — `call_internal_api` handler (research `enable_required_features` body first)
- [x] **5.7** Register all 6 BRS tools in `ToolRegistry`
- [x] **5.8** Unit tests for each BRS tool with mock executor
- [x] **5.9** Integration test: full club-setup workflow replay (`create_club` → `get_club_by_name` → `create_admin_user` → `call_internal_api` → `verify_club_setup`)

---

## Milestone 6: MCP Protocol Transport ✅

- [x] **6.1** Add MCP HTTP transport to `main.py` (FastAPI routes for `tools/list`, `tools/call`)
- [x] **6.2** Implement `/tools` debugging endpoint
- [x] **6.3** Implement `/ready` health check (executor + service URL reachability)
- [x] **6.4** Unit tests for MCP protocol compliance
- [x] **6.5** Integration test: MCP client can list and call tools

**Note:** SSE transport is deferred to Milestone 12+ (post-MVP). Current implementation uses HTTP-only protocol which is sufficient for all MVP tool operations.

---

## Milestone 7: Credential Subsystem ✅

- [x] **7.1** Create Alembic migration for `external_credentials` table
- [x] **7.2** Create `core/credentials/store.py` — encrypted DB-backed credential store
- [x] **7.3** Create `core/credentials/providers/base.py` — `CredentialProvider` protocol
- [x] **7.4** Create `core/credentials/providers/generic.py` — Config-driven OAuth/PAT providers with PROVIDER_PRESETS
- [x] **7.5** ~~Create `core/credentials/providers/github.py`~~ Merged into generic.py with PROVIDER_PRESETS
- [x] **7.6** Create `core/credentials/oauth_flow.py` — authz code + PKCE, exchange, refresh
- [x] **7.7** Create `core/credentials/pat_flow.py` — PAT validation + storage
- [x] **7.8** Add OAuth/PAT routes to main backend (`app/api/credentials.py`): `/api/credentials/atlassian/authorize`, `/api/credentials/atlassian/callback`, `/api/credentials/github/pat`, `DELETE /api/credentials/{provider}`, `GET /api/credentials`
- [x] **7.9** Unit tests: encryption roundtrip, refresh logic, concurrent refresh serialization
- [x] **7.10** Unit tests: PAT validation success/failure, revocation handling
- [x] **7.11** Integration test: OAuth authz redirect → callback → token stored

---

## Milestone 8: External Executor Backends ✅

- [x] **8.1** Implement `core/executors/mcp_proxy.py` — upstream MCP client with credential injection
- [x] **8.2** Implement `core/executors/http_rest.py` — direct REST fallback with allowlist
- [x] **8.3** Add upstream MCP config to YAML files (`upstream_mcps` section)
- [x] **8.4** Unit tests for `mcp_proxy` with mocked upstream
- [x] **8.5** Unit tests for `http_rest` with mocked HTTP

---

## Milestone 9: Atlassian Tools (3)

- [x] **9.1** Implement `tools/jira.py` — `create_ticket` handler
- [x] **9.2** Implement `tools/jira.py` — `get_ticket_status` handler
- [x] **9.3** Implement `tools/jira.py` — `add_comment` handler
- [x] **9.4** Register all 3 Atlassian tools in `ToolRegistry`
- [x] **9.5** Unit tests for each Atlassian tool with mocked `mcp_proxy`
- [x] **9.6** Integration test: `create_ticket` → `get_ticket_status` → `add_comment` with mocked upstream

---

## Milestone 10: System Integration ✅

- [x] **10.1** Register Gateway MCP in `backend/app/config/mcp_config.py` allowlist (per env)
- [x] **10.2** Update `WorkflowOrchestrator` routing to prefer Gateway MCP tools
- [x] **10.3** Update onboarding template to use `create_club` instead of raw BRS names
- [x] **10.4** Verify `MCPToolRegistry` picks up Gateway tools automatically
- [x] **10.5** Integration test: existing onboarding workflow passes with Gateway routing

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

## Post-MVP: Future Work 📋

### SSE Transport (deferred from 6.1)
- Implement Server-Sent Events for streaming tool output
- Required for long-running tools with real-time progress updates
- Not required for MVP as all current tools are short-lived operations
- Stub exists in `core/transport.py:create_sse_stream()`

### Advanced Executor Features
- Connection pooling for upstream MCP backends
- Circuit breaker pattern for upstream failures
- Retry with exponential backoff for transient failures

### Extended Credential Management
- Redis-backed OAuth state store (currently in-memory)
- Credential rotation alerts
- Multi-tenant credential isolation

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
| 2026-05-10 | 4 | 4.1-4.8 | Milestone 4 complete: Core middleware chain with auth, permissions, scopes, approval, audit. 89 tests passing. |
| 2026-05-10 | 5 | 5.1-5.9 | Milestone 5 complete: 6 BRS tool handlers (create_club, get_club_by_name, verify_club_setup, get_club_config, create_admin_user, call_internal_api). Tools registered in ToolRegistry. Added ToolExecutionError to errors.py. CreateClubOutput updated with field alias for name. 21 unit tests + 3 integration tests (full club-setup workflow). 113 tests passing total. |
| 2026-05-10 | 6 | 6.1-6.5 | Milestone 6 complete: MCP HTTP transport with POST /mcp/tools/list and POST /mcp/tools/call routes. /tools debug endpoint wired to ToolRegistry. /ready enhanced with Docker daemon and service URL reachability checks. Added ToolNotFoundError to errors.py. Added transport.py with MCP protocol models (MCPToolSchema, MCPToolCallRequest/Response). 20 unit tests + 14 integration tests. 147 tests passing total. |
| 2026-05-11 | 7 | 7.1-7.11 | Milestone 7 complete: Credential subsystem with encrypted DB store, config-driven generic providers (PROVIDER_PRESETS for Atlassian OAuth + GitHub PAT), OAuth flow with PKCE, PAT validation flow, backend API routes at /api/credentials. Refactored from per-provider files to generic approach. 39 unit tests + 17 integration tests. 203 tests passing total. |
| 2026-05-11 | 8 | 8.1-8.5 | Milestone 8 complete: External executor backends. MCPProxyBackend with upstream MCP client, credential injection via CredentialFetcher callback, call_mcp_tool method for direct tool calls, run_command adapter for ExecutorBackend interface. HTTPRestBackend with complete credential injection, allowlist validation, CredentialMissingError on auth failures. Added provider attribute to CredentialMissingError for better debugging. 27 new tests (17 mcp_proxy + 10 http_rest). 230 tests passing total. |
| 2026-05-10 | 9 | 9.1-9.6 | Milestone 9 complete: Atlassian/Jira tools (create_ticket, get_ticket_status, add_comment). Tools use MCPProxyBackend to call upstream Atlassian MCP with credential injection. create_full_registry() includes all 9 tools. Stateful MockAtlassianMCP for integration tests. 21 unit tests + 6 integration tests. 257 tests passing total. |
| 2026-05-10 | 10 | 10.1-10.5 | Milestone 10 complete: System Integration. Gateway MCP registered in mcp_config.py for all environments (development, staging, production). WorkflowOrchestrator updated with MCP registry integration and GATEWAY_TOOL_MAPPING for legacy BRS tool name resolution. Onboarding template updated to use Gateway tool names (create_club, create_admin_user, verify_club_setup). 19 new tests (16 gateway routing + 3 onboarding integration). Tests verify MCPToolRegistry discovers Gateway tools, orchestrator routes correctly, and legacy names are resolved. |
| 2026-05-11 | 10+ | Spec gaps | Fixed: main.py now uses create_full_registry() exposing all 9 MVP tools. Scope enforcement integrated with credential store. /ready iterates configured services instead of non-existent service_url. call_internal_api uses admin_api service key. SSE transport documented as Milestone 12+ future work. Dual authorization layers documented in mcp_config.py. |
