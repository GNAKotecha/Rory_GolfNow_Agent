# Playwright MCP Server - Production Suitability Assessment

**Date**: 2026-06-05  
**Subject**: Evaluating usefulness of the Playwright MCP server created for Rory Agent  
**Conclusion**: ❌ **Not suitable for production deployment** - ✅ **Good for local development**

---

## Quick Answer

**You're absolutely right.** The Playwright MCP server I built uses stdio (stdin/stdout), which only works locally in Claude Code. For Rory (a deployed web service), this won't work because:

- ❌ Rory's backend is a FastAPI service, not a CLI
- ❌ No stdio pipes between Rory and subprocess MCP servers
- ❌ Deployed services can't spawn local processes
- ❌ Won't work in containerized/cloud environments

---

## Architecture Overview

### How Rory Currently Works

```
Frontend                Backend               MCP Servers
(Next.js)           (FastAPI)               
   |                   |                         |
   |<-- HTTP/WS ------>|                         |
   |   websocket       |                         |
   |   messages        |                         |
   |                   |-- HTTP/aiohttp -->|     |
   |                   |   (via gateway)   |  Gateway
   |                   |   via aiohttp     |  MCP Server
   |                   |                   |
   |                   |<--- Response ------|
   |                   |
   |<-- Chat response-|
```

**Key**: Rory uses **HTTP/aiohttp** to talk to MCP servers (via gateway)

### How stdio MCP Works (What I Built)

```
Claude Code CLI              Playwright MCP Server
       |                            |
       |-- write to stdin -------->|
       |                           |
       |-- read from stdout <------|
       |                            |
       (works great locally)        (stdio connection)
```

**Problem**: This only works in local CLI environments

---

## Comparison: Local vs Production

| Aspect | Local Development | Production Deployment |
|--------|-------------------|----------------------|
| How to run | `node /path/to/index.js` | Docker container in cloud |
| Communication | stdio (CLI process) | HTTP/network services |
| State management | Process lives in CLI | Need persistent service |
| Scaling | Not needed | Horizontal scaling required |
| Failure recovery | Just restart CLI | Need health checks, restart policy |

---

## What Rory Actually Needs

Rory's MCP system (from Phase 4 handover):

✅ **Already Implemented**:
- Gateway MCP Server (aggregates tools via HTTP)
- MCPClient (async HTTP client using aiohttp)
- MCPRegistry (discovers tools from servers)
- MCPToolRegistry (manages tool execution)
- Health checker (verifies server connectivity)
- Credential encryption (manages auth)

✅ **How It Works**:
1. Backend registers MCP servers in database
2. When agent needs a tool, queries MCPRegistry
3. Registry contacts MCP server via HTTP
4. Gateway translates tool calls to MCP protocol
5. Results returned to agent

**Pattern**: All communication is HTTP-based, suitable for deployed services

---

## So... Is Playwright Useful for Rory?

### ❌ As-Is (Stdio MCP): NOT USEFUL FOR RORY

The stdio-based server cannot be used in Rory's deployed architecture.

### ✅ WITH CONVERSION: COULD BE USEFUL

**If you wanted Playwright for Rory, you'd need to:**

1. **Option A: Convert to HTTP Gateway**
   - Keep Playwright logic
   - Expose as REST API instead of stdio
   - Deploy as separate service
   - Register in Rory's gateway
   - **Effort**: 2-3 hours (rebuild as FastAPI/Express server)

2. **Option B: Built-in Python Tool**
   - Port Playwright logic to Python (playwright-python package exists)
   - Implement as `Tool` class in Rory backend
   - Direct integration, no external process
   - **Effort**: 1-2 hours (simpler)

3. **Option C: Use Third-Party Service**
   - Playwright Cloud / Browserless.io / similar service
   - Already HTTP-based
   - Just register endpoint in Rory
   - **Effort**: 30 minutes (just configuration)

---

## Is Playwright Actually Needed for Rory?

### What Would Playwright Let Rory Do?

✅ Take screenshots of websites  
✅ Navigate web pages  
✅ Extract page content  
✅ Click buttons / interact with pages  
✅ Fill forms  
✅ Retrieve page text/HTML  

### Does Rory Need This?

**Current Focus**: Golf club booking agent  
- ✅ Query golf clubs ✅ Check tee times  
- ✅ Make bookings  
- ✅ Query booking status  
- ✅ Cancel bookings  

**For golf agent**: Probably NOT needed (APIs available for BRS)

**Future Use Cases**:
- Web scraping golf clubs (if no API)
- Testing golf booking UI
- Capturing screenshots for reports
- General web automation tasks

**Verdict**: Not immediately needed, but could be useful later

---

## What IS Useful from What I Built

### ✅ Useful for Local Development

The Playwright MCP server is **great for**:

1. **Your local Claude Code workflow** ✅
   - You can use it right now to test browser automation
   - Take screenshots of web pages while working
   - Automate testing locally

2. **The Skill I Created** ✅
   - `/.claude/skills/playwright-screenshot-upload.md`
   - You can invoke it in Claude Code sessions
   - Useful for documenting bugs, testing UIs, etc.

3. **Learning MCP Development** ✅
   - Good reference for building stdio MCP servers
   - Understanding MCP protocol
   - How to structure tool definitions

### ❌ Not Useful for Rory Agent

- Cannot be deployed with Rory
- Won't work in production
- Requires local environment

---

## Recommendations

### Short Term
**Do Nothing**: Rory doesn't need Playwright currently

### If You Want Playwright for Rory Later

**Option 1 (Recommended)**: Use Playwright Cloud
```
1. Sign up for Playwright Cloud / Browserless.io
2. Get API endpoint
3. Create Python tool in Rory backend
4. Register as MCP tool
5. Rory can use it immediately
Effort: 1 hour
```

**Option 2**: Build HTTP Gateway
```
1. Keep my Playwright server
2. Add HTTP endpoints instead of stdio
3. Deploy as separate service (Docker)
4. Register endpoint in Rory
5. Works like other MCP servers
Effort: 3 hours
```

**Option 3**: Native Python Implementation
```
1. Use playwright-python package
2. Create Python tool class
3. Integrate into Rory backend directly
4. No external process needed
Effort: 2 hours
```

### Keep the Skill
The `playwright-screenshot-upload.md` skill is useful for YOU (local work), so keep it.

---

## Clean-up Options

### Option A: Keep Everything
- Playwright MCP server stays in `/mcp_servers/`
- Skill stays in `/.claude/skills/`
- Future-proof if you want to add it later

### Option B: Remove Playwright MCP
- Delete `/Documents/GitHub/mcp_servers/playwright_mcp_server/`
- Delete from settings.json
- Keep the skill (it's useful locally)
- You can rebuild it quickly if needed

### Option C: Document It
- Move to `/docs/examples/mcp-servers/` 
- Keep as reference for future MCP development
- Not loaded in settings.json

**Recommendation**: Option A or C (keep it, won't hurt)

---

## What Should Be Done Instead

For **capturing UI state in Rory**, consider:

✅ **Built-in solutions**:
- Use browser API to send screenshot data back to frontend
- Frontend can capture screenshots without agent
- Store in database for analysis

✅ **For testing**:
- Use existing end-to-end test framework
- Playwright can test Rory UI directly (not as MCP tool)
- Better for CI/CD integration

✅ **For documentation**:
- Frontend can generate screenshots
- Rory backend can log state as JSON
- More useful than actual screenshots

---

## Summary

| Item | Status | Keep? | Notes |
|------|--------|-------|-------|
| Playwright MCP Server | ❌ Not for Rory | A/C | Useful for reference, not production |
| Screenshot Skill | ✅ Useful | YES | Great for your local workflows |
| MCP Gateway Pattern | ✅ Reference | YES | Good example of proper architecture |
| Configuration | ✅ Works | KEEP | Won't hurt, easy to remove later |

---

## Conclusion

You were **absolutely correct** in your assessment:

- ❌ stdio MCP won't work for deployed agents
- ✅ HTTP/network-based MCP is what Rory needs
- ✅ Rory's existing gateway pattern is correct
- ✅ Playwright MCP was good learning, not for production

**Action**: No changes needed. Keep for local use, don't try to deploy with Rory.

If you ever need web automation in Rory, convert to HTTP gateway or use existing services instead.

---

**Lesson Learned**: MCP development should target the deployment model from the start:
- Local CLI tools → stdio MCP ✅
- Deployed services → HTTP/network MCP ✅

Great catch on this distinction!
