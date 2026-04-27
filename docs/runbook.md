# MVP Runbook

## Setup

### Prerequisites
- Docker and Docker Compose
- Access to GPU VM running Ollama
- Access to MCP servers
- PostgreSQL client (optional, for debugging)

### Initial Setup

1. Copy environment file:
   ```bash
   cp infrastructure/.env.example infrastructure/.env
   ```

2. Update `.env` with your values:
   - `OLLAMA_URL`: Your GPU VM endpoint
   - `MCP_SERVER_URL`: Your MCP server endpoint
   - `SECRET_KEY`: Generate secure key

3. Start services:
   ```bash
   cd infrastructure
   docker-compose up -d
   ```

4. Verify services:
   ```bash
   docker-compose ps
   ```

## Development Workflow

### Running locally
```bash
cd infrastructure
docker-compose up
```

### Viewing logs
```bash
docker-compose logs -f backend
docker-compose logs -f openwebui
```

### Database access
```bash
docker-compose exec db psql -U agent_user -d agent_mvp
```

### Restart services
```bash
docker-compose restart backend
```

## Testing

### Backend tests
```bash
cd backend
pytest tests/
```

## Troubleshooting

### Backend can't reach Ollama
- Verify `OLLAMA_URL` in `.env`
- Check GPU VM is running and accessible
- Test: `curl $OLLAMA_URL/api/tags`

### MCP connection fails
- Verify `MCP_SERVER_URL` in `.env`
- Check MCP server is running
- Review backend logs for errors

### Database connection fails
- Check `DATABASE_URL` format
- Verify postgres container is running
- Check postgres logs: `docker-compose logs db`

## Monitoring

### Check service health
- Backend: `http://localhost:8000/health`
- Open WebUI: `http://localhost:3000`
- Database: `docker-compose exec db pg_isready`

### Usage metrics
Query `workflow_analytics` table for usage patterns

## Shutdown

```bash
cd infrastructure
docker-compose down
```

To remove volumes:
```bash
docker-compose down -v
```
