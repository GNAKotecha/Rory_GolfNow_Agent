# Rory API Debugging - Quick Reference Card

## TL;DR - See API Requests in 30 Seconds

```bash
# Terminal 1: Start backend with debug logging
cd ~/Documents/GitHub/Rory_GolfNow_Agent
./debug-rory.sh

# Terminal 2: Watch logs (in another terminal)
./debug-rory.sh watch

# Now use Rory in the frontend - you'll see all API calls in Terminal 2!
```

---

## Three Ways to See Requests/Responses

| Method | Speed | Detail | Command |
|--------|-------|--------|---------|
| **Logs (Easiest)** | 10 sec | High | `./debug-rory.sh` |
| **JSON Files** | 20 sec | Very High | Edit `handlers.py` (Option B) |
| **Charles Proxy** | 2 min | Network-level | Install Charles |

---

## Log Output Examples

### Example 1: Successful Booking API Call

```
DEBUG:root:API Request Details
- method: POST
- url: http://localhost:8056/api/v3/clubs/brsgolfclubsales/bookings
- headers: {'Authorization': 'Bearer eyJ0...', 'Content-Type': 'application/json'}
- body_size: 245

DEBUG:root:API Response Details
- status: 201
- headers: {'content-type': 'application/json', 'location': '/bookings/12345'}
- body_size: 156
- elapsed_ms: 234
```

### Example 2: Failed Validation

```
DEBUG:root:API Request Details
- method: POST
- url: http://localhost:8056/api/v3/clubs/brsgolfclubsales/bookings
- body_size: 150

DEBUG:root:API Response Details
- status: 422
- body_size: 256
→ Contains: {"error": {"code": "VALIDATION_FAILED", "details": {...}}}
```

---

## Common Log Searches

```bash
# View last 50 lines
tail -50 /tmp/rory.log

# Find all API calls to bookings endpoint
grep "bookings" /tmp/rory.log

# Find failed requests (400+)
grep -E "status: [4-9][0-9][0-9]" /tmp/rory.log

# Find slow requests (>1 second)
grep -E "elapsed_ms: [0-9]{4,}" /tmp/rory.log

# Show all URLs called
grep "url:" /tmp/rory.log | cut -d: -f3- | sort | uniq

# View response bodies for specific endpoint
grep -A 5 "POST.*bookings" /tmp/rory.log | grep "body"
```

---

## What Each Log Line Means

### Request Line
```
Calling Teesheet API: POST /api/v3/clubs/brsgolfclubsales/bookings
```
- **POST** = HTTP method
- **/api/v3/clubs/...** = API endpoint
- **brsgolfclubsales** = Club ID being accessed

### Headers Line
```
headers: {'Authorization': 'Bearer eyJ0eXAi...', 'Content-Type': 'application/json'}
```
- **Authorization** = Auth token for this club (truncated in logs)
- **Content-Type** = Request body format

### Response Line
```
status: 422
```
- **2xx** = Success ✅
- **3xx** = Redirect
- **4xx** = Client error (your request was wrong) ⚠️
- **5xx** = Server error (BRS is broken) ❌

### Error Line
```
{"error": {"code": "VALIDATION_FAILED", "details": {"first_name": "must not be blank"}}}
```
- **code** = Error type (matches what agent sees)
- **details** = Which field is wrong and why

---

## Debugging Workflows

### Workflow: "API is returning 422, why?"

1. **See the request:**
   ```bash
   grep "API Request Details" /tmp/rory.log -A 3 | tail -1
   ```
   Look at the **body** being sent

2. **See the response:**
   ```bash
   grep "status: 422" /tmp/rory.log -A 2
   ```
   Look at the **details** field

3. **Compare to API docs:**
   - Open http://localhost:8056/api/documentation/
   - Find the endpoint
   - Check if your body matches the schema

---

### Workflow: "Which URLs is Rory calling?"

```bash
# Get all unique URLs in order
grep "url:" /tmp/rory.log | sed 's/.*url: //' | sort | uniq -c

# Output:
#       3 http://localhost:8056/api/v2/clubs/brsgolfclubsales/members
#       2 http://localhost:8056/api/v3/clubs/brsgolfclubsales/visitor-green-fee-rates.json
#       1 http://localhost:8056/api/v3/clubs/brsgolfclubsales/bookings
```

---

### Workflow: "Is authentication working?"

```bash
# Check if Bearer token is being sent
grep "Authorization.*Bearer" /tmp/rory.log | head -1

# Check if token is consistent (same club)
grep "Bearer" /tmp/rory.log | sort | uniq -c
# If count is 1, same token used for all calls ✓
# If count > 1, multiple tokens (different clubs) ✓
```

---

### Workflow: "Why is this API call slow?"

```bash
# Find slowest calls
grep "elapsed_ms:" /tmp/rory.log | sed 's/.*elapsed_ms: //' | sort -rn | head -5

# Output:
# 5234 ms - POST /api/v3/clubs/.../bookings
# 1200 ms - GET /api/v2/clubs/.../members
# 456 ms - GET /api/v2/clubs/.../booking-rules
```

---

## Script Commands Reference

```bash
# Start backend (logs to /tmp/rory.log)
./debug-rory.sh

# Watch logs in real-time (other terminal)
./debug-rory.sh watch

# Full HTTP protocol logging (very verbose)
./debug-rory.sh httpx

# Clear old logs
./debug-rory.sh clean

# Show help
./debug-rory.sh help
```

---

## Log File Locations

| File | Purpose | View With |
|------|---------|-----------|
| `/tmp/rory.log` | All debug logs | `tail -f /tmp/rory.log` |
| `/tmp/rory_api_calls/` | Captured JSON calls | `ls /tmp/rory_api_calls/` |
| Backend stdout | Console output | Terminal running script |

---

## Troubleshooting

**Q: I don't see any API calls in logs**
```bash
# Make sure logs are being written
tail -f /tmp/rory.log

# Make sure backend is running
curl http://localhost:8000/health

# Trigger an action in frontend that uses API
```

**Q: Logs are very verbose, too much to read**
```bash
# Filter to just your endpoint
grep "bookings" /tmp/rory.log

# Filter to just failures
grep "status: [4-5]" /tmp/rory.log

# Filter by time range
grep "2026-06-05 14:" /tmp/rory.log
```

**Q: Authorization token is truncated**
```
# That's intentional for security
# You can see if it's being sent, but not the full token
# If you need to see it, modify handlers.py (not recommended in prod)
```

**Q: No API calls at all, just agent logs**
```bash
# Check if agent is actually calling the API
# Look for lines containing: "Calling Teesheet API"
grep "Calling Teesheet API" /tmp/rory.log

# If nothing: agent may not be calling API
# Could be: agent is thinking, or workflow doesn't need API calls
```

---

## Next Level: View JSON Responses

After enabling capture (Option B in main guide):

```bash
# View all captured API calls as JSON
ls -t /tmp/rory_api_calls/call_*.json

# View the most recent call
jq . /tmp/rory_api_calls/call_*.json | tail -50

# View just the response body
jq .response.body /tmp/rory_api_calls/call_*.json | head -20

# View just the request body
jq .request.body /tmp/rory_api_calls/call_*.json | head -20

# Find calls to specific endpoint
jq 'select(.url | contains("bookings"))' /tmp/rory_api_calls/call_*.json
```

---

## Key Takeaway

**One command to see everything:**
```bash
./debug-rory.sh watch
```

All API calls appear in real-time with:
- ✓ Method (POST, GET, PATCH, etc.)
- ✓ URL and endpoint
- ✓ Status code (200, 422, 500, etc.)
- ✓ Response time
- ✓ Error messages if any

That's it! 🚀
