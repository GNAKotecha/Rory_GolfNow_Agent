# Frontend Admin UI Roadmap
## Missing Components for Production

**Status:** ⚠️ INCOMPLETE - Admin UI needs implementation  
**Date:** 2026-06-04

---

## Current State

### ✅ What Exists
- ✅ Chat interface (`/chat`)
- ✅ Login page (`/login`)
- ✅ Admin layout with protection (`/admin/layout.tsx`)
- ✅ Trace Explorer (`/admin/traces`)
- ✅ Analytics dashboard (`/analytics/dashboard`)
- ✅ Authentication context with role checking

### ❌ What's Missing
- ❌ **Skills Management UI** - Create, edit, delete, activate tenant skills
- ❌ **MCP Connections UI** - Add, configure, test external MCP servers
- ❌ **Workflows Management UI** - Create/edit workflow templates
- ❌ **Admin Navigation Buttons** - Links from chat to admin section
- ❌ **User Management UI** (optional) - Manage users and roles

---

## Missing Pages & Components

### 1. Skills Management Page
**Location:** `/admin/skills`  
**Components Needed:**

```
/admin/skills/page.tsx
├── SkillsList.tsx          (Table of existing skills)
├── CreateSkillModal.tsx    (Modal to create new skill)
├── EditSkillModal.tsx      (Modal to edit skill)
├── DeleteSkillConfirm.tsx  (Confirmation dialog)
└── SkillFilters.tsx        (Filter/search skills)
```

**Features:**
- List all tenant skills with pagination
- Create new skill with name, description, skill_data JSON
- Edit skill definition and metadata
- Activate/deactivate skills
- Delete skills
- Search and filter by name/status
- Version history (if available)

**API Endpoints:**
```
GET    /api/skills
POST   /api/skills
GET    /api/skills/{id}
PATCH  /api/skills/{id}
DELETE /api/skills/{id}
POST   /api/skills/{id}/activate
```

**Data Model:**
```typescript
interface TenantSkill {
  id: number;
  tenant_id: number;
  skill_name: string;
  description: string;
  skill_data: Record<string, any>;
  version: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  created_by: number;
}
```

---

### 2. MCP Connections Page
**Location:** `/admin/mcp-connections`  
**Components Needed:**

```
/admin/mcp-connections/page.tsx
├── MCPConnectionsList.tsx     (Table of configured MCPs)
├── AddMCPModal.tsx            (Modal to add new MCP)
├── TestMCPConnection.tsx      (Test connectivity)
├── MCPCredentials.tsx         (Manage credentials/auth)
└── DiscoverTools.tsx          (Discover tools from MCP)
```

**Features:**
- List configured external MCP servers
- Add new MCP connection (URL, auth type, credentials)
- Test connection and tool discovery
- View available tools from each MCP
- Manage credentials (OAuth, API keys, etc.)
- Enable/disable MCP connections
- Monitor connection status

**API Endpoints:**
```
GET    /api/mcp/connections
POST   /api/mcp/connections
GET    /api/mcp/connections/{id}
PATCH  /api/mcp/connections/{id}
DELETE /api/mcp/connections/{id}
POST   /api/mcp/connections/{id}/test
GET    /api/mcp/connections/{id}/tools
```

**Data Model:**
```typescript
interface MCPConnection {
  id: number;
  tenant_id: number;
  name: string;
  url: string;
  auth_type: 'none' | 'api_key' | 'oauth' | 'basic';
  credentials: Record<string, string>;
  is_enabled: boolean;
  tools_count: number;
  last_tested: string;
  created_at: string;
  updated_at: string;
}
```

---

### 3. Workflows Management Page
**Location:** `/admin/workflows`  
**Components Needed:**

```
/admin/workflows/page.tsx
├── WorkflowsList.tsx          (Table of workflow templates)
├── CreateWorkflowModal.tsx    (Modal to create workflow)
├── EditWorkflowModal.tsx      (Modal to edit workflow)
├── WorkflowBuilder.tsx        (Visual/code editor for workflow steps)
├── WorkflowPreview.tsx        (Preview workflow execution)
└── WorkflowVersions.tsx       (View version history)
```

**Features:**
- List tenant workflows with versioning
- Create new workflow with YAML/JSON definition
- Edit workflow steps and parameters
- Activate/deactivate workflows
- View workflow execution history
- Rollback to previous versions
- Test/preview workflows
- Search and filter workflows

**API Endpoints:**
```
GET    /api/workflows
POST   /api/workflows
GET    /api/workflows/{id}
PATCH  /api/workflows/{id}
DELETE /api/workflows/{id}
POST   /api/workflows/{id}/activate
GET    /api/workflows/{id}/versions
```

**Data Model:**
```typescript
interface TenantWorkflow {
  id: number;
  tenant_id: number;
  workflow_name: string;
  description: string;
  definition: Record<string, any>; // YAML/JSON workflow steps
  version: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  created_by: number;
}
```

---

### 4. Admin Navigation from Chat
**Location:** `frontend/app/chat/page.tsx`  
**Changes Needed:**

Add admin buttons to chat header (if user has admin role):

```tsx
// In header area, add:
{user?.role === 'admin' && (
  <div className="ml-auto flex items-center gap-2">
    <Link href="/admin/skills" className="px-3 py-1 text-sm rounded hover:bg-gray-100">
      Skills
    </Link>
    <Link href="/admin/mcp-connections" className="px-3 py-1 text-sm rounded hover:bg-gray-100">
      MCPs
    </Link>
    <Link href="/admin/workflows" className="px-3 py-1 text-sm rounded hover:bg-gray-100">
      Workflows
    </Link>
    <Link href="/admin/traces" className="px-3 py-1 text-sm rounded hover:bg-gray-100">
      Traces
    </Link>
  </div>
)}
```

---

### 5. Enhanced Admin Layout
**Location:** `frontend/app/admin/layout.tsx`  
**Changes Needed:**

```tsx
// Add sidebar with all admin sections
<nav className="flex space-x-4">
  <Link href="/admin/skills">Skills</Link>
  <Link href="/admin/mcp-connections">MCP Connections</Link>
  <Link href="/admin/workflows">Workflows</Link>
  <Link href="/admin/traces">Traces</Link>
  <Link href="/admin/users" (optional)>Users</Link>
</nav>
```

---

## Implementation Priority

### Phase 1 (Critical - Blocking Production)
1. ✅ Skills Management UI
2. ✅ Admin Navigation buttons in chat
3. ✅ Enhanced admin layout with navigation

### Phase 2 (Important - Needed for Multi-MCP)
1. ✅ MCP Connections UI
2. ✅ Test connection feature
3. ✅ Tool discovery UI

### Phase 3 (Nice-to-Have)
1. Workflows Management UI
2. Workflow builder/editor
3. User management UI

---

## Component Templates

### Basic Admin Page Template
```tsx
'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api';

export default function AdminPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && (!user || user.role !== 'admin')) {
      router.push('/');
      return;
    }
    fetchItems();
  }, [user, authLoading, router]);

  const fetchItems = async () => {
    setLoading(true);
    try {
      // const data = await apiClient.getSkills(); // or similar
      // setItems(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  };

  if (authLoading || !user) return null;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Section Name</h1>
        <p className="mt-2 text-sm text-gray-600">Description</p>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-sm text-red-800">{error}</p>
        </div>
      )}

      {/* Content */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200">
        {/* List/Table here */}
      </div>
    </div>
  );
}
```

---

## API Client Extensions Needed

Add to `lib/api.ts`:

```typescript
// Skills API
export const getSkills = () => client.get('/api/skills');
export const createSkill = (data: any) => client.post('/api/skills', data);
export const updateSkill = (id: number, data: any) => client.patch(`/api/skills/${id}`, data);
export const deleteSkill = (id: number) => client.delete(`/api/skills/${id}`);
export const activateSkill = (id: number) => client.post(`/api/skills/${id}/activate`);

// MCP Connections API
export const getMCPConnections = () => client.get('/api/mcp/connections');
export const createMCPConnection = (data: any) => client.post('/api/mcp/connections', data);
export const testMCPConnection = (id: number) => client.post(`/api/mcp/connections/${id}/test`);
export const discoverMCPTools = (id: number) => client.get(`/api/mcp/connections/${id}/tools`);

// Workflows API
export const getWorkflows = () => client.get('/api/workflows');
export const createWorkflow = (data: any) => client.post('/api/workflows', data);
export const updateWorkflow = (id: number, data: any) => client.patch(`/api/workflows/${id}`, data);
export const activateWorkflow = (id: number) => client.post(`/api/workflows/${id}/activate`);
```

---

## Deployment Impact

### Current Status
- ✅ Backend APIs complete (skills, workflows, MCP)
- ✅ Database models and migrations ready
- ❌ Frontend UI missing

### Blocking Production?
**NO** - Backend is complete and tested. Frontend UI is enhancement, not blocker.

### Can Deploy Without Frontend?
**YES** - Use API directly via curl/Postman for admin operations.

### Timeline
- **Short term:** Deploy backend, use API directly
- **Medium term:** Build Phase 1 admin UI (skills + nav)
- **Long term:** Build Phase 2+ (MCPs, workflows)

---

## Notes

1. **Backend is production-ready** - All APIs implemented and tested
2. **Admin operations possible via API** - Can manage skills/workflows without UI
3. **Frontend is convenience layer** - Not required for functionality
4. **Incremental rollout recommended** - Build UI as needed, starting with Skills
5. **Reusable component patterns** - All admin pages follow similar structure

---

## Recommendation

**Deploy backend to production now.** Frontend admin UI can be built incrementally:

1. **Week 1:** Deploy backend (prod-ready ✅)
2. **Week 2:** Build Skills Management UI (highest priority)
3. **Week 3:** Build Admin Navigation buttons
4. **Week 4+:** Build MCP Connections UI

This allows production use while frontend catches up.

---

**Status:** Ready for backend deployment, frontend roadmap in progress  
**Next:** Implement Phase 1 admin UI components
