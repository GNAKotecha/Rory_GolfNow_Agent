# MCP Authentication UX Proposal

**Date:** 2026-06-09  
**Purpose:** Define user-friendly authentication flow for MCP servers  
**Status:** PROPOSED (not yet implemented)

---

## Problem Statement

Currently, MCP tool execution fails with 401 errors because:
1. No authentication credentials configured
2. No way for users to provide their own credentials
3. No interactive authentication flow

**Current broken flow:**
```
User: "Use get_club_by_name to look up 'brsgolfclubsales'"
→ Backend calls Gateway MCP
→ Gateway MCP calls BRS API (no auth token)
→ BRS API returns 401 Unauthorized
→ User sees error message (dead end)
```

---

## Proposed Solution: Interactive Authentication

**Key Principle:** Authentication should be **user-driven** and **on-demand**, not system-configured.

---

## UX Flow Option 1: Authenticate at Tool Execution

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ User sends message in chat                                      │
│ "Use get_club_by_name to look up 'brsgolfclubsales'"          │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ Backend attempts to execute tool                                │
│ → Calls Gateway MCP with user session context                  │
│ → Gateway MCP checks if BRS credentials exist for this user    │
└────────────────────────────┬────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
         No credentials              Has credentials
              │                             │
              ▼                             ▼
┌─────────────────────────────┐    ┌────────────────────────────┐
│ Return auth_required        │    │ Execute tool with creds    │
│ response to frontend        │    │ Return result              │
└────────────┬────────────────┘    └────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│ Frontend shows authentication modal                             │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  🔒 Authentication Required                              │  │
│  │                                                           │  │
│  │  The tool "get_club_by_name" requires BRS authentication │  │
│  │                                                           │  │
│  │  [Sign in with BRS]  [Cancel]                           │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                User clicks "Sign in with BRS"
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Open OAuth popup or authentication form                         │
│ User enters BRS credentials                                     │
│ BRS returns auth token                                          │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ Frontend stores token in user session                           │
│ Automatically retry tool execution with credentials             │
│ Show success message with tool result                           │
└─────────────────────────────────────────────────────────────────┘
```

### UI Mockup (Authentication Modal)

```
┌─────────────────────────────────────────────────────────────┐
│                    🔒 Authentication Required                │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  The tool get_club_by_name requires authentication to:      │
│                                                              │
│  • BRS Teesheet API (brsgolfclubsales.com)                 │
│                                                              │
│  Your credentials will be stored securely in your session   │
│  and used for future tool calls.                            │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Authentication Method:                               │  │
│  │  ○ OAuth 2.0 (Recommended)                           │  │
│  │  ○ API Key                                            │  │
│  │  ○ Username/Password                                  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  [Continue with OAuth]  [Enter Credentials Manually]        │
│                                                              │
│  [Cancel]                                                    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Chat Interface Integration

**Before Authentication:**
```
┌─────────────────────────────────────────────────────────────┐
│  You: Use get_club_by_name to look up "brsgolfclubsales"   │
├─────────────────────────────────────────────────────────────┤
│  🤖 Assistant:                                              │
│                                                              │
│  ⚠️  Authentication Required                                │
│                                                              │
│  To use the get_club_by_name tool, you need to             │
│  authenticate with BRS Teesheet API.                        │
│                                                              │
│  [Authenticate Now]                                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**After Authentication:**
```
┌─────────────────────────────────────────────────────────────┐
│  You: Use get_club_by_name to look up "brsgolfclubsales"   │
├─────────────────────────────────────────────────────────────┤
│  🤖 Assistant:                                              │
│                                                              │
│  ✅ Found club: brsgolfclubsales                            │
│                                                              │
│  • Club ID: 1234                                            │
│  • Name: BRS Golf Club Sales                                │
│  • Location: Orlando, FL                                    │
│  • Status: Active                                           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## UX Flow Option 2: Authenticate at MCP Server Registration

### When User Adds MCP Server

```
┌─────────────────────────────────────────────────────────────┐
│  Add MCP Server                                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Server Name: Gateway MCP (BRS & Jira)                      │
│  URL: http://localhost:8090                                 │
│                                                              │
│  ⚠️  This server requires authentication                     │
│                                                              │
│  Downstream Services:                                        │
│  • BRS Teesheet API - [Authenticate] [✓ Connected]         │
│  • Jira API         - [Authenticate] [Not connected]       │
│                                                              │
│  [Test Connection]  [Save]                                  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### MCP Server Settings View

```
┌─────────────────────────────────────────────────────────────┐
│  MCP Server: Gateway MCP                                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Status: 🟢 Connected                                       │
│  URL: http://localhost:8090                                 │
│                                                              │
│  Available Tools: 8                                          │
│  • get_club_by_name        [Requires: BRS Auth]            │
│  • verify_club_setup       [Requires: BRS Auth]            │
│  • get_club_config         [Requires: BRS Auth]            │
│  • get_ticket_status       [Requires: Jira Auth]           │
│  • store_memory            [No Auth Required]               │
│  • retrieve_memory         [No Auth Required]               │
│  • list_memory_keys        [No Auth Required]               │
│  • calculate               [No Auth Required]               │
│                                                              │
│  Authentication Status:                                      │
│  • BRS API:  ✅ Authenticated (expires in 2 hours)         │
│             [Re-authenticate]                               │
│  • Jira API: ❌ Not authenticated                          │
│             [Authenticate Now]                              │
│                                                              │
│  [Remove Server]  [Refresh Tools]                           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Backend API Contract

### 1. Tool Execution with Auth Check

**Request:**
```json
POST /api/chat
{
  "message": "Use get_club_by_name to look up 'brsgolfclubsales'",
  "session_id": "abc123"
}
```

**Response (Missing Auth):**
```json
{
  "type": "auth_required",
  "message": "Authentication required for BRS Teesheet API",
  "tool_name": "get_club_by_name",
  "auth_config": {
    "provider": "BRS",
    "methods": ["oauth2", "api_key", "basic"],
    "oauth_url": "https://brsgolf.com/oauth/authorize",
    "scopes": ["read:clubs", "read:members"]
  }
}
```

**Response (Success):**
```json
{
  "type": "tool_result",
  "tool_name": "get_club_by_name",
  "result": {
    "club_id": 1234,
    "name": "BRS Golf Club Sales",
    "location": "Orlando, FL",
    "status": "active"
  }
}
```

### 2. Store Authentication Credentials

**Request:**
```json
POST /api/integrations/mcp/auth
{
  "provider": "BRS",
  "method": "oauth2",
  "token": "eyJhbGc...",
  "refresh_token": "refresh_abc123",
  "expires_at": "2026-06-09T15:27:00Z"
}
```

**Response:**
```json
{
  "status": "authenticated",
  "provider": "BRS",
  "expires_in": 7200,
  "authenticated_tools": [
    "get_club_by_name",
    "verify_club_setup",
    "get_club_config"
  ]
}
```

### 3. Check Authentication Status

**Request:**
```json
GET /api/integrations/mcp/auth/status
```

**Response:**
```json
{
  "providers": [
    {
      "name": "BRS",
      "authenticated": true,
      "expires_at": "2026-06-09T15:27:00Z",
      "tools": ["get_club_by_name", "verify_club_setup", "get_club_config"]
    },
    {
      "name": "Jira",
      "authenticated": false,
      "tools": ["get_ticket_status", "create_ticket", "add_comment"]
    }
  ]
}
```

---

## Database Schema Changes

### New Table: `user_mcp_credentials`

```sql
CREATE TABLE user_mcp_credentials (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,  -- 'BRS', 'Jira', etc.
    auth_method VARCHAR(20) NOT NULL,  -- 'oauth2', 'api_key', 'basic'
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    token_type VARCHAR(20) DEFAULT 'Bearer',
    expires_at TIMESTAMP,
    scopes TEXT[],  -- Array of OAuth scopes
    metadata JSONB,  -- Additional provider-specific data
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, provider)
);

CREATE INDEX idx_user_mcp_creds_user_id ON user_mcp_credentials(user_id);
CREATE INDEX idx_user_mcp_creds_provider ON user_mcp_credentials(provider);
CREATE INDEX idx_user_mcp_creds_expires_at ON user_mcp_credentials(expires_at);
```

### Update: Add auth metadata to tool definitions

```python
class MCPTool:
    name: str
    description: str
    input_schema: dict
    requires_auth: bool = False  # NEW
    auth_provider: Optional[str] = None  # NEW: 'BRS', 'Jira', etc.
    auth_scopes: List[str] = []  # NEW: Required OAuth scopes
```

---

## Implementation Phases

### Phase 1: Backend Auth Infrastructure (4-6 hours)
- [ ] Create `user_mcp_credentials` table
- [ ] Add auth storage endpoints (`POST /api/integrations/mcp/auth`)
- [ ] Add auth check in MCP client before tool execution
- [ ] Return `auth_required` response when credentials missing
- [ ] Pass user credentials to Gateway MCP in request headers
- [ ] Add token refresh mechanism

### Phase 2: Gateway MCP Auth Handling (2-3 hours)
- [ ] Accept credentials in request headers
- [ ] Validate credentials before calling downstream APIs
- [ ] Return proper error codes when auth fails
- [ ] Add credential caching per request
- [ ] Support multiple auth methods (OAuth, API key, basic)

### Phase 3: Frontend Auth UI (4-6 hours)
- [ ] Create authentication modal component
- [ ] Detect `auth_required` responses from backend
- [ ] Show authentication popup when needed
- [ ] Implement OAuth flow (popup window)
- [ ] Store tokens in localStorage/sessionStorage
- [ ] Retry tool execution after authentication
- [ ] Add visual indicators for auth status

### Phase 4: MCP Server Settings UI (3-4 hours)
- [ ] Add MCP server management page
- [ ] Show authentication status per provider
- [ ] Add "Authenticate" buttons
- [ ] Show which tools require which auth
- [ ] Add token expiry warnings
- [ ] Add re-authentication flow

### Phase 5: Testing & Polish (2-3 hours)
- [ ] E2E test: Tool execution with auth
- [ ] E2E test: Auth popup flow
- [ ] E2E test: Token expiry and refresh
- [ ] Error message improvements
- [ ] Loading states and feedback
- [ ] Documentation

**Total Estimated Time:** 15-22 hours

---

## Security Considerations

### Token Storage
- ✅ Store tokens in database (encrypted at rest)
- ✅ Use secure session cookies for frontend-backend communication
- ✅ Clear tokens on logout
- ✅ Support token rotation/refresh

### Access Control
- ✅ Users can only access their own credentials
- ✅ Admin cannot see user tokens (encrypted)
- ✅ Tokens are per-user, not system-wide
- ✅ Audit log for credential usage

### Token Transmission
- ✅ Always use HTTPS in production
- ✅ Pass tokens in headers (not query params)
- ✅ Don't log tokens
- ✅ Don't expose tokens in error messages

---

## User Experience Benefits

### For End Users:
- ✅ **Self-service:** No admin intervention needed
- ✅ **Transparent:** Clear when auth is needed
- ✅ **Interactive:** OAuth flows supported
- ✅ **Secure:** Per-user credentials
- ✅ **Convenient:** Authenticate once, use many times

### For Admins:
- ✅ **Less work:** No need to configure every MCP server
- ✅ **Better security:** No system-wide credentials
- ✅ **Audit trail:** Track who authenticated with what
- ✅ **Flexible:** Users can bring their own credentials

### For Developers:
- ✅ **Standard pattern:** Works for any MCP server
- ✅ **Extensible:** Easy to add new providers
- ✅ **Testable:** Can mock auth in tests
- ✅ **Maintainable:** No hardcoded credentials

---

## Example: Complete Flow

### User Story
**As a user**, I want to look up club information using the BRS tools without needing admin help.

### Steps

1. **User sends message:**
   ```
   "Use get_club_by_name to look up 'brsgolfclubsales'"
   ```

2. **Backend checks auth:**
   - Query `user_mcp_credentials` for user_id=19, provider='BRS'
   - No record found → return `auth_required`

3. **Frontend shows popup:**
   ```
   🔒 Authentication Required
   
   The tool "get_club_by_name" requires BRS authentication.
   
   [Sign in with BRS]  [Cancel]
   ```

4. **User clicks "Sign in with BRS":**
   - Opens OAuth popup window
   - User enters BRS credentials
   - BRS redirects back with auth code
   - Frontend exchanges code for token
   - Frontend calls `POST /api/integrations/mcp/auth` with token

5. **Backend stores credentials:**
   - Insert into `user_mcp_credentials` table
   - Encrypt access_token
   - Store refresh_token

6. **Frontend retries tool execution:**
   - Send original message again
   - Backend finds credentials in DB
   - Backend calls Gateway MCP with auth token
   - Gateway MCP calls BRS API (authenticated)
   - Tool succeeds ✅

7. **User sees result:**
   ```
   ✅ Found club: brsgolfclubsales
   
   • Club ID: 1234
   • Name: BRS Golf Club Sales
   • Location: Orlando, FL
   ```

8. **Future tool calls:**
   - Credentials already stored
   - No popup needed
   - Automatic authentication ✅

---

## Comparison: Current vs Proposed

| Aspect | Current (Broken) | Proposed (User-Driven) |
|--------|------------------|------------------------|
| **Auth Method** | System-wide env vars | Per-user interactive |
| **Setup** | Admin configures | User authenticates |
| **Security** | Single credential set | Per-user credentials |
| **UX** | Silent failures | Clear auth prompts |
| **OAuth Support** | No | Yes |
| **Token Refresh** | Manual | Automatic |
| **Audit Trail** | No | Yes |
| **Testing** | Hard (needs real creds) | Easy (mock auth) |
| **Production Ready** | ❌ No | ✅ Yes |

---

## Conclusion

**Recommendation:** Implement the user-driven authentication flow (Option 1: Lazy Authentication at Tool Execution).

**Why:**
- Better UX (clear when auth is needed)
- Better security (per-user credentials)
- More flexible (supports OAuth, API keys, etc.)
- Production-ready (no shared credentials)
- Future-proof (works for any MCP server)

**Next Steps:**
1. Review and approve this proposal
2. Create implementation plan
3. Estimate effort per phase
4. Prioritize phases (can ship Phase 1-3 as MVP)
5. Assign developers
6. Track progress in PHASE_6_HANDOVER.md
