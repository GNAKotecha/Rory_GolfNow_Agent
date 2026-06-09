# Phase 6 Handover: SSO, Embedded Auth, and Role-Based Access Control

## Status
🟡 **IN PROGRESS** - Task 2 Complete

## Summary
Phase 6 adds three-way authentication (local, SSO, teesheet embedded) with a unified RBAC layer that determines tool access, data permissions, and actions based on principal type and role.

---

## Completed Work

### ✅ Task 1: Define Principal/RBAC Model (2026-06-09)

**Status**: COMPLETE

**What Was Implemented**:
- Comprehensive RBAC model supporting three principal types:
  - **LocalPrincipal**: Email/password (existing system)
  - **SSOPrincipal**: Single Sign-On from sso.golfnow.com
  - **TeesheetPrincipal**: Embedded auth from brs-teesheet
- Unified PermissionProfile class for all auth sources
- Python class definitions with full type hints and docstrings
- JSON schema for role→permission configuration
- Complete documentation of role mappings and permission model

**Files Created**:
1. `backend/docs/RBAC_MODEL.md` (1,062 lines)
   - Complete RBAC model documentation
   - Principal type definitions
   - Permission model structure
   - Role mappings for all three auth sources
   - Tool access control model
   - Configuration format
   - Security considerations

2. `backend/app/core/rbac/models.py` (311 lines)
   - `AuthSource` enum (LOCAL, SSO, TEESHEET_EMBED)
   - `ScopeType` enum (GLOBAL, TENANT, CLUB)
   - `PermissionProfile` dataclass
   - `Principal` abstract base class
   - `LocalPrincipal`, `SSOPrincipal`, `TeesheetPrincipal` subclasses
   - `AuthenticatedSession` dataclass
   - Full type annotations and docstrings

3. `backend/app/core/rbac/config_schema.json` (188 lines)
   - JSON Schema for role configuration validation
   - Defines structure for local_roles, sso_roles, teesheet_roles
   - Permission profile schema with all fields
   - Required _default entries for unknown roles

4. `backend/app/core/rbac/__init__.py` (31 lines)
   - Module exports for all classes and enums

**Key Design Decisions**:

1. **Unified Permission Model**:
   - Single `PermissionProfile` class regardless of auth source
   - Consistent permission evaluation across all principal types
   - Scope-based access (global, tenant, club)

2. **Principal Hierarchy**:
   - Abstract `Principal` base class
   - Concrete subclasses for each auth type
   - Each principal knows its role and context

3. **Tool Access Control**:
   - Pattern matching (e.g., "brs_*" allows all brs tools)
   - Explicit denials override allows
   - Default deny for security

4. **Backward Compatibility**:
   - Existing local admin/user roles preserved
   - Current JWT tokens continue working
   - No breaking changes to existing auth flow

**Role Mappings Defined**:

Local Roles:
- `admin`: Full access, global scope
- `user`: Standard access, tenant scope

SSO Roles (Job_Role claim):
- `support`: Customer support access
- `implementation`: Implementation consultant access
- `sales`: Demo/sales access
- `engineering`: Engineering debug access
- `admin`: Administrative access
- `_default`: Read-only fallback for unknown roles

Teesheet Roles:
- `brs_superuser`: BRS-wide super admin
- `superuser`: Club super admin
- `admin`: Club administrator
- `manager`: Club manager
- `staff`: Club staff
- `member`: Club member (read-only)
- `_default`: Read-only fallback for unknown roles

**Testing Results**:
- ✅ Python syntax valid (no errors)
- ✅ All classes properly structured
- ✅ JSON schema validates successfully
- ✅ Documentation complete and clear
- ✅ Git commit successful

**Commit**: `0a80036` - "feat(rbac): Define principal/RBAC model for Phase 6 Task 1"

**Self-Review Notes**:
- Model supports all three principal types as required
- Permission profiles are extensible (easy to add new fields)
- Configuration schema allows for easy role management
- Documentation is comprehensive and clear
- Code follows Python best practices (dataclasses, type hints, docstrings)
- No implementation yet (just model definitions - correct for Task 1)

---

## Remaining Tasks

### ✅ Task 2: Add Database Fields (2026-06-09)
**Status**: COMPLETE & VALIDATED

**What Was Implemented**:
- Added 5 new fields to User model for RBAC authentication
- Created Alembic migration eac10a7850ae with autogenerate
- Fixed Python 3.9 compatibility issues in RBAC models
- Added comprehensive test suite (12 test cases)
- Updated API response schema to include RBAC fields

**Files Created/Modified**:
1. `backend/app/models/models.py` - Added auth_source, external_id, sso_claims, club_context, last_login fields
2. `backend/app/core/rbac/models.py` - Fixed Python 3.9 compatibility (Union instead of |)
3. `backend/alembic/versions/eac10a7850ae_add_rbac_authentication_fields_to_user_.py` - Migration script
4. `backend/tests/test_user_rbac_fields.py` - Test suite for new fields (12 tests)
5. `backend/app/api/schemas.py` - Added RBAC fields to UserResponse schema
6. `backend/requirements.txt` - Added alembic==1.13.1
7. `backend/E2E_TEST_RESULTS_2026-06-09-task2.md` - Complete E2E test results

**Key Features**:
- auth_source defaults to LOCAL for backward compatibility
- external_id indexed for fast lookups
- Migration includes server_default='LOCAL' for existing users
- All fields nullable except auth_source
- API responses now include all RBAC fields

**Testing Status**:
- ✅ Python syntax validated
- ✅ Migration applied to database
- ✅ Unit tests: 12/12 passing
- ✅ E2E validation: Auth working
- ✅ E2E validation: Skills discovery (2 skills found)
- ✅ API schema includes RBAC fields
- ⚠️  Backend must be restarted after schema changes to serve updated API responses

**Production Readiness**:
- ✅ Database schema stable and backward compatible
- ✅ All tests passing
- ✅ No breaking changes to existing functionality
- ✅ Ready for Task 3 (SSO endpoints)

**Commits**:
- `da58c8f` - "feat(phase6): Add database fields for RBAC authentication (Task 2)"
- `d23c491` - "docs(phase6): Update handover with Task 2 completion"
- `a4e96c7` - "fix(phase6): Add RBAC fields to UserResponse schema and alembic to requirements"

**Branch**: `phase-6-task-2-database-fields`

**Known Issues Discovered**:
- Migration must be explicitly run (alembic upgrade head) - not automatic on startup
- Backend restart required after schema changes for API to serve updated responses
- Skills endpoint requires authenticated user (working as designed)

---

### 🔲 Task 3: Add SSO Login/Callback Endpoints
**Status**: NOT STARTED

**Required**:
- `GET /api/auth/sso/login` - Start SSO redirect
- `GET /api/auth/sso/callback` - Handle SSO callback
- SSO configuration (client ID, secret, endpoints)
- OIDC/SAML token validation
- User upsert on SSO login

---

### 🔲 Task 4: Add SSO Button to Login Page
**Status**: NOT STARTED

**Required**:
- Update `frontend/src/app/login/page.tsx`
- Add "Sign in with SSO" button
- Handle SSO redirect flow

---

### 🔲 Task 5: Add Embedded Auth Exchange
**Status**: NOT STARTED

**Required**:
- `POST /api/auth/embed/exchange` endpoint
- JWT signature validation
- Token replay protection (JTI tracking)
- Mint Rory JWT from embed token

---

### 🔲 Task 6: Refactor Tool Allowlists
**Status**: NOT STARTED

**Required**:
- Create RBAC service
- Load role configuration
- Replace hardcoded tool allowlists with permission profiles

---

### 🔲 Task 7: Wire RBAC into System
**Status**: NOT STARTED

**Required**:
- MCP tool discovery filtering
- Tool execution permission checks
- Prompt layer permission context

---

### 🔲 Task 8: Add Tests
**Status**: NOT STARTED

**Required**:
- Unit tests for role mapping
- Auth flow integration tests
- Tool access tests

---

### 🔲 Task 9: Documentation
**Status**: NOT STARTED

**Required**:
- Setup instructions
- Claims/token contracts
- Production deployment guide

---

## Known Issues

### From Prior Phases

#### 🔴 Bug #13: Authentication Token Failure (CRITICAL)
- **Status**: BLOCKING
- **Issue**: Multi-turn conversations fail with 503 auth errors
- **Impact**: Chat unusable after first message
- **Location**: `docs/bugs/BUG_13_AUTHENTICATION_TOKEN_FAILURE.md`
- **Must Fix**: Before Phase 6 auth changes

#### 🟡 Bug #12: Slash Command Autocomplete
- **Status**: MEDIUM PRIORITY
- **Issue**: "/" doesn't trigger skill dropdown
- **Impact**: Users can't discover skills via UI
- **Workaround**: Semantic matching still works
- **Location**: `docs/bugs/BUG_12_SLASH_COMMAND_AUTOCOMPLETE.md`

---

## Architecture Changes

### New RBAC Layer

```
┌─────────────────┐
│   Frontend UI   │
└────────┬────────┘
         │ JWT Token
         ▼
┌─────────────────┐
│   API Gateway   │
│  (FastAPI)      │
└────────┬────────┘
         │ Decode Token → Principal
         ▼
┌─────────────────┐
│  RBAC Service   │
│  - Load Config  │
│  - Map Role     │
│  - Get Profile  │
└────────┬────────┘
         │ PermissionProfile
         ▼
┌─────────────────┐
│  MCP Registry   │
│  - Filter Tools │
│  - Check Scope  │
└────────┬────────┘
         │ Allowed Tools
         ▼
┌─────────────────┐
│  Tool Executor  │
│  - Verify Perm  │
│  - Execute      │
└─────────────────┘
```

### Auth Flow

#### Local Auth (Existing)
```
1. POST /api/auth/login {email, password}
2. Verify password
3. Create LocalPrincipal
4. Evaluate permissions
5. Mint JWT with principal data
6. Return JWT to client
```

#### SSO Auth (New)
```
1. GET /api/auth/sso/login
2. Redirect to sso.golfnow.com
3. User authenticates with SSO
4. Callback to /api/auth/sso/callback?code=...
5. Exchange code for SSO token
6. Validate token, extract Job_Role
7. Create/update user, create SSOPrincipal
8. Evaluate permissions
9. Mint JWT with principal data
10. Return JWT to client
```

#### Embedded Auth (New)
```
1. brs-teesheet generates signed JWT
2. POST /api/auth/embed/exchange {embed_token}
3. Validate signature and claims
4. Extract club_id, role from token
5. Check JTI for replay attack
6. Create TeesheetPrincipal (ephemeral)
7. Evaluate permissions
8. Mint JWT with principal data
9. Return JWT to client
```

---

## Dependencies

### Python Packages
- `jose`: JWT encoding/decoding (already installed)
- `pydantic`: Data validation (already installed)
- `jsonschema`: Config validation (need to install)

### Configuration Files
- `backend/config/rbac_config.json` (to be created in Task 6)
- `backend/config/sso_config.json` (to be created in Task 3)

### Environment Variables
```env
# SSO Configuration
SSO_CLIENT_ID=...
SSO_CLIENT_SECRET=...
SSO_DISCOVERY_URL=https://sso.golfnow.com/.well-known/openid-configuration
SSO_REDIRECT_URI=http://localhost:8000/api/auth/sso/callback

# Embed Token Validation
EMBED_TOKEN_PUBLIC_KEY=...  # For JWT signature validation
EMBED_TOKEN_ISSUER=brs-teesheet
EMBED_TOKEN_AUDIENCE=rory-agent
```

---

## Testing Strategy

### Unit Tests
- Role mapping logic (each role → permission profile)
- Tool access evaluation (pattern matching)
- Scope validation (global/tenant/club)
- Token validation (SSO, embed)

### Integration Tests
- SSO login flow (mock SSO provider)
- Embed token exchange (valid/invalid/expired)
- Permission enforcement (API layer)
- Tool filtering (MCP registry)

### E2E Tests
- Local user login → tool access
- SSO user login → correct permissions
- Embed user → club-scoped access
- Unknown role → read-only fallback

---

## Security Considerations

### Token Security
- SSO tokens validated via OIDC/SAML
- Embed tokens must be signed and verified
- JTI tracking prevents replay attacks
- Short TTLs for embed tokens (15-60 min)

### Permission Enforcement
- Multiple layers (API, MCP registry, tool executor)
- Default deny for unknown roles
- Explicit denials override allows
- Scope validation on every access

### Audit Logging
- All permission decisions logged
- Failed authorization attempts tracked
- Tool usage audited per principal

---

## Migration Strategy

### Phase 1: Model (Current)
- ✅ Define RBAC model
- ✅ Create Python classes
- ✅ Document role mappings

### Phase 2: Database
- Add fields to users table
- Create migration script
- Update User model

### Phase 3: Auth Endpoints
- Implement SSO flow
- Implement embed exchange
- Update frontend

### Phase 4: RBAC Service
- Load configuration
- Evaluate permissions
- Replace hardcoded checks

### Phase 5: Integration
- Wire into MCP registry
- Wire into tool executor
- Wire into prompt layer

### Phase 6: Testing & Deployment
- Full test suite
- Documentation
- Production deployment

---

## Next Session

**Immediate Next Step**: Task 2 - Add database fields

**Blockers**:
- None for Task 2
- Bug #13 (auth token failure) should be investigated in parallel

**Questions for User**:
- None at this time

**Estimated Time**:
- Task 2: 30-45 minutes (migration + model updates)

---

## References

- **Phase 6 Spec**: `docs/superpowers/specs/PHASE_6_SPEC.md`
- **RBAC Model Doc**: `backend/docs/RBAC_MODEL.md`
- **Current User Model**: `backend/app/models/models.py`
- **Current Auth Service**: `backend/app/services/auth.py`
- **Bug Reports**: `docs/bugs/BUG_12_*.md`, `BUG_13_*.md`
- **E2E Test Results**: `docs/E2E_TEST_RESULTS_2026-06-09.md`

---

## Git History

```
0a80036 feat(rbac): Define principal/RBAC model for Phase 6 Task 1
```

---

**Last Updated**: 2026-06-09 09:50 UTC
**Updated By**: Claude (Subagent-Driven Development)
