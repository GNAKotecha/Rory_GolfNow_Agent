# MVP Architecture

## System Components

### Frontend
- **Open WebUI**: Chat interface
  - User authentication
  - Conversation UI
  - Message streaming

### Backend
- **Custom Service**: Product logic and orchestration
  - User management
  - Conversation storage
  - Tool/rule/prompt enforcement
  - Workflow classification
  - Analytics tracking
  - MCP client integration

### Model Runtime
- **Ollama**: GPU-accelerated inference
  - Hosted on dedicated GPU VM
  - Model management
  - Inference API

### Tools
- **Remote MCP Servers**: Tool execution
  - Company docs access
  - Domain-specific tools
  - Extensible architecture

### Storage
- **PostgreSQL**: Persistent data
  - Users
  - Conversations
  - Workflow analytics
  - Usage metrics

## Data Flow

1. User sends message via Open WebUI
2. Backend receives request
3. Backend enforces rules/prompts
4. Backend calls Ollama for inference
5. Ollama may request tools via backend
6. Backend executes tools via MCP
7. Backend stores conversation
8. Backend classifies workflow
9. Response streams to Open WebUI

## Design Principles

- Small, verified steps
- Minimal viable features
- Extensible architecture
- Clear separation of concerns
- Backend owns orchestration
