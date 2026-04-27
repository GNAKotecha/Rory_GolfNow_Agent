# Quick Start: Single GPU Pod Demo Setup

**Goal:** Test agent with MCP servers, minimal cost  
**Time:** 10 minutes setup  
**Cost:** ~$0.20/hour (only when running)  

---

## What You Need

1. **Supabase** (free tier) - Get connection string from dashboard
2. **RunPod GPU Pod** (RTX 4500 Ada 32GB or similar)
3. **Docker Hub** account - To host your image

**Note:** Using qwen2.5-coder:32b model (~20GB), requires 32GB VRAM GPU

---

## Setup Steps

### 1. Generate Secret Key (Local)

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Save the output - you'll need it for RunPod.

### 2. Build & Push Image (Local)

```bash
cd /Users/206887576@bwt3.com/Documents/GitHub/Rory_GolfNow_Agent

# Build
./scripts/build-docker.sh latest

# Push to Docker Hub
./scripts/push-docker.sh latest
# Enter your Docker Hub username when prompted
```

Your image: `your-username/internal-agent-backend:latest`

### 3. Update docker-compose.runpod.yml

Edit `backend/docker-compose.runpod.yml` line 17:
```yaml
image: your-actual-username/internal-agent-backend:latest
```

### 4. Create RunPod GPU Pod

1. Go to [RunPod Console](https://www.runpod.io/console/pods)
2. Click **Deploy** → **GPU Cloud**
3. Select GPU:
   - **RTX 4500 Ada (32GB)** - For qwen2.5-coder:32b
   - **RTX 3090 (24GB)** - Alternative, use smaller model
   - **RTX 3060 Ti (12GB)** - Budget option, use 7B model
4. Template: **RunPod Pytorch** (has Docker pre-installed)
5. Container Disk: **40 GB** (32B model is ~20GB)
6. Volume Disk: **0 GB** (not needed, using Supabase)
7. Expose HTTP Ports: **8000** (only backend, Ollama stays internal)
8. Click **Deploy**

### 5. Connect to Pod

Once Pod status shows **Running**, click **Connect** → **SSH over exposed TCP**

```bash
ssh root@your-pod-ip -p your-ssh-port
```

Password will be shown in RunPod dashboard.

### 6. Setup on Pod

```bash
# Install git and docker-compose
apt update && apt install -y git docker-compose

# Clone your repo
git clone https://github.com/your-username/your-repo.git
cd your-repo/backend

# Set environment variables
export DATABASE_URL="postgresql://postgres.xxxx:[PASSWORD]@aws-0-us-west-1.pooler.supabase.com:5432/postgres"
export SECRET_KEY="your-generated-secret-key-from-step-1"

# Start everything
./start-runpod.sh
```

**This will:**
- Start Ollama
- Pull llama2:7b model (~5 minutes)
- Start your backend

### 7. Test It Works

**From inside the Pod:**
```bash
curl http://localhost:8000/health
```

**Expected:**
```json
{
  "status": "healthy",
  "checks": {
    "database": "connected",
    "ollama": "connected"
  }
}
```

### 8. Get Public URL

In RunPod dashboard, find your Pod's proxy URL for port 8000:

```
https://your-pod-id-8000.proxy.runpod.net
```

**Note:** Only the backend (port 8000) is exposed publicly. Ollama (port 11434) stays internal for security.

Test from your local machine:
```bash
curl https://your-pod-id-8000.proxy.runpod.net/health
```

### 9. Create Admin User

**Option A: Command-line (fastest)**
```bash
export DATABASE_URL="your-supabase-url"
python3 scripts/create-admin-user.py --username admin --email admin@test.com --password YourPassword123
```

**Option B: Interactive mode**
```bash
export DATABASE_URL="your-supabase-url"
python3 scripts/create-admin-user.py
# Will prompt for username, email, and password
```

**Option C: From Supabase SQL Editor**
```sql
-- First, hash a password locally:
-- python3 -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('YourPassword123'))"

INSERT INTO users (username, email, hashed_password, role, status, created_at)
VALUES (
    'admin',
    'admin@test.com',
    '$2b$12$your_hash_here',  -- Replace with your hash
    'ADMIN',
    'APPROVED',
    NOW()
);
```

### 10. Test Login

```bash
curl -X POST https://your-pod-url/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"YourPassword123"}'
```

**You should get back an access token!**

---

## Testing Your Agent

### Test Chat Endpoint

```bash
# Save your access token
TOKEN="your-access-token-from-login"

# Create a session
curl -X POST https://your-pod-url/api/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Test Session"}'

# Send a message
curl -X POST https://your-pod-url/api/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": 1,
    "message": "Hello, can you help me?"
  }'
```

### View Logs

```bash
# SSH into Pod
ssh root@your-pod-ip -p your-ssh-port

# View all logs
cd your-repo/backend
docker-compose -f docker-compose.runpod.yml logs -f

# View just backend
docker-compose -f docker-compose.runpod.yml logs -f backend

# View just Ollama
docker-compose -f docker-compose.runpod.yml logs -f ollama
```

---

## Making Changes & Redeploying

### 1. Update Code Locally

```bash
# Make your changes to backend code
# ...

# Rebuild image
./scripts/build-docker.sh latest

# Push to Docker Hub
./scripts/push-docker.sh latest
```

### 2. Update on Pod

```bash
# SSH into Pod
ssh root@your-pod-ip -p your-ssh-port

# Pull new image and restart
cd your-repo/backend
docker-compose -f docker-compose.runpod.yml pull backend
docker-compose -f docker-compose.runpod.yml up -d backend

# Check logs
docker-compose -f docker-compose.runpod.yml logs -f backend
```

**Takes ~30 seconds to redeploy**

---

## When You're Done Testing

### Stop Pod (Save Money)

In RunPod dashboard:
1. Find your Pod
2. Click **Stop**
3. Billing stops immediately

**Next time:** Click **Resume** and everything will be there (Docker volumes persist)

### Or: Terminate Pod

If you're done for good:
1. Click **Terminate**
2. Pod is deleted
3. Next time, start fresh (takes 10 min to setup)

---

## Cost Examples

### RTX 4500 Ada (32GB) - For qwen2.5-coder:32b (~$0.80/hr)

| Activity | Time | Cost |
|----------|------|------|
| Initial setup | 20 min | $0.27 |
| Testing session | 2 hours | $1.60 |
| Demo for client | 1 hour | $0.80 |
| Debugging | 3 hours | $2.40 |
| **Total** | **6.33 hrs** | **$5.07** |

### RTX 3090 (24GB) - For smaller models (~$0.35/hr)

| Activity | Time | Cost |
|----------|------|------|
| Full day testing | 8 hours | $2.80 |
| Week of dev (4hr/day) | 28 hours | $9.80 |

**Much cheaper than continuous deployment!**

---

## Troubleshooting

### Model download stuck

```bash
# Check Ollama logs
docker logs ollama

# Model is ~20GB, can take 10-20 minutes on slower connections
# Check download progress
docker exec ollama ollama list
```

### Out of GPU memory

**Solution:** qwen2.5-coder:32b requires ~20GB VRAM

```bash
# Current model size
docker exec ollama ollama list

# If OOM, use smaller model
docker exec ollama ollama pull qwen2.5-coder:14b  # or
docker exec ollama ollama pull mistral:7b-instruct
```

### Backend can't connect to Ollama

**Check:** Environment variable should be `OLLAMA_URL=http://ollama:11434` (not localhost)

```bash
# View backend env vars
docker inspect backend | grep OLLAMA_URL

# If wrong, restart with correct URL
export OLLAMA_URL="http://ollama:11434"
docker-compose -f docker-compose.runpod.yml up -d backend
```

### Database connection failed

**Check:** Supabase is running (not paused due to inactivity)

1. Go to Supabase dashboard
2. Verify project is active
3. Test connection:
   ```bash
   docker exec backend python3 -c "from app.database import engine; engine.connect()"
   ```

---

## GPU Recommendations for Your Use Case

### Code Generation & Agentic Workflows (Current Setup)

**RTX 4500 Ada (32GB VRAM)** - ~$0.80/hr  
- Model: qwen2.5-coder:32b (specialized for code)
- Users: 1-2
- Speed: Excellent code generation
- **Best for development & coding tasks** ✅

### Testing/Budget Option

**RTX 3060 Ti (12GB VRAM)** - $0.20/hr  
- Model: mistral:7b-instruct or llama3:8b
- Users: 1 (testing only)
- Speed: Fast enough for testing MCP servers
- **Cost-effective for basic testing**

### Balanced Performance

**RTX 3090 (24GB VRAM)** - $0.35/hr  
- Model: qwen2.5-coder:14b or llama3:13b
- Users: 2-3 concurrent  
- Speed: Good balance of cost/performance
- **Good for demos and light production**

### Production (10+ users)

**RTX 4090 or A6000 (48GB VRAM)** - $0.60-1.00/hr  
- Model: Multiple models or 70B+ models
- Users: 10+ concurrent  
- Professional deployment  

---

## Summary

✅ **Current setup (Code-focused agent):**
- GPU: RTX 4500 Ada (32GB) - $0.80/hr
- Model: qwen2.5-coder:32b (excellent for code generation)
- Architecture: Everything on one Pod
- Ollama port: Internal only (secure)
- Backend port: 8000 (publicly accessible)
- Workflow: Spin up → test → spin down
- Cost: ~$5 for full testing cycle

✅ **Budget alternative:**
- GPU: RTX 3090 (24GB) - $0.35/hr  
- Model: qwen2.5-coder:14b or mistral:7b
- Same setup, smaller model
- Cost: ~$2-3 for testing cycle

**Total cost estimate for thorough development cycle: $5-10**

Much better than continuous deployment! 🎉
