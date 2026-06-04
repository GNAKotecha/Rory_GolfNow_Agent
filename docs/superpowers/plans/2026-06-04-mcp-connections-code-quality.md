# MCP Connections UI Code Quality Fixes

**Goal:** Fix 6 critical and high-priority code quality issues in MCP Connections UI components.

**Architecture:** Consolidate duplicate error handling, extract reusable utilities, fix API integration bugs, improve UX.

---

## Task 1: Fix OAuth callback to pass code/state parameters

**Files:**
- Modify: `frontend/lib/api.ts:562-580`

- [ ] Change `completeOAuthCallback` from GET to POST with body containing code and state

```typescript
async completeOAuthCallback(
  integrationId: number,
  code: string,
  state: string
): Promise<TenantMCPIntegration> {
  return this.apiCall<TenantMCPIntegration>(
    `/api/integrations/${integrationId}/oauth/callback`,
    {
      method: 'POST',
      body: JSON.stringify({ code, state }),
    },
    `Failed to complete OAuth for integration ${integrationId}`
  );
}
```

- [ ] Commit: `git add frontend/lib/api.ts && git commit -m "fix: pass code/state to OAuth callback endpoint"`

---

## Task 2: Consolidate try-catch error handling in integration methods

**Files:**
- Modify: `frontend/lib/api.ts:380-590`

Replace all 13 integration methods' try-catch blocks with apiCall wrapper.

- [ ] Update `getIntegrations()`:
```typescript
async getIntegrations(): Promise<TenantMCPIntegration[]> {
  return this.apiCall<TenantMCPIntegration[]>(
    '/api/integrations',
    {},
    'Failed to fetch MCP integrations'
  );
}
```

- [ ] Update `getIntegration(id)`:
```typescript
async getIntegration(id: number): Promise<TenantMCPIntegration> {
  return this.apiCall<TenantMCPIntegration>(
    `/api/integrations/${id}`,
    {},
    `Failed to fetch MCP integration ${id}`
  );
}
```

- [ ] Update `createIntegration(data)`:
```typescript
async createIntegration(
  data: TenantMCPIntegrationCreate
): Promise<TenantMCPIntegration> {
  return this.apiCall<TenantMCPIntegration>(
    '/api/integrations',
    {
      method: 'POST',
      body: JSON.stringify(data),
    },
    'Failed to create MCP integration'
  );
}
```

- [ ] Update `updateIntegration(id, data)`:
```typescript
async updateIntegration(
  id: number,
  data: Partial<TenantMCPIntegrationCreate>
): Promise<TenantMCPIntegration> {
  return this.apiCall<TenantMCPIntegration>(
    `/api/integrations/${id}`,
    {
      method: 'PATCH',
      body: JSON.stringify(data),
    },
    `Failed to update MCP integration ${id}`
  );
}
```

- [ ] Update `deleteIntegration(id)`:
```typescript
async deleteIntegration(id: number): Promise<void> {
  await this.apiCall<void>(
    `/api/integrations/${id}`,
    { method: 'DELETE' },
    `Failed to delete MCP integration ${id}`
  );
}
```

- [ ] Update `enableIntegration(id)`:
```typescript
async enableIntegration(id: number): Promise<TenantMCPIntegration> {
  return this.apiCall<TenantMCPIntegration>(
    `/api/integrations/${id}/enable`,
    { method: 'POST' },
    `Failed to enable MCP integration ${id}`
  );
}
```

- [ ] Update `disableIntegration(id)`:
```typescript
async disableIntegration(id: number): Promise<TenantMCPIntegration> {
  return this.apiCall<TenantMCPIntegration>(
    `/api/integrations/${id}/disable`,
    { method: 'POST' },
    `Failed to disable MCP integration ${id}`
  );
}
```

- [ ] Update `testIntegrationHealth(id)`:
```typescript
async testIntegrationHealth(id: number): Promise<HealthCheckResponse> {
  return this.apiCall<HealthCheckResponse>(
    `/api/integrations/${id}/health`,
    { method: 'POST' },
    `Failed to test integration health for ${id}`
  );
}
```

- [ ] Update `testConnection(id)`:
```typescript
async testConnection(id: number): Promise<HealthCheckResponse> {
  return this.apiCall<HealthCheckResponse>(
    `/api/integrations/${id}/test`,
    { method: 'POST' },
    `Failed to test connection for integration ${id}`
  );
}
```

- [ ] Update `storeApiKey(integrationId, apiKey)`:
```typescript
async storeApiKey(
  integrationId: number,
  apiKey: string
): Promise<TenantMCPIntegration> {
  return this.apiCall<TenantMCPIntegration>(
    `/api/integrations/${integrationId}/api-key`,
    {
      method: 'POST',
      body: JSON.stringify({ api_key: apiKey }),
    },
    `Failed to store API key for integration ${integrationId}`
  );
}
```

- [ ] Update `storePAT(integrationId, token)`:
```typescript
async storePAT(
  integrationId: number,
  token: string
): Promise<TenantMCPIntegration> {
  return this.apiCall<TenantMCPIntegration>(
    `/api/integrations/${integrationId}/pat`,
    {
      method: 'POST',
      body: JSON.stringify({ token }),
    },
    `Failed to store PAT for integration ${integrationId}`
  );
}
```

- [ ] Update `initiateOAuth(integrationId)`:
```typescript
async initiateOAuth(integrationId: number): Promise<OAuthInitiateResponse> {
  return this.apiCall<OAuthInitiateResponse>(
    `/api/integrations/${integrationId}/oauth/initiate`,
    { method: 'POST' },
    `Failed to initiate OAuth for integration ${integrationId}`
  );
}
```

- [ ] Update `listAvailableTools()`:
```typescript
async listAvailableTools(): Promise<MCPToolSchema[]> {
  return this.apiCall<MCPToolSchema[]>(
    '/api/integrations/tools',
    {},
    'Failed to list available tools'
  );
}
```

- [ ] Commit: `git add frontend/lib/api.ts && git commit -m "refactor: consolidate try-catch error handling in integration methods"`

---

## Task 3: Replace mock tool discovery with real API call

**Files:**
- Modify: `frontend/components/admin/DiscoverToolsModal.tsx:22-78`

- [ ] Replace entire useEffect with real API call (add apiClient import):
```typescript
import { apiClient } from '@/lib/api';

useEffect(() => {
  if (isOpen && connection) {
    setLoading(true);
    setError(null);

    const discoverTools = async () => {
      try {
        // TODO: Backend should provide endpoint to discover tools for a specific connection
        // For now, list all available tools; enhance later to filter by connection
        const allTools = await apiClient.listAvailableTools();
        
        if (connection.is_enabled) {
          setTools(allTools);
        } else {
          setError('Connection is disabled. Enable it to discover tools.');
        }
      } catch (err) {
        setError(
          err instanceof Error 
            ? err.message 
            : 'Failed to discover tools for this connection'
        );
        setTools([]);
      } finally {
        setLoading(false);
      }
    };

    discoverTools();
  }
}, [isOpen, connection]);
```

- [ ] Commit: `git add frontend/components/admin/DiscoverToolsModal.tsx && git commit -m "fix: replace mock tool discovery with real API call"`

---

## Task 4: Extract duplicate color utility functions

**Files:**
- Create: `frontend/lib/statusColors.ts`
- Modify: `frontend/components/admin/TestConnectionModal.tsx:50-70`

- [ ] Create utility file:
```typescript
// frontend/lib/statusColors.ts
export const getStatusColors = (
  status: string
): { textColor: string; bgColor: string } => {
  switch (status) {
    case 'healthy':
      return {
        textColor: 'text-green-600',
        bgColor: 'bg-green-50 border-green-200',
      };
    case 'unhealthy':
      return {
        textColor: 'text-red-600',
        bgColor: 'bg-red-50 border-red-200',
      };
    default:
      return {
        textColor: 'text-gray-600',
        bgColor: 'bg-gray-50 border-gray-200',
      };
  }
};
```

- [ ] Update TestConnectionModal to use utility (replace lines 50-70):
```typescript
import { getStatusColors } from '@/lib/statusColors';

// In component:
const { textColor, bgColor } = getStatusColors(testStatus.status);

// Usage in JSX (line 103):
<div className={`mb-4 p-4 border rounded-md ${bgColor}`}>
  <div className="flex items-center justify-between">
    <h3 className={`text-sm font-semibold ${textColor}`}>
```

- [ ] Commit: `git add frontend/lib/statusColors.ts frontend/components/admin/TestConnectionModal.tsx && git commit -m "refactor: extract status color utilities"`

---

## Task 5: Extract duplicate form reset logic

**Files:**
- Create: `frontend/lib/formDefaults.ts`
- Modify: `frontend/components/admin/AddMCPModal.tsx:45-49, 56-60`

- [ ] Create defaults file:
```typescript
// frontend/lib/formDefaults.ts
import { TenantMCPIntegrationCreate } from './api';

export const getMCPFormDefaults = (): TenantMCPIntegrationCreate => ({
  integration_name: '',
  auth_type: 'oauth',
  config: {},
});
```

- [ ] Update AddMCPModal (line 20):
```typescript
import { getMCPFormDefaults } from '@/lib/formDefaults';

const [formData, setFormData] = useState(getMCPFormDefaults());
```

- [ ] Update AddMCPModal (line 45):
```typescript
setFormData(getMCPFormDefaults());
```

- [ ] Update AddMCPModal (line 56):
```typescript
const handleClose = () => {
  setFormData(getMCPFormDefaults());
  setError(null);
  onClose();
};
```

- [ ] Commit: `git add frontend/lib/formDefaults.ts frontend/components/admin/AddMCPModal.tsx && git commit -m "refactor: extract form reset defaults"`

---

## Task 6: Keep user on current page after mutations

**Files:**
- Modify: `frontend/app/admin/mcp-connections/page.tsx:74, 107`

- [ ] Update handleAddConnection (line 74):
```typescript
const handleAddConnection = async (data: TenantMCPIntegrationCreate) => {
  setOperationLoading(true);
  try {
    await apiClient.createIntegration(data);
    setSuccessMessage('MCP connection added successfully');
    setShowAddModal(false);
    // Keep user on current page instead of resetting to page 1
    await fetchConnections();
  } catch (err) {
    setError(
      err instanceof Error ? err.message : 'Failed to add MCP connection'
    );
  } finally {
    setOperationLoading(false);
  }
};
```

- [ ] Update handleConfirmDelete (line 107):
```typescript
const handleConfirmDelete = async () => {
  if (!deleteConfirmConnection) return;

  setOperationLoading(true);
  try {
    await apiClient.deleteIntegration(deleteConfirmConnection.id);
    setSuccessMessage('MCP connection deleted successfully');
    setDeleteConfirmConnection(null);
    // If on last page and last item, go to previous page; otherwise stay on current
    const newTotal = total - 1;
    const newTotalPages = Math.ceil(newTotal / DEFAULT_LIMIT);
    if (page > newTotalPages && newTotalPages > 0) {
      setPage(newTotalPages);
    }
    await fetchConnections();
  } catch (err) {
    setError(
      err instanceof Error ? err.message : 'Failed to delete MCP connection'
    );
  } finally {
    setOperationLoading(false);
  }
};
```

- [ ] Commit: `git add frontend/app/admin/mcp-connections/page.tsx && git commit -m "ux: keep user on current page after mutations"`

---

## Task 7: Verify all changes

- [ ] Run TypeScript compilation: `cd frontend && npm run type-check`
- [ ] Verify no build errors
- [ ] Check that all imports resolve correctly
- [ ] Manual browser test: Add, delete, test connection, discover tools
