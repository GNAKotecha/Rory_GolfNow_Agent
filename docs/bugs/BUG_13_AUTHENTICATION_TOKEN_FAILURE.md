# Bug #13: Authentication Token Failure Causing 503 Errors

## Status
🔴 **OPEN** - Discovered 2026-06-09  
⚠️ **CRITICAL** - Production Blocker

## Severity
**Critical** - Blocks all chat functionality after first message

## Summary
After the first successful message in a conversation, subsequent messages fail with 503 Service Unavailable and authentication errors. This makes the system unusable for multi-turn conversations.

## Expected Behavior
1. User sends first message → works
2. User sends second message → works
3. User sends N messages → all work
4. BRS API token automatically refreshes when needed
5. No authentication errors in multi-turn conversations

## Actual Behavior
1. User sends first message → ✅ works (REINSTATE_USER skill executed successfully)
2. User sends second message → ❌ fails with 503 error
3. Frontend shows alert: "Failed to send message. Please try again."
4. Backend returns: "Agentic workflow error: Authentication failed for API backend token"

## Error Messages

### Frontend Console
```
[ERROR] Failed to load resource: the server responded with a status of 503 (Service Unavailable) 
@ http://localhost:8000/api/chat

[ERROR] [ApiClient] POST /api/chat failed: Agentic workflow error: 
Authentication failed for API backend token

[ERROR] Failed to send message: Error: Agentic workflow error: 
Authentication failed for API backend token
```

### Backend (expected)
```
ERROR: BRS API authentication failed
ERROR: Token expired or invalid
ERROR: Failed to refresh BRS API token
```

## Steps to Reproduce
1. Navigate to http://localhost:3000/chat
2. Send first message: "I need to reinstate user ID 12345 in brsgolfclubsales"
   - ✅ Works - skill executes, response appears
3. Send second message: "What tools do you have access to?"
   - ❌ Fails - 503 error, alert shown

## Environment
- **Frontend**: localhost:3000 (Next.js)
- **Backend**: localhost:8000 (FastAPI)
- **BRS API**: http://localhost:8056 (assumed)
- **User**: admin@test.com
- **Test Date**: 2026-06-09 08:46-08:49 UTC

## Investigation Notes

### What Works
- ✅ First message in conversation succeeds
- ✅ BRS API tools execute (run_sql, call_api worked in first message)
- ✅ Frontend-backend communication layer works initially

### What's Broken
- ❌ Second (and subsequent) messages fail
- ❌ BRS API authentication not persisting across requests
- ❌ Token refresh mechanism not working

### Root Cause Hypotheses

#### Hypothesis 1: Token Expiration (Most Likely)
- BRS API token has short TTL (e.g., 5 minutes)
- First message uses valid token
- Second message arrives after token expired
- Token refresh logic not working

#### Hypothesis 2: Token Not Persisted
- Token obtained for first request
- Not stored in session/memory
- Second request tries to auth again and fails

#### Hypothesis 3: BRS API Connection Lost
- BRS API docker container restarted between requests
- Connection pool closed
- No reconnection logic

#### Hypothesis 4: Configuration Missing
- `BRS_API_KEY` or client credentials missing from `.env`
- First request succeeded with cached token
- Second request fails when trying to refresh

## Files to Investigate

### Backend
- `backend/config.py` - BRS API configuration
- `backend/.env` - API credentials
- `backend/core/brs_client.py` - BRS API client (if exists)
- `backend/core/agentic_orchestrator.py` - Token management
- `backend/tools/brs_admin_tools.py` - BRS tool implementations

### BRS API
- Check if BRS API is running: `docker ps | grep brs`
- Check BRS API logs: `docker logs brs-api`
- Verify OAuth endpoint: `http://localhost:8056/oauth/v2/token`

## Observed Behavior Pattern
```
Request 1 (t=0s):   ✅ Success - Token valid
Request 2 (t=+10s): ❌ Failed - Auth error 503
```

This suggests:
1. Token obtained for request 1
2. Token expired or not available for request 2
3. No automatic refresh mechanism

## Impact
- **Users**: Cannot have multi-turn conversations
- **Workflows**: Multi-step workflows fail after first step
- **Production**: System is unusable in current state

## Related Issues
- May be related to Bug #11 (LLM timeout) if token refresh causes delays
- Phase 4 implemented BRS MCP tools - auth may have worked then

## Fix Priority
**Critical** - Must be fixed before ANY production deployment

## Proposed Fix

### Immediate Actions
1. **Check BRS API Status**
   ```bash
   docker ps | grep brs
   curl http://localhost:8056/api/health
   ```

2. **Verify Backend Configuration**
   ```bash
   cd backend
   grep -i "BRS_" .env
   ```

3. **Check Backend Logs**
   ```bash
   tail -f backend/logs/agentic_*.log | grep -i "auth\|token\|brs"
   ```

### Implementation Steps
1. **Add Token Refresh Logic**
   ```python
   class BRSClient:
       def __init__(self):
           self.token = None
           self.token_expires_at = None
       
       async def get_token(self):
           if self.token and datetime.now() < self.token_expires_at:
               return self.token
           
           # Refresh token
           self.token = await self._fetch_new_token()
           return self.token
   ```

2. **Add Retry with Token Refresh**
   ```python
   async def call_brs_api(self, endpoint, method, data):
       try:
           token = await self.get_token()
           response = await self._request(endpoint, token, method, data)
           return response
       except AuthenticationError:
           # Force token refresh and retry once
           self.token = None
           token = await self.get_token()
           response = await self._request(endpoint, token, method, data)
           return response
   ```

3. **Add Health Check**
   ```python
   async def health_check(self):
       try:
           await self.get_token()
           return True
       except Exception as e:
           logger.error(f"BRS API health check failed: {e}")
           return False
   ```

### Configuration Required
```env
# .env
BRS_API_URL=http://localhost:8056
BRS_CLIENT_ID=your_client_id
BRS_CLIENT_SECRET=your_client_secret
BRS_API_KEY=your_api_key
BRS_TOKEN_TTL=3600  # seconds
```

## Testing Plan
After fix:
1. Send first message → verify success
2. Wait 5 seconds
3. Send second message → verify success
4. Send 10 messages rapidly → all should work
5. Wait for token expiration (if TTL < 5 min) → verify auto-refresh
6. Check backend logs for "token refreshed" messages

## Acceptance Criteria
- ✅ Multi-turn conversations work without errors
- ✅ Token automatically refreshes before expiration
- ✅ Authentication errors are retried with token refresh
- ✅ Backend logs show successful token management
- ✅ No 503 errors in normal operation

## References
- Phase 4: BRS Gateway MCP Implementation
- Phase 5: Skill Invocation System
- BRS API Documentation: http://localhost:8056/api/documentation/

## Notes
- This bug was NOT caught in Phase 5 testing (only single-message tests ran)
- E2E testing should have caught this earlier
- Need to add automated multi-turn conversation tests
- Consider implementing connection pooling and token caching
