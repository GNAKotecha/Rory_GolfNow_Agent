# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Architecture

### Core Components
- **Agentic Workflow Engine**: Orchestrates AI-driven task execution
- **Tool Calling System**: Dynamic tool selection and execution
- **Security Validation Layer**: Enforces strict execution constraints
- **Stateful Agent Management**: Tracks workflow progress and state

### Key Services
- `AgenticService`: Workflow orchestration
- `AgentState`: Execution state tracking
- `AgentMemory`: Persistent memory management
- `WorkflowClassifier`: Workflow type detection

## Development Workflow

### Prerequisites
- Python 3.10+
- Docker
- PostgreSQL
- Ollama

### Test Execution

#### Running Tests
```bash
# Run entire test suite
pytest tests/

# Run specific test file
pytest tests/test_agent_state.py

# Run tests with verbose output
pytest -v tests/test_agent_state.py
```

#### Specific Test Categories
```bash
# Run workflow integration tests
pytest tests/test_workflow_integration.py

# Run MCP client tests
pytest tests/test_mcp_client.py
```

### Core Development Commands

#### Local Server
```bash
# Start development server
uvicorn app.main:app --reload
```

#### Docker Deployment
```bash
# Build docker image
docker-compose -f docker-compose.runpod.yml build

# Start services
docker-compose -f docker-compose.runpod.yml up
```

## Security Highlights

### Bash Execution Safety
- Command execution restricted via strict allowlist
- Blocks dangerous interpreters and network tools
- Implements resource limits
- Validates command arguments

### Connection Management
- Persistent connection pooling
- Configurable timeout and retry mechanisms
- Atomic file operations

## Performance Considerations

- Efficient connection reuse
- Configurable resource limits
- Optimized agent state tracking

## Debugging

### Logging Strategy
- Comprehensive logging in services
- Captures workflow steps and tool executions
- Tracks detailed execution metadata

## Critical Security Fixes

### Implemented Protections
- Prevent TOCTOU race conditions
- Block potential bash script injection
- Manage OllamaClient resource leaks
- Implement WebSocket session validation

## Contribution Guidelines

### Pull Request Process
1. Create feature branch
2. Implement changes
3. Add/update corresponding tests
4. Ensure all tests pass
5. Submit pull request with detailed description
