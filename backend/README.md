# GolfNow Agent Backend

Custom backend service for workflow orchestration, observability, and BRS tool integration.

## Architecture

- **Framework**: FastAPI (async Python)
- **Database**: PostgreSQL (SQLAlchemy ORM, Alembic migrations)
- **LLM Runtime**: Ollama (via custom client wrapper)
- **Observability**: Self-hosted Langfuse
- **Structured Outputs**: Instructor (Pydantic validation)
- **Tools**: BRS Tool Gateway (subprocess execution)

## Quick Start

1. **Setup environment**:
```bash
cd backend
cp .env.example .env
# Edit .env with your values
```

2. **Install dependencies**:
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

3. **Run migrations**:
```bash
alembic upgrade head
```

4. **Start backend**:
```bash
uvicorn app.main:app --reload
```

5. **Start Langfuse (optional)**:
```bash
docker-compose -f docker-compose.langfuse.yml up -d
```

## Development Phases

### Phase 1: Workflow Engine Foundation ✅

**Completed**: 2026-04-29

- ✅ Database schema (workflows, runs, sessions)
- ✅ SQLAlchemy models + Alembic migrations
- ✅ WorkflowOrchestrator service
- ✅ Ollama client wrapper
- ✅ 39 tests passing

**See**: `docs/phase-1-complete.md`

### Phase 2: BRS Tools + Core Observability ✅

**Completed**: 2026-05-01

- ✅ Self-hosted Langfuse for workflow tracing
- ✅ Instructor for structured LLM outputs
- ✅ BRS Tool Gateway (registry → executor → parser)
- ✅ Mock mode for development/testing
- ✅ 3 BRS tools registered (init, superuser, validate)

**See**: `docs/phase-2-complete.md`

## Project Structure

```
backend/
├── app/
│   ├── api/          # FastAPI routes
│   ├── core/         # Config, clients (Ollama, Instructor, Langfuse)
│   ├── models/       # SQLAlchemy models
│   ├── schemas/      # Pydantic schemas
│   └── services/     # Business logic (orchestrator, BRS tools)
├── tests/
│   ├── unit/         # Unit tests
│   └── integration/  # Integration tests
├── alembic/          # Database migrations
└── docs/             # Phase completion docs
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test suite
pytest tests/unit/services/brs_tools/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html
```

## Environment Variables

**Core**:
- `DATABASE_URL` - PostgreSQL connection string
- `OLLAMA_URL` - Ollama API endpoint
- `OLLAMA_MODEL` - Default model name

**Langfuse** (optional):
- `LANGFUSE_ENABLED` - Enable tracing (true/false)
- `LANGFUSE_HOST` - Langfuse server URL
- `LANGFUSE_PUBLIC_KEY` - Project public key
- `LANGFUSE_SECRET_KEY` - Project secret key

**BRS Tools** (optional):
- `BRS_TEESHEET_PATH` - Path to the teesheet repository/resources used by the BRS executor
- `BRS_CONFIG_PATH` - Path to the BRS configuration file or directory
- `BRS_TOOL_TIMEOUT_MULTIPLIER` - Multiplier applied to BRS tool execution timeouts
- `BRS_TOOLS_MOCK_MODE` - Enable mock mode globally (true/false)

## Next Phase

**Phase 3: Onboarding Workflow + Testing + Analytics**
- Build complete teesheet onboarding workflow template
- Add DeepEval for workflow quality testing
- Create analytics dashboard on Langfuse traces
- Add prompt versioning and A/B testing

See: `docs/superpowers/plans/` for implementation plans
