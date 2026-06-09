# RBAC Model - Role-Based Access Control for Rory Agent

## Overview

This document defines the Role-Based Access Control (RBAC) model for the Rory Agent system, supporting three principal types:
1. **Local Users** - Email/password authentication (current system)
2. **SSO Users** - Single Sign-On from `sso.golfnow.com`
3. **Teesheet Embedded Users** - Embedded auth from `brs-teesheet` application

## Design Goals

- **Unified Permission Model**: Single permission evaluation regardless of auth source
- **Backward Compatible**: Existing local `admin`/`user` roles continue working
- **Extensible**: Easy to add new roles or permission types
- **Least Privilege**: Unknown roles default to read-only access
- **Club-Scoped**: Teesheet users have permissions scoped to specific clubs
- **Auditable**: All permission decisions are logged

---

## Principal Types

### 1. Local Principal
**Auth Source**: Email/password stored in local database

**Characteristics**:
- Stored in `users` table
- Password hashed with bcrypt
- Requires admin approval (`approval_status`)
- Tenant-scoped
- Persistent across sessions

**Roles**:
- `admin`: Full system access
- `user`: Standard access

**Lifecycle**:
- Created via registration API
- Approved by existing admin
- Persists until deleted

---

### 2. SSO Principal
**Auth Source**: OIDC/SAML from `https://sso.golfnow.com/app/`

**Characteristics**:
- Authenticated externally
- User record created/updated on first login
- `Job_Role` claim from SSO provider maps to permissions
- No local password
- Tenant assignment based on SSO claims

**Roles** (from `Job_Role` claim):
- `support`: Customer support access
- `implementation`: Implementation/onboarding access
- `sales`: Sales/demo access
- `engineering`: Engineering/development access
- `admin`: Administrative access
- (Others as configured)

**Lifecycle**:
- Created on first SSO login (just-in-time provisioning)
- Updated on subsequent logins (claims refresh)
- Deactivated when SSO session expires

**Claims Contract**:
```json
{
  "sub": "user@golfnow.com",
  "email": "user@golfnow.com",
  "name": "John Doe",
  "Job_Role": "support",
  "tenant": "golfnow",
  "iss": "https://sso.golfnow.com",
  "aud": "rory-agent",
  "exp": 1234567890,
  "iat": 1234567890
}
```

---

### 3. Teesheet Embedded Principal
**Auth Source**: Signed JWT from `brs-teesheet` application

**Characteristics**:
- Short-lived sessions (15-60 minutes)
- Club-scoped permissions
- User may have different roles at different clubs
- No persistent login (re-auth required per embed)
- Context includes club information

**Roles** (from embed token):
- `brs_superuser`: BRS super administrator
- `superuser`: Club super administrator
- `admin`: Club administrator
- `manager`: Club manager
- `staff`: Club staff
- `member`: Club member (read-only)

**Lifecycle**:
- Created on embed token exchange
- Session expires with token (15-60 min)
- No persistent user record (ephemeral)

**Embed Token Contract**:
```json
{
  "sub": "12345",
  "email": "user@club.com",
  "name": "Jane Smith",
  "club_id": 123,
  "club_name": "Pine Valley Golf Club",
  "role": "admin",
  "iss": "brs-teesheet",
  "aud": "rory-agent",
  "exp": 1234567890,
  "iat": 1234567890,
  "jti": "unique-token-id"
}
```

---

## Permission Model

### Permission Profile Structure

Each principal is assigned **one effective permission profile** based on their role and context:

```python
class PermissionProfile:
    """Effective permissions for a principal."""
    
    # Identity
    profile_id: str  # e.g., "local-admin", "sso-support", "teesheet-admin"
    description: str
    
    # Scope
    scope_type: str  # "global", "tenant", "club"
    scope_id: Optional[int]  # tenant_id or club_id if scoped
    
    # Tool Access
    allowed_tools: List[str]  # MCP tool names or patterns
    denied_tools: List[str]   # Explicit denials (override allows)
    
    # Data Access
    can_read_all_conversations: bool
    can_read_own_conversations: bool
    can_write_conversations: bool
    can_access_admin_apis: bool
    
    # Actions
    can_create_skills: bool
    can_modify_skills: bool
    can_delete_skills: bool
    can_create_workflows: bool
    can_modify_workflows: bool
    can_approve_users: bool
    
    # Workflow
    can_trigger_workflows: bool
    max_workflow_cost: Optional[int]  # Max tokens/workflow
    
    # Rate Limits
    max_requests_per_minute: int
    max_tokens_per_day: Optional[int]
```

### Permission Evaluation

```python
def evaluate_permissions(principal: Principal) -> PermissionProfile:
    """Evaluate effective permissions for a principal."""
    
    if isinstance(principal, LocalPrincipal):
        return evaluate_local_permissions(principal)
    elif isinstance(principal, SSOPrincipal):
        return evaluate_sso_permissions(principal)
    elif isinstance(principal, TeesheetPrincipal):
        return evaluate_teesheet_permissions(principal)
    else:
        return get_default_readonly_profile()
```

---

## Role Mappings

### Local Roles

#### `admin`
- **Scope**: Global (all tenants)
- **Tools**: All MCP tools
- **Data**: Read/write all conversations, all admin APIs
- **Actions**: All (create/modify/delete skills, workflows, approve users)
- **Limits**: Unlimited

#### `user`
- **Scope**: Tenant (own tenant only)
- **Tools**: Read-only tools + limited write tools (e.g., booking creation)
- **Data**: Read/write own conversations only
- **Actions**: Trigger workflows, create skills (with approval)
- **Limits**: 100 req/min, 1M tokens/day

---

### SSO Roles

#### `support` (Job_Role)
- **Scope**: Tenant (assigned tenant)
- **Tools**: Read-only tools + customer data tools
- **Data**: Read all conversations (for support), write limited
- **Actions**: Trigger workflows, no skill/workflow modification
- **Limits**: 200 req/min, 2M tokens/day
- **Use Case**: Customer support needs to view user interactions

#### `implementation` (Job_Role)
- **Scope**: Tenant (assigned tenant)
- **Tools**: Configuration tools, setup tools, limited write
- **Data**: Read/write all conversations
- **Actions**: Create/modify skills and workflows (no delete)
- **Limits**: 150 req/min, 1.5M tokens/day
- **Use Case**: Onboarding/implementation consultants

#### `sales` (Job_Role)
- **Scope**: Tenant (demo tenant)
- **Tools**: Demo-safe tools only (no destructive operations)
- **Data**: Read demo conversations
- **Actions**: Trigger workflows only
- **Limits**: 50 req/min, 500K tokens/day
- **Use Case**: Sales demos and trials

#### `engineering` (Job_Role)
- **Scope**: Global (all tenants for debugging)
- **Tools**: All tools + diagnostic tools
- **Data**: Read all conversations, write own
- **Actions**: All (except user approval)
- **Limits**: 500 req/min, unlimited tokens
- **Use Case**: Engineering debugging and development

#### `admin` (Job_Role)
- **Scope**: Global
- **Tools**: All
- **Data**: All
- **Actions**: All
- **Limits**: Unlimited
- **Use Case**: System administrators

#### Unknown SSO Role
- **Scope**: Tenant (assigned tenant)
- **Tools**: Read-only tools only
- **Data**: Read own conversations
- **Actions**: None
- **Limits**: 10 req/min, 10K tokens/day
- **Use Case**: Fail-safe for unmapped roles

---

### Teesheet Embedded Roles

#### `brs_superuser`
- **Scope**: Global (all clubs)
- **Tools**: All BRS tools
- **Data**: Read/write all club data
- **Actions**: All club operations
- **Limits**: 200 req/min, 2M tokens/day

#### `superuser`
- **Scope**: Club (specific club_id from token)
- **Tools**: All BRS tools for own club
- **Data**: Read/write own club data
- **Actions**: All operations within club
- **Limits**: 150 req/min, 1M tokens/day

#### `admin`
- **Scope**: Club (specific club_id from token)
- **Tools**: Management tools (bookings, users, settings)
- **Data**: Read/write own club data
- **Actions**: Manage bookings, users, settings
- **Limits**: 100 req/min, 500K tokens/day

#### `manager`
- **Scope**: Club (specific club_id from token)
- **Tools**: Operational tools (bookings, tee times)
- **Data**: Read/write operational data
- **Actions**: Manage bookings and tee times
- **Limits**: 100 req/min, 500K tokens/day

#### `staff`
- **Scope**: Club (specific club_id from token)
- **Tools**: Limited operational tools (view bookings, create simple bookings)
- **Data**: Read operational data
- **Actions**: Basic booking operations
- **Limits**: 50 req/min, 100K tokens/day

#### `member`
- **Scope**: Club (specific club_id from token)
- **Tools**: Read-only tools
- **Data**: Read own booking data
- **Actions**: View own bookings
- **Limits**: 20 req/min, 50K tokens/day

#### Unknown Teesheet Role
- **Scope**: Club (specific club_id from token)
- **Tools**: Read-only tools
- **Data**: Read own data
- **Actions**: None
- **Limits**: 10 req/min, 10K tokens/day

---

## Tool Access Control

### Tool Categories

Tools are categorized by risk and sensitivity:

1. **Read-Only Tools**: Safe for all users (e.g., `get_booking`, `list_clubs`)
2. **Write Tools**: Modify data (e.g., `create_booking`, `update_member`)
3. **Admin Tools**: System configuration (e.g., `create_tenant`, `approve_user`)
4. **Diagnostic Tools**: Debugging/introspection (e.g., `list_all_tools`, `view_logs`)
5. **Destructive Tools**: Cannot be undone (e.g., `delete_booking`, `cancel_membership`)

### Permission Evaluation for Tools

```python
def can_use_tool(principal: Principal, tool_name: str) -> bool:
    """Check if principal can use a tool."""
    profile = evaluate_permissions(principal)
    
    # Check explicit denials first
    if tool_name in profile.denied_tools:
        return False
    
    # Check explicit allows
    if tool_name in profile.allowed_tools:
        return check_scope(principal, tool_name)
    
    # Check pattern matches (e.g., "brs_*")
    for pattern in profile.allowed_tools:
        if fnmatch(tool_name, pattern):
            return check_scope(principal, tool_name)
    
    # Default deny
    return False


def check_scope(principal: Principal, tool_name: str) -> bool:
    """Verify tool operation is within principal's scope."""
    if principal.scope_type == "global":
        return True
    
    if principal.scope_type == "tenant":
        # Tool must operate on principal's tenant
        return tool_operates_on_tenant(tool_name, principal.scope_id)
    
    if principal.scope_type == "club":
        # Tool must operate on principal's club
        return tool_operates_on_club(tool_name, principal.scope_id)
    
    return False
```

---

## Configuration

### Role Mapping Configuration File

Location: `backend/config/rbac_config.json`

```json
{
  "version": "1.0",
  "local_roles": {
    "admin": {
      "profile_id": "local-admin",
      "description": "Local administrator with full access",
      "scope_type": "global",
      "allowed_tools": ["*"],
      "can_read_all_conversations": true,
      "can_write_conversations": true,
      "can_access_admin_apis": true,
      "can_create_skills": true,
      "can_modify_skills": true,
      "can_delete_skills": true,
      "can_approve_users": true,
      "max_requests_per_minute": -1
    },
    "user": {
      "profile_id": "local-user",
      "description": "Standard local user",
      "scope_type": "tenant",
      "allowed_tools": ["brs_*", "get_*", "list_*", "create_booking"],
      "denied_tools": ["delete_*", "admin_*"],
      "can_read_own_conversations": true,
      "can_write_conversations": true,
      "can_trigger_workflows": true,
      "max_requests_per_minute": 100,
      "max_tokens_per_day": 1000000
    }
  },
  "sso_roles": {
    "support": {
      "profile_id": "sso-support",
      "description": "Customer support role",
      "scope_type": "tenant",
      "allowed_tools": ["get_*", "list_*", "search_*"],
      "can_read_all_conversations": true,
      "can_trigger_workflows": true,
      "max_requests_per_minute": 200
    },
    "implementation": {
      "profile_id": "sso-implementation",
      "description": "Implementation consultant",
      "scope_type": "tenant",
      "allowed_tools": ["*"],
      "denied_tools": ["delete_*", "admin_*"],
      "can_read_all_conversations": true,
      "can_write_conversations": true,
      "can_create_skills": true,
      "can_modify_skills": true,
      "can_create_workflows": true,
      "can_modify_workflows": true,
      "max_requests_per_minute": 150
    },
    "_default": {
      "profile_id": "sso-readonly",
      "description": "Unknown SSO role - read-only access",
      "scope_type": "tenant",
      "allowed_tools": ["get_*", "list_*"],
      "can_read_own_conversations": true,
      "max_requests_per_minute": 10
    }
  },
  "teesheet_roles": {
    "brs_superuser": {
      "profile_id": "teesheet-brs-superuser",
      "description": "BRS super administrator",
      "scope_type": "global",
      "allowed_tools": ["brs_*"],
      "max_requests_per_minute": 200
    },
    "superuser": {
      "profile_id": "teesheet-superuser",
      "description": "Club super administrator",
      "scope_type": "club",
      "allowed_tools": ["brs_*"],
      "max_requests_per_minute": 150
    },
    "admin": {
      "profile_id": "teesheet-admin",
      "description": "Club administrator",
      "scope_type": "club",
      "allowed_tools": ["brs_get_*", "brs_list_*", "brs_create_*", "brs_update_*"],
      "denied_tools": ["brs_delete_*"],
      "max_requests_per_minute": 100
    },
    "_default": {
      "profile_id": "teesheet-readonly",
      "description": "Unknown teesheet role - read-only access",
      "scope_type": "club",
      "allowed_tools": ["brs_get_*", "brs_list_*"],
      "max_requests_per_minute": 10
    }
  }
}
```

---

## Implementation Strategy

### Phase 1: Model Definition (Current Task)
- Define principal types and permission model
- Create configuration schema
- Document role mappings

### Phase 2: Database Schema
- Add auth_source, external_id, sso_claims to users table
- Add club_context for teesheet users
- Migration scripts

### Phase 3: Auth Endpoints
- SSO login/callback
- Embed token exchange
- JWT minting with principal type

### Phase 4: Permission Evaluation
- Implement RBAC service
- Load configuration
- Evaluate permissions per request

### Phase 5: Tool Access Control
- Wire RBAC into MCP registry
- Filter tools by permissions
- Enforce on execution

### Phase 6: Testing
- Unit tests for role mapping
- Integration tests for auth flows
- Tool access tests

---

## Security Considerations

### Principle of Least Privilege
- Default deny for unknown roles
- Explicit allows only
- Scope restrictions enforced

### Token Security
- SSO tokens validated via OIDC/SAML
- Embed tokens signed and verified
- Short TTLs for embed tokens (15-60 min)
- Replay protection via JTI tracking

### Audit Logging
- All permission decisions logged
- Tool usage tracked per principal
- Failed authorization attempts logged

### Defense in Depth
- Permission check at API layer
- Permission check at MCP registry
- Permission check at tool execution
- Scope validation on data access

---

## Migration Path

### Backward Compatibility
- Existing local `admin` and `user` roles unchanged
- Current JWT tokens continue working
- No breaking changes to existing APIs

### Gradual Rollout
1. Deploy RBAC model (no enforcement)
2. Enable permission logging (observe)
3. Enable permission enforcement (warn mode)
4. Enable full enforcement
5. Deprecate old permission logic

---

## Future Enhancements

- **Dynamic Roles**: User-defined roles via UI
- **Permission Templates**: Reusable permission sets
- **Role Hierarchy**: Inheritance (e.g., admin inherits user)
- **Time-Based Access**: Temporary role grants
- **Multi-Factor**: Require MFA for sensitive operations
- **Audit UI**: View permission history and decisions

---

## References

- Phase 6 Spec: `docs/superpowers/specs/PHASE_6_SPEC.md`
- Current User Model: `backend/app/models/models.py`
- Current Auth Service: `backend/app/services/auth.py`
- JWT Standard: RFC 7519
- OIDC Standard: OpenID Connect Core 1.0
