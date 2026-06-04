# Admin Dashboard Guide
## GolfNow Agent - Trace Explorer & Admin Controls

**Status:** ✅ Production Ready

---

## Overview

The GolfNow Agent includes a comprehensive **Admin Dashboard** built with Next.js that provides:

1. **Trace Explorer** - View and search workflow execution traces from Langfuse
2. **Filter Panel** - Filter traces by ID, user, status, date range, and name
3. **Trace Details Modal** - Deep dive into individual trace execution steps
4. **Real-time Dashboard** - Live view of system activity

---

## Accessing the Admin Dashboard

### Local Development
```bash
# Start the frontend
cd frontend
npm run dev

# Admin dashboard accessible at:
http://localhost:3000/admin/traces
```

### Production
```bash
# Admin dashboard accessible at:
https://your-domain.com/admin/traces
```

### Authentication
- Login required (JWT token via `/login` page)
- Only admin users can access `/admin/*` routes
- Tenant context automatically applied to trace queries

---

## Features

### 1. Trace Explorer Page
**Location:** `/admin/traces`

**Features:**
- Browse all workflow execution traces
- Pagination (20 traces per page)
- Real-time loading status
- Error handling with dismissible alerts

### 2. Filter Panel (Left Sidebar)
**Filters Available:**

| Filter | Type | Example |
|--------|------|---------|
| **Trace ID** | Text | `trace_abc123def456` |
| **User ID** | Text/Number | `42` |
| **Status** | Dropdown | `success`, `failed`, `pending` |
| **Start Date** | Date | `2026-06-01` |
| **End Date** | Date | `2026-06-04` |
| **Name** | Text | `onboarding_workflow` |

**Actions:**
- "Apply Filters" - Filter traces
- "Clear Filters" - Reset to show all traces

### 3. Trace List Table (Main Area)
**Displays:**
- Trace ID (clickable)
- Workflow name
- Status (success/failed/pending)
- User ID
- Execution time
- Timestamp

**Actions:**
- Click any row to view detailed trace information

### 4. Trace Detail Modal
**Shows Complete Execution Details:**

```
Trace Information
├── Trace ID
├── Workflow Name
├── Status (success/failed/pending)
├── User ID
├── Start Time
├── End Time
├── Duration
└── Execution Steps

Step Details (if available)
├── Step Name
├── Status
├── Duration
├── Inputs/Outputs
└── Errors (if any)
```

---

## Common Use Cases

### View Recent Traces
1. Go to `/admin/traces`
2. Page loads with most recent traces
3. Traces sorted by timestamp (newest first)

### Find Traces by User
1. Enter user ID in "User ID" filter
2. Click "Apply Filters"
3. View all traces for that user

### Search Failed Workflows
1. Select "failed" in Status dropdown
2. Click "Apply Filters"
3. View all failed workflow traces
4. Click on trace to see error details

### Debug Specific Workflow
1. Copy trace ID from workflow execution
2. Paste into "Trace ID" filter
3. Click "Apply Filters"
4. View specific trace details

### Analyze Performance
1. Set date range (Start Date → End Date)
2. Filter by workflow name (optional)
3. Review execution times and durations
4. Look for patterns or bottlenecks

---

## Understanding Trace Data

### Trace Status Values
- **success** - Workflow completed successfully
- **failed** - Workflow failed with error
- **pending** - Workflow still executing
- **paused** - Workflow paused awaiting approval

### Trace Information Shown

```json
{
  "trace_id": "trace_abc123def456",
  "workflow_name": "club_setup_workflow",
  "user_id": 42,
  "status": "success",
  "start_time": "2026-06-04T10:30:00Z",
  "end_time": "2026-06-04T10:31:45Z",
  "duration_ms": 105000,
  "steps": [
    {
      "step_name": "validate_inputs",
      "status": "success",
      "duration_ms": 150
    },
    {
      "step_name": "create_club",
      "status": "success",
      "duration_ms": 2500
    },
    {
      "step_name": "setup_teesheet",
      "status": "success",
      "duration_ms": 1200
    }
  ]
}
```

---

## Frontend Components

### TraceExplorerPage (`/app/admin/traces/page.tsx`)
**Main page component that:**
- Manages filter state
- Handles trace fetching
- Renders UI layout
- Manages pagination

### TraceFiltersPanel (`/components/admin/TraceFiltersPanel.tsx`)
**Filter sidebar that:**
- Displays filter input fields
- Handles filter input changes
- Provides "Apply" and "Clear" buttons
- Shows loading state

### TraceListTable (`/components/admin/TraceListTable.tsx`)
**Table component that:**
- Displays trace rows
- Shows summary stats
- Handles row click (view detail)
- Manages loading state

### TraceDetailModal (`/components/admin/TraceDetailModal.tsx`)
**Detail modal that:**
- Shows full trace information
- Displays execution steps
- Shows errors (if any)
- Provides close button

---

## API Integration

### Backend Endpoints Used

```
GET /api/admin/traces
  Query Parameters:
    - limit: Number of traces per page (default: 20)
    - offset: Pagination offset
    - trace_id?: Filter by trace ID
    - user_id?: Filter by user ID
    - status?: Filter by status (success/failed/pending)
    - start_date?: Filter by start date (ISO 8601)
    - end_date?: Filter by end date (ISO 8601)
    - name?: Filter by workflow name

GET /api/admin/traces/{trace_id}
  Returns: Detailed trace information with all steps
```

### API Client (`lib/api.ts`)
```typescript
// Fetch paginated trace list
apiClient.getTraces({
  limit: 20,
  offset: 0,
  trace_id: "...",
  user_id: "...",
  status: "success",
  name: "..."
})

// Fetch single trace details
apiClient.getTrace("trace_abc123def456")
```

---

## Troubleshooting

### No traces appearing
1. Check if any workflows have executed
2. Verify Langfuse connection in backend
3. Check if traces are actually being ingested:
   ```bash
   curl http://localhost:8000/api/admin/traces?limit=1
   ```
4. Wait a moment (traces have 5-min cache TTL)

### Filters not working
1. Ensure values are correct format:
   - User IDs should be numeric
   - Dates should be YYYY-MM-DD format
   - Trace IDs should start with "trace_"
2. Clear filters and try again
3. Check browser console for errors

### Slow trace loading
1. Reduce date range
2. Filter by specific user or workflow
3. Reduce page size (currently 20 per page)
4. Check Langfuse service connectivity

### Trace details not loading
1. Verify trace ID is correct
2. Wait for trace ingestion (up to 5 minutes)
3. Check if trace still exists in Langfuse

---

## Production Deployment

### Prerequisites
- Backend API running with admin endpoints
- Langfuse service configured and ingesting traces
- Authentication configured (JWT tokens)
- Admin user role configured

### Environment Variables
```bash
# .env.local (frontend)
NEXT_PUBLIC_API_URL=https://api.your-domain.com
```

### Access Control
- Admin dashboard protected by JWT token validation
- Only users with admin role can access `/admin/*`
- Tenant context enforced on all trace queries

---

## Performance Characteristics

| Operation | Latency | Notes |
|-----------|---------|-------|
| Load trace list | <500ms | Cached, paginated |
| Apply filters | <1s | Real-time search |
| Load trace details | <200ms | Direct query |
| Modal animation | <300ms | Smooth transition |

---

## Next Steps

### Monitor System Health
1. Check trace success rate
2. Monitor workflow execution times
3. Identify failed workflows and debug
4. Track user activity patterns

### Analyze Performance
1. Review trace durations
2. Identify bottleneck steps
3. Optimize slow workflows
4. Monitor tool execution times

### Troubleshoot Issues
1. Search for failed traces
2. View error details in trace modal
3. Identify error patterns
4. Plan fixes based on root causes

---

## Support

**Admin Dashboard Status:** ✅ Production Ready

**Key Features:**
- ✅ Trace explorer with filtering
- ✅ Real-time pagination
- ✅ Detailed trace modal
- ✅ Error handling
- ✅ Responsive design

**Documentation:** See README_PRODUCTION.md for full system documentation.

---

**Last Updated:** 2026-06-04  
**Version:** 1.0  
**Status:** Production Ready
