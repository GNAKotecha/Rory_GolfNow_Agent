# MCP Gateway Integration Investigation

## Problem
The gateway MCP is running on port 8090 and exposing **23 tools**, but the agent only sees **5 basic memory/calc tools**.

## Root Cause
**RBAC Filtering** - Users are created with `role=UserRole.USER` by default, which has a restrictive allowlist.

## Evidence

### 1. Gateway is Working
```bash
curl http://localhost:8090/tools
# Response: {"tools":[...], "count":23}
```

Gateway exposes all 23 tools:
- BRS tools: `create_club`, `get_club_by_name`, `authenticate_club`, `create_booking`, etc.
- Atlassian tools: `create_ticket`, `get_ticket_status`, `add_comment`
- Memory tools: `get_working_memory`, `update_working_memory`, etc.
- Database tools: `run_sql`, `get_schema`, `get_config`
- API tools: `list_routes`, `call_api`

### 2. RBAC Configuration
**File:** `backend/app/config/mcp_config.py`

```python
# Admin: ALL tools (wildcard)
ADMIN_ALLOWLIST = ["*"]  

# User: ONLY 6 basic tools + limited gateway read-only tools
USER_ALLOWLIST = [
    "search",
    "analyze", 
    "compute",
    "summarize",
    "translate",
    "format",
    # Gateway MCP (read-only)
    "get_club_by_name",
    "get_club_config",
    "verify_club_setup",
    "get_ticket_status",
]
```

### 3. User Creation Default
**File:** `backend/app/api/auth.py` (line 69)

```python
user = User(
    email=request.email,
    name=request.name,
    password_hash=get_password_hash(request.password),
    role=UserRole.USER,  # ← Default role
    approval_status=ApprovalStatus.PENDING,
    tenant_id=1,
)
```

### 4. Flow
1. User signs up → assigned `role=UserRole.USER`
2. Agent starts → `AgenticService._get_tool_definitions(user)` called
3. Tools fetched from gateway → 23 tools discovered
4. RBAC filter applied → `filter_tools_by_role(tools, user.role.value)`
5. Result: Only 10 tools allowed (6 basic + 4 gateway read-only)

## Solution Options

### Option 1: Grant Admin Role to Test User (Quick Fix)
**Pros:** Immediate access to all 23 tools  
**Cons:** Bypasses RBAC entirely (not suitable for production)

```python
# In database or via admin endpoint
UPDATE users SET role = 'admin' WHERE email = 'test@example.com';
```

### Option 2: Expand USER_ALLOWLIST (Recommended for MVP)
**Pros:** Preserves RBAC, grants necessary BRS tools to regular users  
**Cons:** Requires updating allowlist in config

```python
USER_ALLOWLIST = [
    "search", "analyze", "compute", "summarize", "translate", "format",
    # Gateway MCP - BRS tools
    "create_club",
    "get_club_by_name",
    "verify_club_setup",
    "get_club_config",
    "authenticate_club",
    "call_api",
    "list_routes",
    "run_sql",
    "get_schema",
    "get_config",
    "create_visitor_green_fee",
    "create_booking",
    "update_configuration",
    # Gateway MCP - Memory tools
    "get_working_memory",
    "update_working_memory",
    "store_session_summary",
    "get_historical_context",
    # Gateway MCP - Atlassian tools
    "create_ticket",
    "get_ticket_status",
    "add_comment",
]
```

### Option 3: Create OPERATOR Role (Production-Ready)
**Pros:** Granular control, workflow-specific permissions  
**Cons:** More complex, requires role assignment logic

```python
OPERATOR_ALLOWLIST = [
    # All USER tools
    *USER_ALLOWLIST,
    # BRS operational tools
    "create_club",
    "authenticate_club",
    "create_booking",
    "create_visitor_green_fee",
    # Database investigation
    "run_sql",
    "get_schema",
    "call_api",
    "list_routes",
]
```

## Recommended Immediate Fix
For the onboarding workflow MVP:

1. **Update `backend/app/config/mcp_config.py`:**
   - Add all BRS tools to `USER_ALLOWLIST`
   - This allows regular users to execute onboarding workflows

2. **Document in handover:**
   - Note that RBAC is working correctly
   - Tools are filtered by role as designed
   - Production should use OPERATOR role for workflow execution

## Files Involved
- `backend/app/config/mcp_config.py` - Tool allowlists
- `backend/app/api/auth.py` - User creation (default role)
- `backend/app/services/mcp_registry.py` - RBAC filtering logic
- `backend/app/services/agentic_service.py` - Tool definition fetching

## Log Evidence
```
MCP_GATEWAY_URL: http://localhost:8090
Using remote gateway: http://localhost:8090
Gateway MCP: http://localhost:8090 (remote)
```

Gateway is connected and responding, but tools are filtered by role before reaching the agent.
