# Hosted Internal Agent MVP

Lightweight MVP for a hosted internal agent with Open WebUI frontend, custom backend orchestration, and Ollama inference.

## Architecture

- **Frontend**: Open WebUI (chat interface)
- **Backend**: Custom service (orchestration, rules, storage)
- **Runtime**: Ollama on GPU VM
- **Tools**: Remote MCP servers
- **Storage**: PostgreSQL

## Quick Start

1. Copy and configure environment:
   ```bash
   cp infrastructure/.env.example infrastructure/.env
   # Edit infrastructure/.env with your values
   ```

2. Start services:
   ```bash
   cd infrastructure
   docker-compose up -d
   ```

3. Access Open WebUI:
   ```
   http://localhost:3000
   ```

## Documentation

- [Architecture](docs/architecture.md)
- [Runbook](docs/runbook.md)

## Development

Work in small, verified tickets:
1. Implement
2. Test
3. Verify acceptance criteria
4. Summarize changes
5. Stop before next ticket

See [CLAUDE.md](.claude/CLAUDE.md) for build rules.
