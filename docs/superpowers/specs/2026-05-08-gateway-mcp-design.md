# Gateway MCP — Design Spec

**Status:** Draft for review
**Date:** 2026-05-08
**Phase:** 4 (supersedes the former Phase 4 plan; Production Hardening becomes Phase 5)
**Related:** `GATEWAY_MCP.md` (root), Phase 2 BRS Tools, Phase 3 Approval Service

---

## Goal

Build a **Gateway MCP** server that exposes business-level tools (`create_club`, `create_admin_user`, `verify_club_setup`, …) to the agent. The server is the policy and execution boundary: every call is authenticated, permission-checked, env-gated, approval-gated where required, and audited. No raw shell, SQL, or HTTP escape hatches are exposed.

MVP success = the agent can set up a club locally through structured MCP tools.

---

## Locked Decisions

| Decision | Choice |
|---|---|
| Relationship to Phase 2 `brs_tools` | **Wrap.** Reuse registry, schemas, parser. Only the executor swaps. |
| MVP tool surface | 6 doc-exact tools (see §3) |
| Execution model | Docker exec locally, `kubectl exec` in QA, workflow-API / job runner in prod |
| Transport | HTTP/SSE FastAPI on port 8090 |
| Packaging | Sibling package: `backend/gateway_mcp/` |
| Deployment (dev) | Host process; no docker socket mount |
| Approval system | Reuses Phase 3 `ApprovalService` |

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│  Agent clients (Open WebUI, Claude Desktop, backend chat API)  │
└─────────────────────┬──────────────────────────────────────────┘
                      │ MCP protocol (HTTP/SSE)
                      ▼
┌────────────────────────────────────────────────────────────────┐
│  Gateway MCP   (backend/gateway_mcp/, FastAPI on :8090)        │
│                                                                │
│  Middleware chain (strict order):                              │
│     start audit → auth → schema validate → env gate            │
│     → permission check → approval check → handler              │
│     → finish audit                                             │
│                                                                │
│  Tool router: create_club · get_club_by_name · get_club_config │
│               create_admin_user · call_internal_api            │
│               verify_club_setup                                │
└─────────┬──────────────────────────┬──────────────────┬────────┘
          │                          │                  │
          ▼                          ▼                  ▼
  ExecutorBackend           brs_tools.parser     internal HTTP client
  (docker_exec |            (schemas, mock)       (whitelisted ops)
   k8s_exec |
   job_runner)
          │
          ▼
  brs-teesheet · brs-admin-api · brs-config-api · mysql · mongo
```

**Principles:**
- The agent describes intent; the gateway owns execution.
- No generic tools (`run_command`, `run_sql`, `curl`) exposed — ever.
- Tool code is portable across environments; executor backends are swapped via config.

---

## Components

```
backend/gateway_mcp/
├── pyproject.toml                       # own deps
├── main.py                              # FastAPI app + MCP HTTP/SSE transport
├── configs/
│   ├── local.yaml
│   ├── qa.yaml
│   └── prod.yaml
├── core/
│   ├── config.py                        # env + service map loader
│   ├── auth.py                          # service token + user id validation
│   ├── permissions.py                   # risk_level → env/role gate
│   ├── approval.py                      # bridge to Phase 3 ApprovalService
│   ├── audit.py                         # structured logger (stdout + Langfuse)
│   ├── errors.py                        # GatewayError hierarchy
│   ├── middleware.py                    # request pipeline assembly
│   └── executors/
│       ├── base.py                      # ExecutorBackend protocol
│       ├── docker_exec.py               # local
│       ├── k8s_exec.py                  # qa
│       ├── job_runner.py                # prod
│       └── mock.py                      # tests (wraps MockBRSToolExecutor)
├── tools/
│   ├── __init__.py                      # ToolRegistry
│   ├── base.py                          # Tool dataclass + metadata
│   ├── clubs.py                         # create_club, get_club_by_name, verify_club_setup
│   ├── config.py                        # get_club_config
│   ├── users.py                         # create_admin_user
│   └── api.py                           # call_internal_api
├── scripts/
│   └── smoke_setup_club.py              # full-workflow MCP smoke test
└── tests/
    ├── unit/
    ├── integration/
    └── e2e/                             # opt-in via GATEWAY_E2E=1
```

**Reuse from Phase 2 (imported across package boundary):**
- `app.services.brs_tools.schemas` — structured output types
- `app.services.brs_tools.parser.BRSToolOutputParser` — stdout → pydantic
- `app.services.brs_tools.registry.BRSToolRegistry` — CLI templates

**Reuse from Phase 3:**
- `app.services.approval_service.ApprovalService` — for `requires_approval=true` tools

**File responsibility invariants:**
- `core/executors/*.py` are the **only** files that start a subprocess or open a raw HTTP socket.
- `tools/*.py` never import subprocess/HTTP directly — only `core/`.
- `core/middleware.py` is the only place the request pipeline is defined — tools don't assemble their own middleware.

---

## Executor Backend Interface

```python
class ExecutorBackend(Protocol):
    async def run_command(
        self, service: str, argv: list[str], timeout: int
    ) -> ExecResult: ...

    async def submit_command(
        self, service: str, argv: list[str], timeout: int
    ) -> JobHandle: ...

    async def query_db(
        self, db: str, query: str, params: list
    ) -> list[dict]: ...

    async def call_http(
        self, service: str, method: str, path: str, body: dict | None
    ) -> HTTPResult: ...


class JobHandle:
    job_id: str
    async def status(self) -> JobStatus: ...         # queued|running|succeeded|failed|cancelled
    async def stream(self) -> AsyncIterator[JobEvent]: ...
    async def result(self) -> ExecResult: ...
    async def cancel(self) -> None: ...
```

- `docker_exec`, `k8s_exec`, `job_runner` each implement both `run_command` (simple await) and `submit_command` (handle-based).
- MVP tool handlers use `run_command`. Long-running prod jobs can opt into `submit_command` without touching other backends.
- `service` is a **logical name** (`teesheet`, `admin_api`, `mysql`) resolved to concrete target (container, k8s pod, job template) via per-env config.

---

## Environment Config

```yaml
# backend/gateway_mcp/configs/local.yaml
env: local
executor_backend: docker_exec
services:
  teesheet:   { container: brs-teesheet }
  admin_api:  { url: http://localhost:8100 }
  config_api: { url: http://localhost:8101 }
  mysql:      { container: brs-mysql, db: brs }
  mongo:      { container: brs-mongo, db: brs }
audit:
  stdout: true
  langfuse: true
```

```yaml
# backend/gateway_mcp/configs/qa.yaml
env: qa
executor_backend: k8s_exec
services:
  teesheet:   { k8s_namespace: brs-qa, pod_selector: app=teesheet }
  admin_api:  { url: https://admin-api.brs.qa.internal }
  config_api: { url: https://config-api.brs.qa.internal }
  mysql:      { k8s_namespace: brs-qa, pod_selector: app=mysql, db: brs }
  mongo:      { k8s_namespace: brs-qa, pod_selector: app=mongo, db: brs }
audit:
  stdout: true
  langfuse: true
```

```yaml
# backend/gateway_mcp/configs/prod.yaml
env: prod
executor_backend: job_runner
services:
  teesheet:   { job_template: brs-teesheet-command }
  admin_api:  { url: https://admin-api.brs.prod.internal }
  config_api: { url: https://config-api.brs.prod.internal }
  mysql:      { job_template: brs-mysql-readonly-query, db: brs }
  mongo:      { job_template: brs-mongo-readonly-query, db: brs }
audit:
  stdout: true
  langfuse: true
```

Loaded by `GATEWAY_ENV=local|qa|prod`. Secrets are **references** (env var names), never values.

---

## MVP Tool Contracts

Each tool declares: `name`, `description`, `input_schema`, `output_schema`, `risk_level`, `allowed_environments`, `requires_approval`, `timeout_seconds`, `handler`, `audit_metadata`.

### 3.1 `create_club`
| | |
|---|---|
| risk_level | `low_write` |
| allowed_envs | `[local, dev]` |
| requires_approval | `false` |
| timeout_seconds | 120 |
| input | `{ name, country (ISO 3166-1 a2), timezone (IANA), currency (ISO 4217) }` |
| executes | `docker exec brs-teesheet ./bin/teesheet new-club <args>` |
| output | `{ club_id, club_name, database_name, created_at }` |

### 3.2 `get_club_by_name`
| | |
|---|---|
| risk_level | `read` |
| allowed_envs | `[local, dev, qa, prod]` |
| requires_approval | `false` |
| timeout_seconds | 15 |
| input | `{ name }` |
| executes | `query_db` on `mysql`: `SELECT id,name,country,timezone,currency,created_at FROM clubs WHERE name=?` |
| output | `{ club_id, name, country, timezone, currency, created_at }` or `null` |

### 3.3 `get_club_config`
| | |
|---|---|
| risk_level | `read` |
| allowed_envs | `[local, dev, qa, prod]` |
| requires_approval | `false` |
| timeout_seconds | 15 |
| input | `{ club_id }` |
| executes | `call_http` GET `config_api` `/configs/{club_id}` |
| output | `{ club_id, modules: [str], settings: dict, version: int }` |

### 3.4 `create_admin_user`
| | |
|---|---|
| risk_level | `medium_write` |
| allowed_envs | `[local, dev]` (prod gated with approval in later phase) |
| requires_approval | `false` (MVP); `true` for staging/prod later |
| timeout_seconds | 60 |
| input | `{ club_id, email, role: admin\|superuser }` |
| executes | `docker exec brs-teesheet ./bin/teesheet update-superusers <args>` |
| output | `{ user_id, club_id, email, role, created_at }` |
| idempotency | handler checks for existing admin with same `(club_id, email)` via read-path and returns existing record on match |

### 3.5 `call_internal_api`
| | |
|---|---|
| risk_level | `medium_write` |
| allowed_envs | `[local, dev]` |
| requires_approval | `false` (MVP) |
| timeout_seconds | 30 |
| input | `{ club_id, operation: enable_required_features }` (enum — not free-form path/body) |
| executes | `call_http` POST `admin_api` `/clubs/{club_id}/features` with a body the gateway owns |
| output | `{ club_id, enabled_features: [str] }` |

### 3.6 `verify_club_setup`
| | |
|---|---|
| risk_level | `read` |
| allowed_envs | `[local, dev, qa, prod]` |
| requires_approval | `false` |
| timeout_seconds | 20 |
| input | `{ club_id }` |
| executes | composite: `get_club_by_name` + `get_club_config` + admin-user existence check |
| output | `{ club_exists: bool, config_valid: bool, has_admin: bool, features_enabled: [str], issues: [str] }` |

**Cross-cutting contract:**
- Input validated by Pydantic before handler runs. Invalid → `ValidationError`, never reaches executor.
- Output is a typed model serialised to JSON.
- Failures map to `GatewayError` with a bounded `code` set (see §Errors).

---

## Middleware Chain (Final)

```
request
  → start audit           # earliest — denied/invalid requests are also audited
  → auth                  # service token + X-User-Id
  → schema validate       # pydantic input validation
  → env gate              # tool.allowed_environments vs GATEWAY_ENV
  → permission check      # risk_level vs caller role
  → approval check        # tool.requires_approval → ApprovalService
  → handler               # tool.handler(input) → output
  → finish audit          # update record with status, duration, error code
```

Failure at any stage writes an audit record with `status=denied|failure` and returns a `GatewayError`. Success writes `status=success`.

---

## Permissions

**Auth:**
- Service-to-service: `GATEWAY_SERVICE_TOKEN` bearer (`.env` local; Vault / k8s secret in qa/prod).
- Caller identity: `X-User-Id` header propagated from backend chat API. Used for audit + role lookup. Not the auth source.
- Open WebUI: authenticates to backend, backend calls gateway — Open WebUI does not reach gateway directly.

**Role model (MVP):**
- `read` risk: any authenticated caller.
- `low_write`, `medium_write`, `high_write`: caller must be in env-configured operator allowlist (`GATEWAY_OPERATOR_USER_IDS`).
- Role table in DB: deferred to later phase.

**Approval:**
- When `tool.requires_approval=true`, gateway calls `ApprovalService.request_approval(...)` with a redacted payload, then raises `ApprovalRequired`. The workflow orchestrator already handles `WAITING_APPROVAL` state (Phase 3). Gateway does not own approval UX; it produces the signal.
- MVP has **zero** tools with `requires_approval=true`. Hook is wired, not exercised.

---

## Audit

One record per request, emitted at start (incomplete) and updated at finish:

```json
{
  "audit_id": "uuid",
  "correlation_id": "uuid",
  "ts_start": "2026-05-08T14:30:00Z",
  "ts_end": "2026-05-08T14:30:01.234Z",
  "env": "local",
  "user_id": "42",
  "tool_name": "create_club",
  "input_hash": "sha256:…",
  "input_redacted_keys": ["password", "api_token"],
  "risk_level": "low_write",
  "status": "success|failure|denied",
  "error_code": "permission_denied|env_restricted|validation_failed|container_unavailable|upstream_error|subprocess_timeout|approval_required|null",
  "duration_ms": 1234,
  "executor_backend": "docker_exec",
  "downstream_ref": "container:brs-teesheet exit=0"
}
```

**Sink v1 (MVP):** structured JSON to stdout. Consumed by Langfuse (span per tool call) through the existing callback handler.
**Sink v2 (later):** append to `gateway_audit_log` table in Postgres for queryability.

**Redaction:** fixed key list (`password`, `api_token`, `secret`, `*_hash`, `authorization`). Values replaced with `"<redacted>"`. Input hashing is for correlation; raw input never logged verbatim.

---

## Errors

Every rejection or failure returns a structured `GatewayError`:

```json
{
  "error": {
    "code": "permission_denied | env_restricted | validation_failed | container_unavailable | upstream_error | subprocess_timeout | approval_required",
    "message": "human-safe message; never includes stdout/stderr verbatim",
    "audit_id": "uuid",
    "retryable": false
  }
}
```

- Stdout/stderr captured for debugging land in the audit log, **not** the agent response.
- `retryable=true` only on `upstream_error` for read tools (see Retries).

---

## Timeouts & Retries

**Timeouts (three layers, all required):**
1. MCP client: 30s default (per `mcp_config.py`).
2. Gateway handler: per-tool `timeout_seconds` (see §Tool Contracts).
3. Executor: hard kill at handler budget + 5s grace.

Any timeout → `subprocess_timeout`, non-retryable.

**Retries:**
- Writes (`low_write`, `medium_write`, `high_write`): **no retries.** Fail loud, caller decides.
- Reads: retry once on `upstream_error` with 500ms backoff.
- Executor-level retries disabled in MVP (requires verify-after-write, not built).

---

## Observability

- **Correlation IDs:** `correlation_id` from client; `audit_id` generated by gateway. Both in every log line, audit record, and Langfuse span metadata.
- **Langfuse:** one span per tool call, named `gateway_mcp.{tool_name}`, with redacted input, full output, `{ audit_id, env, executor_backend, duration_ms, risk_level }` metadata. Spans nest inside workflow traces when `workflow_run_id` is in context.
- **Endpoints:**
  - `GET /health` — process up (always 200).
  - `GET /ready` — dependency check (executor backend reachable + service URLs reachable). 503 on failure. K8s readiness probe target.
  - `GET /tools` — debugging; canonical list is MCP `tools/list`.
- **Explicitly not in MVP:** circuit breakers, Prometheus `/metrics`, OTEL propagation. Revisit on pain.

---

## Integration with Existing System

1. **Register Gateway MCP in allowlist** (`backend/app/config/mcp_config.py`). One entry per env (`DEVELOPMENT_SERVERS`, `STAGING_SERVERS`, `PRODUCTION_SERVERS`).
2. **Workflow orchestrator routing:** `WorkflowOrchestrator._create_step_node` checks `MCPToolRegistry` for `tool:` name; if found under `gateway-mcp`, calls via MCP. Else falls back to `brs_tools` (Phase 2 legacy path).
3. **Onboarding template migration:** update `create_teesheet_onboarding_template` to reference business-level tool names (`create_club`, `create_admin_user`) instead of raw BRS names. Old templates stay runnable on the legacy path.
4. **Chat API:** no change. `MCPToolRegistry` picks up gateway tools automatically once registered.
5. **Open WebUI:** unchanged — Open WebUI → backend chat API → agent → `MCPToolRegistry` → Gateway MCP.

---

## Local Infrastructure

```yaml
# infrastructure/docker-compose.brs.yml — BRS stack only; gateway runs on host
services:
  brs-mysql:
    image: mysql:8
    container_name: brs-mysql
    environment: { MYSQL_ROOT_PASSWORD: ${BRS_DB_PASSWORD} }
    ports: ["3306:3306"]
    volumes: [brs-mysql-data:/var/lib/mysql]

  brs-mongo:
    image: mongo:7
    container_name: brs-mongo
    ports: ["27017:27017"]
    volumes: [brs-mongo-data:/data/db]

  brs-teesheet:
    image: brs-teesheet:local
    container_name: brs-teesheet
    depends_on: [brs-mysql]
    volumes: [../../../brs-teesheet:/app]
    working_dir: /app
    command: ["tail", "-f", "/dev/null"]

  brs-admin-api:
    image: brs-admin-api:local
    container_name: brs-admin-api
    depends_on: [brs-mysql]
    ports: ["8100:8000"]

  brs-config-api:
    image: brs-config-api:local
    container_name: brs-config-api
    depends_on: [brs-mongo]
    ports: ["8101:8000"]

volumes:
  brs-mysql-data:
  brs-mongo-data:
```

**Bring-up:**
```bash
# One-time: clone BRS repos as siblings
git clone git@github.com:GolfNowEng/brs-teesheet.git ../brs-teesheet
git clone git@github.com:GolfNowEng/brs-admin-api.git ../brs-admin-api
git clone git@github.com:GolfNowEng/brs-config-api.git ../brs-config-api

# Per dev session
docker compose -f infrastructure/docker-compose.brs.yml up -d
python -m gateway_mcp.main     # host process on :8090
```

**Prerequisite to flag in the plan:** each BRS repo needs a dev Dockerfile. If upstream lacks one, add a minimal dev-only override in `infrastructure/dockerfiles/` and build with `-f` flag rather than modifying upstream.

**No docker socket mount anywhere.** Local gateway runs on the host and uses the host `docker` CLI. QA uses `k8s_exec` via kubeconfig. Prod uses `job_runner` via workflow API.

---

## Testing Strategy

| Tier | Location | External deps | When |
|---|---|---|---|
| Unit | `tests/unit/` | None; mocked `ExecutorBackend` | every commit |
| Integration | `tests/integration/` | In-process FastAPI + mock executor | every commit |
| E2E | `tests/e2e/` (opt-in `GATEWAY_E2E=1`) | Full docker-compose BRS stack | CI job with docker; not per PR |
| Smoke | `scripts/smoke_setup_club.py` | Configurable per env | post-deploy check |

**Unit tests cover:**
- Each tool module (mocked executor).
- Middleware chain isolated: auth fail, env denial, schema violation, permission deny, approval required, handler exception → correct `GatewayError` + audit record.
- Each executor backend with its own client mocked.

**Integration tests cover:**
- MCP `tools/list` and `tools/call` compliance for all 6 MVP tools.
- Full club-setup workflow replay: `create_club` → `get_club_by_name` → `create_admin_user` → `call_internal_api` → `verify_club_setup`. Assert end state + audit sequence.

**E2E tests cover:**
- Bring up `docker-compose.brs.yml`, run gateway on host, run club-setup end-to-end against real containers.
- Assert final state in real MySQL (`SELECT * FROM clubs`) and Mongo (config exists).

**Smoke script:**
- Works against any backend via `GATEWAY_EXECUTOR_BACKEND=docker_exec|k8s_exec|job_runner|mock`.
- Exercises all 6 tools in order, prints pass/fail.
- Run after qa/prod deploy as a plumbing check.

---

## Acceptance Criteria

MVP ships when all of the following hold:

- [ ] Gateway MCP process starts on `:8090` and responds to MCP `tools/list` with the 6 tools.
- [ ] Each of the 6 tools has a passing unit test.
- [ ] Middleware order verified by integration test (audit record emitted for auth/env/permission denials, not only successes).
- [ ] Full club-setup workflow passes as an integration test against the mock executor.
- [ ] Full club-setup workflow passes as an E2E test against real BRS containers under `docker_exec`.
- [ ] Backend `MCPToolRegistry` lists Gateway MCP tools.
- [ ] Onboarding workflow template updated to call `create_club` (not `brs_teesheet_init`) and passes its existing integration tests.
- [ ] No generic tools (`run_command`, `run_sql`, free-form `curl`) exposed.
- [ ] Every tool call produces an audit record visible in Langfuse.
- [ ] `docker_exec`, `k8s_exec`, and `job_runner` executors all have unit tests; integration-tested only `docker_exec` and `mock` in MVP.
- [ ] Config files for local/qa/prod present; secrets referenced, not stored.

---

## Out of Scope (Deferred)

- Tools beyond the 6 MVP set (green fee rates, booking rules, module management).
- Role table in DB (MVP uses env allowlist).
- `gateway_audit_log` table (MVP is stdout + Langfuse).
- Circuit breakers, Prometheus metrics, OTEL.
- Open WebUI direct connection to Gateway MCP.
- Per-tool cancellation UX (handle exists, no UX).
- Staging/prod `requires_approval=true` tool config (hook wired, not enabled).

---

## Open Questions (Resolve in Plan Phase, Not Design)

- Exact body shape for `call_internal_api(operation=enable_required_features)` — depends on brs-admin-api endpoint contract. Plan will include a small research task to confirm.
- Whether dev Dockerfiles need to be contributed back upstream to the BRS repos or held as local overrides.
- Whether the `docker` Python SDK or shelling out to the `docker` CLI is a better `docker_exec` backend. Plan will prototype both in a spike task.

---

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| BRS repos lack dev Dockerfiles | medium | Prerequisite task to write minimal overrides |
| `./bin/teesheet new-club` has side effects we don't anticipate (e.g. external service calls) | medium | E2E tests in a disposable DB; tear-down + reset between runs |
| `k8s_exec` and `job_runner` backends untestable before QA/prod infra is known | high | Unit test only; treat as interface-compatible placeholders until infra exists |
| MCP protocol version mismatch between server and existing client | low | Pin `mcp` package version; add protocol compatibility test |
| Docker `exec` latency on macOS adds test flakiness | low | Generous timeouts in E2E; mark E2E tests as slow-tier |

---

**End of spec.**
