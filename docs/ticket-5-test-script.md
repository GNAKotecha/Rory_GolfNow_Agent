# Ticket 5 - Verification Test Script

This script tests the authentication and approval flow.

## Prerequisites

1. Backend is running
2. Database is initialized
3. Admin user is created

## Test Flow

### 1. Register New User
```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "testuser@example.com",
    "name": "Test User",
    "password": "test123"
  }'
```

**Expected**: User created with `approval_status: "pending"`

### 2. Login as New User
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "testuser@example.com",
    "password": "test123"
  }'
```

**Expected**: Returns `access_token`

### 3. Try to Access Protected Endpoint (Pending User)
```bash
TOKEN="<your_token_from_step_2>"

curl -X POST http://localhost:8000/api/sessions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "title": "Test Session"
  }'
```

**Expected**: `403 Forbidden` - User not approved

### 4. Login as Admin
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "admin123"
  }'
```

**Expected**: Returns `access_token` for admin

### 5. List Users (Admin Only)
```bash
ADMIN_TOKEN="<your_admin_token_from_step_4>"

curl http://localhost:8000/api/admin/users \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**Expected**: List of all users including pending user

### 6. Approve User
```bash
# Get user_id from step 5, then approve

curl -X POST http://localhost:8000/api/admin/users/{user_id}/approve \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "approve": true
  }'
```

**Expected**: User status changed to "approved"

### 7. Try Protected Endpoint Again (Approved User)
```bash
# Use the original user token from step 2

curl -X POST http://localhost:8000/api/sessions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "title": "Test Session"
  }'
```

**Expected**: `200 OK` - Session created successfully

### 8. Try Unauthenticated Access
```bash
curl -X POST http://localhost:8000/api/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Session"
  }'
```

**Expected**: `403 Forbidden` - No credentials provided

## Acceptance Criteria Checklist

- [ ] Unauthenticated users cannot access protected chat endpoints
- [ ] Approved users can use the product
- [ ] Pending users cannot run agent workflows
- [ ] User identity is attached to sessions/messages
- [ ] Admin can approve new users
- [ ] Login returns JWT token
- [ ] Protected endpoints verify token
- [ ] Sessions belong to authenticated user
