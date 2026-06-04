# Phase 4 Handover: Gateway MCP Implementation

**Last Updated:** 2026-06-04  
**Status:** ✅ COMPLETE - Milestones 1-10 (E2E & Smoke Tests deferred to prod validation phase)

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

### Milestone 5: BRS Tools ✅

**Completed:** 2026-05-10

**What was implemented:**

1. **tools/clubs.py** — Three club-related handlers
   - `create_club_handler`: Creates new clubs via BRS teesheet CLI
   - `get_club_by_name_handler`: Looks up clubs by name
   - `verify_club_setup_handler`: Verifies club setup is complete

2. **tools/config.py** — Configuration handler
   - `get_club_config_handler`: Retrieves club configuration settings

3. **tools/users.py** — User management handler
   - `create_admin_user_handler`: Creates admin/superuser accounts (idempotent)

4. **tools/api.py** — Internal API handler
   - `call_internal_api_handler`: Enum-controlled internal API operations
   - Currently supports `enable_required_features` operation
   - Operation mapping owned by Gateway (not free-form)

5. **tools/__init__.py** — Tool registry integration
   - `create_brs_registry()` factory function
   - `BRS_TOOLS` list for convenience
   - All 6 tools registered with proper metadata

6. **core/errors.py** — Added `ToolExecutionError`
   - For parsing/processing failures in tool handlers

7. **schemas.py** — Fixed `CreateClubOutput`
   - Added `alias="name"` to `club_name` field for JSON parsing
   - Added `populate_by_name=True` for flexibility

**Files created:**
- `backend/gateway_mcp/tools/clubs.py`
- `backend/gateway_mcp/tools/config.py`
- `backend/gateway_mcp/tools/users.py`
- `backend/gateway_mcp/tools/api.py`
- `backend/gateway_mcp/tests/unit/test_brs_tools.py`
- `backend/gateway_mcp/tests/integration/test_brs_workflow.py`

**Tests:**
- ✅ 21 unit tests in `test_brs_tools.py`
  - 3 create_club tests (success, failure, minimal output)
  - 3 get_club_by_name tests (found, not found exit code, not found JSON)
  - 3 verify_club_setup tests (complete, incomplete, nonexistent)
  - 3 get_club_config tests (success, not found, minimal)
  - 3 create_admin_user tests (success, idempotent, superuser)
  - 3 call_internal_api tests (success, fallback, failure)
  - 3 registration tests (all tools, handlers set, risk levels)
- ✅ 3 integration tests in `test_brs_workflow.py`
  - Full club-setup workflow (create → lookup → admin → features → verify)
  - Existing admin idempotent handling
  - Verification with issues
- All 113 gateway_mcp tests passing (no regressions)

**Tool Risk Levels:**
- READ: `get_club_by_name`, `verify_club_setup`, `get_club_config`
- LOW_WRITE: `create_club`
- MEDIUM_WRITE: `create_admin_user`, `call_internal_api`

**Tool Environment Restrictions:**
- Read tools: all environments (LOCAL, DEV, QA, PROD)
- Write tools: LOCAL, DEV, QA only (not PROD)

---

### Milestone 6: MCP Protocol Transport ✅

**Completed:** 2026-05-10

**What was implemented:**

1. **core/transport.py** — MCP HTTP transport layer
   - `MCPToolSchema`, `MCPToolsListRequest`, `MCPToolsListResponse` — MCP protocol models
   - `MCPToolCallRequest`, `MCPToolCallResponse` — Tool invocation models
   - `MCPErrorResponse` — Error response format
   - `create_mcp_router()` — Factory for FastAPI router with MCP routes:
     - `POST /mcp/tools/list` — List available tools with JSON schemas
     - `POST /mcp/tools/call` — Execute a tool through middleware pipeline
   - `_format_output()` — JSON serialization for tool output

2. **main.py** — Enhanced with MCP transport
   - MCP router included via `create_mcp_router(registry, pipeline)`
   - `/tools` debug endpoint now wired to ToolRegistry
     - Returns tool list with name, description, risk_level, requires_approval, allowed_environments
   - `/ready` enhanced with dependency checks:
     - Docker daemon availability check (`docker info`)
     - Service URL reachability check (HTTP GET /health)
     - Returns 503 if any check fails

3. **core/errors.py** — Added `ToolNotFoundError`
   - New `ErrorCode.TOOL_NOT_FOUND` with HTTP 404
   - `ToolNotFoundError` class for unknown tool requests

**Files created/modified:**
- `backend/gateway_mcp/core/transport.py` (new)
- `backend/gateway_mcp/main.py` (modified)
- `backend/gateway_mcp/core/errors.py` (modified)
- `backend/gateway_mcp/tests/unit/test_mcp_transport.py` (new)
- `backend/gateway_mcp/tests/integration/test_mcp_client.py` (new)

**Tests:**
- ✅ 20 unit tests in `test_mcp_transport.py`
  - 5 tools/list tests (all tools, schemas, cursor, empty registry)
  - 8 tools/call tests (execution, headers, missing tool, errors)
  - 4 MCP protocol compliance tests (response formats, request formats)
  - 3 edge case tests (no body, missing name, JSON serialization)
- ✅ 14 integration tests in `test_mcp_client.py`
  - 3 list tools tests (BRS tools, valid schemas, create_club schema)
  - 4 call tools tests (auth required, auth success, unknown tool, validation)
  - 2 workflow tests (list-then-call, correlation ID)
  - 3 debug endpoint tests (/tools, /health, /ready)
  - 2 error handling tests (gateway error format, internal error masking)
- All 147 gateway_mcp tests passing (no regressions)

**MCP Protocol Compliance:**

tools/list response:
```json
{
  "tools": [
    {
      "name": "create_club",
      "description": "Create a new golf club...",
      "inputSchema": {
        "type": "object",
        "properties": {...},
        "required": [...]
      }
    }
  ],
  "nextCursor": null
}
```

tools/call request:
```json
{
  "name": "create_club",
  "arguments": {
    "name": "Test Club",
    "country": "IE"
  }
}
```

tools/call response (success):
```json
{
  "content": [
    {
      "type": "text",
      "text": "{\"club_id\": \"1\", ...}"
    }
  ],
  "isError": false
}
```

tools/call response (error):
```json
{
  "content": [
    {
      "type": "text",
      "text": "Error: Tool 'xyz' not found"
    }
  ],
  "isError": true
}
```

---

### Milestone 7: Credential Subsystem ✅

**Completed:** 2026-05-11

**What was implemented:**

1. **Database Migration** — `external_credentials` table
   - Alembic migration `b2c3d4e5f607_add_external_credentials_table.py`
   - CredentialType enum (oauth, pat)
   - JSONB `provider_metadata` for provider-specific data
   - Indexes on user_id, provider, and revoked_at

2. **core/credentials/store.py** — Encrypted credential store
   - `CredentialEncryption` class using Fernet (AES-128-CBC + HMAC)
   - `generate_encryption_key()` for key generation
   - `Credential` dataclass with scope checking, expiry detection
   - `CredentialStore` class for DB operations:
     - `get_credential()` with auto-refresh logic
     - `store_oauth_credential()` / `store_pat_credential()`
     - `revoke_credential()` / `list_credentials()`
   - PostgreSQL advisory locks for concurrent refresh serialization

3. **core/credentials/providers/base.py** — Protocol definitions
   - `ProviderType` enum (oauth, pat)
   - `ProviderConfig`, `OAuthProviderConfig`, `PATProviderConfig` dataclasses
   - `OAuthProvider` / `PATProvider` protocols
   - `AuthorizationResult`, `TokenExchangeResult`, `PATValidationResult` dataclasses

4. **core/credentials/providers/generic.py** — Config-driven providers
   - `PROVIDER_PRESETS` dict with Atlassian and GitHub configurations
   - `ExtendedOAuthConfig` / `ExtendedPATConfig` dataclasses
   - `GenericOAuthProvider` class with PKCE support
   - `GenericPATProvider` class with scope parsing (header/body modes)
   - Factory functions: `create_oauth_provider()`, `create_pat_provider()`, `create_provider_from_config()`

5. **core/credentials/oauth_flow.py** — OAuth orchestration
   - `OAuthStateStore` class (in-memory, should be Redis in prod)
   - `OAuthFlow` class:
     - `start_authorization()` — generates URL with PKCE
     - `handle_callback()` — exchanges code for tokens
     - `refresh_token()` — refreshes expired tokens

6. **core/credentials/pat_flow.py** — PAT orchestration
   - `PATValidationError` dataclass
   - `PATStorageResult` dataclass
   - `PATFlow` class:
     - `validate_and_prepare()` — validates token and checks scopes
     - `get_token_creation_url()` — returns URL hint for creating tokens

7. **app/api/credentials.py** — REST API routes
   - `GET /api/credentials` — List user's credentials
   - `GET /api/credentials/providers` — List available providers
   - `GET /api/credentials/{provider}/authorize` — Start OAuth flow
   - `GET /api/credentials/{provider}/callback` — OAuth callback
   - `POST /api/credentials/{provider}/pat` — Store PAT
   - `DELETE /api/credentials/{provider}` — Revoke credential
   - `GET /api/credentials/{provider}/token-url` — Get token creation URL

8. **app/models/external_credential.py** — SQLAlchemy model
   - `ExternalCredential` model with encrypted columns
   - `is_expired`, `is_revoked`, `is_valid` properties
   - `scopes_list` property for parsing scope string

**Files created:**
- `backend/alembic/versions/b2c3d4e5f607_add_external_credentials_table.py`
- `backend/app/models/external_credential.py`
- `backend/app/api/credentials.py`
- `backend/gateway_mcp/core/credentials/__init__.py`
- `backend/gateway_mcp/core/credentials/store.py`
- `backend/gateway_mcp/core/credentials/oauth_flow.py`
- `backend/gateway_mcp/core/credentials/pat_flow.py`
- `backend/gateway_mcp/core/credentials/providers/__init__.py`
- `backend/gateway_mcp/core/credentials/providers/base.py`
- `backend/gateway_mcp/core/credentials/providers/generic.py`
- `backend/gateway_mcp/tests/unit/test_credentials.py`
- `backend/gateway_mcp/tests/integration/test_credentials_api.py`

**Tests:**
- ✅ 39 unit tests in `test_credentials.py`
  - 5 encryption tests (roundtrip, key generation, env var, invalid key)
  - 6 Credential tests (bearer, expiry states, scope checking)
  - 2 preset tests (atlassian, github)
  - 5 GenericOAuthProvider tests (PKCE, scopes, preset creation)
  - 5 GenericPATProvider tests (validation, scopes, preset creation)
  - 3 OAuthStateStore tests (store, consume, nonexistent)
  - 6 OAuthFlow tests (start, callback, refresh)
  - 6 PATFlow tests (success, errors, scopes)
- ✅ 17 integration tests in `test_credentials_api.py`
  - Provider listing
  - OAuth authorize (redirect, unknown, custom scopes)
  - OAuth callback (success, invalid state, error)
  - PAT storage (success, invalid, insufficient scopes)
  - Token URL retrieval
  - Credential revocation
  - Credential listing
  - Full OAuth flow simulation
- All 203 gateway_mcp tests passing (no regressions)

**Architecture decisions:**

1. **Config-driven generic providers** — Instead of per-provider files (atlassian.py, github.py), a single `generic.py` with `PROVIDER_PRESETS` dictionary. Add new providers by adding config entries.

2. **PKCE for OAuth** — Mandatory code_verifier/code_challenge for security.

3. **Scope parsing modes** — PAT providers can extract scopes from headers (GitHub's `X-OAuth-Scopes`) or body (generic JSON path).

4. **Advisory locks for refresh** — PostgreSQL pg_advisory_xact_lock prevents concurrent refresh races.

5. **Encryption key from env** — `GATEWAY_CREDENTIAL_ENCRYPTION_KEY` env var required, generated via `generate_encryption_key()`.

**Provider Presets:**

```python
PROVIDER_PRESETS = {
    "atlassian": {
        "type": "oauth",
        "display_name": "Atlassian (Jira/Confluence)",
        "authz_url": "https://auth.atlassian.com/authorize",
        "token_url": "https://auth.atlassian.com/oauth/token",
        "default_scopes": ["read:jira-work", "write:jira-work"],
        "use_pkce": True,
        # ...
    },
    "github": {
        "type": "pat",
        "display_name": "GitHub",
        "validate_url": "https://api.github.com/user",
        "required_scopes": ["repo"],
        "scope_parse_mode": "header",
        "scope_field": "X-OAuth-Scopes",
        # ...
    },
}
```

---

### Milestone 8: External Executor Backends ✅

**Completed:** 2026-05-11

**What was implemented:**

1. **core/executors/mcp_proxy.py** — Upstream MCP client with credential injection
   - `MCPToolCallResult` dataclass for call results
   - `CredentialFetcher` type alias for credential injection callback
   - `MCPProxyBackend` class:
     - `call_mcp_tool()` — Direct MCP tool invocation with arguments dict
     - `run_command()` — ExecutorBackend adapter (argv format)
     - Credential injection via configurable `CredentialFetcher` callback
     - Bearer token support (explicit or via credential store)
     - HTTP status handling: 200→success, 401→CredentialMissingError, 403→UpstreamError, 404→failure result
     - Connection/timeout error handling with proper exceptions

2. **core/executors/http_rest.py** — Direct REST with allowlist and credentials
   - Extended `AllowlistEntry` with optional `provider` field
   - Added `CredentialFetcher` support to `HTTPRestBackend`
   - `_get_credential()` async method for credential lookup
   - Full credential injection in `call_http()`:
     - Auth required? → Must have user_id → Fetch credential → Inject bearer
     - Proper `CredentialMissingError` on 401 responses
   - Connection/timeout error handling

3. **core/errors.py** — Enhanced `CredentialMissingError`
   - Added `provider` attribute for debugging/testing

4. **YAML configs** — Already had `upstream_mcps` section
   - `local.yaml`, `qa.yaml`, `prod.yaml` all configured
   - Atlassian MCP (OAuth) and GitHub MCP (PAT) defined

**Files modified:**
- `backend/gateway_mcp/core/executors/mcp_proxy.py` (rewritten)
- `backend/gateway_mcp/core/executors/http_rest.py` (enhanced)
- `backend/gateway_mcp/core/errors.py` (modified)
- `backend/gateway_mcp/tests/unit/test_executors.py` (extended)

**Tests:**
- ✅ 17 new tests for MCPProxyBackend:
  - Success, bearer token, 401/403/404/500 responses
  - run_command adapter (success/failure)
  - Unknown upstream, missing user_id
  - NotImplemented for submit/query_db/call_http
  - Connection error, timeout error
- ✅ 10 new tests for HTTPRestBackendWithCredentials:
  - Auth injection, public endpoint
  - Missing user_id, 401 response
  - Body/headers, allowlist violations
  - run_command not supported
  - Credential fetcher failure
  - Connection/timeout errors
- All 230 gateway_mcp tests passing (no regressions)

**Architecture:**

```
┌─────────────────────────────────────────────────────────────┐
│                      MCPProxyBackend                         │
├─────────────────────────────────────────────────────────────┤
│  settings.upstream_mcps["atlassian"]                         │
│       ↓                                                      │
│  _get_credential(user_id, provider)                         │
│       ↓ (via CredentialFetcher callback)                    │
│  POST {upstream.url}/tools/call                             │
│       headers: { Authorization: Bearer <token> }            │
│       body: { name: tool_name, arguments: {...} }           │
│       ↓                                                      │
│  MCPToolCallResult { success, result, error, duration_ms }  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     HTTPRestBackend                          │
├─────────────────────────────────────────────────────────────┤
│  allowlist.resolve(service, method, path)                    │
│       ↓ (checks host, methods, path_pattern)                │
│  entry.requires_auth?                                        │
│       ↓ yes                                                  │
│  _get_credential(user_id, entry.provider)                   │
│       ↓                                                      │
│  httpx.request(method, url, json=body, headers={...})       │
│       ↓                                                      │
│  HTTPResult { status_code, body, headers, duration_ms }     │
└─────────────────────────────────────────────────────────────┘
```

**Key Design Decisions:**

1. **CredentialFetcher callback** — Allows flexible credential sourcing. In production, inject a function that calls `CredentialStore.get_credential()`. In tests, provide a mock function.

2. **MCP URL normalization** — Upstream URL is normalized, `/tools/call` appended if not present.

3. **Bearer prefix handling** — Both backends handle tokens with or without "Bearer " prefix.

4. **Consistent error mapping**:
   - 401 → `CredentialMissingError` (reconnect required)
   - 403 → `UpstreamError` (insufficient permissions)
   - Connection issues → `ContainerUnavailableError`
   - Timeouts → `SubprocessTimeoutError`

---

### Milestone 9: Atlassian Tools ✅

**Completed:** 2026-05-10

**What was implemented:**

1. **tools/jira.py** — Three Jira tool handlers
   - `create_ticket_handler`: Creates Jira tickets via upstream Atlassian MCP
     - Translates Gateway's CreateTicketInput to Atlassian's create_issue
     - Supports project_key, summary, description, issue_type, labels
     - Returns ticket_id, ticket_key, url, status, created_at
   - `get_ticket_status_handler`: Gets ticket status via upstream Atlassian MCP
     - Translates Gateway's GetTicketStatusInput to Atlassian's get_issue
     - Returns ticket_key, summary, status, assignee, updated_at, url
     - Returns found=False for non-existent tickets (graceful handling)
   - `add_comment_handler`: Adds comments to tickets via upstream Atlassian MCP
     - Translates Gateway's AddCommentInput to Atlassian's add_comment
     - Returns ticket_key, comment_id, author, created_at
   - `_get_mcp_proxy()` helper to validate executor type

2. **tools/__init__.py** — Tool registry integration
   - Imported `JIRA_TOOLS` from jira.py
   - Added `create_full_registry()` factory (9 tools: 6 BRS + 3 Jira)
   - Added `ALL_TOOLS` convenience list
   - Updated exports

3. **Tool definitions** with proper metadata:
   - `create_ticket_tool`: LOW_WRITE, all environments, requires read:jira-work + write:jira-work
   - `get_ticket_status_tool`: READ, all environments, requires read:jira-work
   - `add_comment_tool`: LOW_WRITE, all environments, requires read:jira-work + write:jira-work
   - All tools use `mcp_proxy` executor and `atlassian` category

**Files created:**
- `backend/gateway_mcp/tools/jira.py` (~330 lines)
- `backend/gateway_mcp/tests/unit/test_jira_tools.py` (~350 lines)
- `backend/gateway_mcp/tests/integration/test_jira_workflow.py` (~300 lines)

**Files modified:**
- `backend/gateway_mcp/tools/__init__.py` (+25 lines)

**Tests:**
- ✅ 21 unit tests in `test_jira_tools.py`
  - 5 create_ticket tests (success, minimal, upstream error, string result, bug type)
  - 5 get_ticket_status tests (success, not found, upstream error, no assignee, display name)
  - 5 add_comment tests (success, upstream error, string result, display name, unknown author)
  - 1 error handling test (non-MCPProxyBackend executor)
  - 5 tool registration tests (definitions, registry integration)
- ✅ 6 integration tests in `test_jira_workflow.py`
  - Full workflow: create_ticket → get_ticket_status → add_comment (stateful mock)
  - Multiple ticket creation
  - Multiple comments on single ticket
  - Non-existent ticket handling
  - Different issue types (Task, Bug, Story)
  - Error handling for comment on non-existent ticket
- All 257 gateway_mcp tests passing (no regressions)

**Tool Schemas:**

```python
# CreateTicketInput
{
    "project_key": "GOLF",     # Jira project key
    "summary": "...",          # Ticket title
    "description": "...",      # Optional markdown description
    "issue_type": "Task",      # Task, Bug, or Story
    "labels": ["onboarding"]   # Optional labels
}

# GetTicketStatusInput
{
    "ticket_key": "GOLF-123"   # Ticket key to look up
}

# AddCommentInput
{
    "ticket_key": "GOLF-123",  # Ticket to comment on
    "comment_body": "..."      # Markdown comment text
}
```

**Upstream MCP Translation:**

| Gateway Tool | Upstream Tool | Key Transformations |
|--------------|---------------|---------------------|
| create_ticket | create_issue | project→{key}, issuetype→{name} |
| get_ticket_status | get_issue | issueIdOrKey parameter |
| add_comment | add_comment | issueIdOrKey + body params |

**Architecture:**

```
┌─────────────────────────────────────────────────────────────┐
│                    Jira Tool Handler                         │
├─────────────────────────────────────────────────────────────┤
│  CreateTicketInput/GetTicketStatusInput/AddCommentInput     │
│       ↓                                                      │
│  _get_mcp_proxy(context) → MCPProxyBackend                  │
│       ↓                                                      │
│  mcp_proxy.call_mcp_tool(                                   │
│      upstream_name="atlassian",                             │
│      tool_name="create_issue" / "get_issue" / "add_comment",│
│      arguments={...translated...},                          │
│      user_id=context.user_id                                │
│  )                                                           │
│       ↓                                                      │
│  Parse MCPToolCallResult → Gateway Output Schema            │
└─────────────────────────────────────────────────────────────┘
```

**Integration Test Mock:**

The integration tests use a stateful `MockAtlassianMCP` class that simulates:
- Ticket creation with auto-incrementing keys (GOLF-1, GOLF-2, etc.)
- Ticket state persistence across calls
- Comment storage on tickets
- Not-found handling for non-existent tickets

---

### Milestone 10: System Integration ✅

**Completed:** 2026-05-10

**What was implemented:**

1. **Gateway MCP Server Registration** (`backend/app/config/mcp_config.py`)
   - Added `gateway-mcp` as first server in all environments (development, staging, production)
   - Gateway MCP URL: `http://localhost:8090/mcp` (dev), `https://gateway-mcp-staging.example.com/mcp` (staging), `https://gateway-mcp.example.com/mcp` (prod)
   - Added `OPERATOR_ALLOWLIST` with Gateway MCP write tools (create_club, create_admin_user, etc.)
   - Updated `TOOL_ALLOWLIST` to include operator role

2. **WorkflowOrchestrator Gateway Routing** (`backend/app/services/workflow_orchestrator.py`)
   - Added `MCPToolRegistry` integration with lazy initialization
   - Added `GATEWAY_TOOL_MAPPING` for legacy BRS tool name resolution:
     - `brs_teesheet_init` → `create_club`
     - `brs_create_superuser` → `create_admin_user`
     - `brs_config_validate` → `verify_club_setup`
   - Added `_execute_tool_call()` method routing tool_call steps through MCP registry
   - Added `_execute_approval_gate()` method for approval gate handling
   - Added `_resolve_template_inputs()` for `{{input.field}}` and `{{step.field}}` variable resolution

3. **Onboarding Template Update** (`backend/app/workflows/teesheet_onboarding.py`)
   - Updated tool names from legacy BRS to Gateway MCP:
     - `brs_teesheet_init` → `create_club`
     - `brs_create_superuser` → `create_admin_user`
     - `brs_config_validate` → `verify_club_setup`
   - Updated step descriptions to reference Gateway MCP
   - Updated input field mappings to match Gateway MCP schemas

4. **Gateway Routing Integration Tests** (`backend/tests/integration/test_gateway_routing.py`)
   - `TestGatewayMCPConfig` — Verifies gateway-mcp is registered in all environments
   - `TestMCPToolRegistryDiscovery` — Verifies registry discovers Gateway tools
   - `TestGatewayToolMapping` — Verifies legacy tool name resolution
   - `TestOrchestratorToolExecution` — Verifies orchestrator routes through Gateway
   - `TestTemplateInputResolution` — Verifies template variable resolution

5. **Onboarding E2E Tests Update** (`backend/tests/integration/test_teesheet_onboarding_e2e.py`)
   - Added `TestGatewayMCPIntegration` class with 3 tests:
     - `test_template_uses_gateway_tool_names`
     - `test_orchestrator_routes_to_gateway_mcp`
     - `test_legacy_tool_names_still_work`

**Files changed:**
- `backend/app/config/mcp_config.py` (+30 lines)
- `backend/app/services/workflow_orchestrator.py` (+150 lines)
- `backend/app/workflows/teesheet_onboarding.py` (updated tool names)
- `backend/tests/integration/test_gateway_routing.py` (new, ~300 lines)
- `backend/tests/integration/test_teesheet_onboarding_e2e.py` (+80 lines)

**Tests:**
- ✅ 16 tests in `test_gateway_routing.py`
- ✅ 3 tests in `test_teesheet_onboarding_e2e.py::TestGatewayMCPIntegration`
- 19 new tests total

---

### Post-Milestone 10 Audit & Runtime Hardening ✅

**Completed:** 2026-05-10

**Why this was needed:**
- Milestone 10 tests were heavily mock-based and did not fully exercise runtime wiring between:
  - backend `MCPClient` → Gateway MCP transport/auth
  - Gateway middleware → concrete executor injection
- This created gaps where code could pass tests but fail in real tool execution.

**What was changed:**

1. **Gateway auth factory fallback for single-token config**
   - File: `backend/gateway_mcp/core/auth.py`
   - `create_auth_service_from_settings()` now supports `GATEWAY_SERVICE_TOKEN` via `settings.service_token` when `service_tokens` map is not provided.
   - Fallback scopes: `["operator", "admin"]` for backward-compatible dev wiring.

2. **Gateway runtime executor injection**
   - File: `backend/gateway_mcp/main.py`
   - Added `_create_executor_factory(settings)` and wired it into `create_middleware_pipeline(...)`.
   - Middleware ToolContext now gets a real backend in runtime:
     - `docker_exec` → `DockerExecBackend`
     - `k8s_exec` → `K8sExecBackend`
     - `job_runner` → `JobRunnerBackend`
     - fallback → `MockExecutorBackend`

3. **Backend MCP client protocol compatibility with Gateway MCP transport**
   - File: `backend/app/services/mcp_client.py`
   - `list_tools()` now uses `POST /tools/list` (Gateway transport contract).
   - `call_tool()` now:
     - sends Gateway auth headers (`Authorization: Bearer $GATEWAY_SERVICE_TOKEN`, `X-User-Id`)
     - accepts MCP content-block responses (`content[]`, `isError`)
     - parses JSON text content into structured result.

4. **User context propagation into MCP tool calls**
   - File: `backend/app/services/mcp_registry.py`
   - `execute_tool()` now passes `user_id` to `MCPClient.call_tool()` so gateway auth/audit context is consistent.

**Files changed:**
- `backend/gateway_mcp/core/auth.py`
- `backend/gateway_mcp/main.py`
- `backend/app/services/mcp_client.py`
- `backend/app/services/mcp_registry.py`

**Tests run:**
- ✅ `cd backend && ../.venv/bin/py.test -p no:rerunfailures gateway_mcp/tests/integration/test_mcp_client.py tests/integration/test_gateway_routing.py tests/test_mcp_registry.py -q`
- Result: **46 passed**

**Remaining risks/blockers after hardening:**
1. ~~Gateway `main.py` still registers BRS-only tools (`create_brs_registry`), so Atlassian tools are not exposed via live `/mcp/tools/list` despite existing implementations.~~ **FIXED:** Now uses `create_full_registry()` exposing all 9 MVP tools.
2. ~~Scope validation is still not wired to the credential store in middleware runtime, so external tool scope enforcement is not production-complete.~~ **FIXED:** `ScopeService._get_user_credential()` now integrates with `CredentialStore` when provided.
3. End-to-end real BRS smoke/E2E remains Milestone 11 work (docker-compose stack + smoke scripts + real container execution).

---

### Post-Milestone 10 Spec Gap Fixes ✅

**Completed:** 2026-05-11

**Spec gaps addressed:**

1. **Gateway now exposes all 9 MVP tools** (`main.py`)
   - Changed from `create_brs_registry()` to `create_full_registry()`
   - Both lifespan and `create_app()` now register all 9 tools (6 BRS + 3 Atlassian)
   - Verified: `python -c "from gateway_mcp.tools import create_full_registry; r = create_full_registry(); print(len(r))"` → 9

2. **Scope enforcement integrated with credential store** (`scopes.py`)
   - `ScopeService._get_user_credential()` now calls `credential_store.get_credential()` when store is provided
   - Returns credential dict with scopes for scope validation
   - Factory updated to accept optional `credential_store` parameter

3. **Fixed /ready health check** (`main.py`)
   - Now iterates `settings.services` dict from config
   - Checks reachability of all HTTP services (those with `url` field)
   - Skips container-based services (teesheet, mysql, mongo)
   - Reports per-service status in response

4. **Fixed call_internal_api service key mismatch** (`api.py`)
   - Changed `service="internal"` to `service="admin_api"`
   - Matches the service key in `configs/local.yaml`

5. **Documented SSE transport as future work** (`transport.py`)
   - Added detailed comment block explaining SSE is Milestone 12+
   - Updated `create_sse_stream()` error message with roadmap reference

6. **Documented dual authorization layers** (`mcp_config.py`)
   - Added comprehensive comment block explaining:
     - Backend role-based allowlist (this file)
     - Gateway permission layer (gateway_mcp/core/permissions.py)
     - How they work together
     - Risk level reference table

**Files changed:**
- `backend/gateway_mcp/main.py`
- `backend/gateway_mcp/core/scopes.py`
- `backend/gateway_mcp/core/transport.py`
- `backend/gateway_mcp/tools/api.py`
- `backend/app/config/mcp_config.py`

**Tests run:**
- ✅ 36 passed (gateway_mcp/tests/unit/test_mcp_transport.py + tests/integration/test_gateway_routing.py)

---

### Per-Tool Executor Routing ✅

**Completed:** 2026-05-11

**What was implemented:**

1. **Executor routing in middleware** (`core/middleware.py`)
   - Added `executor_router` parameter to `MiddlewarePipeline.__init__()`
   - `_execute_tool()` now selects executor based on tool type:
     - `executor_router(tool)` if provided (new pattern)
     - Falls back to `executor_factory()` for backward compatibility
   - Factory `create_middleware_pipeline()` accepts `executor_router` and `credential_store`

2. **Per-tool executor factory** (`main.py`)
   - Added `_create_executor_router(settings)` function
   - Routes BRS tools → environment executor (docker_exec/k8s_exec/job_runner/mock)
   - Routes external tools (Jira) → MCPProxyBackend
   - Checks `tool.is_external()` to determine routing
   - Returns tuple: `(executor_router, credential_fetcher)`

3. **Integration test for executor routing** (`tests/integration/test_mcp_client.py`)
   - Added `TestExecutorRouting` class
   - Tests verify both BRS and Jira tools are registered
   - Tests verify BRS tools use env executor (no MCPProxyBackend error)
   - Tests verify external tools require MCP proxy
   - Tests verify external tool metadata in registry

**Executor Routing Logic:**

```python
def executor_router(tool: Tool) -> ExecutorBackend:
    if tool.is_external():  # has required_scopes
        return mcp_proxy_backend  # MCPProxyBackend
    else:
        return brs_backend  # DockerExec/K8sExec/JobRunner/Mock
```

**Architecture:**

```
┌─────────────────────────────────────────────────────────────┐
│                    MiddlewarePipeline                        │
├─────────────────────────────────────────────────────────────┤
│  _execute_tool(tool, input, auth, audit)                    │
│       ↓                                                      │
│  executor = executor_router(tool)                           │
│       ↓                                                      │
│  ┌──────────────────────────────────────────────────┐       │
│  │ tool.is_external()?                              │       │
│  │   Yes → MCPProxyBackend (Atlassian MCP)         │       │
│  │   No  → BRS Backend (docker_exec/k8s/job)       │       │
│  └──────────────────────────────────────────────────┘       │
│       ↓                                                      │
│  context = ToolContext(..., _executor=executor)             │
│       ↓                                                      │
│  tool.handler(input, context)                               │
└─────────────────────────────────────────────────────────────┘
```

---

### SSE Transport (Post-MVP) 📋

**Status:** Deferred to Milestone 12+

**Current HTTP-only transport:**
- `POST /mcp/tools/list` — List available tools
- `POST /mcp/tools/call` — Execute tool synchronously

**SSE transport (future work):**
- Would enable streaming output for long-running tools
- Required for real-time progress updates during tool execution
- Not required for MVP: all current tools are short-lived operations

**Documentation:**
- `backend/gateway_mcp/core/transport.py` contains `create_sse_stream()` stub
- Raises `NotImplementedError` with roadmap reference
- Full SSE implementation planned for post-MVP iteration

---

## Next Milestone: 11 (E2E & Smoke Tests)

- Create `infrastructure/docker-compose.brs.yml` for local BRS stack
- Document BRS repo prerequisites and dev Dockerfile requirements
- Create `scripts/smoke_setup_club.py` — BRS workflow smoke test
- Create `scripts/smoke_jira.py` — Atlassian tools smoke test
- E2E test: full club-setup against real BRS containers

---

## Running Tests

```bash
# Run all gateway_mcp tests
cd backend && pytest gateway_mcp/tests/ -v

# Run Gateway routing integration tests
cd backend && pytest tests/integration/test_gateway_routing.py -v

# Run Jira tool tests
cd backend && pytest gateway_mcp/tests/unit/test_jira_tools.py gateway_mcp/tests/integration/test_jira_workflow.py -v

# Run executor tests (including mcp_proxy/http_rest tests)
cd backend && pytest gateway_mcp/tests/unit/test_executors.py -v

# Run only credential tests
cd backend && pytest gateway_mcp/tests/unit/test_credentials.py gateway_mcp/tests/integration/test_credentials_api.py -v

# Run only MCP transport tests
cd backend && pytest gateway_mcp/tests/unit/test_mcp_transport.py gateway_mcp/tests/integration/test_mcp_client.py -v

# Run only middleware tests
cd backend && pytest gateway_mcp/tests/unit/test_middleware.py gateway_mcp/tests/integration/test_middleware_integration.py -v
```
