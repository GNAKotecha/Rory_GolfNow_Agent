# Skill System - Complete Analysis

**Reviewer:** Claude Code  
**Date:** 2026-06-05  
**Scope:** Skill creation UX + runtime integration  
**Time Invested:** Codebase review + analysis

---

## What You Asked

> "Why is creating a skill so hard? Why is Skill Data JSON formatted?"

## What I Found

### The Bad News (UX)
- ❌ Users must write raw JSON by hand
- ❌ No editor support (syntax highlighting, validation, hints)
- ❌ Confusing placeholder (`{"type": "custom", "config": {}}`)
- ❌ No templates or examples
- ❌ No guided workflow

### The Bad News (Runtime)
- ❌ Skills are created but **never actually used**
- ❌ Agent doesn't load skills at execution time
- ❌ Skills never reach Claude/Ollama
- ❌ No interpreter to execute skill_data

### The Good News
- ✅ CRUD operations fully working
- ✅ Admin UI complete and functional
- ✅ Database persistence solid
- ✅ Infrastructure foundation is there

---

## Two Separate Problems

### Problem #1: Creation UX (Addressable)

**Current state:** Raw JSON textarea

```
┌─────────────────────────────────────────┐
│ Create New Skill                        │
├─────────────────────────────────────────┤
│ Skill Name: [________]                  │
│ Description: [________]                 │
│ Skill Data (JSON):                      │
│ [                                       │
│   "type": "custom",                     │
│   "config": {}                          │
│ ]                                       │
│                 [Cancel] [Create Skill] │
└─────────────────────────────────────────┘
```

**Problem:** Users don't know what to put in the JSON.

**Your proposed solution:** Structured workflow builder

```
┌─────────────────────────────────────────┐
│ Step 1: Basics                          │
├─────────────────────────────────────────┤
│ Skill Name: [Make Sandwich___]          │
│ Description: [A skill to make food]     │
│                        [Next]           │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│ Step 2: Workflow Steps                  │
├─────────────────────────────────────────┤
│ □ Step 1: Slice Bread      [✕]          │
│ □ Step 2: Toast            [✕]          │
│ □ Step 3: Add PB & Jelly   [✕]          │
│ □ Step 4: Mmmmmmmm yummy   [✕]          │
│                 [Add Step] [Create]     │
└─────────────────────────────────────────┘
```

**Auto-generates JSON:**
```json
{
  "type": "workflow",
  "steps": [
    {"order": 1, "action": "Slice Bread"},
    {"order": 2, "action": "Toast"},
    {"order": 3, "action": "Add PB & Jelly"},
    {"order": 4, "action": "Mmmmmmmm yummy"}
  ]
}
```

**Effort to implement:** 2-3 hours for UI + auto-generation

### Problem #2: Runtime Integration (Bigger Issue)

**Current state:** Skills stored but never used

```
User creates skill "Make Sandwich"
    ↓
Stored in database
    ↓
Agent starts conversation
    ↓
Agent ignores skill ❌
    ↓
"Make Sandwich" skill never used
```

**Gap:** No code to:
1. Load skills when agent starts
2. Pass skills to Claude/Ollama
3. Execute or apply skills

**Effort to fix:** 4-6 hours for full integration

---

## Why JSON in the First Place?

### Reason 1: Flexibility
- Could store any skill type (workflows, tools, validators, etc.)
- No schema enforced
- Backend accepts anything

**Problem:** This flexibility requires users to know the structure.

### Reason 2: No Schema
The system has **zero documentation** on what skill_data should contain:

```python
# In backend:
class TenantSkillCreate(BaseModel):
    skill_name: str
    description: Optional[str] = None
    skill_data: Dict[str, Any]  # ← Accept anything, validate nothing
```

There's no:
- Pydantic schema
- JSON Schema
- Documentation
- Examples
- Validation

### Reason 3: Incomplete Design
Skills are a work-in-progress feature:
- ✅ Storage layer done
- ✅ API layer done
- ✅ UI layer done
- ❌ **Runtime layer incomplete**

Without knowing how skills will be used, it's hard to define their structure.

---

## Current Architecture (Visual)

### Frontend

```
Admin UI
├── Skills Page
├── Create Skill Modal
│   ├── Name (text)
│   ├── Description (textarea)
│   └── Skill Data (JSON textarea) ← Users edit raw JSON
└── API client
    └── POST /api/skills
```

### Backend

```
REST API
├── POST /api/skills (create)
├── GET /api/skills (list)
├── PATCH /api/skills/{id} (update)
└── DELETE /api/skills/{id} (delete)
    ↓
Skill Service
└── CRUD operations on database
    ↓
Database
└── tenant_skills table
    ├── skill_name
    ├── description
    ├── skill_data (JSON blob)
    └── is_active
```

### Runtime (INCOMPLETE)

```
Agent Loop
├── Load workflow ✅
├── Load skills ❌ (method exists, never called)
├── Load MCP tools ✅
├── Build system prompt (skills not included) ❌
├── Call Claude/Ollama (skills not passed) ❌
└── Execute result ✅
```

---

## Three Solutions to Improve UX

### Solution 1: Structured Workflow Builder (Recommended)

**Effort:** 2-3 hours

**Impact:** 
- Eliminates JSON editing
- Auto-generates correct structure
- Guides user through creation

**How it works:**
1. User enters skill name, description
2. Shows step-by-step input fields
3. Auto-converts to JSON on submit
4. User never sees raw JSON

**Code change:** Replace JSON textarea with custom component

**File:** `frontend/components/admin/CreateSkillModal.tsx`

### Solution 2: Template Library

**Effort:** 1-2 hours

**Impact:**
- Provides starting points
- Shows examples
- Reduces blank-page syndrome

**How it works:**
1. Dropdown with preset templates
2. "Blank Workflow" → auto-structure
3. "API Integration" → auto-structure
4. "Data Processor" → auto-structure

**File:** `frontend/components/admin/CreateSkillModal.tsx` + template constants

### Solution 3: Smart JSON Editor

**Effort:** 3-4 hours

**Impact:**
- Full flexibility retained
- Better editing experience
- IDE-like features

**How it works:**
1. Monaco Editor (VS Code)
2. Syntax highlighting
3. Auto-completion
4. Schema hints
5. Format button

**File:** `frontend/components/admin/CreateSkillModal.tsx` + monaco-editor dependency

---

## Recommended Path Forward

### Phase 1: Improve Creation (2-3 hours)

**Option A (Recommended):** Implement structured workflow builder
- Eliminate raw JSON editing
- Auto-generate structure
- Guide user step-by-step

**Implement:**
1. New component `WorkflowStepsBuilder`
2. Replace JSON textarea in `CreateSkillModal`
3. Auto-convert steps to JSON
4. Add 2-3 preset templates

### Phase 2: Complete Runtime (4-6 hours)

**What's needed:**
1. Add `_load_skills_context()` method in AgenticService
2. Include skills in system prompt
3. Decide execution model (prompts, tools, validators, templates)
4. Implement skill executor

### Phase 3: Schema & Validation (1-2 hours)

**What's needed:**
1. Define skill_data schema with Pydantic
2. Validate on creation
3. Document expected structures
4. Add type hints

---

## Decision Point: What Are Skills For?

Before building the full solution, clarify: **What should skills actually do?**

### Model 1: Prompts/Context
Skills provide metadata to the agent. Agent decides how to use them.
- **Simplest to implement**
- **Least capable**

### Model 2: Tools
Skills define new tools that the agent can call.
- **Most powerful**
- **Most complex to implement**

### Model 3: Validators
Skills define validation rules applied after agent outputs.
- **Middle ground**
- **Good for safety**

### Model 4: Workflow Templates
Skills are templates to create new workflows.
- **Aligns with existing architecture**
- **Moderate complexity**

**Recommend:** Model 4 (Workflow Templates) — aligns with Phase 4/5 handover structure.

---

## Code Locations Reference

### Frontend
- Skills page: `frontend/app/admin/skills/page.tsx`
- Create modal: `frontend/components/admin/CreateSkillModal.tsx`
- Form utils: `frontend/components/admin/skillFormUtils.ts`
- API client: `frontend/lib/api.ts` (methods: getSkills, createSkill, etc.)

### Backend
- Models: `backend/app/models/models.py` (TenantSkill)
- API routes: `backend/app/api/skills.py`
- Service layer: `backend/app/services/skill_workflow_service.py`
- Runtime service: `backend/app/services/workflow_runtime_service.py`
- Agentic loop: `backend/app/services/agentic_service.py` (needs integration)

---

## Summary: Two Documents to Read

1. **`SKILL_CREATION_UX_ANALYSIS.md`**
   - Problem: JSON editing is hard
   - Solution: Structured workflow builder
   - Effort: 2-3 hours
   - Focus: Frontend UX improvement

2. **`SKILL_RUNTIME_INTEGRATION_STATUS.md`**
   - Problem: Skills never used at runtime
   - Solution: Load and pass skills to agent
   - Effort: 4-6 hours
   - Focus: Backend runtime integration

---

## Quick Start: What to Do Next

### Option A: Improve Creation UX Now
1. Read `SKILL_CREATION_UX_ANALYSIS.md`
2. Use `/superpowers:writing-plans` to design workflow builder
3. Implement structured UI
4. Test with admin dashboard

### Option B: Fix Runtime Integration Now
1. Read `SKILL_RUNTIME_INTEGRATION_STATUS.md`
2. Add `_load_skills_context()` to AgenticService
3. Include skills in system prompt
4. Test with agent conversation

### Option C: Do Both (Recommended)
1. Phase 1: Improve creation (2-3 hours)
2. Phase 2: Complete runtime (4-6 hours)
3. Total: ~6-9 hours for full skill feature

---

## Final Assessment

| Aspect | Status | Comment |
|--------|--------|---------|
| Can create skills? | ✅ Yes | Full CRUD works |
| Easy to create? | ❌ No | JSON editing is friction |
| Skills actually used? | ❌ No | Runtime integration incomplete |
| Worth fixing? | ✅ Yes | Could be powerful feature |
| Effort to fix both? | ✅ 6-9 hours | Reasonable investment |

**Bottom line:** Skills are a well-architected feature that's 60% complete. Both the UX friction and runtime gap are addressable with focused work.
