# Milestone 11 Runbook

## Overview

This runbook covers operational procedures for Milestone 11: Gateway MCP integration
with CredentialStore, executor routing, and deployment preparation.

## Components

| Component | Port | Purpose |
|-----------|------|---------|
| Backend API | 8000 | Main agent API, chat, OAuth |
| Gateway MCP | 8090 | Tool execution, MCP protocol |
| Ollama | 11434 | LLM inference |
| PostgreSQL | 5432 | Primary database |

## Pre-Deployment Checklist

### Environment Variables

Required:
- [ ] `DATABASE_URL` - PostgreSQL connection string
- [ ] `SECRET_KEY` - JWT signing key (32+ characters)
- [ ] `GATEWAY_CREDENTIAL_ENCRYPTION_KEY` - Fernet encryption key

Optional:
- [ ] `OLLAMA_URL` - Ollama endpoint (default: `http://localhost:11434`)
- [ ] `MCP_GATEWAY_URL` - Gateway endpoint (default: `http://localhost:8090`)
- [ ] `GATEWAY_ENV` - Environment name (local/dev/qa/prod)

### Generate Encryption Key

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Database Migration

```bash
cd backend
alembic upgrade head
```

## Startup Sequence

### Local Development

```bash
# Terminal 1: Start Ollama
ollama serve

# Terminal 2: Start Gateway MCP
cd backend
GATEWAY_ENV=local python -m gateway_mcp.main

# Terminal 3: Start Backend
cd backend
uvicorn app.main:app --reload --port 8000
```

### Docker Compose

```bash
# Development
docker-compose -f docker-compose.runpod.yml up -d

# Production (RunPod)
docker-compose -f docker-compose.runpod-prod.yml up -d
```

## Health Checks

### Backend

```bash
# Liveness
curl http://localhost:8000/health

# Readiness (checks DB, Gateway, Ollama)
curl http://localhost:8000/ready
```

### Gateway

```bash
# Liveness
curl http://localhost:8090/health

# Readiness
curl http://localhost:8090/ready

# Tool list
curl http://localhost:8090/tools
```

## Smoke Tests

### Gateway Smoke Test

```bash
cd backend
python -m gateway_mcp.scripts.smoke_gateway
```

Expected output:
```
Gateway MCP Smoke Tests
Target: http://localhost:8090

-> Checking /health endpoint
[OK] Health check passed: status=healthy, version=0.1.0

-> Checking /ready endpoint
[OK] Readiness check passed: status=ready, env=local

-> Checking /tools endpoint
[OK] Tools list: 9 tools registered
[OK] All 9 MVP tools present

-> Checking MCP tools/list endpoint
[OK] MCP tools/list: 9 tools

Summary: 4/4 checks passed
```

### Onboarding E2E Smoke Test

```bash
cd backend
python scripts/smoke_onboarding_e2e.py
```

## Common Operations

### View Registered Tools

```bash
curl -s http://localhost:8090/tools | jq '.tools[].name'
```

### Test Tool Execution (Mock)

```bash
curl -X POST http://localhost:8090/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "init_database",
      "arguments": {
        "club_id": "TEST001",
        "club_name": "Test Golf Club"
      }
    }
  }'
```

### Check Credential Store Status

```bash
# Via Backend API (requires auth)
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/credentials/status
```

## Troubleshooting

### Gateway Not Starting

**Symptoms:** Gateway fails to start, port 8090 not listening

**Checks:**
```bash
# Check if port is in use
lsof -i :8090

# Check logs
docker logs gateway 2>&1 | tail -50

# Verify config
cat backend/gateway_mcp/configs/local.yaml
```

**Common causes:**
1. Port already in use
2. Invalid YAML config
3. Missing environment variables

### Credential Store Errors

**Symptoms:** `CredentialMissingError` for external tools

**Checks:**
```bash
# Verify encryption key is set
echo $GATEWAY_CREDENTIAL_ENCRYPTION_KEY

# Check database has credentials table
psql $DATABASE_URL -c "\d external_credentials"

# List stored credentials (encrypted)
psql $DATABASE_URL -c "SELECT user_id, provider, credential_type FROM external_credentials"
```

**Resolution:**
1. User must complete OAuth flow at `/api/v1/oauth/{provider}/authorize`
2. Or paste PAT at `/api/v1/credentials/{provider}/pat`

### Tool Execution Timeout

**Symptoms:** Tools return 504 or timeout errors

**Checks:**
```bash
# Check Docker containers
docker ps -a

# Check container resources
docker stats

# View executor logs
docker logs -f teesheet
```

**Resolution:**
1. Increase tool timeout in config
2. Check container has enough resources
3. Verify BRS container is running

### Database Connection Issues

**Symptoms:** `connection refused` or `timeout` errors

**Checks:**
```bash
# Test connection
psql $DATABASE_URL -c "SELECT 1"

# Check if PostgreSQL is running
docker ps | grep postgres

# Verify network connectivity
docker network ls
docker network inspect <network_name>
```

**Resolution:**
1. Start PostgreSQL container
2. Verify `DATABASE_URL` is correct
3. Check network configuration

## Monitoring

### Key Metrics

| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| Gateway latency p99 | Langfuse | > 5s |
| Tool error rate | Langfuse | > 5% |
| Credential refresh failures | Logs | > 0/hour |
| DB connection pool | PostgreSQL | > 80% used |

### Log Locations

| Service | Log Location |
|---------|--------------|
| Backend | `docker logs backend` |
| Gateway | `docker logs gateway` |
| Ollama | `docker logs ollama` |
| Langfuse | `http://localhost:3000` |

### Langfuse Dashboard

Access at: `http://localhost:3000`

Key traces to monitor:
- `gateway.tool.execute` - Tool execution latency
- `gateway.credential.fetch` - Credential fetch latency
- `gateway.mcp.request` - MCP request processing

## Rollback Procedures

### Configuration Rollback

```bash
# Revert to previous config
git checkout HEAD~1 -- backend/gateway_mcp/configs/

# Restart services
docker-compose restart gateway backend
```

### Database Rollback

```bash
# Rollback last migration
cd backend
alembic downgrade -1

# Verify
alembic current
```

### Full Rollback

```bash
# Stop services
docker-compose down

# Checkout previous version
git checkout v0.10.0

# Rebuild and restart
docker-compose build
docker-compose up -d
```

## Security Procedures

### Rotate Encryption Key

**Warning:** This will invalidate all stored credentials.

1. Generate new key:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

2. Update environment variable

3. Clear old credentials:
   ```sql
   TRUNCATE external_credentials;
   ```

4. Notify users to re-authenticate

### Revoke User Credentials

```sql
UPDATE external_credentials 
SET revoked_at = NOW() 
WHERE user_id = <user_id>;
```

### Audit Credential Access

```bash
# Check recent credential fetches (via Langfuse)
curl -H "Authorization: Bearer $LANGFUSE_KEY" \
  "https://langfuse.example.com/api/traces?name=gateway.credential.fetch&limit=100"
```

## Contacts

| Role | Contact |
|------|---------|
| On-call | #internal-agent-oncall |
| Backend Lead | @backend-lead |
| Security | @security-team |
