# RunPod Deployment Profile

## Overview

This document describes the deployment topology for the Internal Agent on RunPod,
with private pod networking for backend↔gateway communication and only the backend
exposed to external clients.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         RunPod Pod                              │
│                                                                 │
│   ┌─────────────┐    Private    ┌─────────────┐                │
│   │   Backend   │◄────────────►│   Gateway   │                │
│   │    :8000    │    :8090      │   MCP       │                │
│   │  (public)   │               │  (private)  │                │
│   └─────────────┘               └─────────────┘                │
│         │                              │                        │
│         │                              │                        │
│   ┌─────▼──────┐               ┌──────▼──────┐                 │
│   │   Ollama   │               │  Upstream   │                 │
│   │   :11434   │               │  MCP Servers│                 │
│   │ (private)  │               │  (external) │                 │
│   └────────────┘               └─────────────┘                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
         │
         │ HTTPS Proxy
         ▼
   External Clients
   (Open WebUI, API)
```

## Network Configuration

### Exposed Ports

| Service | Port | Exposure | Purpose |
|---------|------|----------|---------|
| Backend | 8000 | **Public** (HTTPS proxy) | Agent API, chat, OAuth |
| Gateway | 8090 | Private (localhost only) | MCP tool execution |
| Ollama | 11434 | Private (localhost only) | LLM inference |

### Port Mapping in RunPod

When creating the pod, only expose port 8000:

```
Exposed HTTP Ports: 8000
```

RunPod will provide an HTTPS proxy URL:
```
https://<pod-id>-8000.proxy.runpod.net
```

### Internal Communication

Services communicate via localhost within the pod:

- Backend → Gateway: `http://localhost:8090`
- Backend → Ollama: `http://localhost:11434`
- Gateway → Upstream MCP: External (HTTPS)

## Docker Compose Configuration

### Production Profile (`docker-compose.runpod-prod.yml`)

```yaml
version: '3.8'

services:
  # Ollama - GPU inference, internal only
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    # NO ports exposed - internal only
    volumes:
      - ollama_data:/root/.ollama
    restart: unless-stopped
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]
      interval: 30s
      timeout: 10s
      retries: 3

  # Gateway MCP - internal only
  gateway:
    image: gnakotecha/internal-agent-gateway:latest
    container_name: gateway
    # NO ports exposed externally - internal only
    environment:
      - GATEWAY_ENV=prod
      - GATEWAY_PORT=8090
      - GATEWAY_CREDENTIAL_ENCRYPTION_KEY=${GATEWAY_CREDENTIAL_ENCRYPTION_KEY}
      - DATABASE_URL=${DATABASE_URL}
    volumes:
      # Docker socket mount required for docker_exec backend
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

  # Backend - public facing
  backend:
    image: gnakotecha/internal-agent-backend:latest
    container_name: backend
    ports:
      - "8000:8000"  # ONLY public port
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - OLLAMA_URL=http://ollama:11434
      - MCP_GATEWAY_URL=http://gateway:8090
      - SECRET_KEY=${SECRET_KEY}
    depends_on:
      gateway:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  ollama_data:

networks:
  default:
    driver: bridge
```

## Timeout-Safe Execution Path

### Problem

Long-running tool executions can timeout when:
1. Client request times out (60s default)
2. RunPod proxy times out
3. Database locks held too long

### Solution: Async Execution Queue

For operations expected to exceed 30 seconds:

1. **Submit job** → Returns job ID immediately
2. **Poll status** → Check `/jobs/{id}/status`
3. **Get result** → Fetch result when complete

### Implementation

```python
# Backend submits to Gateway with async flag
response = await gateway.call_tool(
    tool="run_migration",
    params={"club_id": 12345},
    async_mode=True,  # Don't wait for completion
)

# Gateway returns job ID
# {"job_id": "abc123", "status": "queued"}

# Backend polls for completion
while True:
    status = await gateway.get_job_status("abc123")
    if status["completed"]:
        result = status["result"]
        break
    await asyncio.sleep(5)
```

### Timeout Configuration

| Layer | Default | Max | Notes |
|-------|---------|-----|-------|
| Client HTTP | 60s | 300s | Configurable per-request |
| RunPod Proxy | 300s | 300s | Fixed by RunPod |
| Gateway Tool | 60s | 600s | Per-tool configurable |
| DB Lock | 30s | 60s | Advisory lock timeout |

## Environment Variables

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection | `postgresql://user:pass@host/db` |
| `SECRET_KEY` | JWT signing secret | `<32+ char secret>` |
| `GATEWAY_CREDENTIAL_ENCRYPTION_KEY` | Fernet key for credential encryption | `<base64 key>` |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `OLLAMA_URL` | Ollama endpoint | `http://ollama:11434` |
| `MCP_GATEWAY_URL` | Gateway endpoint | `http://gateway:8090` |
| `BACKEND_PORT` | Backend port | `8000` |
| `GATEWAY_PORT` | Gateway port | `8090` |
| `GATEWAY_ENV` | Environment name | `prod` |

### Generating Encryption Key

```bash
# Generate Fernet-compatible key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Volume Mounts

### Persistent Data

| Path | Purpose | Size |
|------|---------|------|
| `/app/data` | SQLite fallback, logs | 5 GB |
| `/root/.ollama` | Model weights | 50+ GB |

### Network Volume Setup

1. Create network volume in RunPod dashboard
2. Mount at `/app/data` and `/root/.ollama`
3. Models persist across pod restarts

## Health Checks

### Liveness vs Readiness

| Endpoint | Purpose | Failure Response |
|----------|---------|------------------|
| `/health` | Process alive | Restart container |
| `/ready` | Dependencies ready | Remove from LB |

### Cascading Health Checks

Backend `/ready` checks:
1. Database connection
2. Gateway `/health` reachable
3. Ollama `/health` reachable

If Gateway is unhealthy, Backend reports not ready.

## Deployment Steps

### 1. Build Images

```bash
# Build and push images
./scripts/build-docker.sh latest
./scripts/push-docker.sh latest docker.io
```

### 2. Create Pod

1. Go to RunPod dashboard → Pods
2. Select GPU type (RTX 4090 recommended)
3. Container image: `gnakotecha/internal-agent-backend:latest`
4. Volume: Create 50 GB network volume
5. Exposed ports: `8000` only

### 3. Configure Environment

Add environment variables in RunPod pod settings:
- `DATABASE_URL`
- `SECRET_KEY`
- `GATEWAY_CREDENTIAL_ENCRYPTION_KEY`

### 4. Deploy

Click Deploy and monitor logs for startup completion.

### 5. Verify

```bash
# Check backend health
curl https://<pod-id>-8000.proxy.runpod.net/health

# Check readiness (includes gateway)
curl https://<pod-id>-8000.proxy.runpod.net/ready
```

## Security Considerations

### Network Isolation

- Gateway and Ollama are NOT accessible from internet
- Only Backend API is public
- All internal traffic stays within pod

### Docker Socket Access

- Gateway container mounts `/var/run/docker.sock` (read-only)
- Required for `docker_exec` backend to run commands in sibling containers
- Gateway image includes Docker CLI (installed from official Docker repo)
- Socket is mounted read-only to limit exposure
- Only gateway has socket access; backend does not

### Credentials

- OAuth tokens encrypted at rest (Fernet)
- Encryption key in environment variable
- Never logged or exposed in error messages

### Rate Limiting

- Backend implements rate limiting
- Gateway trusts only local Backend
- No external access to Gateway

## Troubleshooting

### Gateway Unreachable

```bash
# Check gateway is running
docker logs gateway

# Test internal connectivity
docker exec backend curl http://gateway:8090/health
```

### Ollama OOM

```bash
# Check GPU memory
nvidia-smi

# Reduce model size or batch size
docker exec ollama ollama run <smaller-model>
```

### Database Connection Issues

```bash
# Verify DATABASE_URL
docker exec backend env | grep DATABASE

# Test connection
docker exec backend python -c "from app.db.session import check_db_connection; print(check_db_connection())"
```
