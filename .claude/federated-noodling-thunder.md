# MCP Tool Management Frontend UI - Implementation Plan

## Status Summary

**Session 1 Completion: Step 2 ✅**
- Date: 2026-06-04
- Work: Extended ApiClient with full integration management methods
- Files Modified: `/frontend/lib/api.ts`
- Status: Ready for Step 3 (Page + Components)
- Next: Continue in separate Claude session with subagent-driven-development for remaining components

**Progress: 2 of 4 steps complete (50%)**

---

## Context

The backend already has a complete MCP integration system built (Phase 4 - Gateway MCP), but there's no frontend UI to manage it. Admins can't currently:
- See what MCP integrations are configured for their tenant
- Add new integrations (Jira, external APIs, etc.)
- Manage credentials (OAuth, API keys, PATs)
- Enable/disable tools
- Test integration health

This plan builds a comprehensive admin dashboard for managing MCP integrations and tools routed through the gateway MCP.

---

## What Already Exists

**Backend is complete:**
- ✅ `/api/integrations` endpoints (CRUD, OAuth, credentials, health check)
- ✅ `TenantMCPIntegration` + `ExternalCredential` models
- ✅ Tool registry with ToolRegistry + MCPToolRegistry
- ✅ Credential encryption & OAuth flow
- ✅ Multi-tenant isolation
- ✅ Tenant-scoped tool catalog

**Frontend patterns exist:**
- ✅ Admin layout with auth & role-based access (`/frontend/app/admin/layout.tsx`)
- ✅ Example page pattern (traces) with filters + table + detail modal
- ✅ ApiClient class with type-safe methods (`/frontend/lib/api.ts`)
- ✅ Reusable admin components (TraceFiltersPanel, TraceListTable, TraceDetailModal)
- ✅ Tailwind CSS styling established

**Missing:**
- ❌ Frontend admin page for integrations management
- ❌ Integration list view with status
- ❌ Create/edit integration forms
- ❌ Credential setup UI (OAuth, API key, PAT)
- ❌ Health check display
- ❌ Tool discovery/enablement UI

---

## Implementation Approach

### Phase 1: Extend ApiClient with Integration Methods

**File:** `/frontend/lib/api.ts`

Add methods mirroring backend endpoints:
```typescript
// Integration CRUD
getIntegrations(): Promise<TenantMCPIntegration[]>
getIntegration(id: number): Promise<TenantMCPIntegration>
createIntegration(data: TenantMCPIntegrationCreate): Promise<TenantMCPIntegration>
updateIntegration(id: number, data: Partial<TenantMCPIntegration>): Promise<TenantMCPIntegration>
deleteIntegration(id: number): Promise<void>
enableIntegration(id: number): Promise<TenantMCPIntegration>
disableIntegration(id: number): Promise<TenantMCPIntegration>
testIntegrationHealth(id: number): Promise<HealthCheckResponse>

// Credentials
storeApiKey(integrationId: number, apiKey: string, baseUrl?: string): Promise<void>
storePAT(integrationId: number, token: string, baseUrl?: string): Promise<void>
initiateOAuth(integrationId: number, redirectUri: string): Promise<OAuthInitiateResponse>
// Note: OAuth callback handled server-side, returns session

// Tool discovery (via gateway MCP)
listAvailableTools(): Promise<MCPToolSchema[]>
```

**Types to add:**
- `TenantMCPIntegration` (already in backend response types)
- `TenantMCPIntegrationCreate` (integration_name, auth_type, config)
- `HealthCheckResponse` (status, message, timestamp)
- `OAuthInitiateResponse` (authorizationUrl, state)
- `MCPToolSchema` (name, description, inputSchema)

---

### Phase 2: Create Integrations Admin Page

**File:** `/frontend/app/admin/integrations/page.tsx`

**Structure:**
- Top navigation: "Integrations" in admin layout
- State management:
  - `integrations: TenantMCPIntegration[]` (list)
  - `selectedIntegration: TenantMCPIntegration | null` (detail modal)
  - `showCreateForm: boolean` (create modal)
  - `loading, error` (error handling)
- useEffect hook: fetch integrations on mount
- Error handling: display errors in toast/banner
- Actions: Create, Edit, Delete, Enable/Disable, Test Health

**Page Layout:**
- Header: "MCP Integrations" + Create button
- Search/filter bar (by name, auth_type, status)
- Integration list table with columns:
  - Name, Auth Type, Enabled (toggle), Status, Created, Actions (Edit, Delete, Test)
- Three modals:
  - IntegrationDetailModal (view/edit details)
  - IntegrationCreateModal (create new)
  - CredentialSetupModal (OAuth, API key, or PAT)

---

### Phase 3: Create Reusable Admin Components

**IntegrationListTable** (`/frontend/components/admin/IntegrationListTable.tsx`)
- Props: integrations[], onEdit, onDelete, onTest, onToggleEnable
- Columns: Name, Auth Type, Enabled (toggle), Health Status, Created, Actions
- Health status: green (healthy), yellow (unknown), red (failed), gray (not tested)
- Pagination: standard 10/25/50 items per page
- Empty state: "No integrations configured"

**IntegrationDetailModal** (`/frontend/components/admin/IntegrationDetailModal.tsx`)
- Props: integration, onClose, onSave, onDelete, onTestHealth
- Tabs:
  - Details: read-only display of integration_name, auth_type, config, created_at
  - Credentials: form to add/update credentials (router to CredentialSetupModal)
  - Health: last health check result with button to re-check
- Actions: Edit Config (opens form), Delete, Close

**IntegrationCreateModal** (`/frontend/components/admin/IntegrationCreateModal.tsx`)
- Props: onClose, onSuccess
- Form fields:
  - Integration Name (required, text)
  - Auth Type (required, radio: oauth | api_key | pat)
  - Config (optional, JSON editor for baseUrl, scopes, etc.)
- Validation: name must be unique per tenant
- Submit → createIntegration → CredentialSetupModal → close

**CredentialSetupModal** (`/frontend/components/admin/CredentialSetupModal.tsx`)
- Props: integration, authType, onClose, onSuccess
- Three paths based on authType:
  - OAuth: button → opens popup to authorize_url → handles callback → stores token
  - API Key: text input → validate → store
  - PAT: text input → validate → store
- Validation: POST to test endpoint before storing
- Success: show message, close modal, refresh integrations list

**IntegrationFiltersPanel** (`/frontend/components/admin/IntegrationFiltersPanel.tsx`)
- Props: filters, onChange
- Filters: search (name), auth_type (dropdown), enabled (toggle)
- Reusable pattern from TraceFiltersPanel

---

### Phase 4: Integration Flow UI

**Create New Integration:**
1. Click "Create Integration" → IntegrationCreateModal
2. Enter name, select auth_type, optional config
3. Submit → POST /api/integrations → success → CredentialSetupModal
4. Setup credentials (OAuth/API key/PAT)
5. Store credential → success → close → show in list with "Not Tested" status
6. Click "Test Health" → POST /api/integrations/{id}/test → show result

**Edit Existing Integration:**
1. Click row or "Edit" → IntegrationDetailModal
2. View details (read-only on Details tab)
3. Tab "Credentials" → manage credentials (add/update)
4. Tab "Health" → view last check + re-test button
5. Close → refresh list

**Delete Integration:**
1. Click "Delete" → confirm dialog
2. DELETE /api/integrations/{id}
3. Remove from list + success toast

**Enable/Disable:**
1. Toggle switch in list
2. POST /api/integrations/{id}/enable or /disable
3. Update in list immediately

---

## File Structure to Create

```
/frontend/
├── app/admin/
│   ├── integrations/
│   │   └── page.tsx                      # Main page (new)
│   └── layout.tsx                        # Existing, update nav
├── components/admin/
│   ├── IntegrationListTable.tsx          # New
│   ├── IntegrationDetailModal.tsx        # New
│   ├── IntegrationCreateModal.tsx        # New
│   ├── CredentialSetupModal.tsx          # New
│   └── IntegrationFiltersPanel.tsx       # New
└── lib/
    └── api.ts                             # Extend with integration methods (existing)
```

---

## Implementation Order

### Step 1: Backend Extension (Minor)
- ✅ VERIFIED - All integration endpoints already implemented in backend
- ✅ OAuth callback redirect handling confirmed
- ✅ Credential encryption and multi-tenant isolation working

### Step 2: Frontend API Client
- ✅ **COMPLETED** - `/frontend/lib/api.ts` extended with all integration methods
- ✅ Added 5 TypeScript interfaces: TenantMCPIntegration, TenantMCPIntegrationCreate, HealthCheckResponse, OAuthInitiateResponse, MCPToolSchema
- ✅ Added 11 async methods: getIntegrations, createIntegration, updateIntegration, deleteIntegration, enableIntegration, disableIntegration, testIntegrationHealth, storeApiKey, storePAT, initiateOAuth, listAvailableTools
- ✅ Bearer token authentication and multi-tenant isolation implemented
- ✅ Error handling with try/catch and meaningful messages

### Step 3: Page + Components
- ✅ **COMPLETED** (2026-06-05)
- [x] Create `/frontend/app/admin/integrations/page.tsx` with state management
- [x] Create IntegrationListTable (display list)
- [x] Create IntegrationDetailModal (view/edit)
- [x] Create IntegrationCreateModal (create flow)
- [x] Create CredentialSetupModal (OAuth/API key/PAT)
- [x] Create IntegrationFiltersPanel (filters)
- [x] Code quality review and fixes (types, OAuth loading, error states, accessibility)

### Step 4: Integration + Testing
- [ ] Wire up all callbacks and data flows
- [ ] Test create/edit/delete flows
- [ ] Test OAuth callback flow
- [ ] Test credentials validation
- [ ] Test health check display
- [ ] Test multi-tenant isolation

---

## Verification

**Manual Testing:**
1. Login as admin
2. Navigate to `/admin/integrations`
3. See empty state (no integrations)
4. Create integration:
   - OAuth: enter name → select oauth → see auth_url popup → callback → stored
   - API Key: enter name → enter key → validate → stored
   - PAT: enter name → enter token → validate → stored
5. See in list with status
6. Test health: see result
7. Edit: update config
8. Delete: remove from list
9. Enable/Disable: toggle and verify

**UI/UX Checks:**
- Empty states are clear
- Loading states show spinners
- Error messages are helpful
- Forms validate before submit
- Success messages appear after actions
- Responsive on mobile

**Multi-Tenant:**
- Two admin users in different tenants see different integrations
- Delete by one tenant doesn't affect other

---

## Notes

- **Existing Patterns:** Follow TraceExplorer page + component patterns (filters, table, modal)
- **Styling:** Use Tailwind CSS matching current admin UI
- **Error Handling:** Display HTTP errors in toast notifications
- **OAuth Flow:** Use standard popup for authorization_url, handle callback server-side
- **Credentials:** Never display stored credentials, only show "Configured" status
- **Tool Discovery:** Future enhancement - can show available tools from ToolRegistry
