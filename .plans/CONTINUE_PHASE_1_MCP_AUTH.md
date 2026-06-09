# Continuation Prompt: Phase 1 MCP Authentication Backend

## Context

You are continuing Phase 1 of the MCP Authentication Backend Infrastructure implementation. This work fixes **Bug #12** - MCP tool execution fails with 401 errors because no user credentials are passed to downstream services (BRS API, Jira).

**Work completed in previous session:**
- ✅ Task 1: Database schema and migration created
- ✅ Task 2: SQLAlchemy model `UserMCPCredential` created

**Work remaining:**
- 🔄 Task 3: Create auth storage API endpoints
- 🔄 Task 4: Add auth check to MCP client
- 🔄 Task 5: Implement credential passthrough to Gateway MCP
- 🔄 Task 6: Add token refresh mechanism
- 🔄 Task 7: End-to-end integration test (including frontend UI testing)
- 🔄 Task 8: Update documentation

## Your Objective

Complete Tasks 3-8 from the Phase 1 implementation plan, with special focus on **E2E testing through the frontend** to verify the complete authentication flow works end-to-end.

## Step-by-Step Instructions

### Step 1: Read Current State

First, understand what's been completed:

```
Read backend/PHASE_5_HANDOVER.md (focus on "Phase 1 MCP Authentication Backend Infrastructure" section)
Read .plans/phase-1-mcp-auth-backend.md (full implementation plan)
Read docs/MCP_AUTH_UX_PROPOSAL.md (UX design and API contracts)
```

Key files already created:
- `backend/alembic/versions/m9n0o1p2q3r4_add_user_mcp_credentials_table.py` - Migration
- `backend/app/models/user_mcp_credential.py` - SQLAlchemy model

### Step 2: Implement Task 3 - Auth Storage API Endpoints

Create `backend/app/api/mcp_auth.py` with these endpoints:

**POST /api/integrations/mcp/auth**
```json
Request:
{
  "provider": "BRS",
  "auth_method": "oauth2",
  "access_token": "eyJhbGc...",
  "refresh_token": "refresh_abc123",
  "expires_at": "2026-06-09T18:00:00Z",
  "scopes": ["read:clubs", "read:members"]
}

Response (200):
{
  "status": "authenticated",
  "provider": "BRS",
  "expires_in": 7200,
  "authenticated_tools": ["get_club_by_name", "verify_club_setup", "get_club_config"]
}
```

**GET /api/integrations/mcp/auth** - List all user's credentials

**GET /api/integrations/mcp/auth/{provider}** - Get specific provider credentials
```json
Response (200):
{
  "provider": "BRS",
  "auth_method": "oauth2",
  "is_authenticated": true,
  "expires_at": "2026-06-09T18:00:00Z",
  "scopes": ["read:clubs"],
  "authenticated_tools": ["get_club_by_name", "verify_club_setup"]
}

Response (404):
{
  "error": {
    "code": "NOT_FOUND",
    "message": "No credentials found for provider: BRS"
  }
}
```

**DELETE /api/integrations/mcp/auth/{provider}** - Delete credentials

**POST /api/integrations/mcp/auth/{provider}/refresh** - Refresh token

**Implementation Notes:**
- Use existing auth middleware from `app/api/auth_deps.py` (get_current_user)
- Follow error handling patterns from `app/api/chat.py`
- Use Pydantic models for request/response validation
- Mount router in `app/main.py`

**Test after implementation:**
```bash
# Test with curl
curl -X POST http://localhost:8000/api/integrations/mcp/auth \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider":"BRS","auth_method":"api_key","access_token":"test_token_123"}'

# Expected: 200 OK with JSON response
```

### Step 3: Implement Task 4 - Auth Check in MCP Client

Modify `backend/app/services/mcp_client.py`:

**Add auth check before tool execution:**
```python
async def call_tool(self, tool_name: str, arguments: dict, user_id: int):
    # 1. Get tool metadata to determine provider
    provider = self._get_provider_for_tool(tool_name)
    
    # 2. Check if user has credentials for provider
    credentials = await self.get_user_credentials(user_id, provider)
    
    # 3. If no credentials, return auth_required response
    if not credentials:
        return {
            "type": "auth_required",
            "message": f"Authentication required for {provider}",
            "tool_name": tool_name,
            "auth_config": {
                "provider": provider,
                "methods": ["oauth2", "api_key"],
                "oauth_url": f"https://{provider}.com/oauth/authorize",
                "scopes": ["read:data"]
            }
        }
    
    # 4. If credentials expired, try refresh
    if credentials.is_expired():
        credentials = await self.refresh_token(credentials)
    
    # 5. Pass credentials to Gateway MCP
    headers = self._build_auth_headers(credentials)
    
    # 6. Call Gateway MCP with auth headers
    result = await self._call_gateway_mcp(tool_name, arguments, headers)
    return result
```

**Add helper methods:**
```python
async def get_user_credentials(self, user_id: int, provider: str):
    """Get credentials from database."""
    from app.models.user_mcp_credential import UserMCPCredential
    return UserMCPCredential.get_by_user_and_provider(self.db, user_id, provider)

def _get_provider_for_tool(self, tool_name: str) -> str:
    """Map tool name to provider."""
    # Hardcoded mapping for now (can be metadata later)
    tool_provider_map = {
        "get_club_by_name": "BRS",
        "verify_club_setup": "BRS",
        "get_club_config": "BRS",
        "create_jira_issue": "Jira",
        "get_jira_issue": "Jira",
    }
    return tool_provider_map.get(tool_name, "Unknown")

def _build_auth_headers(self, credentials) -> dict:
    """Build auth headers for Gateway MCP."""
    return {
        "X-MCP-Auth-Provider": credentials.provider,
        "X-MCP-Auth-Token": credentials.access_token,
        "X-MCP-Auth-Type": credentials.token_type,
        "X-MCP-Auth-Scopes": ",".join(credentials.scopes_list),
    }
```

### Step 4: Implement Task 5 - Credential Passthrough to Gateway MCP

Modify Gateway MCP request handler to extract and use auth headers:

**Find Gateway MCP entry point** (likely `gateway_mcp/server.py` or similar):
```python
# Extract auth headers from request
auth_provider = request.headers.get("X-MCP-Auth-Provider")
auth_token = request.headers.get("X-MCP-Auth-Token")
auth_type = request.headers.get("X-MCP-Auth-Type", "Bearer")

# Pass credentials to downstream API client
if auth_provider == "BRS":
    # Inject credentials into BRS client
    brs_client.set_auth_token(auth_token, token_type=auth_type)
elif auth_provider == "Jira":
    # Inject credentials into Jira client
    jira_client.set_auth_token(auth_token, token_type=auth_type)
```

**Test:** Verify Gateway MCP receives headers and passes them to BRS API.

### Step 5: Implement Task 6 - Token Refresh Mechanism

Add to `mcp_client.py`:

```python
async def refresh_token(self, credentials: UserMCPCredential) -> UserMCPCredential:
    """Refresh OAuth2 token if expired."""
    if credentials.auth_method != "oauth2":
        raise ValueError("Only OAuth2 tokens can be refreshed")
    
    if not credentials.refresh_token:
        raise ValueError("No refresh token available")
    
    # Call provider's token refresh endpoint
    new_tokens = await self._call_provider_refresh(
        credentials.provider,
        credentials.refresh_token
    )
    
    # Update credentials in database
    credentials.access_token = new_tokens["access_token"]
    credentials.expires_at = new_tokens["expires_at"]
    await self.db.commit()
    await self.db.refresh(credentials)
    
    return credentials

async def _call_provider_refresh(self, provider: str, refresh_token: str) -> dict:
    """Call provider-specific refresh endpoint."""
    if provider == "BRS":
        # BRS OAuth2 refresh
        response = await self._http_client.post(
            "https://brs-api.com/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": os.environ.get("BRS_CLIENT_ID"),
                "client_secret": os.environ.get("BRS_CLIENT_SECRET"),
            }
        )
        data = response.json()
        return {
            "access_token": data["access_token"],
            "expires_at": datetime.utcnow() + timedelta(seconds=data["expires_in"])
        }
    else:
        raise ValueError(f"Token refresh not implemented for provider: {provider}")
```

### Step 6: Implement Task 7 - End-to-End Integration Test

**Create `backend/tests/test_mcp_auth_e2e.py`:**

```python
import pytest
from datetime import datetime, timedelta

@pytest.mark.asyncio
async def test_mcp_tool_with_auth(test_client, test_user, test_db):
    """Test MCP tool execution with stored credentials."""
    # Setup: Store BRS credentials for test user
    response = test_client.post(
        "/api/integrations/mcp/auth",
        json={
            "provider": "BRS",
            "auth_method": "oauth2",
            "access_token": "test_token_123",
            "expires_at": (datetime.utcnow() + timedelta(hours=2)).isoformat(),
        },
        headers={"Authorization": f"Bearer {test_user.jwt_token}"}
    )
    assert response.status_code == 200

    # Execute: Call MCP tool
    response = test_client.post(
        "/api/chat",
        json={"message": "Use get_club_by_name to look up 'brsgolfclubsales'"},
        headers={"Authorization": f"Bearer {test_user.jwt_token}"}
    )

    # Verify: Tool execution succeeded (no 401 error)
    data = response.json()
    assert response.status_code == 200
    assert "error" not in data or data.get("error", {}).get("code") != "UNAUTHORIZED"
    assert "club_id" in data.get("result", {})


@pytest.mark.asyncio
async def test_mcp_tool_without_auth(test_client, test_user):
    """Test MCP tool execution without credentials returns auth_required."""
    # Execute: Call MCP tool without storing credentials
    response = test_client.post(
        "/api/chat",
        json={"message": "Use get_club_by_name to look up 'brsgolfclubsales'"},
        headers={"Authorization": f"Bearer {test_user.jwt_token}"}
    )

    # Verify: Returns auth_required response
    data = response.json()
    assert data.get("type") == "auth_required"
    assert data.get("tool_name") == "get_club_by_name"
    assert "auth_config" in data
```

**Run tests:**
```bash
cd backend
pytest tests/test_mcp_auth_e2e.py -v
```

### Step 7: Frontend E2E Testing (CRITICAL)

**Test the complete flow through the frontend UI:**

1. **Start all services:**
```bash
# Terminal 1: Backend
cd backend && uvicorn app.main:app --reload

# Terminal 2: Frontend
cd frontend && npm run dev

# Terminal 3: Gateway MCP (if separate)
cd gateway_mcp && python server.py
```

2. **Test via browser:**
   - Open http://localhost:3000
   - Register/login as test user
   - Approve user (if needed)

3. **Store credentials (via browser console or API):**
```javascript
// Browser console
fetch('http://localhost:8000/api/integrations/mcp/auth', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer ' + localStorage.getItem('token')
  },
  body: JSON.stringify({
    provider: 'BRS',
    auth_method: 'oauth2',
    access_token: 'test_brs_token_from_env',
    expires_at: new Date(Date.now() + 7200000).toISOString()
  })
}).then(r => r.json()).then(console.log)
```

4. **Test tool execution in chat UI:**
   - Type: "Use get_club_by_name to look up 'brsgolfclubsales'"
   - **Expected:** Tool executes successfully, returns club data
   - **Not Expected:** 401 error or "authentication error" message

5. **Test without credentials:**
   - Delete credentials: `DELETE /api/integrations/mcp/auth/BRS`
   - Try same message
   - **Expected:** System prompts for authentication
   - **Not Expected:** Generic error

6. **Test token expiry:**
   - Store credential with expires_at in past
   - Try tool execution
   - **Expected:** System attempts refresh or prompts for re-auth

**Use Playwright for automated frontend testing:**
```typescript
// frontend/tests/mcp-auth.spec.ts
import { test, expect } from '@playwright/test';

test('MCP tool execution with authentication', async ({ page }) => {
  // Login
  await page.goto('http://localhost:3000/login');
  await page.fill('[name="email"]', 'test@example.com');
  await page.fill('[name="password"]', 'password123');
  await page.click('button[type="submit"]');

  // Wait for chat interface
  await expect(page.locator('.chat-interface')).toBeVisible();

  // Store credentials via API (use page.evaluate to call fetch)
  await page.evaluate(() => {
    return fetch('http://localhost:8000/api/integrations/mcp/auth', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + localStorage.getItem('token')
      },
      body: JSON.stringify({
        provider: 'BRS',
        auth_method: 'oauth2',
        access_token: 'test_token',
        expires_at: new Date(Date.now() + 7200000).toISOString()
      })
    });
  });

  // Send message to use MCP tool
  await page.fill('.chat-input', 'Use get_club_by_name to look up brsgolfclubsales');
  await page.click('.send-button');

  // Wait for response
  await page.waitForSelector('.message.assistant', { timeout: 10000 });

  // Verify no 401 error
  const response = await page.locator('.message.assistant').last().textContent();
  expect(response).not.toContain('401');
  expect(response).not.toContain('authentication error');
  expect(response).toContain('club'); // Should contain club data
});
```

**Run Playwright tests:**
```bash
cd frontend
npx playwright test tests/mcp-auth.spec.ts
```

### Step 8: Update Documentation

Update `backend/PHASE_5_HANDOVER.md`:

1. **Mark Bug #12 as RESOLVED:**
```markdown
#### Bug #12: MCP Authentication Failure (P0 - RESOLVED)

**Severity:** CRITICAL  
**Status:** ✅ RESOLVED (2026-06-09)  
**Resolution:** Phase 1 MCP Authentication Backend complete

**What Was Fixed:**
- Created user_mcp_credentials table for per-user credential storage
- Implemented API endpoints for credential management
- Added auth check in MCP client before tool execution
- Implemented credential passthrough to Gateway MCP
- Added token refresh mechanism for OAuth2
- Verified via E2E tests (backend + frontend)

**How to Use:**
1. Store credentials: `POST /api/integrations/mcp/auth`
2. Call MCP tool: System automatically uses stored credentials
3. Token refresh: Automatic if expires within 5 minutes
```

2. **Update Phase 1 section:**
```markdown
### Phase 1 MCP Authentication Backend Infrastructure (COMPLETE)

**Date Started:** 2026-06-09 14:30 UTC  
**Date Completed:** 2026-06-09 XX:XX UTC  
**Status:** ✅ COMPLETE  
**All 8 tasks completed successfully**

**Files Created:**
- backend/alembic/versions/m9n0o1p2q3r4_add_user_mcp_credentials_table.py
- backend/app/models/user_mcp_credential.py
- backend/app/api/mcp_auth.py
- backend/tests/test_mcp_auth_e2e.py
- frontend/tests/mcp-auth.spec.ts (Playwright)

**E2E Test Results:**
- ✅ Tool execution with valid credentials: PASS
- ✅ Tool execution without credentials: Returns auth_required
- ✅ Token expiry handling: Auto-refresh works
- ✅ Frontend UI testing: PASS (Playwright)
- ✅ No more 401 errors from downstream APIs

**Next Steps:**
- Phase 2: Frontend auth prompt UI (see MCP_AUTH_UX_PROPOSAL.md)
- Phase 3: OAuth2 flow implementation
- Phase 4: MCP settings page
```

## Success Criteria

You are done when:

- [ ] All API endpoints work (test with curl)
- [ ] MCP client checks auth before tool execution
- [ ] Credentials passed to Gateway MCP successfully
- [ ] Token refresh mechanism works
- [ ] Backend E2E tests pass: `pytest tests/test_mcp_auth_e2e.py -v`
- [ ] **Frontend E2E test passes via Playwright**
- [ ] Manual browser test confirms: No 401 errors when calling MCP tools
- [ ] Bug #12 marked as RESOLVED in PHASE_5_HANDOVER.md
- [ ] All commits pushed to main branch

## Important Notes

1. **Use /subagent-driven-development for execution** (if comfortable with the pattern)
2. **Test incrementally** - Don't wait until all tasks are done to test
3. **Frontend testing is mandatory** - Bug #12 only fixed if frontend works
4. **Use real BRS credentials** from environment variables for testing
5. **Document any blockers** in PHASE_5_HANDOVER.md

## Reference Documents

- Implementation plan: `.plans/phase-1-mcp-auth-backend.md`
- UX proposal: `docs/MCP_AUTH_UX_PROPOSAL.md`
- Current handover: `backend/PHASE_5_HANDOVER.md`
- Bug report: See "Bug #12" in PHASE_5_HANDOVER.md

## Getting Help

If you encounter blockers:
1. Document the blocker in PHASE_5_HANDOVER.md
2. Check existing credential patterns in `app/api/credentials.py`
3. Check MCP client patterns in `app/services/mcp_client.py`
4. Review error handling in `app/api/chat.py`

Good luck! 🚀
