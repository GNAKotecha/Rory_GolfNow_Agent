# Skill-to-Tool Architecture Report

## Problem Statement

The Gateway MCP shows 23 static tools but skills stored in `tenant_skills` table (like `REINSTATE_USER`) are **not exposed as callable MCP tools**. Skills exist only as prompt context, not as executable tools.

## Current Architecture

### 1. **Gateway MCP Tool Registration (Static)**

**Location**: `backend/gateway_mcp/tools/__init__.py`

**Mechanism**: Tools are **hardcoded** and registered at startup via `create_full_registry()`:

```python
def create_full_registry() -> ToolRegistry:
    """Create registry with all Gateway tools (18 static tools)"""
    registry = create_brs_registry()
    registry.register_all(MEMORY_TOOLS)     # 4 tools
    registry.register_all(TEESHEET_TOOLS)   # 4 tools
    registry.register_all(JIRA_TOOLS)       # 3 tools
    return registry
```

**Static Tool Collections**:
- `CLUB_TOOLS`: create_club, get_club_by_name, verify_club_setup
- `CONFIG_TOOLS`: get_club_config
- `USER_TOOLS`: create_admin_user, authenticate_club
- `API_TOOLS`: call_internal_api
- `MEMORY_TOOLS`: get_working_memory, update_working_memory, store_session_summary, get_historical_context
- `TEESHEET_TOOLS`: list_routes, call_api, run_sql, get_config
- `JIRA_TOOLS`: create_ticket, get_ticket_status, add_comment

**Key Finding**: No database query or dynamic tool loading in `create_full_registry()`.

### 2. **Backend Skill Loading (Prompt-Only)**

**Location**: `backend/app/services/agentic_service.py`

**Mechanism**: Skills are loaded from database and **injected into system prompt**, not as tools:

```python
def _load_skills_context(self) -> None:
    """Load active skills for tenant and add to system prompt"""
    skills = WorkflowRuntimeService.load_active_skills(
        session=self.session,
        tenant_id=self.tenant_id
    )
    
    if skills:
        self.skills_context = WorkflowRuntimeService.get_skills_context(skills)
        
        # ⚠️ Skills added to PROMPT, not as callable tools
        skills_info = f"\n\nAvailable Skills:\n{json.dumps(self.skills_context.get('skill_data', {}), indent=2)}"
        system_msg["content"] += skills_info
```

**Key Finding**: Skills become **documentation in the prompt**, not **executable tools**.

### 3. **TenantSkill Database Model**

**Location**: `backend/app/models/models.py`

**Schema**:
```python
class TenantSkill(Base):
    """Tenant-scoped custom skills/capabilities."""
    __tablename__ = "tenant_skills"
    
    id: int
    tenant_id: int
    skill_name: str        # e.g., "REINSTATE_USER"
    skill_data: dict       # Workflow steps
    version: int
    is_active: bool
    created_at: datetime
```

**Example skill_data**:
```json
{
    "type": "workflow",
    "triggers": ["on_chat_message"],
    "steps": [
        {"action": "approve_required", "gates": ["manager_approval"]},
        {"action": "execute_tool", "tool": "github_pr_create"}
    ]
}
```

**Key Finding**: Skills have structured workflow definitions but no tool execution layer.

## Why Skills Are NOT Tools

### Architecture Gap

1. **Gateway MCP has no database connection**
   - Gateway loads tools from Python code at startup
   - No mechanism to query `tenant_skills` table
   - No dynamic tool registration

2. **Backend loads skills but doesn't expose them**
   - Backend queries `tenant_skills` but only for prompt context
   - No bridge between skill workflow steps and MCP tool calls
   - Skills are **instructions to the LLM**, not **executable tools**

3. **Workflow steps are not MCP tools**
   - Skills define multi-step workflows (approve → execute → log)
   - These are **orchestration patterns**, not atomic tool calls
   - LLM must interpret steps and call existing tools manually

## Design Intent (Inferred)

The current architecture suggests:

1. **Skills = Workflow Templates**
   - Skills teach the agent **how to use** existing tools
   - Example: "REINSTATE_USER" skill might say:
     ```
     1. Call `get_user_status` tool
     2. If suspended, call `update_user` tool with status=active
     3. Log action with `store_session_summary` tool
     ```

2. **Agent Interprets Skills**
   - LLM reads skill workflow in prompt
   - LLM chooses which existing tools to call
   - LLM orchestrates multi-step workflows

3. **Tools = Atomic Operations**
   - Gateway exposes low-level tools (create_club, call_api)
   - Skills compose these tools into higher-level workflows

## Why REINSTATE_USER Doesn't Appear

```
User Request: "Reinstate user X"
                    ↓
┌──────────────────────────────────────────────────┐
│ Backend AgenticService                           │
│ - Loads REINSTATE_USER skill from database       │
│ - Adds workflow steps to system prompt           │
│ - LLM sees: "To reinstate: 1) check 2) update"  │
└──────────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────────┐
│ LLM Decision                                     │
│ - Reads skill instructions                       │
│ - Chooses to call: get_user_status               │
│ - Then calls: call_internal_api(...update user)  │
└──────────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────────┐
│ Gateway MCP                                      │
│ - Receives tool calls: get_user_status, call_*  │
│ - Executes via HTTP/Docker backend               │
│ - Returns results                                │
└──────────────────────────────────────────────────┘
```

**Conclusion**: `REINSTATE_USER` is a **recipe** (skill), not a **tool**. It instructs the LLM how to orchestrate existing tools.

## Architectural Trade-offs

### Current Approach (Skills = Prompt Instructions)

✅ **Pros**:
- Flexible: LLM can adapt workflow based on context
- No skill-to-tool code generation needed
- Easy to version and update skills in database
- LLM can handle edge cases not in workflow definition

❌ **Cons**:
- Skills not discoverable as tool names
- LLM must interpret workflow steps (more tokens, slower)
- No type checking on workflow inputs/outputs
- Harder to test skill execution in isolation

### Alternative (Skills = Dynamic Tools)

Would require:
1. **Skill-to-Tool Compiler**
   - Convert workflow steps into executable tool handler
   - Generate input schema from workflow parameters
   - Wrap workflow orchestration in tool execution

2. **Gateway Database Connection**
   - Query `tenant_skills` at startup
   - Register dynamic tools from database
   - Hot-reload on skill updates

3. **Workflow Executor**
   - Interpret skill steps (approve_required, execute_tool, etc.)
   - Call downstream tools programmatically
   - Return structured results

**Example**:
```python
# Auto-generated from REINSTATE_USER skill
@tool
def reinstate_user(user_id: int) -> dict:
    """Reinstate suspended user (from tenant_skills)"""
    # Step 1: Check status
    status = call_tool("get_user_status", user_id=user_id)
    
    # Step 2: Update if suspended
    if status == "suspended":
        call_tool("call_internal_api", 
                  endpoint="users/update", 
                  params={"user_id": user_id, "status": "active"})
    
    return {"status": "reinstated"}
```

## Recommended Path Forward

### Option A: Keep Current Architecture (Skills as Prompts)
**If workflow flexibility is priority:**
1. Document that skills are orchestration guides, not tools
2. Add skill catalog endpoint: `GET /api/skills` (for UI discoverability)
3. Improve prompt formatting so LLM clearly sees skill steps
4. Add skill execution tracking (log when LLM follows a skill workflow)

### Option B: Add Dynamic Tool Generation
**If type safety and testability are priority:**
1. Create `SkillCompiler` service
2. Generate tool handlers from `tenant_skills.skill_data`
3. Register dynamic tools at Gateway startup
4. Add skill reload endpoint for hot updates

### Option C: Hybrid Approach
**If both flexibility and discoverability are needed:**
1. Keep skills as prompt context (current)
2. Add **skill invocation tool**: `execute_skill(skill_name, params)`
3. Backend interprets skill steps when invoked
4. Gateway sees skills as a single tool, backend orchestrates

**Example**:
```python
# Gateway tool
execute_skill(
    skill_name="REINSTATE_USER",
    params={"user_id": 123}
)

# Backend workflow executor
- Loads REINSTATE_USER skill
- Executes steps sequentially
- Returns final result
```

## Summary

**How skills SHOULD become tools**: They currently **don't** and **aren't designed to**.

Skills are **workflow templates** stored in the database and injected into the LLM's system prompt as instructions. The LLM interprets these instructions and calls existing atomic tools (create_club, call_internal_api, etc.) to execute the workflow.

The Gateway MCP has no mechanism to:
- Query the database for tenant skills
- Dynamically register tools from database records
- Convert workflow definitions into callable tool handlers

This is an architectural design choice, not a missing implementation. Skills provide **orchestration knowledge**, tools provide **atomic execution capability**.
