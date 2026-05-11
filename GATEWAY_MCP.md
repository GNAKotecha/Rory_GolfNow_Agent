# Gateway MCP Overview

Build a **Gateway MCP** that acts as the controlled execution layer between the AI agent and internal systems.

The agent should never call raw shell commands, Docker commands, SQL, or arbitrary HTTP directly. Instead, it calls structured MCP tools exposed by the gateway. The gateway then validates inputs, applies permissions, executes the appropriate backend action, and returns a clean, structured result.

## Purpose

The Gateway MCP provides a safe way for the agent to perform internal workflows such as creating and configuring a club.

It should support:

- Internal CLI command execution (via docker exec)
- Internal API calls (HTTP to BRS services)
- External HTTP API calls
- Docker-based DB lookups
- Docker-based app commands
- Audit logging
- Permission checks
- Environment-aware safety controls

## High-Level Architecture

```text
AI Agent / Orchestrator
        ↓
Gateway MCP
        ↓
Tool Router
        ↓
------------------------------------------------
| Internal CLI | Internal APIs | External APIs |
| Docker Exec  | DB Lookups    | App Commands  |
------------------------------------------------
```

## Core Principle

Do not expose generic tools like:

```
run_command(command)
docker_exec(command)
run_sql(query)
curl(url, payload)
```

Instead expose business-level tools like:

```
create_club
get_club_by_name
get_club_config
create_admin_user
call_internal_api
verify_club_setup
```

The model describes intent. The gateway owns execution.

## BRS Tool Implementation

The BRS tools use a hybrid approach:
- **API-first**: Use HTTP APIs when available (get_club_by_name, verify_club_setup, call_internal_api)
- **Docker exec fallback**: Use console commands only when no API exists (create_club, create_admin_user)

### BRS Console Commands (via docker exec)

```bash
# Create a new club (no API available)
docker exec php php app/console brs:tbs:create-installation \
  --club-id=<club_id> \
  --name="<name>" \
  --country=<country> \
  --latitude=<lat> \
  --longitude=<lng> \
  --member-module=y

# Sync superusers (no API available)
docker exec php php app/console brs:tbs:brs-superusers:update \
  --club-id=<club_id>
```

### BRS API Endpoints (HTTP)

```
# Search for clubs
GET /api/admin/v1/clubs?keyword=<name>

# Get club configuration
GET /{clubId}/api/v3/
```

## Tool Categories

### 1. Internal CLI Tools

Used for approved app commands when no API exists.

Example:

```
create_club(name, country, timezone, currency)
```

Internally routes to:

```bash
docker exec php php app/console brs:tbs:create-installation --club-id=<derived> --name=<name> ...
```

Requirements:

- Whitelist allowed commands
- Validate arguments
- No arbitrary shell interpolation
- Use safe subprocess execution
- Capture stdout/stderr
- Return structured success/failure
- Log command metadata

### 2. Internal API Tools

Used to interact with internal backend endpoints.

Example:

```
update_club_settings(club_id, settings)
```

Internally routes to:

```
POST /internal/clubs/{club_id}/settings
```

Requirements:

- Whitelist allowed endpoints
- Use service credentials, not user-provided tokens
- Validate request body
- Handle auth centrally
- Return normalized JSON
- Block unknown endpoints

### 3. External API Tools

Used for third-party integrations.

Example:

```
create_payment_provider_account(club_id, provider)
```

Requirements:

- Explicit allowlist per external service
- Strict schema validation
- Timeout/retry handling
- No arbitrary outbound HTTP
- Secrets loaded from environment variables

### 4. Docker / DB Lookup Tools

Used for read-only database inspection.

Example:

```
get_club_by_name(name)
get_club_config(club_id)
get_admin_users(club_id)
```

Internally can use:

```bash
docker exec <db-container> mysql ...
```

or a direct DB client if available.

Requirements:

- Prefer read-only DB user
- Only allow predefined queries
- Never expose free-form SQL initially
- Return only required fields
- Redact secrets/password hashes/tokens
- Log query name, not sensitive output

### 5. Controlled Write Tools

Used for necessary setup actions like creating an admin user.

Example:

```
create_admin_user(club_id, email, role)
```

Requirements:

- Only allowed in local/dev initially
- Explicit schema validation
- Approval gate if environment is staging/prod
- Idempotent where possible
- Verify result after write
- Audit log every write

## Example Club Setup Workflow

The agent should be able to execute this workflow through gateway tools:

1. `create_club(name, country, timezone, currency)`
2. `get_club_by_name(name)`
3. `get_club_config(club_id)`
4. `create_admin_user(club_id, email, role)`
5. `call_internal_api(club_id, operation="enable_required_features")`
6. `verify_club_setup(club_id)`
7. Return setup summary

## Safety Rules

The Gateway MCP must enforce:

- No arbitrary shell execution
- No arbitrary SQL
- No arbitrary curl
- No direct Docker socket access from the agent
- Tool-level permissions
- Environment restrictions
- Approval gates for risky actions
- Structured logging for every action
- Secret redaction
- Clear error handling

## Suggested Tool Shape

Each MCP tool should have:

- `name`
- `description`
- `input_schema`
- `risk_level`
- `allowed_environments`
- `requires_approval`
- `handler`
- `validator`
- `audit_metadata`

Example:

```json
{
  "name": "create_club",
  "risk_level": "low_write",
  "allowed_environments": ["local", "dev"],
  "requires_approval": false
}
```

## Recommended Implementation

Use a small service such as:

**FastAPI Gateway MCP**

Structure:

```
gateway-mcp/
  app/
    main.py
    tools/
      clubs.py
      users.py
      db.py
      internal_api.py
      external_api.py
    core/
      config.py
      permissions.py
      audit.py
      command_runner.py
      docker_runner.py
      http_client.py
      schemas.py
```

## Key Design Decision

The Gateway MCP is not just a proxy.

It is the **policy and execution boundary**.

The agent can request:

> "Create a club"

But the gateway decides:

- Whether that action is allowed
- Which command/API/query to run
- What arguments are valid
- Whether approval is needed
- What output is safe to return

## MVP Scope

Start with the tools needed to create a club

Avoid generic tools until the system has stronger permissioning, approvals, and audit logs.

## Acceptance Criteria

- Agent can create a club through a structured MCP tool
- Gateway executes the approved Docker/CLI command locally
- Agent can retrieve the created club via read-only DB lookup
- Agent can create an admin user through a controlled tool
- Agent can call a whitelisted internal API operation
- All actions are logged
- No arbitrary command, SQL, or HTTP execution is exposed
- Errors are returned in a structured format
