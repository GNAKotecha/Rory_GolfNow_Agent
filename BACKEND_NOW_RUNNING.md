# Backend Running - Real-Time API Visibility Active ✅

## Status

✅ Backend is running on **http://localhost:8000**

✅ API debugging is **ENABLED**

✅ Every API call will print to the terminal with:
- Request method & URL
- Request headers & body
- Response status & timing
- Response headers & body

---

## What to Do Now

### 1. Use Rory in the Frontend

Open your frontend (typically http://localhost:3000 or similar) and use Rory to:
- Create a booking
- Update member info
- Create green fees
- Or any other API-dependent action

### 2. Watch for API Calls

As Rory makes API calls, you'll see output like:

```
================================================================================
API CALL COMPLETED: POST http://localhost:8056/api/v3/clubs/brsgolfclubsales/bookings
================================================================================
Status: 201 | Time: 234ms

REQUEST HEADERS:
  Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGci...
  Content-Type: application/json

REQUEST BODY:
  {
    "tee_sheet_booking": {
      "course_id": 1,
      "date": "2026-05-28",
      ...
    }
  }

RESPONSE HEADERS:
  content-type: application/json

RESPONSE BODY:
  {
    "id": 12345,
    "status": "confirmed"
  }
================================================================================
```

### 3. Analyze the Output

**Successful (2xx status):**
- Status: 200, 201, 204
- Response should have the data or confirmation

**Failed (4xx status):**
- Status: 400, 422 (validation), 401 (auth)
- Response will have error details in `error.details`

**Server Error (5xx status):**
- Status: 500, 503
- Something went wrong on the API side

---

## Key Information in Output

### Status Code

| Code | Meaning |
|------|---------|
| 201 | Created - Success ✓ |
| 204 | No Content - Success ✓ |
| 422 | Validation Failed - Check error.details |
| 401 | Unauthorized - Auth issue |
| 500 | Server Error - API crashed |

### Timing (Time: Xms)

- < 200ms: Very fast ✓
- 200-500ms: Normal ✓
- 500ms-2s: Slow (maybe overloaded)
- 2s+: Very slow (check if API is down)

### Authorization Header

- Present: `Authorization: Bearer eyJ0...` → Auth working ✓
- Missing: No Authorization header → Auth failed ✗

---

## Common Scenarios

### Scenario 1: Booking Created Successfully

```
Status: 201 | Time: 234ms

REQUEST BODY:
  {
    "tee_sheet_booking": {
      "course_id": 1,
      "date": "2026-05-28",
      ...
    }
  }

RESPONSE BODY:
  {
    "id": 12345,
    "status": "confirmed"
  }
```

→ **Result**: ✅ Booking successfully created with ID 12345

---

### Scenario 2: Validation Error (422)

```
Status: 422 | Time: 123ms

REQUEST BODY:
  {
    "email": "not-an-email"
  }

RESPONSE BODY:
  {
    "error": {
      "code": "VALIDATION_FAILED",
      "details": {
        "email": "must be a valid email address"
      }
    }
  }
```

→ **Result**: ⚠️ Email format is invalid. Agent needs to send proper email format.

---

### Scenario 3: Authentication Failed (401)

```
Status: 401 | Time: 50ms

REQUEST HEADERS:
  (No Authorization header, or expired token)

RESPONSE BODY:
  {
    "error": {
      "code": "UNAUTHORIZED",
      "message": "Token expired or invalid"
    }
  }
```

→ **Result**: ⚠️ Auth token is missing or expired. Check BRSAuthProvider.

---

### Scenario 4: Server Error (500)

```
Status: 500 | Time: 1234ms

RESPONSE BODY:
  {
    "error": {
      "code": "INTERNAL_ERROR",
      "message": "Internal server error"
    }
  }
```

→ **Result**: ❌ BRS API crashed. Try again or check if service is down.

---

## Reading the Full Output

### Header Line
```
API CALL COMPLETED: POST http://localhost:8056/api/v3/clubs/brsgolfclubsales/bookings
```
- **Method**: GET, POST, PATCH, DELETE, etc.
- **URL**: Full endpoint path

### Status & Timing
```
Status: 201 | Time: 234ms
```
- **Status**: HTTP status code
- **Time**: How long request took

### Request Section
```
REQUEST HEADERS:
  Authorization: Bearer ...
  Content-Type: application/json

REQUEST BODY:
  {...full JSON...}
```
- Shows exactly what Rory is sending to the API

### Response Section
```
RESPONSE HEADERS:
  content-type: application/json

RESPONSE BODY:
  {...response JSON...}
```
- Shows exactly what the API returns

---

## Debugging Tips

### "I see an error in the response - what does it mean?"

Look at `error.details` in the RESPONSE BODY:
```json
{
  "error": {
    "details": {
      "field_name": "error message describing what's wrong"
    }
  }
}
```

The error message tells you exactly what's wrong with that field.

### "The request looks correct but API rejected it"

1. Compare your REQUEST BODY to the API docs
2. Check if all required fields are present
3. Check if field formats match expectations (email, date, numbers, etc.)

### "Is authentication working?"

Look for `Authorization` header in REQUEST HEADERS:
- **Present**: `Authorization: Bearer eyJ0...` → Working ✓
- **Missing**: → Auth setup failed ✗

---

## Next Steps

1. **Use Rory** to trigger API calls
2. **Watch terminal** for API call output
3. **Compare requests** to what you expect
4. **Check responses** for errors

Every API call is now visible! 🔍

---

## Saving Terminal Output

If you want to save logs for later review:

```bash
# Start backend and save to file
cd ~/Documents/GitHub/Rory_GolfNow_Agent/backend
DEBUG=1 uvicorn app.main:app --reload 2>&1 | tee /tmp/rory_api_debug.log
```

Then you can search:
```bash
# Find all API calls
grep "API CALL COMPLETED" /tmp/rory_api_debug.log

# Find failed calls
grep "Status: [4-5]" /tmp/rory_api_debug.log

# Find slow calls
grep "Time: [0-9][0-9][0-9][0-9]" /tmp/rory_api_debug.log
```

---

## Summary

✅ Backend is running with enhanced API logging  
✅ Every call from Rory will print to terminal  
✅ Shows full request and response  
✅ No additional setup needed  

Just use Rory and watch! 🚀
