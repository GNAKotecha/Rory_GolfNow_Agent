# Rory Agent — Developer Handover

**Last Updated**: 2026-06-10  
**Audience**: New developer joining the project  
**Repo**: `Rory_GolfNow_Agent`

---

## 1. What Is This?

Rory is a hosted internal AI agent for GolfNow. It lets staff interact with the BRS teesheet platform via natural language — querying member data, running workflows (e.g. reinstating users), and executing BRS API operations — without needing direct database or API access.

Think of it as a chat interface with structured workflows and tool access, not a general-purpose chatbot.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (Next.js — localhost:3000)                     │
│  - Chat interface                                        │
│  - Admin dashboard (skills, workflows, MCP connections)  │
│  - User management                                       │
└────────────────────┬────────────────────────────────────┘
                     │ REST + WebSocket
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Backend (FastAPI — localhost:8000)                      │
│  - Auth (JWT, local users)                               │
│  - Agentic service (LLM orchestration)                   │
│  - Skill system (pre-built workflows)                    │
│  - MCP client (tool routing)                             │
│  - Tenant MCP manager                                    │
│  - Workflow analytics + Langfuse tracing                 │
└─────┬────────────────────────────┬───────────────────────┘
      │                            │
      ▼                            ▼
┌─────────────────┐   ┌────────────────────────────────┐
│  LLM Runtime    │   │  Gateway MCP (localhost:8090)   │
│  Ollama / API   │   │  - BRS teesheet tools           │
│  (configurable) │   │  - run_sql, call_api, etc.      │
└─────────────────┘   └────────────────────────────────┘
                                   │
                                   ▼
                       ┌─────────────────────┐
                       │  BRS API            │
                       │  localhost:8056      │
                       │  (PHP teesheet)      │
                       └─────────────────────┘
```

**Storage**: SQLite (dev) / PostgreSQL (prod) — one DB for users, conversations, workflow runs, skill definitions, MCP credentials.

**Tracing**: Langfuse (optional) — all LLM calls traced.

---

## 3. What's Been Built (Phases 1–6)

### Phase 1: Workflow Engine Foundation
- FastAPI backend scaffolding
- SQLAlchemy models: User, Conversation, Message, WorkflowTemplate, WorkflowRun
- Alembic migrations
- MetricsCollector service (workflow analytics)
- WorkflowOrchestrator with LangGraph integration

### Phase 2: BRS Tools + Observability
- Gateway MCP server (`backend/gateway_mcp/`) with BRS teesheet tools
- Langfuse tracing integration
- `run_sql`, `call_api`, `get_club_by_name`, `verify_club_setup`, `get_club_config` tools
- Analytics API (`/api/analytics/`)

### Phase 3: Onboarding Workflow + Testing
- "Reinstate User" skill — full multi-step workflow via natural language
- DeepEval test suite for workflow correctness/hallucination
- Admin analytics dashboard (traces, workflows)
- Skill invocation from chat (semantic matching)

### Phase 4: Gateway MCP Implementation
- Gateway MCP as a separate FastAPI service on port 8090
- JSON-RPC 2.0 and stdio MCP client support
- Tenant-aware MCP manager (per-tenant MCP server config)
- Tool discovery endpoint

### Phase 5: Frontend Admin UI + Skills System
- Full admin dashboard in Next.js:
  - `/admin/mcp-connections` — add/edit/test MCP server connections
  - `/admin/integrations` — OAuth credential management
  - `/admin/skills` — view/create/edit skills
  - `/admin/workflows` — workflow run history
  - `/admin/traces` — Langfuse trace viewer
- Skill execution isolation (each skill runs with its own LLM context)
- Per-skill timeout configuration
- Bug #11 resolved: LLM timeout increased 60s→180s, retry with backoff added
- Documentation system added to production readiness loop

### Phase 6: RBAC + Auth Infrastructure (In Progress)
- RBAC model: `LocalPrincipal`, `SSOPrincipal`, `TeesheetPrincipal`
- `PermissionProfile` class — unified permissions across all auth sources
- Role mappings: local admin/user, SSO job roles, BRS teesheet roles
- Database migration: `auth_source`, `external_id`, `sso_claims`, `club_context`, `last_login` fields added to User
- `UserMCPCredential` model — per-user credential storage for MCP auth
- MCP auth backend (Phase 1 of Bug #12 fix): credential storage API endpoints, OAuth 2.0 support

---

## 4. Current State (as of 2026-06-10)

### What Works
- ✅ Chat with BRS tools (first message in a session)
- ✅ Skill execution ("Reinstate User" workflow)
- ✅ Admin dashboard — skills, workflows, traces, MCP connections UI
- ✅ MCP connection management (add/test/delete servers)
- ✅ OAuth credential storage per user per provider
- ✅ RBAC model defined and DB schema migrated
- ✅ Langfuse tracing

### Critical Bugs (Blocking Production)

#### Bug #12: MCP 401 Errors — Partially Fixed
- **Status**: Phase 1 backend infra complete, E2E not yet verified
- **Issue**: BRS API credentials not passed through to tool calls; 401 errors on tool execution
- **What's done**: `UserMCPCredential` model, storage API, OAuth endpoints, credential passthrough to Gateway MCP
- **What's left**: Token refresh mechanism, E2E test, frontend credential setup flow
- **File**: `docs/bugs/BUG_12_SLASH_COMMAND_AUTOCOMPLETE.md`

#### Bug #13: Multi-Turn Auth Failure (BLOCKING)
- **Status**: Not fixed
- **Issue**: Second+ messages in a conversation fail with 503 auth errors
- **Root cause hypothesis**: BRS API OAuth token expires mid-conversation (~5 min TTL); refresh logic not working
- **Impact**: Chat is unusable after the first message
- **File**: `docs/bugs/BUG_13_AUTHENTICATION_TOKEN_FAILURE.md`
- **Fix approach**: Implement token refresh in `backend/app/services/mcp_client.py` and `oauth_service.py`

#### Bug #12b: Slash Command Autocomplete
- **Status**: Low priority
- **Issue**: "/" in chat input doesn't trigger skill dropdown
- **Workaround**: Semantic matching still works (type the skill name naturally)

---

## 5. Directory Structure

```
Rory_GolfNow_Agent/
├── backend/                    # FastAPI Python backend
│   ├── app/
│   │   ├── api/                # Route handlers
│   │   │   ├── auth.py         # Login/register
│   │   │   ├── chat.py         # Chat endpoint (main LLM flow)
│   │   │   ├── integrations.py # OAuth credential management
│   │   │   ├── mcp_auth.py     # MCP credential storage endpoints
│   │   │   ├── skills.py       # Skill CRUD
│   │   │   ├── tenants.py      # Tenant management
│   │   │   ├── tools.py        # Tool listing
│   │   │   └── traces.py       # Langfuse trace proxy
│   │   ├── core/
│   │   │   ├── config.py       # Settings (env vars)
│   │   │   └── rbac/           # RBAC model (Phase 6)
│   │   │       └── models.py   # Principal types, PermissionProfile
│   │   ├── models/
│   │   │   └── models.py       # SQLAlchemy models (User, Conversation, Skill, etc.)
│   │   ├── services/
│   │   │   ├── agentic_service.py    # Core LLM orchestration
│   │   │   ├── mcp_client.py         # MCP tool caller
│   │   │   ├── oauth_service.py      # OAuth token management
│   │   │   ├── simple_tools.py       # Built-in tools (run_sql, call_api)
│   │   │   └── tenant_mcp_manager.py # Per-tenant MCP server registry
│   │   └── main.py             # App entrypoint
│   ├── gateway_mcp/            # Gateway MCP server (port 8090)
│   │   ├── server.py           # JSON-RPC 2.0 MCP server
│   │   └── tools/              # BRS tool implementations
│   │       ├── brs_tools.py    # call_api, run_sql, etc.
│   │       └── schemas.py      # Tool input schemas
│   ├── alembic/                # DB migrations
│   ├── tests/                  # Test suite
│   └── .env.example            # Environment variable template
├── frontend/                   # Next.js frontend
│   ├── app/
│   │   ├── chat/               # Chat UI
│   │   ├── admin/              # Admin dashboard
│   │   │   ├── mcp-connections/ # MCP server management
│   │   │   ├── integrations/   # OAuth integrations
│   │   │   ├── skills/         # Skill management
│   │   │   ├── workflows/      # Workflow history
│   │   │   └── traces/         # Langfuse traces
│   │   └── login/              # Auth pages
│   ├── components/admin/       # Admin UI components
│   └── lib/api.ts              # API client
├── docs/                       # All project documentation (this folder)
│   ├── HANDOVER.md             # This file
│   ├── architecture.md         # Original architecture notes
│   ├── bugs/                   # Bug reports
│   └── specs/                  # Phase specs
└── .mcp.json                   # Claude Code MCP server config
```

---

## 6. How to Run Locally

### Prerequisites
- Python 3.9+
- Node.js 18+
- SQLite (dev) or PostgreSQL (prod)
- Ollama (for local LLM) OR an Anthropic API key

### Backend

```bash
cd backend

# Create virtual environment
python -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — set DATABASE_URL, OLLAMA_URL or USE_API_KEY+ANTHROPIC_AUTH_TOKEN

# Run migrations
alembic upgrade head

# Create admin user
python -m app.db.create_admin

# Start backend
uvicorn app.main:app --reload --port 8000
```

### Gateway MCP

```bash
cd backend/gateway_mcp
python server.py
# Runs on port 8090
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Runs on port 3000
```

### BRS API (External dependency)
The BRS teesheet PHP API must be running on `localhost:8056`. This is the `brs-teesheet` repo.  
See: `backend/gateway_mcp/docs/brs_dev_setup.md`

---

## 7. Key Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | SQLite or PostgreSQL connection string | `sqlite:///./data/agent.db` |
| `OLLAMA_URL` | Ollama inference server URL | `http://localhost:11434` |
| `USE_API_KEY` | `true` to use Anthropic API instead of Ollama | `false` |
| `ANTHROPIC_AUTH_TOKEN` | Anthropic API key (when `USE_API_KEY=true`) | — |
| `ANTHROPIC_BASE_URL` | API base URL (when `USE_API_KEY=true`) | — |
| `SECRET_KEY` | JWT signing secret — **change in production** | — |
| `MCP_GATEWAY_URL` | Gateway MCP server URL | `http://localhost:8090` |
| `LANGFUSE_ENABLED` | Enable LLM tracing | `true` |
| `BRS_TEESHEET_PATH` | Path to BRS teesheet repo | — |

---

## 8. Skill System

Skills are pre-built workflows that the agent can detect and execute from natural language.

**How it works:**
1. User sends a message (e.g. "Reinstate user John Doe at club X")
2. `agentic_service.py` checks for skill matches via intent patterns
3. If matched, executes the skill's workflow steps with isolated LLM context
4. Returns structured result

**Skill definition stored in DB** — admin can create/edit via `/admin/skills`.

**Built-in skills** (seeded on startup):
- `reinstate_user` — reinstates a suspended member at a BRS club

**Adding a new skill**: Use the admin UI at `/admin/skills` or POST to `POST /api/skills`.

---

## 9. MCP Tool System

The agent calls tools via the Model Context Protocol. Two layers:

1. **Built-in tools** (`simple_tools.py`): `run_sql`, `call_api`, `ask_user`
2. **Gateway MCP** (`gateway_mcp/`): BRS-specific tools running as a separate service

**Tool routing**: `mcp_client.py` → `tenant_mcp_manager.py` → gateway or remote MCP server

**Adding a new BRS tool**: Add to `backend/gateway_mcp/tools/brs_tools.py` and register in `tools/__init__.py`.

**Per-user MCP credentials**: Users can store OAuth tokens for MCP providers via the integrations UI. These are stored in `user_mcp_credentials` table and passed to gateway on tool calls.

---

## 10. Database Schema (Key Tables)

| Table | Purpose |
|-------|---------|
| `users` | User accounts with RBAC fields (`auth_source`, `external_id`, etc.) |
| `conversations` | Chat sessions per user |
| `messages` | Individual messages in conversations |
| `skill_definitions` | Skill templates (name, intent patterns, steps) |
| `workflow_runs` | Execution history for skills |
| `workflow_step_executions` | Step-level execution tracking |
| `user_mcp_credentials` | Per-user OAuth tokens for MCP providers |
| `tenant_mcp_servers` | MCP server configurations per tenant |

Run `alembic upgrade head` after pulling to apply any new migrations.

---

## 11. Immediate Next Steps (Priority Order)

### P0 — Fix Before Any Real Usage

1. **Fix Bug #13** (multi-turn auth failure)
   - File: `docs/bugs/BUG_13_AUTHENTICATION_TOKEN_FAILURE.md`
   - Where: `backend/app/services/oauth_service.py`, `mcp_client.py`
   - Fix: Implement token refresh when 401 received mid-conversation; ensure BRS OAuth token is refreshed automatically

2. **Complete MCP Auth E2E** (Bug #12 finish line)
   - Plan: `.plans/phase-1-mcp-auth-backend.md`
   - Tasks 5–7 remaining: credential passthrough → token refresh → E2E test
   - Then verify no 401 errors in multi-message conversations

### P1 — Phase 6 Remaining Tasks

3. **SSO Login** (Phase 6, Task 3–4)
   - Add `GET /api/auth/sso/login` and `GET /api/auth/sso/callback` endpoints
   - Add SSO button to frontend login page
   - Config: `SSO_CLIENT_ID`, `SSO_CLIENT_SECRET`, `SSO_DISCOVERY_URL` env vars

4. **Embedded Auth Exchange** (Phase 6, Task 5)
   - `POST /api/auth/embed/exchange` — validates signed JWT from brs-teesheet
   - JTI replay protection
   - Mints a Rory JWT from embed token

5. **Wire RBAC into tool filtering** (Phase 6, Tasks 6–7)
   - `backend/app/core/rbac/models.py` is defined; now needs to drive tool allowlists
   - Replace hardcoded checks in `agentic_service.py` with `PermissionProfile` lookups

### P2 — Quality & Productionisation

6. **Slash command autocomplete** (Bug #12b) — frontend-side, add "/" trigger to chat input
7. **Production deployment** — Dockerize, configure PostgreSQL, set up proper secrets management
8. **Add more skills** — billing queries, tee time creation, member search

---

## 12. Key Files to Know

| File | Why It Matters |
|------|----------------|
| `backend/app/services/agentic_service.py` | Core LLM loop — everything flows through here |
| `backend/app/services/mcp_client.py` | Tool call routing to MCP servers |
| `backend/app/services/oauth_service.py` | BRS OAuth token management (bug #13 is here) |
| `backend/app/api/chat.py` | Chat endpoint — entry point for messages |
| `backend/gateway_mcp/server.py` | Gateway MCP server — BRS tool implementations |
| `backend/app/core/rbac/models.py` | RBAC principal/permission model (Phase 6) |
| `frontend/app/admin/mcp-connections/page.tsx` | MCP server management UI |
| `frontend/lib/api.ts` | All frontend API calls |
| `.plans/phase-1-mcp-auth-backend.md` | MCP auth implementation plan (in progress) |
| `backend/docs/RBAC_MODEL.md` | Full RBAC documentation |

---

## 13. Testing

```bash
# Backend unit tests
cd backend && pytest tests/ -v

# Specific test
pytest tests/test_user_rbac_fields.py -v

# E2E test (requires backend + gateway MCP running)
pytest tests/test_mcp_auth_e2e.py -v
```

No frontend test suite currently exists. Playwright is available for E2E testing.

---

## 14. Known Limitations

- **Single-tenant only** — multi-tenancy is partially scaffolded but not enforced
- **No production deployment** — runs locally only; no Docker Compose for full stack yet
- **Ollama dependency** — needs a running Ollama or Anthropic API key; no fallback
- **BRS API tightly coupled** — the gateway MCP tools are tightly coupled to localhost:8056
- **No automated frontend tests** — admin UI changes aren't regression tested

---

*This document supersedes the individual PHASE_N_HANDOVER.md files for new developer orientation. For detailed implementation history, see `backend/docs/phase-N-complete.md`.*
