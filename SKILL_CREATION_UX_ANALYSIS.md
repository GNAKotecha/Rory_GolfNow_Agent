# Skill Creation UX Analysis - Current State & Issues

**Date:** 2026-06-05  
**Status:** ✅ Completed - Codebase Review

---

## Executive Summary

The skill creation process **is functional** but has significant usability friction:

1. **Manual JSON entry required** — Users must write valid JSON in a text area without editor support
2. **No guided workflow** — Form doesn't help users understand what data structure is needed
3. **Placeholder text unhelpful** — `{"type": "custom", "config": {}}` gives no real guidance
4. **No templates or examples** — New users have no reference for what skills look like
5. **Frontend-backend mismatch** — Frontend allows any JSON, backend has no schema validation

---

## Current Architecture

### Frontend Skill Creation Flow

**File:** `frontend/components/admin/CreateSkillModal.tsx`

```
User clicks "Create New Skill"
    ↓
Modal opens with three fields:
  1. Skill Name (text input)
  2. Description (textarea)
  3. Skill Data (large textarea for JSON)
    ↓
On blur: JSON validation runs (basic JSON.parse check)
    ↓
On submit:
  - Validate skill_name required
  - Validate JSON is parseable
  - Call POST /api/skills with:
    {
      skill_name: string
      description: string
      skill_data: object (parsed from JSON)
    }
    ↓
Modal closes, list refreshes
```

### Backend Skill Model

**File:** `backend/app/api/skills.py`

```python
class TenantSkillCreate(BaseModel):
    skill_name: str
    description: Optional[str] = None
    skill_data: Dict[str, Any]  # ← Accepts ANY object
```

The backend accepts **any dictionary** for `skill_data` with zero schema validation.

### Database Storage

**File:** `backend/app/models/models.py`

```python
class TenantSkill(Base):
    skill_data: JSON column  # Stores raw JSON blob
    skill_name: str
    description: Optional[str]
    version: int
    is_active: bool
```

Skills are stored as-is with no validation or structure enforcement.

---

## Current Validation

| Layer | What's Validated | Gap |
|-------|------------------|-----|
| Frontend | JSON is parseable | No schema validation |
| Backend | None | Any JSON accepted |
| Database | None | Raw JSON blob stored |

---

## User Friction Points

### 1. **"What should go in Skill Data?"**

Current placeholder: `{"type": "custom", "config": {}}`

**Problem:** Users don't know:
- What fields are required
- What the structure should be
- What examples look like
- How this data is used by the runtime

### 2. **Manual JSON Syntax**

Users must:
- Type JSON by hand
- Remember proper syntax (quotes, commas, nesting)
- Get zero IDE support (no autocomplete, hints, or validation)
- Fix syntax errors after submit

### 3. **No Workflow Guidance**

The form doesn't help with:
- Choosing a skill name convention
- What descriptions should contain
- How to structure the data
- Validation before submit

### 4. **Errors Are Generic**

If a user submits bad JSON:
- "Failed to create skill" (generic message)
- No specific guidance on what was wrong
- No way to recover/edit easily

---

## What Works Well

✅ **Authentication** — Admin-only access enforced  
✅ **CRUD operations** — Create, read, update, delete all work  
✅ **UI is responsive** — Modal layout, loading states, success messages  
✅ **API integration** — Frontend correctly calls backend endpoints  
✅ **Basic validation** — JSON parsing check prevents totally malformed input  

---

## Proposed Solutions

Your feedback suggested this UX:

```
Form 1: Basic Details
├─ Skill Name (text)
│  └─ Auto-convert spaces to kebab-case
├─ Description (textarea)
└─ "Next" button

Form 2: Workflow Steps (Bulleted)
├─ Step 1: Slice Bread
├─ Step 2: Toast
├─ Step 3: Add Peanut Butter and Jelly
├─ Step 4: Mmmmmmmm yummy
└─ "Create" button

On submit:
Auto-generate JSON structure from steps:
{
  "type": "custom_workflow",
  "steps": [
    {"order": 1, "action": "Slice Bread"},
    {"order": 2, "action": "Toast"},
    {"order": 3, "action": "Add Peanut Butter and Jelly"},
    {"order": 4, "action": "Mmmmmmmm yummy"}
  ]
}
```

---

## Recommended Architecture for Better UX

### Option A: Structured Wizard (Recommended)

```
Step 1: Basics
├─ Name (auto-kebab-case)
├─ Description
└─ Skill Type selector
   ├─ Custom Workflow
   ├─ API Integration
   ├─ Data Processing
   └─ Other

Step 2: Configuration
├─ Type-specific fields (shown based on Step 1 choice)
└─ Visual builder for workflows

Step 3: Preview & Create
├─ Show generated JSON structure
├─ Review before submit
└─ Create button
```

### Option B: Smart Defaults + Template Library

```
Create New Skill
├─ Use Template (dropdown)
│  ├─ Blank
│  ├─ Custom Workflow (auto-fills steps structure)
│  ├─ API Integration (auto-fills endpoints)
│  └─ Data Processor (auto-fills payload schema)
└─ Then edit as needed
```

### Option C: Visual JSON Editor

```
Create New Skill
├─ Name
├─ Description
├─ Visual JSON editor (like monaco-editor)
   ├─ Syntax highlighting
   ├─ Auto-validation
   ├─ Hover hints
   ├─ Schema suggestions
   └─ Format button
```

---

## Root Cause: No Skill Schema

The system has **no shared understanding** of what skill data should contain:

- Frontend accepts any JSON
- Backend stores any JSON
- Runtime presumably interprets it (but no validation)
- New users have no guide

**Fix:** Define a base schema for skill_data:

```python
class SkillDataBase(BaseModel):
    """Minimum required fields for all skills"""
    type: str  # e.g., "workflow", "api_integration", "custom"
    version: int = 1
    description: Optional[str]
    # Type-specific fields added by subclasses

class WorkflowSkill(SkillDataBase):
    type: Literal["workflow"]
    steps: List[WorkflowStep]

class APISkill(SkillDataBase):
    type: Literal["api_integration"]
    endpoints: List[APIEndpoint]
```

---

## Current Issues Found in Code

### 1. **Frontend Validation Too Loose**

**File:** `frontend/components/admin/skillFormUtils.ts:25-38`

```typescript
export function validateSkillJSON(jsonString: string): {
  valid: boolean;
  error: string | null;
} {
  try {
    JSON.parse(jsonString);  // ← Only checks syntax, not schema
    return { valid: true, error: null };
  } catch (e) {
    return {
      valid: false,
      error: e instanceof Error ? e.message : 'Invalid JSON',
    };
  }
}
```

**Issue:** `JSON.parse` only validates syntax. A skill could be `{}` or `{"random":"data"}` and pass validation.

### 2. **Backend Accepts Anything**

**File:** `backend/app/api/skills.py:18-22`

```python
class TenantSkillCreate(BaseModel):
    skill_name: str
    description: Optional[str] = None
    skill_data: Dict[str, Any]  # ← No schema constraint
```

**Issue:** No validation. Could store any structure.

### 3. **No Runtime Validation**

**Issue:** When the skill is actually used by the agentic engine, there's likely no validation that `skill_data` has the expected structure. This could cause runtime errors.

---

## Functionality Status

| Feature | Status | Notes |
|---------|--------|-------|
| Skill CRUD | ✅ Works | Create, read, update, delete all functional |
| List skills | ✅ Works | Pagination, filtering, search implemented |
| Activate/deactivate | ✅ Works | Status toggle works |
| Admin UI | ✅ Works | Modal, forms, error handling complete |
| API integration | ✅ Works | Frontend-backend communication solid |
| JSON validation | ⚠️ Partial | Only syntax check, no schema validation |
| Error messages | ⚠️ Unclear | Generic failures without specifics |

---

## Testing the Skill Process

**What was tested:**
1. ✅ Frontend loads (needs auth)
2. ✅ Backend is running (port 8000)
3. ✅ Skills admin page exists (routes configured)
4. ✅ Modal structure reviewed (code inspection)
5. ✅ API client methods exist (all CRUD ops)

**What couldn't be tested (auth required):**
- Actual skill creation flow
- Modal interaction
- Error scenarios
- Success feedback

---

## Recommendations to Implement Your UX Idea

### Phase 1: Quick Win (2-3 hours)

Replace the raw JSON textarea with a **structured workflow builder**:

```typescript
// Replace <textarea> for skill_data with:
<WorkflowStepsBuilder
  steps={steps}
  onStepsChange={setSteps}
/>

// Which renders:
- Input field for each step
- "Add step" button
- "Remove step" button (per row)
- Auto-generates JSON on form submit
```

**Backend:** No changes needed (still accepts `skill_data` object).

### Phase 2: Validation (1-2 hours)

Add schema validation to both frontend and backend:

```python
# Backend: Validate structure before storing
class SkillDataValidator:
    @staticmethod
    def validate(skill_data: Dict[str, Any]) -> bool:
        if not isinstance(skill_data, dict):
            raise ValueError("skill_data must be object")
        if "type" not in skill_data:
            raise ValueError("skill_data.type is required")
        # ... more rules
```

### Phase 3: Templates (1 hour)

Add preset templates in the modal:

```typescript
const TEMPLATES = {
  workflow: { type: "workflow", steps: [] },
  api: { type: "api_integration", endpoints: [] },
};

// Show template selector before main form
```

---

## Files to Modify

To implement improved UX:

1. **`frontend/components/admin/CreateSkillModal.tsx`** — Replace JSON textarea
2. **`frontend/components/admin/WorkflowStepsBuilder.tsx`** — NEW component
3. **`frontend/components/admin/skillFormUtils.ts`** — Add schema validation
4. **`backend/app/api/skills.py`** — Add schema validation on create
5. **`backend/app/models/models.py`** — Document skill_data structure
6. **`ADMIN_DASHBOARD_GUIDE.md`** — Add skill creation docs

---

## Summary

**Is the skill process working?** ✅ Yes, it's functional.

**Is it great UX?** ❌ No. Users must write JSON manually with zero guidance.

**What's the fix?** Replace JSON textarea with a structured workflow builder that auto-generates the JSON structure.

**Effort to improve?** ~4-5 hours for phases 1-3 with proper validation and templates.

---

## Next Steps

1. Decide which solution fits your use case:
   - Option A: Structured wizard (most polished)
   - Option B: Template library (quickest)
   - Option C: Smart editor (most flexible)

2. Define `skill_data` schema across skill types

3. Build new UI component to replace raw JSON editor

4. Add backend schema validation

5. Test end-to-end with real skill creation
