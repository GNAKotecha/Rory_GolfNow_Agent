# BRS Local Development Setup

This document covers setting up the BRS (Teesheet API) for local development and testing with the Gateway MCP system.

## Overview

The BRS (Business Rules Server) provides teesheet management, booking, and club configuration APIs. For testing Gateway MCP tools (create_club, verify_club_setup, etc.), you need a running BRS instance.

**Port:** 8056 (for API)  
**Database Port:** 5433 (PostgreSQL, to avoid conflicts with main app)  
**Docker Compose:** `infrastructure/docker-compose.brs.yml`

---

## Prerequisites

### System Requirements
- Docker and Docker Compose (v1.29+)
- Bash or similar shell
- ~2GB disk space for BRS database
- ~1GB RAM for BRS container

### Required Environment Variables
```bash
export BRS_DOCKER_IMAGE="ghcr.io/company/brs-api:latest"
export BRS_DB_PASSWORD="brs_dev_password"
export BRS_API_KEY="dev-api-key-12345"
```

Or create a `.env` file in the project root:
```
BRS_DOCKER_IMAGE=ghcr.io/company/brs-api:latest
BRS_DB_PASSWORD=brs_dev_password
BRS_API_KEY=dev-api-key-12345
```

---

## Repository Setup

### 1. Clone BRS Repository

```bash
# Clone the BRS repository (adjust URL to your org)
git clone https://github.com/company/brs-api.git ../brs

# Or if already cloned:
cd ../brs
git fetch origin
git checkout main
```

### 2. Build BRS Docker Image

From the BRS repository root:

```bash
# Build the Docker image
docker build \
  -t ghcr.io/company/brs-api:latest \
  -f Dockerfile \
  .

# Verify the image was created
docker images | grep brs-api
```

**If Dockerfile doesn't exist or needs modifications:**

The BRS Dockerfile should:
1. Use a Python base image (3.10+) matching the BRS requirements
2. Install dependencies from `requirements.txt`
3. Run database migrations on startup
4. Expose port 8056
5. Use `/api/health` as the health check endpoint

**Example Dockerfile (if creating custom):**
```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8056

# Run migrations
RUN python manage.py migrate --noinput

CMD ["python", "manage.py", "runserver", "0.0.0.0:8056"]
```

### 3. Database Initialization

BRS requires initial database setup:

```bash
# Option A: Let docker-compose handle it (recommended)
# The BRS container will run migrations on first startup

# Option B: Manual database setup
docker exec brs_api python manage.py migrate --noinput
docker exec brs_api python manage.py seed_test_data  # If available
```

### 4. Seed Test Data (Optional)

To populate test clubs, members, and tee sheets:

```bash
# Check if BRS has a seed command
docker exec brs_api python manage.py seed_test_data

# Or if using custom scripts
docker exec -it brs_api bash
> python scripts/seed_test_clubs.py
```

**Test Data Expectations:**
- At least one test club (e.g., `testclub1779893558` or `brsgolfclubsales`)
- Test club should have tee sheets configured for upcoming dates
- Test members (optional for initial smoke tests)

---

## Running the BRS Stack

### Start Services

```bash
# From project root
docker-compose -f infrastructure/docker-compose.brs.yml up

# Or in background
docker-compose -f infrastructure/docker-compose.brs.yml up -d

# View logs
docker-compose -f infrastructure/docker-compose.brs.yml logs -f brs_api
```

### Verify BRS is Running

```bash
# Check health endpoint
curl http://localhost:8056/api/health

# Expected response:
# {"status": "ok", "version": "1.0.0"}

# List available endpoints (Swagger)
curl http://localhost:8056/api/documentation/
```

### Stop Services

```bash
docker-compose -f infrastructure/docker-compose.brs.yml down

# Or keep data, just stop containers
docker-compose -f infrastructure/docker-compose.brs.yml stop

# Restart after stopping
docker-compose -f infrastructure/docker-compose.brs.yml start
```

### Reset Database

```bash
# Warning: This deletes all data
docker-compose -f infrastructure/docker-compose.brs.yml down -v

# Then restart to re-initialize
docker-compose -f infrastructure/docker-compose.brs.yml up
```

---

## Environment Configuration

### Local Development (.env file)

Create `.env` in project root:

```bash
# BRS Configuration
BRS_DOCKER_IMAGE=ghcr.io/company/brs-api:latest
BRS_DB_PASSWORD=brs_dev_password
BRS_API_KEY=dev-api-key-12345

# Gateway MCP Configuration (for connecting to BRS)
GATEWAY_URL=http://localhost:8090
GATEWAY_SERVICE_TOKEN=dev-token-123

# Backend Configuration (for connecting to Gateway)
BRS_SERVICE_URL=http://localhost:8056
```

### Docker Network

BRS runs on the `brs_network` bridge network. To connect other containers:

```yaml
# In your docker-compose.yml
services:
  gateway_mcp:
    networks:
      - brs_network

networks:
  brs_network:
    external: true
```

---

## Common Issues & Troubleshooting

### BRS Container Fails to Start

**Error:** `FATAL: role "brs_user" does not exist`

**Solution:**
```bash
# Restart with fresh database
docker-compose -f infrastructure/docker-compose.brs.yml down -v
docker-compose -f infrastructure/docker-compose.brs.yml up
```

**Error:** `Connection refused on port 8056`

**Solution:**
```bash
# Check if BRS container is running
docker ps | grep brs_api

# Check logs for startup errors
docker-compose -f infrastructure/docker-compose.brs.yml logs brs_api

# Verify health check
curl -v http://localhost:8056/api/health
```

### Database Connection Issues

**Error:** `could not connect to server`

**Solution:**
```bash
# Check if postgres container is healthy
docker-compose -f infrastructure/docker-compose.brs.yml ps

# Restart postgres
docker-compose -f infrastructure/docker-compose.brs.yml restart brs_postgres
```

### Port Already in Use

**Error:** `port is already allocated`

**Solution:**
```bash
# Find what's using port 8056
lsof -i :8056

# Either stop that service or use different port in docker-compose.yml
# Change: ports: ["8056:8056"] to ["8057:8056"]
```

### API Key Authentication Failures

**Error:** `401 Unauthorized - Invalid API key`

**Solution:**
```bash
# Verify BRS_API_KEY in .env matches BRS_API_KEY in requests
export BRS_API_KEY="dev-api-key-12345"

# Send with requests:
curl -H "X-API-Key: $BRS_API_KEY" http://localhost:8056/api/v2/clubs
```

### Tee Sheet Not Found

**Error:** `POST /api/v3/clubs/{clubId}/bookings returns 404`

**Solution:**
```bash
# Verify club exists
curl -H "X-API-Key: $BRS_API_KEY" http://localhost:8056/api/v2/clubs

# Create test club manually
curl -X POST http://localhost:8056/api/v3/clubs \
  -H "X-API-Key: $BRS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Club", "country": "IE", "timezone": "UTC"}'

# Check if tee sheet is configured for the club
# See BRS API documentation at http://localhost:8056/api/documentation/
```

---

## BRS API Reference

### Available Endpoints

For full endpoint documentation:
- **Main API Docs:** http://localhost:8056/api/documentation/
- **Admin API Docs:** http://localhost:8056/api/admin/documentation/
- **GolfNow G1 API Docs:** http://localhost:8056/api/g1/documentation/

### Common Operations for Testing

#### Create a Club
```bash
curl -X POST http://localhost:8056/api/v3/clubs \
  -H "X-API-Key: $BRS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Club",
    "country": "IE",
    "timezone": "UTC",
    "contact_email": "admin@test.club"
  }'
```

#### Get Club by Name
```bash
curl http://localhost:8056/api/v2/clubs \
  -H "X-API-Key: $BRS_API_KEY"
```

#### Create Tee Sheet
```bash
curl -X POST http://localhost:8056/api/v3/clubs/{clubId}/teesheets \
  -H "X-API-Key: $BRS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "course_id": 1,
    "date": "2026-06-15",
    "start_time": "08:00",
    "slots_total": 20
  }'
```

#### Create Booking
```bash
curl -X POST http://localhost:8056/api/v3/clubs/{clubId}/bookings \
  -H "X-API-Key: $BRS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "tee_sheet_booking": {
      "course_id": 1,
      "date": "2026-06-15",
      "time": "09:00",
      "holes": 18,
      "reservation_name": "Test Booking",
      "slots": {
        "1": {
          "player": {
            "type": "GUEST",
            "name_on_tee_sheet": "Test Player"
          }
        }
      }
    }
  }'
```

---

## Integration with Gateway MCP

### Testing Gateway Tools Against BRS

Once BRS is running, you can test Gateway MCP tools:

```bash
# Set up environment
export GATEWAY_URL=http://localhost:8090
export GATEWAY_SERVICE_TOKEN=dev-token-123
export BRS_API_URL=http://localhost:8056

# Run smoke tests
cd backend
python -m scripts.smoke_setup_club
python -m scripts.smoke_jira
```

### Verifying Tool Execution

```bash
# Check if Gateway can see BRS tools
curl -X POST http://localhost:8090/mcp/tools/list \
  -H "Authorization: Bearer $GATEWAY_SERVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'

# Should include: create_club, get_club_by_name, verify_club_setup, etc.
```

---

## Performance Tuning

### For High-Load Testing

Adjust BRS container resources in `docker-compose.brs.yml`:

```yaml
services:
  brs_api:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

### Database Optimization

For improved query performance:

```bash
# Connect to database
docker exec -it brs_postgres psql -U brs_user -d brs_dev

# Run maintenance
VACUUM ANALYZE;
CREATE INDEX IF NOT EXISTS idx_clubs_name ON clubs(name);
```

---

## Next Steps

1. Start BRS stack: `docker-compose -f infrastructure/docker-compose.brs.yml up`
2. Verify health: `curl http://localhost:8056/api/health`
3. Run smoke tests: `python backend/scripts/smoke_setup_club.py`
4. Check Gateway integration: `curl http://localhost:8090/mcp/tools/list`
5. Run E2E tests: `pytest backend/gateway_mcp/tests/e2e/test_club_setup_e2e.py -v`

---

## Related Documentation

- **Gateway MCP Overview:** `backend/gateway_mcp/README.md`
- **BRS API Reference:** `../.claude/rules/brs-api-reference.md`
- **Smoke Tests:** `backend/scripts/smoke_setup_club.py`, `backend/scripts/smoke_jira.py`
- **E2E Tests:** `backend/gateway_mcp/tests/e2e/test_club_setup_e2e.py`
