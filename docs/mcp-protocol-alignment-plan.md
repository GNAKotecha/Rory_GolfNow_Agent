# MCP Protocol Alignment Plan

## Overview

This document outlines the plan for aligning the Gateway MCP server with the latest
MCP protocol specification and migration path toward Streamable HTTP transport.

## Current Implementation Status

### Transport Layer
- **Current:** HTTP/JSON-RPC (plain POST, no streaming)
- **Endpoint:** `POST /mcp/tools/*` with JSON request/response
- **Port:** 8090

### Protocol Support
- **MCP Version:** 1.0 (draft)
- **Capabilities:**
  - `tools/list` - List available tools
  - `tools/call` - Execute a tool
  - Basic error responses with error codes

### Missing Capabilities (MVP Scope)
- Session lifecycle management (`initialize`/`shutdown`)
- Capability negotiation
- Resource subscriptions
- Prompt templates
- Logging levels

## MCP Lifecycle Support

### Phase 1: Initialize/Shutdown (Post-MVP)

Add proper MCP session lifecycle:

```python
# New endpoints to add
POST /mcp/initialize
POST /mcp/shutdown
```

**Initialize Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "1.0",
    "capabilities": {
      "tools": {}
    },
    "clientInfo": {
      "name": "agent-client",
      "version": "1.0.0"
    }
  }
}
```

**Initialize Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "1.0",
    "capabilities": {
      "tools": {
        "listChanged": true
      }
    },
    "serverInfo": {
      "name": "gateway-mcp",
      "version": "0.1.0"
    }
  }
}
```

### Phase 2: Capability Negotiation

Support for capability flags:
- `tools.listChanged` - Notify client when tool list changes
- `resources.subscribe` - Allow resource subscriptions (future)
- `prompts.listChanged` - Notify when prompts change (future)

### Implementation Notes

1. **Session State:** Store session state in memory with TTL
2. **Graceful Degradation:** If client doesn't send `initialize`, treat as legacy client
3. **Cleanup:** Background task to expire stale sessions

## Streamable HTTP Migration Path

### Background

MCP is moving toward "Streamable HTTP" as the primary transport, replacing the
current SSE-based approach. Streamable HTTP offers:
- Bidirectional communication
- Better connection handling
- Improved mobile/proxy compatibility

### Timeline

| Phase | Transport | Status |
|-------|-----------|--------|
| MVP | HTTP/SSE | **Current** |
| v1.1 | HTTP/SSE + Streamable HTTP (dual) | Planned |
| v2.0 | Streamable HTTP only | Future |

### Migration Steps

#### Step 1: Add Streamable HTTP Endpoint (v1.1)

Add new endpoint alongside existing SSE:

```python
# Existing (keep for compatibility)
POST /mcp/sse/* → SSE response

# New (Streamable HTTP)
POST /mcp/stream/* → Chunked response
```

#### Step 2: Feature Detection

Clients negotiate transport via Accept header:
```
Accept: text/event-stream       → SSE
Accept: application/octet-stream → Streamable HTTP
Accept: */*                     → Default to SSE
```

#### Step 3: Deprecation (v2.0)

1. Log warning for SSE requests
2. Set deprecation date in response header
3. Eventually remove SSE support

### Streamable HTTP Protocol

**Request Format:**
```http
POST /mcp/stream HTTP/1.1
Content-Type: application/json
Accept: application/octet-stream

{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {...}}
```

**Response Format:**
- Chunked transfer encoding
- Each chunk is a JSON-RPC message
- Final chunk signals completion

### Implementation Considerations

1. **Connection Pooling:** Reuse connections for multiple requests
2. **Backpressure:** Handle slow clients gracefully
3. **Timeouts:** Configurable per-tool timeout with chunked keepalive
4. **Proxy Compatibility:** Test with corporate proxies

## Action Items

### Immediate (MVP+1)

- [ ] Add `initialize` and `shutdown` endpoints
- [ ] Store session state with TTL
- [ ] Add `protocolVersion` to responses
- [ ] Add deprecation warnings for missing `initialize`

### Short-term (v1.1)

- [ ] Implement Streamable HTTP transport
- [ ] Add transport negotiation via Accept header
- [ ] Dual-transport support period
- [ ] Update client SDKs

### Long-term (v2.0)

- [ ] Remove SSE transport
- [ ] Full MCP 2.0 spec compliance
- [ ] Resource subscriptions
- [ ] Prompt templates

## References

- [MCP Specification](https://spec.modelcontextprotocol.io/)
- [MCP Transports](https://spec.modelcontextprotocol.io/specification/2024-11-05/protocol/transports/)
- [Streamable HTTP Draft](https://github.com/modelcontextprotocol/specification/discussions)
