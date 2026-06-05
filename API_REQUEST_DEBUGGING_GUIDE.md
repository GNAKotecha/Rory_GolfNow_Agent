# API Request/Response Debugging Guide

How to see all HTTP requests and responses that Rory makes to external APIs.

---

## Quick Start: Three Approaches

### **Approach 1: View Logs in Real-Time (Easiest)**

**Best for**: Quick debugging, seeing what's happening right now

```bash
# Start backend with debug logging enabled
cd backend
DEBUG=1 uvicorn app.main:app --reload

# In another terminal, watch logs:
tail -f /tmp/rory_agent.log
```

**You'll see:**
- Every API call URL, method, headers
- Every response status code
- Auth tokens being used
- Errors and timeouts

---

### **Approach 2: Enable HTTP Debug via httpx (Most Detailed)**

**Best for**: Seeing raw HTTP wire protocol, headers, bodies

Modify `backend/gateway_mcp/tools/teesheet/handlers.py` to enable httpx logging:

```python
import logging
import httpx

# Enable httpx debug logging (shows raw HTTP)
logging.getLogger("httpx").setLevel(logging.DEBUG)

async def call_api_handler(...):
    # ... existing code ...
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        # httpx will now log all requests/responses
        try:
            response = await client.request(...)
```

**Run with:**
```bash
DEBUG=1 HTTPX_LOG=1 uvicorn app.main:app --reload
```

**You'll see:**
```
DEBUG:httpx:send: POST http://localhost:8056/api/v3/clubs/brsgolfclubsales/bookings
DEBUG:httpx:req_headers: {'authorization': 'Bearer ...', 'content-type': 'application/json'}
DEBUG:httpx:req_body: {"tee_sheet_booking": {...}}
DEBUG:httpx:response: 200
DEBUG:httpx:res_headers: {'content-type': 'application/json'}
DEBUG:httpx:res_body: {"id": 123, ...}
```

---

### **Approach 3: Intercept Requests with Charles/Fiddler (Professional)**

**Best for**: Network-level inspection, exact byte-for-byte view

1. Install [Charles Proxy](https://www.charlesproxy.com/) or [Fiddler](https://www.telerik.com/fiddler)
2. Configure your app to route through proxy:

```bash
# MacOS with Charles (default: localhost:8888)
HTTP_PROXY=http://localhost:8888 \
HTTPS_PROXY=http://localhost:8888 \
uvicorn app.main:app --reload
```

3. Open Charles → see all HTTP traffic

**You'll see:**
- Complete request/response headers and bodies
- Timing information
- Compression details
- SSL/TLS handshakes

---

## Detailed Setup Options

### **Option A: Add Comprehensive Logging to call_api_handler**

The code already has basic debug logging. Enhance it:

```python
# File: backend/gateway_mcp/tools/teesheet/handlers.py

async def call_api_handler(
    input: CallApiInput,
    context: ToolContext,
) -> CallApiOutput:
    # ... existing setup ...
    
    logger.debug(
        f"API Request Details",
        extra={
            "method": method,
            "url": url,
            "headers": {k: v[:50] + "..." if k == "Authorization" else v 
                       for k, v in headers.items()},
            "body_format": input.body_format,
            "body_size": len(str(input.body)) if input.body else 0,
        }
    )
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.request(...)
            
            # Log response details
            logger.debug(
                f"API Response Details",
                extra={
                    "status": response.status_code,
                    "headers": dict(response.headers),
                    "body_size": len(response.content),
                    "elapsed_ms": response.elapsed.total_seconds() * 1000,
                }
            )
```

---

### **Option B: Create a Request/Response Capture File**

Add middleware to save all API calls to a file:

```python
# File: backend/gateway_mcp/tools/teesheet/handlers.py

import json
from pathlib import Path
from datetime import datetime

API_LOG_DIR = Path("/tmp/rory_api_calls")
API_LOG_DIR.mkdir(exist_ok=True)

async def call_api_handler(...):
    # ... existing code ...
    
    # Before request
    start_time = datetime.now().isoformat()
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.request(...)
    
    # After request - save to file
    call_record = {
        "timestamp": start_time,
        "method": method,
        "url": url,
        "request": {
            "headers": dict(headers),
            "body": input.body if isinstance(input.body, (dict, str)) else str(input.body),
        },
        "response": {
            "status": response.status_code,
            "headers": dict(response.headers),
            "body": response.json() if response.headers.get("content-type") == "application/json" else response.text,
        },
        "elapsed_ms": (datetime.now() - datetime.fromisoformat(start_time)).total_seconds() * 1000,
    }
    
    # Save to file
    call_file = API_LOG_DIR / f"call_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
    with open(call_file, "w") as f:
        json.dump(call_record, f, indent=2, default=str)
    
    logger.info(f"API call logged to {call_file}")
```

Then view:
```bash
# View all API calls
ls -ltr /tmp/rory_api_calls/

# View specific call
cat /tmp/rory_api_calls/call_20260605_143022_123456.json

# Pretty-print with jq
jq . /tmp/rory_api_calls/call_20260605_143022_123456.json

# See all URLs called:
for f in /tmp/rory_api_calls/call_*.json; do jq .url $f; done
```

---

### **Option C: Enable Python Logging Handlers**

Configure Python logging to output to both console and file:

```python
# File: backend/app/core/logging_config.py (new or existing)

import logging
import sys
from pathlib import Path

def configure_api_logging():
    """Configure detailed API request/response logging."""
    
    # Create logger for API calls
    api_logger = logging.getLogger("api_calls")
    api_logger.setLevel(logging.DEBUG)
    
    # File handler
    log_file = Path("/tmp/rory_api_calls.log")
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    
    # Formatter with details
    detailed_formatter = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s - %(message)s - %(extra)s"
    )
    file_handler.setFormatter(detailed_formatter)
    
    api_logger.addHandler(file_handler)
    api_logger.addHandler(console_handler)
    
    return api_logger

# In call_api_handler:
api_logger = logging.getLogger("api_calls")
api_logger.info(
    f"API Call: {method} {url}",
    extra={
        "headers": dict(headers),
        "body": input.body,
        "response_status": response.status_code,
        "response_body": response.text[:500],  # First 500 chars
    }
)
```

---

## Real-World Debugging Workflows

### **Workflow 1: Debug Failed BRS API Call**

```bash
# 1. Start backend with full logging
DEBUG=1 HTTPX_LOG=1 uvicorn app.main:app --reload 2>&1 | tee /tmp/rory.log

# 2. Trigger agent action in frontend (make an API call)

# 3. Search logs for the failing endpoint
grep -A 20 "POST /api/v3/clubs" /tmp/rory.log

# 4. See the exact request that was sent
# Example output:
# DEBUG:httpx:send: POST http://localhost:8056/api/v3/clubs/brsgolfclubsales/bookings
# DEBUG:httpx:req_headers: {...}
# DEBUG:httpx:req_body: {"tee_sheet_booking": {...}}
# DEBUG:httpx:response: 422
# DEBUG:httpx:res_body: {"error": {"code": "VALIDATION_FAILED", ...}}

# 5. Compare request format to API docs
curl -X POST http://localhost:8056/api/documentation/ | grep booking
```

---

### **Workflow 2: Compare Expected vs Actual Requests**

```bash
# 1. Save expected request to file
cat > /tmp/expected_request.json << 'EOF'
{
  "tee_sheet_booking": {
    "course_id": 1,
    "date": "2026-05-28",
    "time": "09:00",
    "slots": {
      "1": {"player": {"type": "MEMBER", "id": 17}}
    }
  }
}
EOF

# 2. Enable capture (see Option B above)
DEBUG=1 uvicorn app.main:app --reload

# 3. Trigger action that makes API call

# 4. Compare
jq . /tmp/rory_api_calls/call_*.json > /tmp/actual_request.json
diff /tmp/expected_request.json /tmp/actual_request.json

# 5. See the difference
# > Expected: "type": "MEMBER"
# < Actual: "type": "member"  ← lowercase!
```

---

### **Workflow 3: Monitor API Performance**

```bash
# Extract timing from logs
grep "API response" /tmp/rory.log | grep -oE "elapsed_ms: [0-9]+" | sort -t: -k2 -n

# Slowest calls
for f in /tmp/rory_api_calls/call_*.json; do 
  echo "$(jq .url $f): $(jq .elapsed_ms $f)ms"
done | sort -t: -k2 -n | tail -10
```

---

## Environment Variables for Debugging

Add to your shell or `.env.local`:

```bash
# Enable debug logging
DEBUG=1

# Enable httpx HTTP protocol logging
HTTPX_LOG=1

# Increase request timeout for slow debugging
TEESHEET_REQUEST_TIMEOUT=120

# Log all environment variables (careful - sensitive data!)
LOG_ENV_VARS=1

# Disable SSL verification (for intercepting proxies)
# WARNING: Security risk - dev only!
# SSL_VERIFY=false
```

---

## Reading the Logs

### **What to Look For**

1. **URL Construction**
   ```
   Calling Teesheet API: POST /api/v3/clubs/brsgolfclubsales/bookings
   ```
   → Verify club ID, path, method are correct

2. **Authentication**
   ```
   headers: {'Authorization': 'Bearer eyJ0eXAi...', 'Content-Type': 'application/json'}
   ```
   → Is token present? Is it the right club?

3. **Request Body**
   ```
   req_body: {"tee_sheet_booking": {"course_id": 1, "date": "2026-05-28", ...}}
   ```
   → Matches API schema? All required fields?

4. **Response Status**
   ```
   response: 422
   ```
   → 200-299 = success, 400-499 = client error, 500+ = server error

5. **Error Messages**
   ```
   res_body: {"error": {"code": "VALIDATION_FAILED", "details": {"first_name": "must not be blank"}}}
   ```
   → Tells you exactly what field is wrong

---

## Bonus: tcpdump for Network Level Inspection

See **every byte** sent over the network:

```bash
# Capture traffic to localhost:8056
sudo tcpdump -i lo0 -n port 8056 -w /tmp/teesheet.pcap

# Later, view with Wireshark
wireshark /tmp/teesheet.pcap

# Or filter with tcpdump:
sudo tcpdump -i lo0 -n port 8056 -A | grep -i POST
```

---

## Summary: Recommended Setup

**For daily development:**
1. Run backend with `DEBUG=1`
2. Watch logs in terminal: `tail -f /tmp/rory.log`
3. Make agent requests from frontend
4. See requests/responses in real-time

**For debugging specific issues:**
1. Enable Option B (capture to JSON files)
2. Trigger the failing action
3. Examine `/tmp/rory_api_calls/` JSON files
4. Compare against API docs

**For deep network inspection:**
1. Use Charles Proxy on Mac
2. Route traffic through it
3. See compressed requests, SSL details, timing

---

## Quick Commands

```bash
# View all recent API calls
tail -100 /tmp/rory_api_calls.log

# Find failed requests (status >= 400)
grep "status.*[4-9][0-9][0-9]" /tmp/rory_api_calls.log

# Search by endpoint
grep "POST.*bookings" /tmp/rory_api_calls.log

# Find slow requests (> 5 seconds)
grep "elapsed_ms.*[5-9][0-9][0-9][0-9]" /tmp/rory_api_calls.log

# See what URLs are being called
grep "url:" /tmp/rory_api_calls.log | sort | uniq

# Format JSON response nicely
jq .response.body /tmp/rory_api_calls/call_*.json | head -50
```

---

## Troubleshooting

**Q: Logs are going to stdout but I can't find them**
A: Logs are in your terminal output. Try `DEBUG=1 uvicorn ... 2>&1 | tee /tmp/rory.log` to save to file.

**Q: httpx debug logging not showing**
A: Add this to the top of your Python script:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("httpx").setLevel(logging.DEBUG)
```

**Q: Authorization header is redacted/hidden**
A: Check logs - they intentionally hide full tokens. You can search logs for partial token to find which call used it.

**Q: Too much logging, can't find what I'm looking for**
A: Use grep to filter:
```bash
grep "bookings" /tmp/rory.log | grep -i "error"
```

---

## See Also

- [BRS API Docs](http://localhost:8056/api/documentation/)
- [httpx Documentation](https://www.python-httpx.org/)
- [Python Logging Guide](https://docs.python.org/3/library/logging.html)
