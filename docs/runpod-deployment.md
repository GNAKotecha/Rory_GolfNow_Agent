# RunPod Deployment Guide

## Overview

This guide covers deploying the internal agent backend to RunPod GPU cloud.

## Container Image

**Image Name:** `internal-agent-backend`

**Registry:** Docker Hub (or custom registry)

**Build locally:**
```bash
./scripts/build-docker.sh latest
```

**Push to registry:**
```bash
./scripts/push-docker.sh latest docker.io
# Will prompt for Docker Hub username
```

## Required Environment Variables

Set these in RunPod Pod configuration:

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | Database connection string | `sqlite:///./data/agent.db` |
| `OLLAMA_URL` | Ollama service endpoint | `http://host.docker.internal:11434` |
| `SECRET_KEY` | JWT signing secret | `your-secret-key-here` |
| `BACKEND_PORT` | Port to expose (optional) | `8000` |
| `MCP_SERVER_URL` | MCP server endpoint (optional) | `http://mcp-server:8080` |

**Important:** Never commit actual secrets to version control. Use RunPod's environment variable interface.

## Exposed Ports

- **8000** - Main HTTP API

RunPod will provide an HTTPS proxy URL (e.g., `https://abc123-8000.proxy.runpod.net`)

## Volume Mounts

For persistent data, mount a network volume at:

- `/app/data` - SQLite database storage

**RunPod Volume Configuration:**
1. Create a network volume in RunPod dashboard
2. Mount at `/app/data` in Pod settings
3. Database will persist across Pod restarts

## RunPod Pod Setup

### 1. Create Pod

1. Go to RunPod dashboard → Pods
2. Click "Deploy"
3. Select GPU type (or CPU if no GPU workload needed)

### 2. Container Configuration

**Container Image:**
```
your-dockerhub-username/internal-agent-backend:latest
```

**Container Disk:** 10 GB minimum

**Exposed Ports:**
- HTTP: `8000`

### 3. Environment Variables

Click "Add Environment Variable" for each:
- `DATABASE_URL=sqlite:///./data/agent.db`
- `OLLAMA_URL=http://your-ollama-endpoint:11434`
- `SECRET_KEY=your-production-secret-key`

### 4. Volume Mounts (Optional but Recommended)

1. Create network volume: "agent-data" (5 GB minimum)
2. Add volume mount:
   - Volume: `agent-data`
   - Mount Path: `/app/data`

### 5. Deploy

Click "Deploy" and wait for Pod to start (30-60 seconds)

## Post-Deployment Verification

### 1. Get Pod URL

RunPod provides a proxy URL in the Pod details:
```
https://abc123-8000.proxy.runpod.net
```

### 2. Health Check

```bash
curl https://your-pod-url.proxy.runpod.net/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2026-04-27T12:34:56Z"
}
```

### 3. API Endpoints

Test authentication endpoint:
```bash
curl -X POST https://your-pod-url.proxy.runpod.net/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"test@example.com","password":"testpass"}'
```

### 4. Run Smoke Test

From your local machine:
```bash
export RUNPOD_URL=https://your-pod-url.proxy.runpod.net
./scripts/runpod-smoke-test.sh
```

## Monitoring

### Logs

View logs in RunPod dashboard:
1. Click Pod name
2. Go to "Logs" tab
3. Look for startup messages:
   - `✅ All required environment variables are set`
   - `✅ Configuration loaded successfully`
   - `Uvicorn running on http://0.0.0.0:8000`

### Health Check

The container includes automatic health checks (30s intervals):
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3
```

RunPod will show "Healthy" status when checks pass.

## Updating the Deployment

### 1. Build new image
```bash
./scripts/build-docker.sh v1.1.0
```

### 2. Push to registry
```bash
./scripts/push-docker.sh v1.1.0
```

### 3. Update Pod

In RunPod dashboard:
1. Stop Pod
2. Edit configuration
3. Update image tag: `your-username/internal-agent-backend:v1.1.0`
4. Start Pod

## Troubleshooting

### Pod fails to start

**Check logs for:**
- Missing environment variables: `❌ ERROR: Missing required environment variables`
- Database connection errors
- Port binding issues

**Solution:** Verify all required env vars are set in Pod configuration

### Health check failing

**Check:**
```bash
curl https://your-pod-url.proxy.runpod.net/health -v
```

**Common causes:**
- App not listening on 0.0.0.0
- Port mismatch (must be 8000)
- Application startup crash

**Solution:** Review logs for Python exceptions during startup

### Database permission errors

**Symptom:** SQLite errors about read-only database

**Solution:** Ensure `/app/data` has write permissions or is mounted as network volume

### Ollama connection errors

**Symptom:** API calls fail with connection refused

**Solution:** 
- Verify `OLLAMA_URL` is accessible from RunPod network
- If Ollama is local, use RunPod's network volume or deploy Ollama separately
- Consider using remote Ollama endpoint or cloud LLM API

## Security Considerations

1. **Secrets:** Use RunPod's environment variable interface (not visible in logs)
2. **Network:** RunPod provides HTTPS proxy by default
3. **Database:** If using network volume, data persists after Pod deletion
4. **Secret Key:** Generate strong random key for production:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

## Cost Optimization

- **GPU:** Only needed if Ollama runs on same Pod (not recommended for MVP)
- **CPU:** 2-4 vCPU sufficient for API backend
- **RAM:** 4-8 GB recommended
- **Storage:** 10 GB container + 5 GB network volume

**Recommended Pod:** CPU instance (cheaper) with network volume for data persistence

## Next Steps

1. Deploy Ollama separately (RunPod GPU Pod or external service)
2. Set up MCP server (if needed)
3. Configure domain name (optional, via RunPod proxy or custom domain)
4. Set up monitoring/alerting
5. Configure backup strategy for database
