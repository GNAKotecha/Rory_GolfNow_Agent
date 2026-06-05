# Real-Time API Call Visibility - NOW IMPLEMENTED ✅

I've enhanced the `call_api` handler to print every request and response with full details directly to your terminal.

---

## TL;DR - Start Seeing API Calls Right Now

```bash
cd ~/Documents/GitHub/Rory_GolfNow_Agent/backend
DEBUG=1 uvicorn app.main:app --reload
```

Then use Rory in the frontend. **Every API call will print to your terminal.**

---

## What Changed

### File Modified
`backend/gateway_mcp/tools/teesheet/handlers.py` - Added comprehensive logging to `call_api_handler()`

### What Gets Logged
✅ HTTP method and URL  
✅ Request headers (Authorization, Content-Type, etc.)  
✅ Request body (JSON/form/raw format)  
✅ Response status code  
✅ Response headers  
✅ Response body (complete JSON)  
✅ Elapsed time in milliseconds  

---

## Example Output

### Successful API Call (Status 201)

```
================================================================================
API CALL COMPLETED: POST http://localhost:8056/api/v3/clubs/brsgolfclubsales/bookings
================================================================================
Status: 201 | Time: 234ms

REQUEST HEADERS:
  Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGci...
  Content-Type: application/json
  Accept: application/json

REQUEST BODY:
  {
    "tee_sheet_booking": {
      "course_id": 1,
      "date": "2026-05-28",
      "time": "09:00",
      "holes": 18,
      "reservation_name": "Test Booking",
      "reservation_type": "Visitor",
      "slots": {
        "1": {
          "player": {
            "type": "MEMBER",
            "id": 17,
            "name_on_tee_sheet": "A Kotecha"
          }
        }
      }
    }
  }

RESPONSE HEADERS:
  content-type: application/json
  location: /api/v3/clubs/brsgolfclubsales/bookings/12345
  content-length: 256

RESPONSE BODY:
  {
    "id": 12345,
    "status": "confirmed",
    "created_at": "2026-06-05T14:30:22Z"
  }
================================================================================
```

### Failed API Call (Status 422)

```
================================================================================
API CALL COMPLETED: PATCH http://localhost:8056/api/v2/user?user=18
================================================================================
Status: 422 | Time: 123ms

REQUEST HEADERS:
  Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGci...
  Content-Type: application/x-www-form-urlencoded

REQUEST BODY:
  email=invalid-email-format

RESPONSE HEADERS:
  content-type: application/json

RESPONSE BODY:
  {
    "error": {
      "code": "VALIDATION_FAILED",
      "message": "Validation failed",
      "status": 422,
      "details": {
        "email": "must be a valid email address"
      }
    }
  }
================================================================================
```

---

## How to Use

### 1. Start Backend with Debug Logging

**Option A: Terminal mode (see output in terminal)**
```bash
cd ~/Documents/GitHub/Rory_GolfNow_Agent/backend
DEBUG=1 uvicorn app.main:app --reload
```

**Option B: Save to file**
```bash
cd ~/Documents/GitHub/Rory_GolfNow_Agent/backend
DEBUG=1 uvicorn app.main:app --reload 2>&1 | tee /tmp/rory_api_calls.log
```

### 2. Use Rory in Frontend

1. Open frontend in browser
2. Make Rory perform actions (bookings, updates, etc.)

### 3. Watch Terminal 1

Every API call will appear with full request/response details.

---

## Reading the Output

### Line by Line

**1. Header**
```
API CALL COMPLETED: POST http://localhost:8056/api/v3/clubs/brsgolfclubsales/bookings
```
- **Method**: POST (could be GET, PATCH, DELETE, etc.)
- **URL**: Full endpoint being called

**2. Status & Timing**
```
Status: 201 | Time: 234ms
```
- **Status Code**:
  - 2xx = Success ✓
  - 4xx = Client error (your request was wrong)
  - 5xx = Server error (API crashed)
- **Time**: How long the request took

**3. Request Headers**
```
REQUEST HEADERS:
  Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGci...
  Content-Type: application/json
```
- Shows what you're sending TO the API
- Authorization = Authentication token (truncated for safety)
- Content-Type = Format of request body

**4. Request Body**
```
REQUEST BODY:
  {
    "tee_sheet_booking": {...}
  }
```
- Shows exact JSON/data being sent
- Indented for readability
- Truncated if very large (>500 chars)

**5. Response Headers**
```
RESPONSE HEADERS:
  content-type: application/json
  location: /api/v3/clubs/.../bookings/12345
```
- Shows what API is returning
- May include helpful info (like Location header with new resource ID)

**6. Response Body**
```
RESPONSE BODY:
  {
    "id": 12345,
    "status": "confirmed"
  }
```
- Complete JSON response from API
- This is what Rory receives back
- Truncated if very large (>1000 chars)

---

## Debugging Scenarios

### Scenario 1: "API returned error - what went wrong?"

Look at the **RESPONSE BODY** - it will have an error section:
```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "details": {
      "email": "must be a valid email address"
    }
  }
}
```

→ The error tells you exactly what's wrong

---

### Scenario 2: "I want to verify the request format"

Look at the **REQUEST BODY** section:
```json
{
  "tee_sheet_booking": {
    "course_id": 1,
    "date": "2026-05-28",
    ...
  }
}
```

Compare to API docs at http://localhost:8056/api/documentation/
- Does every required field exist?
- Is the format correct?

---

### Scenario 3: "Is authentication working?"

Look for the **Authorization** header:
```
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGci...
```

- **Present** → Auth is working ✓
- **Missing** → Auth setup failed

---

### Scenario 4: "Why is this API call slow?"

Look at the **Time** value:
```
Status: 200 | Time: 5234ms
```

- < 500ms: Normal
- 500ms - 2s: Slow
- 2s+: Very slow (BRS API might be overloaded)

---

## Status Code Reference

| Code | Meaning | What It Means |
|------|---------|--------------|
| **200** | OK | Request succeeded ✓ |
| **201** | Created | New resource created ✓ |
| **204** | No Content | Success, no body returned ✓ |
| **400** | Bad Request | Malformed request syntax |
| **401** | Unauthorized | Authentication failed |
| **403** | Forbidden | No permission (different user's data) |
| **404** | Not Found | Resource doesn't exist |
| **422** | Validation Failed | Invalid data format |
| **500** | Server Error | API crashed ❌ |
| **503** | Service Unavailable | API is down ❌ |

---

## Capturing for Later Review

### Save All Logs to File

```bash
DEBUG=1 uvicorn app.main:app --reload 2>&1 | tee /tmp/rory_full_log.txt
```

Then later:
```bash
# View all API calls
grep -A 50 "API CALL COMPLETED" /tmp/rory_full_log.txt

# Find failed requests
grep -B 2 "Status: [4-5]" /tmp/rory_full_log.txt

# Find slow requests (>2000ms)
grep -B 2 "Time: [2-9][0-9][0-9][0-9]ms" /tmp/rory_full_log.txt
```

---

## Integration with Previous Debugging Tools

You now have:

1. **Real-time terminal output** ← **START HERE** (this document)
   - Most immediate, no setup needed
   - Shows everything in terminal

2. **Log files** (`/tmp/rory.log`)
   - Save to file for review
   - Search for patterns

3. **JSON capture** (see `API_REQUEST_DEBUGGING_GUIDE.md`)
   - For complete structured data
   - More setup required

4. **Charles Proxy** (see `API_REQUEST_DEBUGGING_GUIDE.md`)
   - Network-level inspection
   - For advanced debugging

---

## Implementation Details

### What Was Added

In `backend/gateway_mcp/tools/teesheet/handlers.py`:

1. **Timing**: Track request start/end time
2. **Request capture**: Store request body before sending
3. **Pretty printing**: Format output with borders and indentation
4. **Truncation**: Long bodies truncated at 500-1000 chars
5. **Auth safety**: Authorization header truncated to first 50 chars
6. **Flush output**: Use `flush=True` to ensure immediate terminal display

### Key Code

```python
# Capture timing
request_start = time.time()

# ... make request ...

# Calculate elapsed time
elapsed_ms = (time.time() - request_start) * 1000

# Print with full details
print(f"Status: {response.status_code} | Time: {elapsed_ms:.0f}ms", flush=True)
print(f"REQUEST BODY:\n  {json.dumps(request_body_for_log, indent=2)}", flush=True)
```

---

## Troubleshooting

### Q: I don't see any output

**Answer:**
1. Make sure backend is running: `DEBUG=1 uvicorn app.main:app --reload`
2. Make sure you triggered an API call from frontend
3. Check that the call actually reaches the backend (might be cached)

---

### Q: Output is too long, scrolling off screen

**Answer:**
```bash
# Save to file and view with less
DEBUG=1 uvicorn app.main:app --reload 2>&1 | tee /tmp/rory.log

# In another terminal:
less +F /tmp/rory.log  # View and follow in real-time
```

---

### Q: Response body is truncated

**Answer:**
The output is truncated at 1000 characters for readability. To see full response:
1. Save to file (above)
2. Extract the specific call
3. Pretty-print with `jq` if it's JSON

---

### Q: I want to see only failed requests

**Answer:**
```bash
DEBUG=1 uvicorn app.main:app --reload 2>&1 | \
  grep -B 5 "Status: [4-5][0-9][0-9]"
```

---

## Next Steps

1. **Try it now**: Start backend with `DEBUG=1 uvicorn ...`
2. **Trigger API calls** from frontend
3. **Watch terminal** for real-time output
4. **Compare request to API docs** if errors occur

---

## Summary

**One command to see everything:**
```bash
cd ~/Documents/GitHub/Rory_GolfNow_Agent/backend
DEBUG=1 uvicorn app.main:app --reload
```

**Every API call from Rory will print with:**
- ✓ Exact request being sent
- ✓ Exact response received
- ✓ Timing information
- ✓ Error details (if any)

That's all you need to debug what Rory is doing! 🚀
