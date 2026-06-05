# How to See API Requests and Responses - Complete Guide

**Goal**: See what HTTP requests Rory is making to BRS and other APIs, including the exact request body and response.

---

## Fastest Way: Start Here (60 seconds)

```bash
# Terminal 1
cd ~/Documents/GitHub/Rory_GolfNow_Agent
./debug-rory.sh

# Terminal 2 (different terminal)
./debug-rory.sh watch

# Terminal 3: Use Rory in frontend
# Watch Terminal 2 - you'll see all API calls!
```

**What you'll see:**
```
POST http://localhost:8056/api/v3/clubs/brsgolfclubsales/bookings | 201 | 234ms
PATCH http://localhost:8056/api/v2/user?user=18 | 204 | 123ms
GET http://localhost:8056/api/v2/clubs/brsgolfclubsales/members | 200 | 567ms
```

---

## The Three Approaches

### 1. **Log Streaming (Easiest, Immediate Results)**
- See all API calls in terminal
- Real-time as they happen
- Request URL, method, headers
- Response status, timing
- **Setup time**: 30 seconds

```bash
./debug-rory.sh         # Terminal 1: Start backend
./debug-rory.sh watch   # Terminal 2: Watch logs
```

**Where to look:**
```
/tmp/rory.log         ← All logs end up here
```

---

### 2. **JSON File Capture (Most Detail)**
- Every request/response saved as JSON file
- Complete request body
- Complete response body
- Timing information
- **Setup time**: 5 minutes (need to edit code)

**How to enable:**
See `API_REQUEST_DEBUGGING_GUIDE.md` - **Option B**

**Where to look:**
```
/tmp/rory_api_calls/call_*.json  ← Each call is a file
```

**View:**
```bash
jq . /tmp/rory_api_calls/call_*.json
```

---

### 3. **Network Interception Proxy (Professional)**
- See raw HTTP wire protocol
- Man-in-the-middle inspection
- Charles Proxy or Fiddler
- **Setup time**: 10 minutes (install tool)

**How to use:**
Install Charles → Configure proxy → See all traffic

**Where to look:**
Charles application window

---

## Quick Answer Guide

### Q: "I want to see what Rory just sent to the API"

**Answer:**
```bash
# Check the logs
tail -20 /tmp/rory.log

# Search for "API Request Details" - that shows the exact request
# Search for "API Response Details" - that shows the response
```

Example output:
```
API Request Details
- method: PATCH
- url: http://localhost:8056/api/v2/user?user=18
- body: {"email": "new.email@example.com"}
- headers: {'Authorization': 'Bearer ...', 'Content-Type': 'application/x-www-form-urlencoded'}

API Response Details
- status: 204
- elapsed_ms: 123
```

---

### Q: "The API returned an error - I want to see exactly why"

**Answer:**
1. Search logs for the error status code:
   ```bash
   grep "status: 422" /tmp/rory.log
   ```

2. Look at the response body (usually contains error details):
   ```
   res_body: {"error": {"code": "VALIDATION_FAILED", "details": {"email": "invalid format"}}}
   ```

3. Compare to API docs:
   - http://localhost:8056/api/documentation/
   - Find the endpoint
   - Check what fields are required

---

### Q: "I want to see if authentication is working"

**Answer:**
```bash
# Check if Bearer token is being sent
grep "Authorization.*Bearer" /tmp/rory.log | head -1

# If you see: Authorization: 'Bearer eyJ0eXAiOiJKV1QiLCJh...'
# Then auth is working ✓

# If you see: no Authorization header
# Then auth failed ✗
```

---

### Q: "Which API endpoints is Rory calling?"

**Answer:**
```bash
# Get list of all unique URLs
grep "url:" /tmp/rory.log | sed 's/.*url: //' | sort | uniq

# Example output:
# http://localhost:8056/api/v2/clubs/brsgolfclubsales/members
# http://localhost:8056/api/v3/clubs/brsgolfclubsales/bookings
# http://localhost:8056/api/v3/clubs/brsgolfclubsales/visitor-green-fee-rates.json
```

---

### Q: "I want to see the exact JSON body being sent"

**Answer:** Use the JSON capture method (Option 2):

1. Edit `backend/gateway_mcp/tools/teesheet/handlers.py`
2. Add logging as shown in API_REQUEST_DEBUGGING_GUIDE.md - **Option B**
3. Make the API call
4. View the file:
   ```bash
   jq .request.body /tmp/rory_api_calls/call_*.json | jq .
   ```

Or from logs:
```bash
grep -A 5 "req_body" /tmp/rory.log | head -10
```

---

## Understanding Log Format

### Request Log Entry
```
DEBUG:root:Calling Teesheet API: POST /api/v3/clubs/brsgolfclubsales/bookings
extra={
  'method': 'POST',
  'path': '/api/v3/clubs/brsgolfclubsales/bookings',
  'club_id': 'brsgolfclubsales',
  'club_slug': 'brsgolfclubsales'
}
```

**Meanings:**
- **method**: HTTP verb (GET, POST, PATCH, DELETE)
- **path**: API endpoint
- **club_id**: Which club is being accessed
- **club_slug**: Normalized club identifier

### Response Log Entry
```
DEBUG:root:Teesheet API response: 201
extra={
  'correlation_id': '...',
  'status': 201,
  'elapsed_ms': 234
}
```

**Meanings:**
- **status**: HTTP status code (201 = created, 422 = validation error, 500 = server error)
- **elapsed_ms**: How long the request took

### Header Log Entry (line 244 in handlers.py)
```
DEBUG: Final headers: {'Authorization': 'Bearer eyJ0...', 'Content-Type': 'application/json', 'Accept': 'application/json'}
```

**Meanings:**
- **Authorization**: Token for API authentication
- **Content-Type**: Format of request body
- **Accept**: What format we expect in response

---

## Common Scenarios

### Scenario 1: User reports "Email update failed"

1. Run frontend action again
2. Watch logs:
   ```bash
   grep "PATCH.*user" /tmp/rory.log -A 10
   ```
3. Look for response status:
   - **204** = Success ✓
   - **422** = Validation error (email format wrong?)
   - **401** = Not authorized
   - **500** = Server error

4. See error details:
   ```bash
   grep "res_body" /tmp/rory.log | tail -1
   ```

### Scenario 2: Booking creation is slow

1. Check elapsed time:
   ```bash
   grep "POST.*bookings" /tmp/rory.log | grep "elapsed_ms"
   ```
2. If > 5000ms, API is slow (could be BRS issue)
3. If < 1000ms, our code is the bottleneck

### Scenario 3: Authentication keeps failing

1. Check if token is being sent:
   ```bash
   grep "Authorization.*Bearer" /tmp/rory.log | wc -l
   ```
2. If 0 = token not being sent (BRSAuthProvider issue)
3. If > 0 = token is sent, but might be wrong/expired

---

## Files to Know

| File | Purpose |
|------|---------|
| `debug-rory.sh` | Script to start backend with logging |
| `DEBUG_QUICK_REFERENCE.md` | Quick commands and searches |
| `API_REQUEST_DEBUGGING_GUIDE.md` | Detailed setup options |
| `/tmp/rory.log` | All debug output |
| `backend/gateway_mcp/tools/teesheet/handlers.py` | Where HTTP requests are made |
| `http://localhost:8056/api/documentation/` | BRS API docs |

---

## Commands Cheat Sheet

```bash
# Start debug mode
./debug-rory.sh

# Watch logs live
./debug-rory.sh watch

# Find failures
grep "status: [4-5]" /tmp/rory.log

# Find slow calls (>1 second)
grep -E "elapsed_ms: [0-9]{4}" /tmp/rory.log

# See all URLs called
grep "url:" /tmp/rory.log | sed 's/.*url: //' | sort | uniq

# View only response statuses
grep "status:" /tmp/rory.log | sort | uniq -c

# Find errors in responses
grep -i "error" /tmp/rory.log

# Search by endpoint
grep "bookings" /tmp/rory.log

# Last 50 lines
tail -50 /tmp/rory.log

# Real-time stream
tail -f /tmp/rory.log
```

---

## Troubleshooting

**Problem: No logs showing up**
- Make sure backend started: `./debug-rory.sh`
- Make sure you made an API call from frontend
- Check file exists: `ls /tmp/rory.log`
- View it: `cat /tmp/rory.log`

**Problem: Authorization token truncated in logs**
- That's intentional for security
- You can still see if it's being sent (starts with "Bearer")
- To see full token: Edit handlers.py line 244 (not recommended in production)

**Problem: Too many logs, can't find anything**
- Filter by endpoint: `grep "bookings" /tmp/rory.log`
- Filter by status: `grep "422" /tmp/rory.log`
- Filter by club: `grep "brsgolfclubsales" /tmp/rory.log`
- Show last 50: `tail -50 /tmp/rory.log`

**Problem: Can't run ./debug-rory.sh**
- Make it executable: `chmod +x debug-rory.sh`
- Run from project root: `cd ~/Documents/GitHub/Rory_GolfNow_Agent`

---

## Next Steps

1. **Quick Test (2 min):**
   ```bash
   ./debug-rory.sh
   ./debug-rory.sh watch  # (other terminal)
   # Make an API call in frontend - see it in logs
   ```

2. **Enable JSON Capture (5 min):**
   - Follow Option B in `API_REQUEST_DEBUGGING_GUIDE.md`
   - See complete request/response bodies

3. **Use Charles Proxy (10 min):**
   - Install Charles Proxy
   - Route traffic through it
   - See network-level details

---

## TL;DR

```bash
./debug-rory.sh watch
```

**That's it.** Everything you need to see API calls is in the logs now.

When something fails, check the logs for:
1. **Request method/URL** - Did we call the right endpoint?
2. **Request headers** - Is authentication included?
3. **Response status** - What error code?
4. **Response body** - What's the error message?

The answer is always in `/tmp/rory.log` 🔍
