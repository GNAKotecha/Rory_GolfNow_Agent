# See API Calls from Rory Agent - NOW WITH ENHANCED LOGGING

I've added comprehensive logging to show **exactly** what Rory is sending and receiving from APIs.

---

## Quick Start: 30 Seconds

```bash
# Terminal 1: Start backend
cd ~/Documents/GitHub/Rory_GolfNow_Agent/backend
DEBUG=1 uvicorn app.main:app --reload

# Terminal 2: Use Rory in frontend
# Watch Terminal 1 - you'll see every API call with full details
```

---

## What You'll See

When Rory calls an API, you'll see output like this:

```
================================================================================
API CALL COMPLETED: POST http://localhost:8056/api/v3/clubs/brsgolfclubsales/bookings
================================================================================
Status: 201 | Time: 234ms

REQUEST HEADERS:
  Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc...
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

---

## Example: Failed Request (You'll See the Error)

```
================================================================================
API CALL COMPLETED: PATCH http://localhost:8056/api/v2/user?user=18
================================================================================
Status: 422 | Time: 123ms

REQUEST HEADERS:
  Authorization: Bearer ...
  Content-Type: application/x-www-form-urlencoded

REQUEST BODY:
  email=invalid-format-not-an-email

RESPONSE HEADERS:
  content-type: application/json
  content-length: 256

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

## What Information Is Captured

✅ **Method & URL** - What endpoint is being called
✅ **Request Headers** - Auth tokens, content types, etc.
✅ **Request Body** - The exact JSON/form data being sent
✅ **Response Status** - HTTP status code (200, 422, 500, etc.)
✅ **Response Headers** - Returned by the API
✅ **Response Body** - The full JSON response
✅ **Timing** - How long the request took

---

## How to Trigger API Calls

1. Start backend (see above)
2. Open frontend in browser
3. Use Rory to perform actions that need API calls:
   - Create a booking
   - Update member info
   - Create green fees
   - Etc.

4. Watch Terminal 1 - API calls will appear with full details

---

## Capturing Output to File

If you want to save all API calls for later review:

```bash
# Start backend and save to file
DEBUG=1 uvicorn app.main:app --reload 2>&1 | tee /tmp/rory_complete_log.txt

# Later, extract just API calls:
grep -A 100 "API CALL COMPLETED" /tmp/rory_complete_log.txt
```

---

## View Specific Calls

```bash
# Find all failed calls (4xx, 5xx)
grep -B 2 "Status: [4-5]" /tmp/rory_complete_log.txt

# Find all booking calls
grep -A 50 "POST.*bookings" /tmp/rory_complete_log.txt

# Find slow calls (>1000ms)
grep -B 2 "Time: [1-9][0-9][0-9][0-9]" /tmp/rory_complete_log.txt

# See all endpoints called
grep "API CALL COMPLETED:" /tmp/rory_complete_log.txt
```

---

## What Each Status Code Means

| Status | Meaning | Action |
|--------|---------|--------|
| **200** | OK - Request succeeded | ✓ Good |
| **201** | Created - New resource created | ✓ Good |
| **204** | No Content - Success, no body | ✓ Good |
| **400** | Bad Request - Malformed request | ⚠️ Check request body format |
| **401** | Unauthorized - Auth failed | ⚠️ Check auth token |
| **422** | Validation Failed - Invalid data | ⚠️ Check validation errors in response |
| **500** | Server Error - API crashed | ❌ BRS API issue |

---

## Understanding the Output

### Request Body Format

- **JSON**: `{"key": "value"}` - Standard format
- **Form**: `key=value&key2=value2` - URL-encoded (for some APIs)
- **Raw**: `<?xml...?>` - Custom format (rarely used)

### Authorization Header

- Shows first 50 chars of token, then `...`
- Token format: `Bearer eyJ0eXAiOiJKV1QiLCJhbGci...`
- If present, authentication is working
- If missing, auth setup may have failed

### Timing (Time: 234ms)

- < 200ms: Very fast
- 200-500ms: Normal
- 500ms-2s: Slow
- > 2s: Very slow (check if BRS is overloaded)

---

## Real-World Examples

### Example 1: Successful Booking

**What you see:**
```
Status: 201
REQUEST BODY: {"tee_sheet_booking": {...}}
RESPONSE BODY: {"id": 12345, "status": "confirmed"}
```

**Interpretation:** ✓ Booking created successfully

---

### Example 2: Email Validation Failed

**What you see:**
```
Status: 422
REQUEST BODY: email=not-an-email
RESPONSE BODY: {"error": {"details": {"email": "must be valid"}}}
```

**Interpretation:** ⚠️ Agent sent invalid email format

---

### Example 3: Auth Token Expired

**What you see:**
```
Status: 401
RESPONSE BODY: {"error": "Unauthorized - token expired"}
```

**Interpretation:** ⚠️ Need to refresh auth token (BRSAuthProvider issue)

---

## Debugging Tips

### Q: "I see the error in the response, what does it mean?"

Look at the **RESPONSE BODY** - it will tell you exactly:
```
"details": {"field_name": "error message"}
```

Example:
```
"details": {"date": "date must be in future"}
```
→ Agent sent a past date, API rejected it

---

### Q: "The request looks correct but API rejected it"

Compare your REQUEST BODY to the API docs:
1. Open http://localhost:8056/api/documentation/
2. Find the endpoint
3. Compare expected fields to what you sent
4. Look for missing required fields

---

### Q: "Is Rory using the right auth token?"

Look for the **Authorization** header in REQUEST HEADERS:
```
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGci...
```

- **Present** → Auth is working ✓
- **Missing** → Auth failed (check BRS credentials)

---

### Q: "Why is the API call so slow?"

Look at **Time: Xms**:
```
Status: 201 | Time: 5234ms
```

→ 5+ seconds means BRS API is slow (could be overloaded or processing expensive operation)

---

## Terminal Tips

To make logs easier to read:

```bash
# Color-code output
DEBUG=1 uvicorn app.main:app --reload 2>&1 | \
  sed 's/Status: [2-3][0-9][0-9]/\x1b[32m&\x1b[0m/g' | \
  sed 's/Status: [4-5][0-9][0-9]/\x1b[31m&\x1b[0m/g'

# Watch for failures only
DEBUG=1 uvicorn app.main:app --reload 2>&1 | grep -E "Status: [4-5]|error|Error|ERROR"

# Show only the API call headers
DEBUG=1 uvicorn app.main:app --reload 2>&1 | grep -E "API CALL|Status:|Time:"
```

---

## Summary

**Start here:**
```bash
cd ~/Documents/GitHub/Rory_GolfNow_Agent/backend
DEBUG=1 uvicorn app.main:app --reload
```

**Then trigger API calls from frontend and watch Terminal 1.**

Every call will show:
- What was sent (method, URL, headers, body)
- What was received (status, response body)
- How long it took

That's it! 🔍

If you see a problem in the response, the error message will tell you exactly what went wrong.
