# Gateway MCP Server Startup Guide

**Status:** READY FOR QA  
**Port:** 8090  
**Environment:** Local development or Docker production  
**Date:** 2026-06-04

---

## Overview

The Gateway MCP (Model Context Protocol) server runs on **port 8090** and provides:
- Business-level MCP tools with unified policy, authentication, and audit
- Tool abstraction layer for BRS (teesheet) and Atlassian tools (Jira, GitHub)
- Executor routing to Docker, Kubernetes, or mock backends
- Credential management and OAuth flow handling

**Location:** `/backend/gateway_mcp/main.py`

---

## Quick Start (Local Development)

### Prerequisites

```bash
# Ensure Python 3.11+ is installed
python3 --version

# Ensure venv is activated
source /Users/206887576@bwt3.com/Documents/GitHub/Rory_GolfNow_Agent/backend/venv/bin/activate

# Ensure all dependencies are installed
pip install -r requirements.txt
```

### Start Gateway MCP on Port 8090

**Option 1: Direct Python Command**

```bash
cd /Users/206887576@bwt3.com/Documents/GitHub/Rory_GolfNow_Agent/backend
python -m gateway_mcp.main
```

Expected output:
```
Gateway MCP starting: env=local, executor=mock, port=8090
Registered 9 tools
INFO:     Uvicorn running on http://0.0.0.0:8090
```

**Option 2: With Custom Port**

```bash
export GATEWAY_PORT=8090
export GATEWAY_HOST=0.0.0.0
export GATEWAY_ENV=local
python -m gateway_mcp.main
```

**Option 3: With Environment Variables Set**

```bash
GATEWAY_PORT=8090 \
GATEWAY_HOST=0.0.0.0 \
GATEWAY_ENV=local \
GATEWAY_CREDENTIAL_ENCRYPTION_KEY="test-key-32-chars-minimum-1234567" \
GATEWAY_SERVICE_TOKEN="test-service-token" \
python -m gateway_mcp.main
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GATEWAY_PORT` | 8090 | Port to listen on |
| `GATEWAY_HOST` | 0.0.0.0 | Host to bind to |
| `GATEWAY_ENV` | local | Environment: local, dev, prod |
| `GATEWAY_CREDENTIAL_ENCRYPTION_KEY` | (required) | 32-char encryption key for credentials |
| `GATEWAY_SERVICE_TOKEN` | (optional) | Service-to-service auth token |
| `DATABASE_URL` | (optional) | PostgreSQL connection string |
| `EXECUTOR_BACKEND` | mock | Backend: mock, docker_exec, k8s_exec, job_runner |

### Default Configuration

For **local development**, the Gateway MCP runs with:
- Executor: `mock` (no actual Docker/K8s execution)
- Port: 8090
- Host: 0.0.0.0 (accessible on localhost:8090)
- All 9 MVP tools registered and available

---

## Startup Script

Create `/Users/206887576@bwt3.com/Documents/GitHub/Rory_GolfNow_Agent/backend/start-gateway-mcp.sh`:

```bash
#!/bin/bash
set -e

echo "🚀 Starting Gateway MCP Server..."
echo "================================================"

# Ensure venv is activated
VENV_PATH="/Users/206887576@bwt3.com/Documents/GitHub/Rory_GolfNow_Agent/backend/venv"
if [ ! -d "$VENV_PATH" ]; then
  echo "❌ ERROR: Virtual environment not found at $VENV_PATH"
  exit 1
fi

source "$VENV_PATH/bin/activate"

# Set defaults if not provided
export GATEWAY_PORT=${GATEWAY_PORT:-8090}
export GATEWAY_HOST=${GATEWAY_HOST:-0.0.0.0}
export GATEWAY_ENV=${GATEWAY_ENV:-local}
export GATEWAY_CREDENTIAL_ENCRYPTION_KEY=${GATEWAY_CREDENTIAL_ENCRYPTION_KEY:-"test-key-32-chars-minimum-1234567"}
export GATEWAY_SERVICE_TOKEN=${GATEWAY_SERVICE_TOKEN:-"test-service-token"}

echo "✅ Configuration:"
echo "   Port: $GATEWAY_PORT"
echo "   Host: $GATEWAY_HOST"
echo "   Environment: $GATEWAY_ENV"
echo "   Executor Backend: ${EXECUTOR_BACKEND:-mock}"
echo ""

# Start the server
cd /Users/206887576@bwt3.com/Documents/GitHub/Rory_GolfNow_Agent/backend
python -m gateway_mcp.main
```

Make it executable:
```bash
chmod +x /Users/206887576@bwt3.com/Documents/GitHub/Rory_GolfNow_Agent/backend/start-gateway-mcp.sh
```

Run it:
```bash
/Users/206887576@bwt3.com/Documents/GitHub/Rory_GolfNow_Agent/backend/start-gateway-mcp.sh
```

---

## Docker Deployment

### Using docker-compose (Production)

```bash
cd /Users/206887576@bwt3.com/Documents/GitHub/Rory_GolfNow_Agent/backend

# Start all services (Ollama, Gateway, Backend)
docker-compose -f docker-compose.runpod-prod.yml up -d

# Check Gateway MCP is running
docker logs gateway
```

### Environment Variables for Docker

Required environment variables in `.env` or docker-compose:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/golfnow_agent
GATEWAY_CREDENTIAL_ENCRYPTION_KEY=your-32-character-encryption-key-here
GATEWAY_SERVICE_TOKEN=your-service-token-here
SECRET_KEY=your-secret-key-here
```

### Docker Compose Service

From `docker-compose.runpod-prod.yml`:

```yaml
gateway:
  image: gnakotecha/internal-agent-gateway:latest
  build:
    context: .
    dockerfile: Dockerfile.gateway
  container_name: gateway
  environment:
    - GATEWAY_ENV=prod
    - GATEWAY_PORT=8090
    - GATEWAY_HOST=0.0.0.0
    - GATEWAY_CREDENTIAL_ENCRYPTION_KEY=${GATEWAY_CREDENTIAL_ENCRYPTION_KEY}
    - GATEWAY_SERVICE_TOKEN=${GATEWAY_SERVICE_TOKEN}
    - DATABASE_URL=${DATABASE_URL}
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock:ro
  depends_on:
    ollama:
      condition: service_healthy
  restart: unless-stopped
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8090/health"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 30s
```

---

## Verification

### Health Check Endpoint

Verify the server is running:

```bash
curl http://localhost:8090/health
```

Expected response:
```json
{
  "status": "healthy",
  "version": "0.1.0"
}
```

### Readiness Probe

Check if all dependencies are available:

```bash
curl http://localhost:8090/ready
```

Expected response (local dev):
```json
{
  "status": "ready",
  "config": true,
  "env": "local",
  "executor_backend": "mock",
  "executor_available": true
}
```

### List Available Tools

```bash
curl http://localhost:8090/tools
```

Expected response:
```json
{
  "tools": [
    {
      "name": "create_booking",
      "description": "Create a tee time booking on BRS",
      "risk_level": "high",
      "requires_approval": true,
      "allowed_environments": ["qa", "prod"]
    },
    ...
  ],
  "count": 9
}
```

---

## Troubleshooting

### Port Already in Use

If port 8090 is already in use:

```bash
# Find what's using it
lsof -i :8090

# Kill the process (if needed)
kill -9 <PID>

# Or use a different port
export GATEWAY_PORT=8091
python -m gateway_mcp.main
```

### Module Import Error

Ensure the backend is in Python path:

```bash
cd /Users/206887576@bwt3.com/Documents/GitHub/Rory_GolfNow_Agent/backend
export PYTHONPATH="${PWD}:${PYTHONPATH}"
python -m gateway_mcp.main
```

### Encryption Key Missing

```bash
export GATEWAY_CREDENTIAL_ENCRYPTION_KEY="your-32-character-minimum-key-12345"
python -m gateway_mcp.main
```

### Docker Socket Not Available (for docker_exec backend)

If running with `EXECUTOR_BACKEND=docker_exec`:

```bash
# Ensure Docker socket is available
ls -la /var/run/docker.sock

# If using Docker Desktop on Mac, you may need to mount the socket
docker run -v /var/run/docker.sock:/var/run/docker.sock ...
```

---

## QA Testing Checklist

- [ ] Gateway MCP starts on port 8090 without errors
- [ ] Health endpoint returns 200 with healthy status
- [ ] Ready endpoint returns 200 with ready status
- [ ] Tools endpoint lists all 9 MVP tools
- [ ] Backend can connect to Gateway on http://gateway:8090 (Docker) or http://localhost:8090 (local)
- [ ] MCP transport routes are accessible
- [ ] Middleware pipeline is functional
- [ ] Executor routing works for BRS vs external tools

---

## Architecture

```
┌─────────────────────────────────────────┐
│     FastAPI Application (Port 8090)     │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │   MCP Transport Routes          │   │
│  │   (/mcp/initialize, /mcp/...)   │   │
│  └──────────────┬──────────────────┘   │
│                 │                       │
│  ┌──────────────▼──────────────────┐   │
│  │   Middleware Pipeline           │   │
│  │  - Auth & Credential validation │   │
│  │  - Policy enforcement           │   │
│  │  - Audit logging                │   │
│  └──────────────┬──────────────────┘   │
│                 │                       │
│  ┌──────────────▼──────────────────┐   │
│  │   Executor Router               │   │
│  │  - BRS tools → docker_exec      │   │
│  │  - External tools → MCP proxy   │   │
│  └─────────────────────────────────┘   │
│                                         │
└─────────────────────────────────────────┘
        ↓              ↓              ↓
   [Docker]      [BRS API]    [Upstream MCPs]
  containers    (localhost)   (Jira, GitHub)
```

---

## Integration with Backend

The Backend service connects to Gateway MCP via environment variable:

```env
MCP_GATEWAY_URL=http://localhost:8090  # Local dev
MCP_GATEWAY_URL=http://gateway:8090    # Docker Compose
```

The Backend's `mcp_client.py` calls Gateway MCP endpoints for tool execution.

---

## Next Steps for QA

1. Start Gateway MCP: `python -m gateway_mcp.main`
2. Verify health: `curl http://localhost:8090/health`
3. List tools: `curl http://localhost:8090/tools`
4. Test MCP initialization: `curl -X POST http://localhost:8090/mcp/initialize`
5. Test tool calls via Backend API: `POST /api/workflows/{workflow_id}/step`

---

## Version

- **Gateway MCP Version:** 0.1.0
- **Last Updated:** 2026-06-04
- **Python:** 3.11+
- **FastAPI/Uvicorn:** Latest from requirements.txt
