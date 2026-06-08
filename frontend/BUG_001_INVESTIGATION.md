# BUG-001 Investigation Findings

## Current Implementation

### Message Fetching
- **Function:** `loadMessages()` (line 166-173)
- **API Endpoint:** `apiClient.getSessionMessages(sessionId)`
- **When called:** Only when selecting a session from sidebar (line 213)
- **Issue:** **NOT called after sending a message** ❌

### Message Rendering
- **Component:** Direct `messages.map()` in page.tsx (line 563)
- **State:** `messages` useState array
- **Issue:** Renders correctly IF messages are in state

### WebSocket Setup
- **Configured:** YES (lines 50-139)
- **URL:** `process.env.NEXT_PUBLIC_API_URL` or `http://localhost:8000`
- **Connection:** Attempts to connect when `useStreaming` is true
- **Issue:** 4 connection failures in console logs ❌

### Session Management
- **Storage:** `currentSession` state
- **ID tracking:** `currentSessionIdRef.current`
- **Issue:** Session exists (ID 172) but messages not fetched after creation

### Authentication
- **Method:** Bearer token from localStorage (`access_token`)
- **Headers:** `Authorization: Bearer ${token}` in ApiClient
- **Issue:** Token is included, but WebSocket auth may be failing ❌

## Issues Identified

### Issue 1: Missing Message Fetch After Sending
**Evidence:** Lines 386-413 in page.tsx
```typescript
const response = await apiClient.sendMessage({...});
// ... 
setMessages(prev => {
  const withoutOptimistic = prev.filter(m => m.id !== optimisticUserMessage.id);
  return [...withoutOptimistic, response.message, response.response].filter(Boolean);
});
```

**Impact:** 
- Code assumes `response.message` and `response.response` exist
- Backend actually returns these fields correctly (ChatResponse interface confirmed)
- BUT: When a NEW session is created, `currentSession` is null initially
- The optimistic message is added (line 348) but response handling may fail

**Root Cause:** Line 393-400 tries to handle new session creation, but the logic is fragile:
```typescript
if (!currentSession) {
  const newSession = sessions.find(s => s.id === response.session_id);
  if (newSession) {
    setCurrentSession(newSession);
  } else {
    await loadSessions(); // Async without await properly handled
  }
}
```

### Issue 2: WebSocket Connection Failures
**Evidence:** 4 WebSocket errors in console
```
[ERROR] WebSocket error: Event @ ...
[ERROR] WebSocket connection failed: Event @ ...
```

**Impact:** When streaming is enabled (default), messages are sent via WebSocket but:
- Connection fails repeatedly
- No error recovery
- Messages sent via WebSocket but responses never received
- UI shows empty state because WebSocket events don't fire

**Root Cause:** WebSocket connection to `http://localhost:8000` likely fails because:
1. Backend WebSocket endpoint may not exist or be misconfigured
2. Authentication may fail during WebSocket handshake
3. CORS or proxy issues preventing connection

### Issue 3: Streaming Mode Enabled by Default
**Evidence:** Line 23
```typescript
const [useStreaming, setUseStreaming] = useState(true);
```

**Impact:** 
- User sends message
- Code tries WebSocket first (lines 351-378)
- WebSocket fails silently
- No fallback to HTTP API
- Message disappears, no response shown

**Root Cause:** The streaming path doesn't have proper error handling. When WebSocket fails, it should fall back to HTTP.

### Issue 4: No Message Refetch After HTTP Send
**Evidence:** Lines 402-405
```typescript
setMessages(prev => {
  const withoutOptimistic = prev.filter(m => m.id !== optimisticUserMessage.id);
  return [...withoutOptimistic, response.message, response.response].filter(Boolean);
});
```

**Impact:**
- This SHOULD work for HTTP mode
- But it doesn't refetch from server
- If response format changes or is incomplete, messages lost

**Best Practice:** After sending, refetch messages from server: `await loadMessages(sessionId)`

## Root Cause Confirmed

**Primary Issue:** WebSocket streaming is enabled by default but WebSocket connection fails, causing all messages to be sent via WebSocket with no response handling.

**Secondary Issue:** Even when WebSocket is disabled, the code doesn't refetch messages from server after sending, relying on the API response format which may be incomplete.

## Recommended Fix Order

### Fix 1: Disable Streaming by Default (Quick Fix)
**File:** `frontend/app/chat/page.tsx` line 23
**Change:**
```typescript
const [useStreaming, setUseStreaming] = useState(false); // Disable until WebSocket is fixed
```

**Rationale:** This will force HTTP mode, which has better error handling.

### Fix 2: Add Message Refetch After Send (Critical)
**File:** `frontend/app/chat/page.tsx` lines 402-407
**Change:**
```typescript
// After successful send, refetch all messages from server
await loadMessages(sessionId);
setLoading(false);
```

**Rationale:** Ensures messages are always fetched from authoritative source (backend database).

### Fix 3: Add Error Handling for WebSocket (Important)
**File:** `frontend/app/chat/page.tsx` lines 350-378
**Add:**
```typescript
try {
  if (useStreaming && wsRef.current?.isConnected()) {
    // ... existing WebSocket code
  } else {
    // ... existing HTTP fallback
  }
} catch (wsError) {
  console.error('WebSocket send failed, falling back to HTTP:', wsError);
  // Fallback to HTTP if WebSocket fails
  const response = await apiClient.sendMessage({...});
  await loadMessages(sessionId);
  setLoading(false);
}
```

### Fix 4: Fix WebSocket Connection (Future)
**Investigation needed:**
- Check if backend has `/ws` endpoint
- Verify WebSocket authentication
- Configure Next.js proxy if needed
- Test WebSocket connection separately

## Testing Plan

1. **Apply Fix 1 + Fix 2** (disable streaming, add refetch)
2. **Test:** Send message "Hello, what tools do you have?"
3. **Verify:**
   - Message displays in UI
   - Response displays in UI
   - No console errors
   - Backend logs show success
4. **If successful:** Mark BUG-001 as FIXED
5. **If still broken:** Investigate API response format mismatch

## Expected Outcome

After Fix 1 + Fix 2:
- ✅ Messages display correctly in UI
- ✅ No WebSocket errors (streaming disabled)
- ✅ E2E test Phase 1.2 passes
- ✅ Production readiness loop can continue
