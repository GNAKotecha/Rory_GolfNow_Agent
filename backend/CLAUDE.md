# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Setup

### Prerequisites
- Python 3.11
- Docker (optional)

### Environment Setup
```bash
# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Testing

### Running Tests
```bash
# Run all tests
pytest tests/

# Run a specific test file
pytest tests/test_mcp_config.py

# Run a specific test
pytest tests/test_mcp_config.py::test_server_config_creation
```

## Architecture Overview

### Core Components
- **MCP (Multi-Client Protocol) Integration**
  - Centralized tool registry and execution framework
  - Handles discovery, validation, and execution of tools across multiple servers
  - Implements robust error handling and logging

### Key Services
1. **MCP Client (`app/services/mcp_client.py`)**
   - Manages connections to external MCP servers
   - Provides unified interface for tool execution
   - Implements connection pooling, timeouts, and retries

2. **MCP Tool Registry (`app/services/mcp_registry.py`)**
   - Discovers and manages available tools
   - Handles tool execution across different environments
   - Provides role-based tool access control

### Execution Flow
1. Initialize MCP clients for configured servers
2. Discover available tools
3. Validate tool availability and user permissions
4. Execute tools with comprehensive logging and error handling

### Configuration Management
- Environment-specific server configurations
- Role-based access control for tools
- Configurable execution context with step and timeout limits

## Important Notes

### Logging
- Use `logging.getLogger(__name__)` for module-specific loggers
- Include contextual information in log messages
- Log at appropriate levels (INFO, WARNING, ERROR)

### Error Handling
- Centralized error handling in MCP tool execution
- Detailed logging of tool call attempts and results
- Graceful handling of tool discovery and execution failures

### Dependency Management
Key dependencies include:
- FastAPI (Web framework)
- SQLAlchemy (Database ORM)
- Pydantic (Data validation)
- HTTPX (HTTP client)
- Uvicorn (ASGI server)

## Development Workflow

### Docker
```bash
# Build Docker image
docker build -t rory-golfnow-agent .

# Run Docker container
docker run -p 8000:8000 rory-golfnow-agent
```

### Running the Application
```bash
# Start the application
uvicorn app.main:app --reload
```
