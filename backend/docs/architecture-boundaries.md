# Architecture Boundaries: Backend / Gateway MCP

**Last Updated:** 2026-05-13  
**Owner:** Backend Team  
**Status:** Enforced via CI tests

---

## Overview

This document describes the architectural boundary between the **Backend** (agent orchestration) and **Gateway MCP** (tool execution and credential management). This separation is critical for:

1. **Security**: External credentials (Atlassian, GitHub tokens) never leave the Gateway boundary
2. **Scalability**: Backend can scale independently of credential-sensitive operations  
3. **Maintainability**: Clear ownership boundaries for debugging and extending

---

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                          Frontend                                │
│                    (Open WebUI / Chat Shell)                     │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                          Backend                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ AgenticService  │  │ MCPToolRegistry │  │ ToolCatalog     │  │
│  │ (Orchestration) │  │ (Discovery)     │  │ (Filtering)     │  │
│  └────────┬────────┘  └────────┬────────┘  └─────────────────┘  │
│           │                    │                                 │
│           └──────────┬─────────┘                                 │
│                      ▼                                           │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                      MCPClient                             │  │
│  │              (MCP Protocol over HTTP)                      │  │
│  │       *** NO CREDENTIALS PASS THROUGH HERE ***             │  │
│  └────────────────────────────┬──────────────────────────────┘  │
└───────────────────────────────┼──────────────────────────────────┘
                                │ MCP Protocol (tools/call)
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Gateway MCP                                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ PermissionSvc   │  │ ToolContext     │  │ Auth Service    │  │
│  │ (RBAC + Risk)   │  │ (Credential     │  │ (OAuth/Token    │  │
│  │                 │  │  Abstraction)   │  │  Management)    │  │
│  └─────────────────┘  └────────┬────────┘  └─────────────────┘  │
│                                │                                 │
│                                ▼                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    Tool Handlers                           │  │
│  │   BRS Tools      │   Atlassian Tools   │   Internal APIs   │  │
│  │   (create_club)  │   (create_ticket)   │   (call_api)      │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Boundary Rules

### Backend Responsibilities

The Backend owns:
- **Agent orchestration** (step execution, retry logic, state management)
- **Tool discovery** (via MCP `tools/list`)
- **Tool catalog filtering** (workflow, risk, role-based exposure)
- **User session management** (not OAuth tokens)

The Backend must **NOT**:
- Access external provider credentials directly (e.g., `ATLASSIAN_TOKEN`)
- Import Gateway credential modules (`gateway_mcp.core.auth`)
- Store or cache OAuth tokens
- Make direct HTTP calls to external APIs (Jira, GitHub, etc.)

### Gateway MCP Responsibilities

The Gateway MCP owns:
- **Credential management** (OAuth token storage, refresh)
- **Permission enforcement** (risk level, environment restrictions)
- **Tool execution** (actual calls to BRS, Atlassian, etc.)
- **Audit logging** (tool invocations with user context)

The Gateway provides:
- `ToolContext` abstraction for tools to access credentials
- `get_credential(provider)` method for transparent token access
- Permission checks before tool execution

---

## Credential Flow

```
User Request → Backend → MCPClient → Gateway MCP
                                          │
                                          ▼
                              ┌─────────────────────┐
                              │ Permission Check    │
                              │ (Risk Level)        │
                              └─────────┬───────────┘
                                        │
                                        ▼
                              ┌─────────────────────┐
                              │ Tool Handler        │
                              │ context.get_credential("atlassian")
                              │ → Returns valid token
                              └─────────┬───────────┘
                                        │
                                        ▼
                              ┌─────────────────────┐
                              │ External API Call   │
                              │ (Jira, GitHub, etc.)│
                              └─────────────────────┘
```

---

## Enforcement

### Automated Tests (CI)

The following tests run on every commit:

| Test | Purpose |
|------|---------|
| `test_no_forbidden_env_var_access` | Backend services don't access credential env vars |
| `test_no_hardcoded_credential_patterns` | No hardcoded tokens in source |
| `test_no_forbidden_gateway_imports` | Backend doesn't import gateway auth modules |
| `test_gateway_has_credential_module` | Gateway owns credential handling |
| `test_tool_context_has_credential_fetcher` | ToolContext provides credential abstraction |

See: `backend/tests/test_architecture_boundaries.py`

### Code Review Checklist

For PRs touching Backend services:
- [ ] No new `os.environ.get("*_TOKEN")` accesses
- [ ] No imports from `gateway_mcp.core.auth` or `.credentials`
- [ ] Tool calls go through MCPClient, not direct HTTP

For PRs touching Gateway MCP:
- [ ] Credentials accessed via `ToolContext.get_credential()`
- [ ] New tools define appropriate `risk_level`
- [ ] Sensitive operations have audit logging

---

## Adding New External Integrations

When adding a new external integration (e.g., Slack, Salesforce):

1. **Gateway Side**:
   - Add credential storage in `gateway_mcp/core/credentials.py`
   - Add provider to `ToolContext.get_credential()` dispatch
   - Create tool handlers in `gateway_mcp/tools/`
   - Define appropriate `risk_level` and `allowed_environments`

2. **Backend Side**:
   - Add tool names to `DEFAULT_TOOL_METADATA_REGISTRY` in `tool_catalog.py`
   - Update `TOOL_ALLOWLIST` in `mcp_config.py` for role access
   - Add workflow tags if applicable

3. **Tests**:
   - Add provider to `FORBIDDEN_CREDENTIAL_PATTERNS` if needed
   - Add integration tests for the new tools

---

## Exceptions

The following are **allowed** to cross the boundary:

1. **Type imports**: `from gateway_mcp.tools.base import RiskLevel, Environment`
   - These are enums/types, not credentials
   
2. **Configuration**: Environment name, server URLs
   - These are non-sensitive deployment config

3. **Audit IDs**: Correlation IDs for tracing
   - No sensitive data, just UUIDs

---

## Monitoring

Track boundary violations via:
- CI test failures (immediate feedback)
- Code review gates (human review)
- Runtime audit logs (post-hoc analysis)

---

## References

- [Gateway MCP Permissions](../../gateway_mcp/core/permissions.py)
- [MCP Protocol Spec](https://modelcontextprotocol.io/)
- [Architecture Tests](../../tests/test_architecture_boundaries.py)
