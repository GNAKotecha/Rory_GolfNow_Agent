# Gateway MCP — Design Spec

**Status:** Draft for review
**Date:** 2026-05-08 (amended same day: external integrations + OAuth)
**Phase:** 4 (supersedes the former Phase 4 plan; Production Hardening becomes Phase 5)
**Related:** `GATEWAY_MCP.md` (root), Phase 2 BRS Tools, Phase 3 Approval Service

---

## Goal

Build a **Gateway MCP** server that exposes business-level tools (`create_club`, `create_admin_user`, `verify_club_setup`, `create_ticket`, …) to the agent. The server is the policy and execution boundary: every call is authenticated, permission-checked, env-gated, scope-checked, approval-gated where required, and audited. No raw shell, SQL, HTTP, or third-party tokens escape to the agent.

Gateway also serves as the **single integration surface** for external systems (Atlassian, Github, Slack, …). External MCP servers and direct REST APIs are plugged in as `ExecutorBackend` implementations so they inherit the same policy, OAuth, RBAC, and audit guarantees as internal BRS tools.

MVP success = the agent can (a) set up a club locally through structured MCP tools, and (b) log follow-up work to Jira through OAuth-authenticated, scope-checked tools.

---

## Locked Decisions

| Decision | Choice |
|---|---|
| Relationship to Phase 2 `brs_tools` | **Wrap.** Reuse registry, schemas, parser. Only the executor swaps. |
| MVP tool surface | 9 tools: 6 BRS + 3 Atlassian (see §3) |
| Internal execution | Docker exec locally, `kubectl exec` in QA, workflow-API / job runner in prod |
| External execution | Gateway proxies community/external MCP servers via `mcp_proxy` backend; direct REST via `http_rest` backend |
| External credentials | Unified subsystem handles **both** OAuth (Atlassian) and **user-pasted PAT** (Github, future). Single encrypted `external_credentials` table. |
| Atlassian MCP endpoint | `https://mcp.atlassian.com/v1/mcp` (official remote MCP, OAuth-authenticated) |
| Github MCP endpoint | `https://api.githubcopilot.com/mcp/` (official remote MCP, PAT-authenticated). Infra wired in Phase 4; tools deferred. |
| First external integration | Atlassian / Jira (3 tools). Github is wiring-only in Phase 4. |
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
│     → permission check → scope check → approval check          │
│     → handler → finish audit                                   │
│                                                                │
│  Tool router:                                                  │
│    BRS:       create_club · get_club_by_name · get_club_config │
│               create_admin_user · call_internal_api            │
│               verify_club_setup                                │
│    Atlassian: create_ticket · get_ticket_status · add_comment  │
│                                                                │
│  OAuth + PAT subsystem: credential_store · refresh · providers │
└─────────┬───────────────────────┬──────────────────────────────┘
          │                       │
          ▼                       ▼
   ExecutorBackend          External credentials (DB, encrypted)
   ┌──────────────┐
   │ docker_exec  │ ─────► brs-teesheet · mysql · mongo (local)
   │ k8s_exec     │ ─────► k8s pods in QA
   │ job_runner   │ ─────► workflow API in prod
   │ mcp_proxy    │ ─────► Atlassian MCP (OAuth) · Github MCP (PAT)
   │ http_rest    │ ─────► direct external REST (fallback)
   └──────────────┘
```

**Principles:**
- The agent describes intent; the gateway owns execution.
- No generic tools (`run_command`, `run_sql`, `curl`, raw upstream tool names) exposed — ever.
- Tool code is portable across environments; executor backends are swapped via config.
- External systems get the same policy layer as internal ones. User credentials (OAuth tokens or PATs) never leave the gateway.

---

## Components

```
backend/gateway_mcp/
├── pyproject.toml                       # own deps
├── main.py                              # FastAPI app + MCP HTTP/SSE transport + OAuth routes
├── configs/
│   ├── local.yaml
│   ├── qa.yaml
│   └── prod.yaml
├── core/
│   ├── config.py                        # env + service map + oauth provider config
│   ├── auth.py                          # service token + user id validation
│   ├── permissions.py                   # risk_level → env/role gate
│   ├── scopes.py                        # required_scopes → token scope check
│   ├── approval.py                      # bridge to Phase 3 ApprovalService
│   ├── audit.py                         # structured logger (stdout + Langfuse)
│   ├── errors.py                        # GatewayError hierarchy
│   ├── middleware.py                    # request pipeline assembly
│   ├── credentials/
│   │   ├── store.py                     # encrypted DB-backed credential store (OAuth + PAT)
│   │   ├── oauth_flow.py                # authz code + PKCE, exchange, refresh
│   │   ├── pat_flow.py                  # PAT validation + storage (user-pasted)
│   │   └── providers/
│   │       ├── base.py                  # CredentialProvider protocol
│   │       ├── atlassian.py             # Atlassian Cloud (OAuth)
│   │       └── github.py                # Github (PAT; infra-only in Phase 4)
│   └── executors/
│       ├── base.py                      # ExecutorBackend protocol
│       ├── docker_exec.py               # local BRS
│       ├── k8s_exec.py                  # qa BRS
│       ├── job_runner.py                # prod BRS
│       ├── mcp_proxy.py                 # upstream MCP server client (e.g. Atlassian MCP)
│       ├── http_rest.py                 # direct external REST (fallback)
│       └── mock.py                      # tests
├── tools/
│   ├── __init__.py                      # ToolRegistry
│   ├── base.py                          # Tool dataclass + metadata (incl. required_scopes)
│   ├── clubs.py                         # create_club, get_club_by_name, verify_club_setup
│   ├── config.py                        # get_club_config
│   ├── users.py                         # create_admin_user
│   ├── api.py                           # call_internal_api
│   └── jira.py                          # create_ticket, get_ticket_status, add_comment
├── scripts/
│   ├── smoke_setup_club.py              # full BRS workflow smoke test
│   └── smoke_jira.py                    # OAuth + Atlassian smoke test
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

**New DB migration (Alembic):**
- `external_credentials` table:
  `(id, user_id, provider, credential_type, secret_enc, refresh_token_enc, scope, expires_at, metadata (jsonb), revoked_at, created_at, updated_at)`
- `credential_type` is an enum: `oauth | pat`
- `refresh_token_enc`, `scope`, `expires_at` nullable (not applicable to PATs)
- Composite unique index on `(user_id, provider)` (one credential per provider per user)

**File responsibility invariants:**
- `core/executors/*.py` are the **only** files that start a subprocess, open a raw HTTP socket, or connect to an upstream MCP server.
- `core/credentials/*.py` are the **only** files that touch provider secrets. Tools see them only via injected `UserContext`.
- `tools/*.py` never import subprocess/HTTP directly — only `core/`.
- `core/middleware.py` is the only place the request pipeline is defined.

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

## External Integrations & Credentials

Two executor backends handle external systems:

### `mcp_proxy` backend
Gateway acts as an MCP client to another MCP server and re-exposes that server's capabilities under Gateway's own policy layer.

```python
class MCPProxyBackend(ExecutorBackend):
    def __init__(self, upstream_name: str, upstream_url: str, auth_mode: str):
        self.client = MCPClient(upstream_url)  # reuses existing app.services.mcp_client
        self.auth_mode = auth_mode             # "oauth" | "pat"

    async def run_command(self, service, argv, timeout, user_ctx):
        tool_name, args = argv[0], argv[1:]
        credential = await user_ctx.credential(service)  # resolves OAuth or PAT
        return await self.client.call_tool(
            tool_name, args, timeout=timeout, auth=credential.as_bearer()
        )
```

- Upstream MCP tool names (e.g. `atlassian_issues_create_v3`) are **never** visible to the agent. Gateway tools (`create_ticket`) translate between Gateway's business schema and the upstream tool's schema.
- Transparent credential injection: the middleware resolves the right credential type for the provider and hands a ready-to-use bearer to the backend.

**Pinned MCP endpoints:**
| Provider | URL | Auth |
|---|---|---|
| Atlassian | `https://mcp.atlassian.com/v1/mcp` | OAuth (PKCE) |
| Github | `https://api.githubcopilot.com/mcp/` | PAT (user-pasted) |

Github MCP is wired in Phase 4 (config, provider, executor, store, UI) but no Github **tools** are implemented in MVP — those come in a later phase.

### `http_rest` backend
For external systems without an MCP server. Thin HTTP client with per-tool allowlisting of (host, method, path pattern). No free-form URL access.

```python
class HTTPRestBackend(ExecutorBackend):
    async def call_http(self, service, method, path, body, user_ctx):
        endpoint = self.allowlist.resolve(service, method, path)  # raises if not allowlisted
        credential = await user_ctx.credential(service) if self.requires_auth else None
        return await self.client.request(method, endpoint, body=body, auth=credential)
```

### Credentials subsystem

Unified store handles both OAuth tokens and user-pasted PATs.

**Storage (`external_credentials` table):**
| column | type | notes |
|---|---|---|
| `id` | serial PK | |
| `user_id` | int FK users.id | |
| `provider` | str | `atlassian`, `github`, … |
| `credential_type` | enum(`oauth`, `pat`) | |
| `secret_enc` | bytes | AES-GCM; the access_token (OAuth) or PAT (Github) |
| `refresh_token_enc` | bytes nullable | OAuth only |
| `scope` | str nullable | OAuth: space-separated scope list. PAT: null (scopes are inside the token and validated by probing upstream). |
| `expires_at` | timestamptz nullable | OAuth only; PATs assumed non-expiring unless user set expiry |
| `metadata` | jsonb | per-provider: e.g. Atlassian `cloud_id`, Github `user_login`, scope strings reported by validation probe |
| `revoked_at` | timestamptz nullable | set when user disconnects or upstream reports 401/403 |
| `created_at`, `updated_at` | timestamptz | |

Composite unique index on `(user_id, provider)`. Encryption key from env (`GATEWAY_CREDENTIAL_ENCRYPTION_KEY`) — Vault / k8s secret in qa/prod.

### Flow A: OAuth (Atlassian)

```
1. User clicks "Connect Jira" in Open WebUI
2. Frontend → backend GET /api/credentials/atlassian/authorize
   → backend generates PKCE verifier + state, stores in session
   → backend returns https://auth.atlassian.com/authorize?... with client_id + PKCE challenge + state
3. Frontend redirects browser to Atlassian authz URL
4. User consents in Atlassian, Atlassian redirects to
   → backend GET /api/credentials/atlassian/callback?code=&state=
   → backend validates state, exchanges code + PKCE verifier for tokens
   → backend probes Atlassian for cloud_id, stores in metadata
   → encrypts and stores in external_credentials (credential_type=oauth)
   → redirects browser back to Open WebUI
5. Subsequent tool calls transparently use the stored token
```

**Refresh:** `credentials.store.get(user_id, "atlassian")` checks `expires_at`; if expiring within 60s, refreshes transparently using `refresh_token_enc` and updates the record. Concurrent refresh serialised with an advisory lock (`pg_advisory_lock`) keyed by `(user_id, provider)` to prevent thundering-herd refresh. Refresh failures set `revoked_at` and raise `token_refresh_failed` — caller must re-authorize.

### Flow B: PAT (Github)

```
1. User clicks "Connect Github" in Open WebUI
2. Frontend opens a modal with:
   - Link to https://github.com/settings/tokens/new
     pre-filled with recommended scopes (e.g. repo, read:user) if possible via query params
   - Paste field for the PAT
   - "Save" button
3. Frontend POST /api/credentials/github/pat  { pat: "ghp_..." }
4. Backend validates the PAT:
   - GET https://api.github.com/user using PAT → must 200
   - GET https://api.github.com/user → extracts user_login, stored in metadata
   - Validates scope coverage of configured default_required_scopes
   - If validation fails → 400 with actionable error
5. Backend encrypts and stores (credential_type=pat, refresh_token_enc=null, expires_at=null if not set)
6. Subsequent tool calls use the stored PAT
```

**No refresh for PATs.** On upstream 401/403, backend marks `revoked_at` and responds with `credential_missing` + `reconnect_url` pointing at the reconnect modal.

### Credential routes (in main backend)

Routes live in `backend/app/api/credentials.py` (not Gateway — Gateway has no session). Backend stores credentials; Gateway reads via shared DB access.

- `GET  /api/credentials/atlassian/authorize` — start OAuth flow
- `GET  /api/credentials/atlassian/callback`  — finish OAuth flow
- `POST /api/credentials/github/pat`          — store a user-pasted PAT
- `DELETE /api/credentials/{provider}`        — user disconnects, sets `revoked_at`
- `GET  /api/credentials`                     — list user's connected providers (without secrets) for UI

### Scope enforcement (middleware step)

Each tool declares `required_scopes`. Middleware resolution varies by credential type:

- **OAuth (Atlassian):** compare stored `scope` column to `required_scopes`. Missing → `insufficient_scope` with `reconnect_url` hint.
- **PAT (Github, later phase):** probe upstream (`GET /user` for scope headers) lazily — cache result on the credential record in `metadata`. Missing → `insufficient_scope`.

Never silently downgrades or calls with fewer scopes.

### Provider + upstream config

```yaml
# backend/gateway_mcp/configs/local.yaml (additions)
credentials:
  providers:
    atlassian:
      type: oauth
      client_id_env: ATLASSIAN_CLIENT_ID
      client_secret_env: ATLASSIAN_CLIENT_SECRET
      authz_url: https://auth.atlassian.com/authorize
      token_url: https://auth.atlassian.com/oauth/token
      default_scopes: ["read:jira-work", "write:jira-work"]
      redirect_uri: http://localhost:8000/api/credentials/atlassian/callback
    github:
      type: pat
      validate_url: https://api.github.com/user
      default_required_scopes: ["repo", "read:user"]
      token_creation_hint_url: https://github.com/settings/tokens/new
upstream_mcps:
  atlassian:
    url: https://mcp.atlassian.com/v1/mcp
    auth_mode: oauth
    provider: atlassian
  github:
    url: https://api.githubcopilot.com/mcp/
    auth_mode: pat
    provider: github
```

---

## MVP Tool Contracts

Each tool declares: `name`, `description`, `input_schema`, `output_schema`, `risk_level`, `allowed_environments`, `requires_approval`, `timeout_seconds`, `required_scopes` (external tools only), `handler`, `audit_metadata`.

### BRS Tools (6)

#### 3.1 `create_club`
| | |
|---|---|
| risk_level | `low_write` |
| allowed_envs | `[local, dev]` |
| requires_approval | `false` |
| timeout_seconds | 120 |
| input | `{ name, country (ISO 3166-1 a2), timezone (IANA), currency (ISO 4217) }` |
| executes | `docker exec brs-teesheet ./bin/teesheet new-club <args>` |
| output | `{ club_id, club_name, database_name, created_at }` |

#### 3.2 `get_club_by_name`
| | |
|---|---|
| risk_level | `read` |
| allowed_envs | `[local, dev, qa, prod]` |
| requires_approval | `false` |
| timeout_seconds | 15 |
| input | `{ name }` |
| executes | `query_db` on `mysql`: `SELECT id,name,country,timezone,currency,created_at FROM clubs WHERE name=?` |
| output | `{ club_id, name, country, timezone, currency, created_at }` or `null` |

#### 3.3 `get_club_config`
| | |
|---|---|
| risk_level | `read` |
| allowed_envs | `[local, dev, qa, prod]` |
| requires_approval | `false` |
| timeout_seconds | 15 |
| input | `{ club_id }` |
| executes | `call_http` GET `config_api` `/configs/{club_id}` |
| output | `{ club_id, modules: [str], settings: dict, version: int }` |

#### 3.4 `create_admin_user`
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

#### 3.5 `call_internal_api`
| | |
|---|---|
| risk_level | `medium_write` |
| allowed_envs | `[local, dev]` |
| requires_approval | `false` (MVP) |
| timeout_seconds | 30 |
| input | `{ club_id, operation: enable_required_features }` (enum — not free-form path/body) |
| executes | `call_http` POST `admin_api` `/clubs/{club_id}/features` with a body the gateway owns |
| output | `{ club_id, enabled_features: [str] }` |

#### 3.6 `verify_club_setup`
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

### Atlassian Tools (3)

All Atlassian tools share:
- `executor_backend: mcp_proxy` via upstream Atlassian MCP server
- `required_scopes` checked against stored user token before handler runs
- Per-user OAuth token injected transparently — tool handler code never touches tokens
- `allowed_envs: [local, dev, qa, prod]` — reads and low-risk writes; safe across envs
- On `token_refresh_failed` or missing token → `oauth_not_authorized` returned with a re-authorize hint

#### 3.7 `create_ticket`
| | |
|---|---|
| risk_level | `low_write` |
| allowed_envs | `[local, dev, qa, prod]` |
| requires_approval | `false` |
| required_scopes | `["write:jira-work"]` |
| timeout_seconds | 30 |
| input | `{ project_key (required), summary (required), description, issue_type (enum: Task\|Bug\|Story, default Task), labels: [str] }` |
| executes | `mcp_proxy.run_command(service="atlassian", argv=["create_issue", ...])` — upstream MCP receives project_key, summary, description, type |
| output | `{ ticket_id, ticket_key (e.g. GOLF-123), url, status, created_at }` |

#### 3.8 `get_ticket_status`
| | |
|---|---|
| risk_level | `read` |
| allowed_envs | `[local, dev, qa, prod]` |
| requires_approval | `false` |
| required_scopes | `["read:jira-work"]` |
| timeout_seconds | 15 |
| input | `{ ticket_key (e.g. GOLF-123) }` |
| executes | `mcp_proxy.run_command(service="atlassian", argv=["get_issue", ticket_key])` |
| output | `{ ticket_key, summary, status, assignee, updated_at, url }` or `null` if not found |

#### 3.9 `add_comment`
| | |
|---|---|
| risk_level | `low_write` |
| allowed_envs | `[local, dev, qa, prod]` |
| requires_approval | `false` |
| required_scopes | `["write:jira-work"]` |
| timeout_seconds | 20 |
| input | `{ ticket_key, comment_body (required, max 32KB) }` |
| executes | `mcp_proxy.run_command(service="atlassian", argv=["add_comment", ticket_key, body])` |
| output | `{ ticket_key, comment_id, author, created_at }` |

---

## Middleware Chain (Final)

```
request
  → start audit           # earliest — denied/invalid requests are also audited
  → auth                  # service token + X-User-Id
  → schema validate       # pydantic input validation
  → env gate              # tool.allowed_environments vs GATEWAY_ENV
  → permission check      # risk_level vs caller role
  → scope check           # external tools: required_scopes vs stored token scope
  → approval check        # tool.requires_approval → ApprovalService
  → handler               # tool.handler(input, user_ctx) → output
  → finish audit          # update record with status, duration, error code
```

Failure at any stage writes an audit record with `status=denied|failure` and returns a `GatewayError`. Success writes `status=success`.

`user_ctx` passed to handler carries `user_id`, injected OAuth token fetcher, correlation IDs. Tools never see raw tokens — they call `ctx.oauth_token("atlassian")` which goes through the token store + refresh.

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
    "code": "permission_denied | env_restricted | validation_failed | container_unavailable | upstream_error | subprocess_timeout | approval_required | insufficient_scope | credential_missing | token_refresh_failed",
    "message": "human-safe message; never includes stdout/stderr/tokens/PATs verbatim",
    "audit_id": "uuid",
    "retryable": false,
    "reconnect_url": "optional; returned for credential-related errors. For OAuth providers → the authz start URL. For PAT providers → the frontend reconnect modal URL."
  }
}
```

- Stdout/stderr/tokens/PATs captured for debugging land in the audit log with redaction, **not** the agent response.
- `retryable=true` only on `upstream_error` for read tools (see Retries).
- `reconnect_url` returned on `credential_missing`, `insufficient_scope`, `token_refresh_failed` so the frontend can prompt the user to reconnect cleanly (OAuth re-consent or PAT re-paste, depending on provider).
- `token_refresh_failed` only applies to OAuth providers; PAT providers never raise this code (they raise `credential_missing` with `revoked_at` set when the upstream rejects the token).

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
- Middleware chain isolated: auth fail, env denial, schema violation, permission deny, scope miss, approval required, handler exception → correct `GatewayError` + audit record.
- Each executor backend with its own client mocked (`docker_exec`, `k8s_exec`, `job_runner`, `mcp_proxy`, `http_rest`).
- OAuth subsystem: token encryption roundtrip, refresh at near-expiry, concurrent refresh serialization, refresh failure → `token_refresh_failed`.
- PAT subsystem: validation success (200 on `/user`) stores correctly; validation failure rejects with actionable 400; upstream 401 marks `revoked_at` and raises `credential_missing`.
- Scope check: missing scope → `insufficient_scope`; credential absent → `credential_missing`.

**Integration tests cover:**
- MCP `tools/list` and `tools/call` compliance for all 9 MVP tools.
- Full BRS club-setup workflow replay: `create_club` → `get_club_by_name` → `create_admin_user` → `call_internal_api` → `verify_club_setup`. Assert end state + audit sequence.
- Atlassian flow with mocked upstream MCP: `create_ticket` → `get_ticket_status` → `add_comment`. OAuth token injected from fixture; verify upstream received it and Gateway audited the call.
- OAuth routes: authz redirect, callback code exchange (mocked Atlassian token endpoint), token stored encrypted, reused on next tool call.
- PAT routes: `POST /api/credentials/github/pat` validates against mocked Github `/user` endpoint, stores encrypted, rejects invalid PAT with 400. (No Github tools exercised — infra-only.)

**E2E tests cover:**
- Bring up `docker-compose.brs.yml`, run gateway on host, run BRS club-setup end-to-end against real containers.
- Assert final state in real MySQL and Mongo.
- Atlassian E2E opt-in (`GATEWAY_E2E_ATLASSIAN=1`) against a real Atlassian test instance + real OAuth app — run manually, not in CI default.

**Smoke scripts:**
- `backend/gateway_mcp/scripts/smoke_setup_club.py` — BRS workflow, configurable executor backend.
- `backend/gateway_mcp/scripts/smoke_jira.py` — exercises all 3 Atlassian tools given a user_id with stored token. Prints pass/fail.

---

## Acceptance Criteria

MVP ships when all of the following hold:

- [ ] Gateway MCP process starts on `:8090` and responds to MCP `tools/list` with all 9 tools.
- [ ] Each of the 9 tools has a passing unit test.
- [ ] Middleware order verified by integration test (audit record emitted for auth / env / permission / scope / approval denials, not only successes).
- [ ] Full BRS club-setup workflow passes as an integration test against the mock executor.
- [ ] Full BRS club-setup workflow passes as an E2E test against real BRS containers under `docker_exec`.
- [ ] Backend `MCPToolRegistry` lists Gateway MCP tools.
- [ ] Onboarding workflow template updated to call `create_club` (not `brs_teesheet_init`) and passes its existing integration tests.
- [ ] No generic tools (`run_command`, `run_sql`, free-form `curl`, raw upstream MCP tool names) exposed.
- [ ] Every tool call produces an audit record visible in Langfuse.
- [ ] `docker_exec`, `k8s_exec`, `job_runner`, `mcp_proxy`, `http_rest` executors all have unit tests; integration-tested: `docker_exec`, `mock`, `mcp_proxy` (mocked upstream).
- [ ] Config files for local/qa/prod present; secrets referenced, not stored.
- [ ] `external_credentials` table migration applied; credentials stored encrypted at rest.
- [ ] OAuth authz + callback routes work for Atlassian (endpoint `https://mcp.atlassian.com/v1/mcp` is the pinned upstream); user can connect Jira from Open WebUI.
- [ ] PAT paste + validate routes work for Github; `https://github.com/settings/tokens/new` link surfaced in the UI; invalid PAT rejected with actionable error. Github MCP upstream (`https://api.githubcopilot.com/mcp/`) configured but no Github tools exposed.
- [ ] Atlassian tool calls transparently fetch + refresh the user's token; no token or PAT ever appears in Gateway responses or audit payloads.
- [ ] Missing scope returns `insufficient_scope` with a valid `reconnect_url`; missing credential returns `credential_missing`.

---

## Out of Scope (Deferred)

- Tools beyond the 9 MVP set (green fee rates, booking rules, module management; Github; Slack; other Atlassian tools like search/JQL).
- Role table in DB (MVP uses env allowlist).
- `gateway_audit_log` table (MVP is stdout + Langfuse).
- Circuit breakers, Prometheus metrics, OTEL.
- Open WebUI direct connection to Gateway MCP.
- Per-tool cancellation UX (handle exists, no UX).
- Staging/prod `requires_approval=true` tool config (hook wired, not enabled).
- Per-site OAuth tenants (currently one Atlassian Cloud site per user; multi-site selection deferred).
- Service-account OAuth fallback when no user is attached to the call (e.g. background workflow). MVP requires a user context for external calls.

---

## Open Questions (Resolve in Plan Phase, Not Design)

- Exact body shape for `call_internal_api(operation=enable_required_features)` — depends on brs-admin-api endpoint contract. Plan will include a small research task to confirm.
- Whether dev Dockerfiles need to be contributed back upstream to the BRS repos or held as local overrides.
- Whether the `docker` Python SDK or shelling out to the `docker` CLI is a better `docker_exec` backend. Plan will prototype both in a spike task.
- Whether `https://mcp.atlassian.com/v1/mcp` requires OAuth app registration in our GolfNow Atlassian tenant (client_id/secret provisioning). Plan includes a prerequisite task to register the app and document the redirect URI flow.
- Github PAT scope recommendations — the UI should pre-populate a suggested scope list when pointing the user to `https://github.com/settings/tokens/new`. Plan confirms the exact query-string parameters Github accepts for scope pre-selection.

---

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| BRS repos lack dev Dockerfiles | medium | Prerequisite task to write minimal overrides |
| `./bin/teesheet new-club` has side effects we don't anticipate (e.g. external service calls) | medium | E2E tests in a disposable DB; tear-down + reset between runs |
| `k8s_exec` and `job_runner` backends untestable before QA/prod infra is known | high | Unit test only; treat as interface-compatible placeholders until infra exists |
| MCP protocol version mismatch between server and existing client | low | Pin `mcp` package version; add protocol compatibility test |
| Docker `exec` latency on macOS adds test flakiness | low | Generous timeouts in E2E; mark E2E tests as slow-tier |
| Atlassian MCP (`mcp.atlassian.com/v1/mcp`) API stability | medium | Pin upstream MCP version header if the server supports it; smoke test in CI to detect drift |
| Credential leakage via logs / error messages | high-impact, low-prob | Strict redaction in audit; unit test asserting no `ghp_` / `Bearer ` substring appears in any response; secrets never logged |
| User pastes the wrong PAT (e.g. a classic token instead of a fine-grained one, or wrong scopes) | medium | Validation probe on `/user` + scope coverage check before storing; actionable error back to UI |
| Encryption key rotation complexity | medium | Design v1 accepts a single key; document rotation procedure in plan, implement dual-key read/single-key write when needed |
| Concurrent OAuth refresh storms on shared workflows | low | `pg_advisory_lock` per `(user_id, provider)` prevents thundering-herd refresh |
| User consent drift (user revokes scope in Atlassian) | medium | Token refresh failure surfaced as `oauth_not_authorized` with re-authorize URL; frontend guides user through reconnect |

---

**End of spec.**
