"""
Gateway MCP Core Components

- config: Environment and service configuration
- auth: Service token and user ID validation
- permissions: Risk level vs env/role gating
- scopes: Required scopes vs token scope checking
- approval: Bridge to Phase 3 ApprovalService
- audit: Structured logging + Langfuse integration
- errors: GatewayError hierarchy
- middleware: Request pipeline assembly
"""
