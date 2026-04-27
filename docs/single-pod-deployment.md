# Single GPU Pod Deployment (Demo/Testing)

**Use Case:** Demo, testing, iterative development  
**Cost:** ~$0.20-0.35/hr (only while running)  
**Setup Time:** 10 minutes  

## Architecture

Instead of running backend and Ollama separately, run BOTH on one GPU Pod:

```
┌─────────────────────────────┐
│      RunPod GPU Pod         │
│                             │
│  ┌──────────┐  ┌─────────┐ │
│  │ Backend  │  │ Ollama  │ │
│  │ (FastAPI)│  │ (LLM)   │ │
│  │ Port 8000│  │Port 11434│ │
│  └──────────┘  └─────────┘ │
│                             │
│  Exposes: 8000 (backend)    │
└─────────────────────────────┘
         │
         ├─> Supabase (DB)
         └─> Public access
```

**Benefits:**
- ✅ Pay for only ONE Pod (~$0.20-0.35/hr)
- ✅ Can spin up/down as needed (only pay when testing)
- ✅ Simpler networking (localhost communication)
- ✅ Perfect for demos and iterative testing

---

## GPU Requirements

### For Testing/Demo (1-2 users)

**RTX 3060 Ti (12GB VRAM)** - ~$0.20/hr
- Can run: 7B models (llama2, mistral, codellama)
- Good for: Testing MCP servers, prompt adherence, basic demos
- Concurrent users: 1-2
- Inference speed: ~20-30 tokens/sec

**Recommended for your use case** ✅

### For Light Production (2-5 users)

**RTX 3090 (24GB VRAM)** - ~$0.35/hr
- Can run: 13B models or multiple 7B models
- Good for: Small team usage, better quality responses
- Concurrent users: 2-5
- Inference speed: ~30-40 tokens/sec

### For Production (10+ users)

**RTX 4090 or A40 (48GB VRAM)** - ~$0.60-0.80/hr
- Can run: 30B+ models or multiple 13B models
- Good for: Production deployment, many concurrent users
- Concurrent users: 10+
- Inference speed: ~50+ tokens/sec

---

## Model Selection

### 7B Models (Recommended for Testing)

**llama2:7b** - 4GB VRAM
- Good all-around performance
- Fast inference
- Works great for demos

**mistral:7b** - 4GB VRAM
- Slightly better quality than llama2
- Good instruction following
- Fast

**codellama:7b** - 4GB VRAM
- Better for code-related tasks
- Good for technical demos

### 13B Models (If You Have Budget)

**llama2:13b** - 8GB VRAM
- Better quality responses
- Still reasonably fast
- Good for client demos

---

## Setup Instructions

### 1. Create Docker Compose File

Create `backend/docker-compose.runpod.yml`:

```yaml
version: '3.8'

services:
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    restart: unless-stopped

  backend:
    image: your-username/internal-agent-backend:latest
    container_name: backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - OLLAMA_URL=http://ollama:11434
      - SECRET_KEY=${SECRET_KEY}
    depends_on:
      - ollama
    restart: unless-stopped

volumes:
  ollama_data:
```

**Key point:** `OLLAMA_URL=http://ollama:11434` (internal Docker networking)

### 2. Create Startup Script

Create `backend/start-runpod.sh`:

```bash
#!/bin/bash
set -e

echo "🚀 Starting Internal Agent on RunPod..."
echo "================================================"

# Pull Ollama model
echo "📦 Pulling Ollama model (this may take a few minutes)..."
docker-compose -f docker-compose.runpod.yml up -d ollama
sleep 5
docker exec ollama ollama pull llama2:7b

echo ""
echo "✅ Model pulled successfully"
echo ""

# Start backend
echo "🔧 Starting backend..."
docker-compose -f docker-compose.runpod.yml up -d backend

echo ""
echo "✅ All services started!"
echo ""
echo "Backend: http://localhost:8000"
echo "Ollama: http://localhost:11434"
echo ""
echo "View logs:"
echo "  docker-compose -f docker-compose.runpod.yml logs -f"
echo ""
```

Make it executable:
```bash
chmod +x backend/start-runpod.sh
```

### 3. Deploy to RunPod

#### Option A: Using RunPod Template (Easiest)

1. **Create GPU Pod:**
   - Go to RunPod → Deploy
   - Select GPU: **RTX 3060 Ti** or **RTX 3090**
   - Template: **Docker** (or Ubuntu)
   - Container Disk: 30 GB (for model storage)
   - Expose HTTP Port: **8000**

2. **Connect via SSH:**
   ```bash
   ssh root@your-pod-ip -p your-ssh-port
   ```

3. **Install Docker Compose (if needed):**
   ```bash
   apt update
   apt install -y docker-compose
   ```

4. **Clone your repo:**
   ```bash
   git clone https://github.com/your-username/your-repo.git
   cd your-repo/backend
   ```

5. **Set environment variables:**
   ```bash
   export DATABASE_URL="postgresql://..."
   export SECRET_KEY="your-secret-key"
   ```

6. **Run startup script:**
   ```bash
   ./start-runpod.sh
   ```

#### Option B: Custom Dockerfile (More Automated)

Create `backend/Dockerfile.runpod`:

```dockerfile
FROM ollama/ollama:latest AS ollama-base

FROM python:3.11-slim

# Install Ollama
COPY --from=ollama-base /bin/ollama /bin/ollama

# Install backend dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY . .

# Create data directory
RUN mkdir -p /app/data

# Copy startup script
COPY start-combined.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 8000 11434

CMD ["/start.sh"]
```

Create `backend/start-combined.sh`:

```bash
#!/bin/bash
set -e

# Start Ollama in background
echo "Starting Ollama..."
ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready
echo "Waiting for Ollama to be ready..."
sleep 5

# Pull model
echo "Pulling model..."
ollama pull llama2:7b

# Start backend
echo "Starting backend..."
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Build and push:**
```bash
cd backend
docker build -f Dockerfile.runpod -t your-username/internal-agent-combined:latest .
docker push your-username/internal-agent-combined:latest
```

**Deploy to RunPod:**
- Container Image: `your-username/internal-agent-combined:latest`
- GPU: RTX 3060 Ti
- Expose port: 8000
- Set env vars: DATABASE_URL, SECRET_KEY

---

## 4. Test Your Deployment

### Get Pod URL

RunPod provides: `https://abc123-8000.proxy.runpod.net`

### Test Health

```bash
curl https://your-pod-url/health
```

### Test Ollama

```bash
curl https://your-pod-url/health
# Check that "ollama": "connected"
```

### Create Admin User

From your local machine:

```bash
# SSH into Pod
ssh root@your-pod-ip -p your-ssh-port

# Inside Pod, run:
export DATABASE_URL="your-supabase-url"
python3 scripts/create-admin-user.py
```

Or use the Supabase SQL Editor to insert manually.

---

## Cost Breakdown

### On-Demand Testing (Recommended for You)

| GPU | Cost/hr | 8hr testing | 40hr testing |
|-----|---------|-------------|--------------|
| RTX 3060 Ti | $0.20 | $1.60 | $8.00 |
| RTX 3090 | $0.35 | $2.80 | $14.00 |

**Example:** 
- Demo prep: 2 hours = $0.40-0.70
- Client demo: 1 hour = $0.20-0.35
- Iteration (10 sessions × 2hr): $4.00-7.00

**Total for full demo cycle: ~$5-10**

### Spot Instances (50-70% Cheaper)

RunPod offers "spot" pricing (can be interrupted):
- RTX 3060 Ti: ~$0.10/hr
- RTX 3090: ~$0.18/hr

**Good for:** Development, can handle interruptions  
**Not good for:** Live demos, production

---

## Testing Workflow

### 1. Spin Up Pod
```bash
# Start Pod in RunPod dashboard
# Wait 2-3 minutes for startup
```

### 2. Test Your Changes
```bash
# Make API calls
# Test MCP servers
# Test prompt adherence
```

### 3. View Logs
```bash
# SSH into Pod
docker-compose -f docker-compose.runpod.yml logs -f backend
docker-compose -f docker-compose.runpod.yml logs -f ollama
```

### 4. Make Changes
```bash
# Locally: update code
# Push to Docker Hub
./scripts/build-docker.sh latest
./scripts/push-docker.sh latest

# On Pod: pull new image
docker-compose -f docker-compose.runpod.yml pull backend
docker-compose -f docker-compose.runpod.yml up -d backend
```

### 5. Spin Down When Done
```bash
# Stop Pod in RunPod dashboard
# Only pay for time used
```

---

## Quick Reference

### Environment Variables

**Required:**
```bash
DATABASE_URL="postgresql://postgres.xxxx:...@aws-0-us-west-1.pooler.supabase.com:5432/postgres"
SECRET_KEY="your-generated-secret-key"
```

**Internal (automatic):**
```bash
OLLAMA_URL="http://ollama:11434"  # Docker internal networking
```

### Useful Commands

**View logs:**
```bash
docker-compose -f docker-compose.runpod.yml logs -f
```

**Restart backend only:**
```bash
docker-compose -f docker-compose.runpod.yml restart backend
```

**Pull new model:**
```bash
docker exec ollama ollama pull mistral:7b
```

**List loaded models:**
```bash
docker exec ollama ollama list
```

**Check GPU usage:**
```bash
nvidia-smi
```

---

## Troubleshooting

### Ollama not responding

```bash
# Check if running
docker ps

# Check logs
docker logs ollama

# Restart
docker-compose -f docker-compose.runpod.yml restart ollama
```

### Out of VRAM

**Solution:** Use smaller model or larger GPU

```bash
# Try 7B instead of 13B
docker exec ollama ollama pull llama2:7b

# Or upgrade to RTX 3090
```

### Model download slow

RunPod datacenter bandwidth varies. First download may take 5-10 minutes for 7B model.

### Backend can't connect to Ollama

**Check:** `OLLAMA_URL` should be `http://ollama:11434` (not localhost)

---

## Summary

**For your use case (demo, testing, iteration):**

✅ **Use:** Single GPU Pod (RTX 3060 Ti)  
✅ **Model:** llama2:7b (fast, good quality)  
✅ **Cost:** ~$0.20/hr × hours tested  
✅ **Workflow:** Spin up → test → spin down  

**Total cost for thorough testing: $5-10**

Much better than ~$340/month for 24/7 operation!
