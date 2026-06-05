# Skill Runtime Integration Status

**Date:** 2026-06-05  
**Status:** ⚠️ PARTIALLY IMPLEMENTED - Skills are stored but NOT used at runtime

---

## Executive Summary

Skills can be created, stored, and managed through the admin UI, but **the agent does not actually use them at runtime**. The infrastructure exists but is incomplete.

| Component | Status | Details |
|-----------|--------|---------|
| Skill CRUD API | ✅ Complete | Create, read, update, delete working |
| Skill Admin UI | ✅ Complete | Full management interface |
| Skill Storage | ✅ Complete | Database schema, persistence |
| Skill Loading at Runtime | ❌ **NOT IMPLEMENTED** | Method exists but never called |
| Skill Execution | ❌ **NOT IMPLEMENTED** | No interpreter/executor |
| Agent Integration | ❌ **NOT IMPLEMENTED** | Skills not passed to Claude/Ollama |

---

## Current Architecture

### Skill Storage Layer

**Files:** `backend/app/models/models.py`

```python
class TenantSkill(Base):
    __tablename__ = "tenant_skills"
    
    id: int
    tenant_id: int
    skill_name: str
    description: Optional[str]
    skill_data: JSON  # ← Raw JSON blob, no validation
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: Optional[int]
```

Skills are stored as-is with **zero interpretation**.

### Skill Management Layer

**File:** `backend/app/services/skill_workflow_service.py`

Provides CRUD operations:
- `create_skill()` — Create and store
- `list_skills()` — List all
- `get_skill()` — Fetch one
- `update_skill()` — Modify
- `delete_skill()` — Remove

**Gap:** These methods only manage storage, not execution.

### Skill Runtime Layer (INCOMPLETE)

**File:** `backend/app/services/workflow_runtime_service.py`

Has loading infrastructure but **is never called**:

```python
@staticmethod
def load_active_skills(session: Session, tenant_id: int) -> List[TenantSkill]:
    """Load all active skills for tenant."""
    skills = session.query(TenantSkill).filter(
        TenantSkill.tenant_id == tenant_id,
        TenantSkill.is_active == True
    ).all()
    return skills

@staticmethod
def get_skills_context(skills: List[TenantSkill]) -> Dict[str, Any]:
    """Extract runtime context from active skills."""
    context = {
        "skill_names": [skill.skill_name for skill in skills],
        "skill_data": {
            skill.skill_name: skill.skill_data or {}
            for skill in skills
        }
    }
    return context
```

**Status:** ✅ Code exists, ❌ never invoked.

### Agent Execution Layer (INCOMPLETE)

**File:** `backend/app/services/agentic_service.py`

The main agent loop has **stub properties but no implementation**:

```python
class AgentExecutor:
    def __init__(self, ...):
        self.workflow_name = workflow_name
        self.workflow_context: Dict[str, Any] = {}
        self.skills_context: Dict[str, Any] = {}  # ← Defined but never populated
        
    def _load_workflow_context(self) -> None:
        """Load workflow context (implemented)."""
        # ... this works
        self.workflow_context = WorkflowRuntimeService.get_workflow_context(workflow)
        
    def _load_skills_context(self) -> None:
        """NOT IMPLEMENTED - This method doesn't exist."""
        # Missing: Should call WorkflowRuntimeService.load_active_skills()
        # Missing: Should call WorkflowRuntimeService.get_skills_context()
        # Missing: Should store result in self.skills_context
```

**Status:** ❌ No `_load_skills_context()` method exists.

### Claude/Ollama Integration (INCOMPLETE)

**File:** `backend/app/services/agentic_service.py` (lines ~442+)

The system prompt is built but **skills are not included**:

```python
def _execute_agentic_loop(self, current_messages):
    # Step 1: Build tool list
    available_tools = [...]  # From MCP registry
    
    # Step 2: Build system prompt
    system_prompt = f"""You are a helpful AI assistant with access to tools. 
When the user's request requires tool use, call the appropriate tool."""
    
    # Step 3: Call Claude/Ollama
    # ✅ Tools passed to model
    # ❌ Skills NOT passed to model
    # ❌ Skill context NOT in system prompt
    
    response = ollama_client.chat(
        model=model_name,
        messages=current_messages,
        tools=available_tools,  # ← Tools included
        # Missing: skills_context
        # Missing: skill_data in system prompt
    )
```

**Gap:** Skills metadata never reaches the model.

---

## What Works

✅ **Skill Admin UI**
- Create new skills with name, description, JSON data
- Edit existing skills
- Activate/deactivate
- Delete
- List with pagination

✅ **Skill Storage**
- Persisted to database
- Tenant-isolated
- Versioned

✅ **Skill API**
- RESTful endpoints for CRUD
- Proper error handling
- Pagination support

---

## What's Missing (Critical Path)

### 1. Load Skills at Runtime

**Missing Method:** `AgentExecutor._load_skills_context()`

```python
def _load_skills_context(self) -> None:
    """Load and extract skills context before execution."""
    if not self.workflow_name:
        return
    
    try:
        skills = WorkflowRuntimeService.load_active_skills(
            session=self.db,
            tenant_id=self.tenant_id
        )
        
        if skills:
            self.skills_context = WorkflowRuntimeService.get_skills_context(skills)
            logger.info(f"Loaded {len(skills)} skills for tenant {self.tenant_id}")
        else:
            logger.debug(f"No active skills for tenant {self.tenant_id}")
    except Exception as e:
        logger.error(f"Error loading skills: {e}")
        self.skills_context = {}
```

**Where:** `backend/app/services/agentic_service.py` around line 266 (next to `_load_workflow_context`)

**When to call:** In `_prepare_execution()` method, right after `_load_workflow_context()`

### 2. Include Skills in System Prompt

**Missing:** Skill metadata should be in system message to Claude/Ollama

**Current behavior:**
```python
system_prompt = """You are a helpful AI assistant with access to tools."""
```

**Should be:**
```python
system_prompt = f"""You are a helpful AI assistant with access to tools and skills.

## Available Skills
{json.dumps(self.skills_context, indent=2)}

## Tool Usage
When the user's request aligns with an available skill, consider using it.
Skills may provide context, validation rules, or workflow guidance."""
```

**Where:** `backend/app/services/agentic_service.py` around line 535 (in message building)

### 3. Decide Skill Execution Model

**Question:** How should skills actually execute?

**Current design gap:** `skill_data` is stored as JSON but there's no interpreter to execute it.

**Options:**

**Option A: Skills as Prompts/Context**
- Skills provide metadata + instructions to the model
- Model decides whether to use them
- No code execution, pure LLM inference
- Example: `{"type": "workflow", "steps": [...]}` → Added to system prompt
- **Effort:** 1-2 hours (just integrate into prompt)

**Option B: Skills as Tool Definitions**
- Skills define new tools that can be called
- When model calls a skill tool, it executes the defined steps
- Requires skill runtime interpreter
- Example: `{"type": "tool", "actions": [...]}` → Build tool registry
- **Effort:** 4-6 hours (need tool interpreter)

**Option C: Skills as Validators/Rules**
- Skills define validation rules and constraints
- Applied after model generates output
- No independent execution
- Example: `{"type": "rule", "conditions": [...]}` → Applied to check result
- **Effort:** 2-3 hours

**Option D: Skills as Workflow Templates**
- Skills are templates for workflows
- Model can instantiate them as new workflows
- Stored procedures pattern
- Example: `{"type": "workflow_template", "params": [...]}` → Create workflow from template
- **Effort:** 3-4 hours

---

## Current Code Gaps

### Gap 1: Skills Not Loaded

**File:** `backend/app/services/agentic_service.py` line 442

```python
def _prepare_execution(self) -> None:
    """Prepare for execution."""
    self._load_workflow_context()  # ✅ Loads workflow
    # ❌ Missing: self._load_skills_context()
```

**Fix:** Add skill loading call.

### Gap 2: Skills Not Passed to Model

**File:** `backend/app/services/agentic_service.py` line ~535

```python
current_messages.insert(0, {
    "role": "system",
    "content": system_prompt
})

response = ollama_client.chat(
    model=model_name,
    messages=current_messages,
    tools=available_tools,  # ← Tools included
    # ❌ Missing: skills_context parameter
    # ❌ Missing: skill info in system prompt
)
```

**Fix:** Include skills in system message or as parameter.

### Gap 3: No Skill Interpreter

**Issue:** `skill_data` can be anything. No code to interpret/execute it.

**Current:** Skills are just JSON blobs stored in database.

**Needed:** Interpreter that takes `skill_data` and executes it.

---

## Testing Current State

### What You Can Do (Working)

```python
# Create a skill via API
POST /api/skills
{
  "skill_name": "workflow_test",
  "description": "Test skill",
  "skill_data": {"type": "workflow", "steps": ["step1", "step2"]}
}
# ✅ Returns 201, skill stored

# List skills
GET /api/skills
# ✅ Returns skill you just created

# Use skill in UI
# ✅ Can see it in admin dashboard
# ✅ Can edit it
# ✅ Can delete it
```

### What You Cannot Do (Not Implemented)

```python
# Use skill in agent conversation
# ❌ Start a conversation, agent never loads or uses the skill
# ❌ Skill data never reaches Claude/Ollama
# ❌ Model has no awareness of skills

# Actually execute a skill
# ❌ No interpreter for skill_data
# ❌ No way to invoke skill steps
# ❌ skill_data is just metadata, not executable
```

---

## Implementation Plan

### Phase 1: Load & Pass Skills (2-3 hours)

1. Add `_load_skills_context()` method
2. Call it from `_prepare_execution()`
3. Include skills in system prompt
4. Test that skills reach the model

**Outcome:** Skills visible to agent (but not executable)

### Phase 2: Define Skill Execution Model (1-2 hours)

Choose one of options A-D above:
- A: Skills as prompts (easiest, least functional)
- B: Skills as tools (most powerful, most complex)
- C: Skills as validators (middle ground)
- D: Skills as workflow templates (most aligned)

### Phase 3: Implement Skill Execution (varies by option)

**Option A (Prompts):** Just add to system prompt → Done
**Option B (Tools):** Build skill tool registry + executor → 4-6 hours
**Option C (Validators):** Post-processing rules → 2-3 hours
**Option D (Templates):** Workflow factory pattern → 3-4 hours

### Phase 4: Test End-to-End

- Create a skill
- Start agent conversation
- Verify skill is used/applied
- Test skill execution

---

## Files Needing Changes

### Core Implementation Files

1. **`backend/app/services/agentic_service.py`**
   - Add `_load_skills_context()` method
   - Call from `_prepare_execution()`
   - Include skills in system prompt
   - Build skill handling in `_execute_agentic_loop()`

2. **`backend/app/services/skill_executor.py`** (NEW)
   - Create skill interpreter
   - Based on chosen execution model (A-D)
   - Handle skill_data types and execution

3. **`backend/app/api/skills.py`**
   - Add optional schema validation for skill_data
   - Document expected structures

### Testing Files

4. **`backend/tests/services/test_agentic_skill_integration.py`** (NEW)
   - Test skill loading
   - Test skill passing to model
   - Test skill execution (varies by option)

---

## Data Flow (Current vs. Needed)

### Current Flow (Incomplete)

```
User creates skill in Admin UI
    ↓
POST /api/skills
    ↓
Stored in database
    ↓
Agent starts
    ↓
Skills ignored ❌
    ↓
No skill context passed to Claude/Ollama
```

### Needed Flow

```
User creates skill in Admin UI
    ↓
POST /api/skills
    ↓
Stored in database
    ↓
Agent starts
    ↓
AgentExecutor._load_skills_context() ← NEW
    ↓
Skills loaded from database
    ↓
Skills added to system prompt or context ← NEW
    ↓
Claude/Ollama receives skill metadata
    ↓
Model can use skills (method depends on execution model)
    ↓
Skill is executed or applied ← NEW
```

---

## Why Skills Don't Work Now

1. **No loading:** `_load_skills_context()` method doesn't exist
2. **No passing:** Skills never reach Claude/Ollama
3. **No execution:** No interpreter for skill_data
4. **No integration:** Agent loop has no skill handling

The infrastructure (storage, API, UI) is built, but the **runtime integration is a stub**.

---

## Recommended Next Step

**Highest value:** Implement Phase 1 (2-3 hours)

This will:
- Make skills visible to the agent
- Unblock testing of skill-aware prompts
- Enable feedback loop for skill design

Then decide on execution model (A-D) based on actual use case.

---

## Summary Table

| Layer | Component | Status | Gap | Fix |
|-------|-----------|--------|-----|-----|
| Storage | TenantSkill model | ✅ | None | - |
| API | CRUD endpoints | ✅ | None | - |
| UI | Admin dashboard | ✅ | None | - |
| Runtime | Load skills | ❌ | Method missing | Add `_load_skills_context()` |
| Runtime | Pass to model | ❌ | Not in prompt | Include in system message |
| Runtime | Execute | ❌ | No interpreter | Build based on execution model |

---

## Key Insight

**Skills are a management feature, not a runtime feature.** You can create and store them, but the agent never uses them. This is like having a tool registry with no tools actually wired up.

To make skills useful, the agent needs to:
1. Load them at execution time
2. Understand what they do (from skill_data)
3. Apply or execute them somehow

The **execution model** you choose (option A-D) determines how #3 works.
