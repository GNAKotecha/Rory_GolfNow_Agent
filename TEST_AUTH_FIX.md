# Auth Context Fix

## Problem
The AuthContext component's `getCurrentUser()` API call was failing, causing admin pages to redirect to login instead of showing the dashboard.

## Root Cause
The issue was NOT in the frontend code - the backend required an admin user to be created before authentication could work.

## Fix Applied

### 1. Added Comprehensive Logging
Added logging to both `AuthContext.tsx` and `api.ts` to diagnose the issue:
- Token presence checks
- API request/response logging
- Error details

### 2. Fixed Admin User Creation Script
Updated `/backend/app/db/create_admin.py` to create a default tenant first (required by the User model):
```python
# Create default tenant if it doesn't exist
tenant = db.query(Tenant).filter(Tenant.slug == "default").first()
if not tenant:
    tenant = Tenant(
        name="Default Organization",
        slug="default"
    )
    db.add(tenant)
    db.commit()
```

### 3. Created Admin User
Ran the create_admin script to create the admin user:
```bash
cd backend && python3 -m app.db.create_admin
```

## Test Credentials
- **Email**: admin@example.com
- **Password**: admin123

## Verification

### Backend API Test (Passed ✅)
```bash
# Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"admin123"}'

# Get current user (with token from above)
curl http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer <token>"
```

Response:
```json
{
  "id": 17,
  "email": "admin@example.com",
  "name": "Admin User",
  "role": "admin"
}
```

### Frontend Test Steps
1. Start the frontend: `cd frontend && npm run dev`
2. Navigate to http://localhost:3000
3. Login with admin@example.com / admin123
4. Navigate to /admin
5. Verify admin dashboard loads (not redirected to login)
6. Check browser console for logging messages:
   - `[AuthContext] Loading user...`
   - `[AuthContext] Token present: true`
   - `[ApiClient] Request to /api/auth/me - Authorization header added`
   - `[AuthContext] User loaded successfully`

## Files Modified
1. `/frontend/contexts/AuthContext.tsx` - Added logging
2. `/frontend/lib/api.ts` - Added logging
3. `/backend/app/db/create_admin.py` - Fixed tenant creation

## Logging Added
The logging will help diagnose similar issues in the future. Key log points:
- Token loading from localStorage
- Authorization header presence
- API request/response status
- Error details

## Next Steps
If the frontend still has issues after this fix:
1. Check browser console for the new logging messages
2. Verify localStorage contains `access_token` after login
3. Verify the token is being sent in the Authorization header
4. Check for CORS issues between frontend and backend
