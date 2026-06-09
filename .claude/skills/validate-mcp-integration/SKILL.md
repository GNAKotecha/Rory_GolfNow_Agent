---
name: validate-mcp-integration
version: 1.0.0
type: task
description: Validate MCP server integration in frontend (internal brs-admin + external playwright)
triggers:
  - "validate mcp integration"
  - "test mcp servers"
  - "check mcp connections"
inputs:
  required:
    - mcp_servers: List of MCP servers to validate
  optional:
    - test_tool_calls: Whether to test actual tool execution
workflow:
  1. "Check frontend MCP configuration files"
  2: "Verify MCP server processes are running"
  3: "Test tool discovery via frontend API"
  4: "Execute sample tool call for each server"
  5: "Validate error handling for unavailable servers"
tools:
  - Read (config files)
  - Bash (check processes, test connectivity)
  - mcp__playwright__browser_* (frontend UI testing)
  - Write (validation report)
error_handling:
  1: "Server not running → Start server, retry once"
  2: "Tools not discovered → Check config, restart frontend"
  3: "Tool execution fails → Capture error, document issue"
validation_criteria:
  brs_admin:
    - "Server running on expected path"
    - "Tools discoverable via API"
    - "run_sql tool executable"
    - "call_api tool executable"
  playwright:
    - "Server running and connected"
    - "Browser tools available"
    - "Can navigate and interact"
output_format: |
  === MCP Integration Validation ===
  
  ## brs-admin MCP
  Status: PASS/FAIL
  Tools Found: [count]
  Test Execution: PASS/FAIL
  Issues: [list if any]
  
  ## playwright MCP  
  Status: PASS/FAIL
  Tools Found: [count]
  Test Execution: PASS/FAIL
  Issues: [list if any]
  
  Overall: READY / BLOCKED
---

# Validate MCP Integration

## Purpose
Verify internal and external MCP servers are properly integrated and functional in the frontend application.

## Notes
- Tests both brs-admin (internal) and playwright (external) MCP servers
- Validates tool discovery and execution
- Documents any integration issues for fixing
