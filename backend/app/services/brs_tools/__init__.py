"""BRS Tool Gateway - Internal service for executing BRS CLI commands.

NOT an MCP server. This is a direct subprocess wrapper with:
- Tool Registry: definitions → CLI templates → output schemas
- Execution Layer: validate → build → run → parse
- Mock Mode: fake CLI responses for dev/test
"""