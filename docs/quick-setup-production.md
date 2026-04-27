# Quick Setup Guide - Production Deployment

## Prerequisites Checklist

Before deploying to RunPod, you need:

- [ ] Supabase account with PostgreSQL database
- [ ] Ollama endpoint (RunPod GPU Pod recommended)
- [ ] Docker Hub account (for image hosting)
- [ ] Production secret key generated

---

## 1. Supabase Database Setup

### Get Your Connection String

1. Go to [Supabase Dashboard](https://app.supabase.com)
2. Select your project
3. Settings → Database → Connection string
4. Copy the **URI** format (use "Transaction" pooler)

**Example:**
```
postgresql://postgres.xxxx:[PASSWORD]@aws-0-us-west-1.pooler.supabase.com:5432/postgres
```

### Set as Environment Variable

```bash
export DATABASE_URL="postgresql://postgres.xxxx:[PASSWORD]@aws-0-us-west-1.pooler.supabase.com:5432/postgres"
```

**Important:** Replace `[PASSWORD]` with your actual database password

---

## 2. Ollama Setup (GPU Required)

### Option A: RunPod GPU Pod (Recommended)

1. **Create GPU Pod:**
   - Go to RunPod → Deploy
   - Select **GPU Cloud**
   - Choose GPU: RTX 3090 or better ($0.30-0.50/hr)
   - Container Image: `ollama/ollama:latest`
   - Container Disk: 20 GB
   - Expose HTTP Port: `11434`

2. **Get Ollama URL:**
   - Wait for Pod to start (30-60 seconds)
   - Copy the proxy URL from Pod details
   - Format: `https://abc123-11434.proxy.runpod.net`

3. **Pull Model:**
   - Connect via RunPod terminal or SSH
   - Run: `ollama pull llama2` (or your preferred model)
   - Wait for download to complete

4. **Test:**
   ```bash
   curl https://your-pod-url-11434.proxy.runpod.net/api/tags
   ```

### Option B: Modal, Replicate, or Other GPU Cloud

If using another GPU cloud provider:
- Deploy Ollama container
- Expose port 11434
- Get the public URL
- Use that as `OLLAMA_URL`

### Set as Environment Variable

```bash
export OLLAMA_URL="https://your-ollama-pod-11434.proxy.runpod.net"
```

---

## 3. Generate Production Secret Key

### Using Python (Recommended)

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Example output:**
```
xK7pQm2vR5nL8wT3hJ6fY9cN1dZ4aS0bE5gH8jM2pL7
```

### Using OpenSSL

```bash
openssl rand -base64 32
```

### Set as Environment Variable

```bash
export SECRET_KEY="your-generated-secret-key-here"
```

**Security Notes:**
- **Never commit** this to git
- **Never share** publicly
- Use different secrets for dev/staging/prod
- Store securely (password manager, secrets manager)

---

## 4. Create Admin User

After your backend is deployed and database is initialized:

### Run the Admin User Script

```bash
# From project root
cd /Users/206887576@bwt3.com/Documents/GitHub/Rory_GolfNow_Agent

# Set your database URL
export DATABASE_URL="postgresql://..."

# Run the script
python3 scripts/create-admin-user.py
```

**You'll be prompted for:**
- Username (e.g., "admin")
- Email (e.g., "admin@yourcompany.com")
- Password (enter securely)
- Confirm password

**Script will:**
- Hash your password using bcrypt
- Create user with `role=ADMIN` and `status=APPROVED`
- Return the user ID and details

### Alternative: Manual SQL Insert

If you prefer to use Supabase SQL Editor:

```sql
-- Generate password hash first using Python:
-- python3 -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('YourPassword123'))"

INSERT INTO users (username, email, hashed_password, role, status, created_at)
VALUES (
    'admin',
    'admin@yourcompany.com',
    '$2b$12$...',  -- Your bcrypt hash here
    'ADMIN',
    'APPROVED',
    NOW()
);
```

---

## 5. Build and Push Docker Image

### Build Image

```bash
./scripts/build-docker.sh latest
```

### Push to Docker Hub

```bash
./scripts/push-docker.sh latest
# Will prompt for Docker Hub username
```

**Your image will be:**
```
your-username/internal-agent-backend:latest
```

---

## 6. Deploy Backend to RunPod

### Create CPU Pod

1. Go to RunPod → Deploy → **CPU Cloud** (GPU not needed for backend)
2. Select CPU: 4 vCPUs, 8 GB RAM ($0.10-0.15/hr)
3. **Container Image:**
   ```
   your-username/internal-agent-backend:latest
   ```
4. **Container Disk:** 10 GB
5. **Expose HTTP Port:** `8000`

### Set Environment Variables

In RunPod Pod configuration, add:

| Variable | Value |
|----------|-------|
| `DATABASE_URL` | `postgresql://postgres.xxxx:...` (from Supabase) |
| `OLLAMA_URL` | `https://your-ollama-pod-11434.proxy.runpod.net` |
| `SECRET_KEY` | Your generated secret key |

### Deploy

Click **Deploy** and wait for Pod to start (30-60 seconds)

---

## 7. Verify Deployment

### Get Backend URL

From RunPod Pod details, copy the proxy URL:
```
https://your-backend-abc123-8000.proxy.runpod.net
```

### Run Smoke Test

```bash
export RUNPOD_URL="https://your-backend-abc123-8000.proxy.runpod.net"
./scripts/runpod-smoke-test.sh
```

**Expected:**
```
✅ All smoke tests passed!
```

### Manual Test

```bash
curl https://your-backend-abc123-8000.proxy.runpod.net/health
```

**Expected response:**
```json
{
  "status": "healthy",
  "checks": {
    "database": "connected",
    "ollama": "connected"
  }
}
```

---

## 8. Login as Admin

### Using curl

```bash
curl -X POST https://your-backend-url/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "YourPassword123"
  }'
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "admin",
    "email": "admin@yourcompany.com",
    "role": "ADMIN",
    "status": "APPROVED"
  }
}
```

### Access Admin Analytics

```bash
curl -X GET https://your-backend-url/api/admin/analytics \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

---

## Cost Estimation

### Monthly Costs (24/7 operation)

| Service | Spec | Cost/hr | Monthly |
|---------|------|---------|---------|
| Backend Pod | 4 vCPU, 8GB RAM | $0.12 | ~$86 |
| Ollama Pod | RTX 3090 | $0.35 | ~$252 |
| Supabase | Free tier | $0 | $0 |
| **Total** | | | **~$338** |

### Cost Optimization

- **On-demand Ollama:** Spin up GPU Pod only when needed
- **Smaller GPU:** Use RTX 3060 Ti for lighter models (~$0.20/hr)
- **Spot instances:** Use RunPod spot pricing (50-70% cheaper, can be interrupted)
- **Local Ollama:** Run Ollama locally during development

---

## Environment Variables Summary

**Required:**

```bash
# Database (Supabase)
DATABASE_URL="postgresql://postgres.xxxx:[PASSWORD]@aws-0-us-west-1.pooler.supabase.com:5432/postgres"

# Ollama (RunPod GPU Pod)
OLLAMA_URL="https://your-ollama-pod-11434.proxy.runpod.net"

# Security
SECRET_KEY="your-generated-secret-key-32-chars-minimum"
```

**Optional:**

```bash
# Backend (usually default is fine)
BACKEND_PORT=8000

# MCP Server (if using)
MCP_SERVER_URL="http://your-mcp-server:8080"
```

---

## Troubleshooting

### Backend won't start

**Check logs:**
```bash
# In RunPod, go to Pod → Logs tab
# Look for:
❌ ERROR: Missing required environment variables
```

**Solution:** Verify all 3 required env vars are set

### Can't connect to database

**Error:** `database connection failed`

**Solutions:**
1. Check Supabase is running (not paused)
2. Verify DATABASE_URL is correct (including password)
3. Check Supabase allows connections from RunPod IPs
4. Try connection pooler URL instead of direct connection

### Can't connect to Ollama

**Error:** `ollama connection refused`

**Solutions:**
1. Verify Ollama Pod is running
2. Check OLLAMA_URL includes correct port (11434)
3. Test Ollama directly: `curl $OLLAMA_URL/api/tags`
4. Ensure Ollama Pod has model pulled (`ollama list`)

### Health check failing

**RunPod shows "Unhealthy"**

**Solutions:**
1. Check if app is listening on 0.0.0.0:8000
2. View startup logs for errors
3. Verify database connection
4. Increase health check `start-period` in Dockerfile

### Admin login not working

**Error:** `invalid credentials`

**Solutions:**
1. Verify admin user exists: Query Supabase `users` table
2. Check user `status` is `APPROVED`
3. Check user `role` is `ADMIN`
4. Re-run `create-admin-user.py` script
5. Verify password hash was generated correctly

---

## Next Steps

1. ✅ Set up Supabase database
2. ✅ Deploy Ollama GPU Pod
3. ✅ Generate secret key
4. ✅ Build and push Docker image
5. ✅ Deploy backend Pod
6. ✅ Create admin user
7. ✅ Run smoke tests
8. ✅ Login and verify access

**Ready to build!** 🚀

See `docs/runpod-deployment.md` for detailed deployment instructions.
