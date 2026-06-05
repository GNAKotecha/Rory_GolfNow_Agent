# MCP Architecture & Gateway Flow

**Date**: 2026-06-05  
**Status**: Design Document - Implementation Roadmap  
**Scope**: Full MCP gateway flow, skills management (platform + per-user), centralized knowledge layer, RBAC

---

## Overview

Rory's MCP system is built on three core layers:

1. **Gateway MCP Server** - aggregates all external/internal MCP tools, enforces auth/RBAC
2. **Skills System** - reusable, invocable workflows (platform-wide or per-user)
3. **Knowledge Base** - centralized research, error handling, best practices (avoids repeated MCP calls)

### Current State (Phase 4 ✅)
- Gateway MCP Server: fully implemented
- MCP Client (aiohttp): connects backend → MCP servers
- MCPRegistry: discovers tools from servers
- Credentials: encrypted, per-tenant storage
- Frontend: MCP Connections UI (code complete, auth context needs fix)

### Next Steps (Phase 5+)
- Skills management backend + frontend
- Centralized documentation/knowledge layer
- Semantic skill invocation
- Platform-wide + per-user skill tiers

---

## Part 1: Full MCP Gateway Flow

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        RORY AGENT (Claude)                      │
│  list_tools() → choose_tool() → invoke_tool() → response        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           │ HTTP + Bearer Token + Tenant-ID
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                   GATEWAY MCP SERVER                            │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ 1. list_tools()                                            │ │
│  │    - Query MCPRegistry for all tenant's MCP servers       │ │
│  │    - Aggregate all tools from all servers                 │ │
│  │    - Filter by user role/permissions                      │ │
│  │    - Return unified tool list                             │ │
│  └────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ 2. invoke_tool(name, args)                                │ │
│  │    - Validate user has permission for tool               │ │
│  │    - Route to specific MCP server                         │ │
│  │    - Pass through auth headers/credentials               │ │
│  │    - Receive response from MCP server                    │ │
│  │    - Return response to agent                             │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                ┌──────────┼──────────┐
                │          │          │
    HTTP call   │      HTTP call      │      HTTP call
                │          │          │
    ┌───────────▼──┐ ┌────▼──────┐ ┌─▼─────────────┐
    │  MCP Server  │ │ MCP Server │ │ MCP Server N  │
    │  (BRS Golf)  │ │ (Internal) │ │ (Custom)      │
    │              │ │            │ │               │
    │ - tools:     │ │ - tools:   │ │ - tools:      │
    │   •get_clubs │ │   •memory  │ │   • [custom]  │
    │   •book_tee  │ │   •search  │ │               │
    │   •cancel    │ │   •store   │ │               │
    └──────────────┘ └────────────┘ └───────────────┘
```

### Data Flow: User Adds MCP Connection

**Step 1-2: Frontend → Backend (User Adds Connection)**
```
User clicks "Add MCP Connection" in /admin/mcp-connections
  ↓
Frontend form:
  - Name: "Golf Club API"
  - URL: "http://mcp-server:3000"
  - Auth type: OAuth / API Key / Basic
  - Credentials: [encrypted form]
  ↓
POST /api/integrations
  {
    "name": "Golf Club API",
    "server_url": "http://mcp-server:3000",
    "auth_type": "oauth",
    "skill_data": { "oauth_provider": "custom" }
  }
```

**Step 3: Backend Stores Connection**
```python
# backend/app/api/integrations.py
@router.post("/integrations")
async def create_integration(
    request: CreateIntegrationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Create TenantMCPIntegration record
    integration = TenantMCPIntegration(
        tenant_id=current_user.tenant_id,
        name=request.name,
        server_url=request.server_url,
        auth_type=request.auth_type,
        is_enabled=True,
    )
    db.add(integration)
    db.commit()
    
    # Store credentials in ExternalCredential (encrypted)
    credential = ExternalCredential(
        integration_id=integration.id,
        credential_type=request.auth_type,
        encrypted_value=encrypt_credentials(request.credentials)
    )
    db.add(credential)
    db.commit()
    
    return integration
```

**Step 4: Gateway MCP Discovers Tools**
```python
# backend/app/services/mcp_registry.py
async def discover_tools_from_server(
    integration: TenantMCPIntegration,
    credential: ExternalCredential
):
    # Decrypt credentials
    creds = decrypt_credentials(credential.encrypted_value)
    
    # Create authenticated client
    client = MCPClient(
        server_url=integration.server_url,
        auth=creds  # OAuth token, API key, or Basic auth
    )
    
    # Call server's list_tools endpoint
    tools = await client.list_tools()
    
    # Store tools in cache/registry
    for tool in tools:
        save_tool_to_registry(
            integration_id=integration.id,
            tenant_id=integration.tenant_id,
            tool=tool,
            permissions=tool.get("required_roles", [])  # RBAC
        )
    
    return tools
```

**Step 5: Agent Requests Tools**
```
Agent: "Get me all available tools"
  ↓
Backend: gateway_mcp.list_tools(tenant_id=X, user_role="admin")
  ↓
Gateway queries MCPRegistry:
  SELECT * FROM mcp_tools
  WHERE tenant_id = X
  AND user_role IN (user's roles)
  ↓
Returns:
  {
    "tools": [
      { "name": "get_clubs", "description": "...", "source": "golf_api" },
      { "name": "book_tee", "description": "...", "source": "golf_api" },
      { "name": "cancel_booking", "description": "...", "source": "golf_api" },
      { "name": "memory_store", "description": "...", "source": "internal" },
      { "name": "memory_recall", "description": "...", "source": "internal" },
    ]
  }
```

**Step 6: Agent Invokes Tool**
```
Agent: "Book a tee time: club=123, date=2026-06-15, time=09:00"
  ↓
Backend: gateway_mcp.invoke_tool(
    name="book_tee",
    args={...},
    tenant_id=X,
    user_id=Y,
    user_role="admin"
)
  ↓
Gateway validates:
  1. User has permission for "book_tee" (check RBAC)
  2. Get integration source for "book_tee"
  3. Get encrypted credentials for that integration
  4. Decrypt credentials
  ↓
Gateway calls specific MCP server:
  POST http://mcp-server:3000/invoke
    Authorization: Bearer <decrypted_token>
    {
      "tool": "book_tee",
      "arguments": { ... }
    }
  ↓
MCP server executes tool, returns response
  ↓
Gateway returns response to agent
  ↓
Agent receives result and continues conversation
```

---

## Part 2: Skills Management System

### Two-Tier Model

**Tier 1: Platform-Wide Skills**
- Created by admins in `/admin/skills`
- Available to all agents, all tenants
- Examples: "research_golf_club", "error_recovery", "booking_analysis"
- Invoked: `/research_golf_club` or semantically when agent needs research
- Stored: `PlatformSkill` table (global, not tenant-scoped)

**Tier 2: Per-User Skills**
- Created by individual users in `/agent/my-skills`
- Private to that user's context
- Examples: "my_preferred_workflow", "my_custom_booking_logic"
- Invoked: `/my_preferred_workflow` or semantically
- Stored: `UserSkill` table (tenant_id + user_id scoped)

### Database Models

```python
# Platform-wide skills
class PlatformSkill(Base):
    __tablename__ = "platform_skills"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)  # "research_golf_club"
    description = Column(String)
    slug = Column(String, unique=True)  # "research-golf-club"
    invoke_pattern = Column(String)  # "research_*" or exact name
    skill_data = Column(JSON)  # { "mcp_calls": [...], "logic": "..." }
    created_by = Column(Integer, ForeignKey("user.id"))  # admin
    created_at = Column(DateTime)
    is_published = Column(Boolean, default=True)

# User-scoped skills
class UserSkill(Base):
    __tablename__ = "user_skills"
    
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenant.id"))
    user_id = Column(Integer, ForeignKey("user.id"))
    name = Column(String)  # "my_preferred_workflow"
    description = Column(String)
    slug = Column(String)  # "my-preferred-workflow"
    invoke_pattern = Column(String)
    skill_data = Column(JSON)
    created_at = Column(DateTime)
    is_active = Column(Boolean, default=True)
    
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "slug"),
    )
```

### Skill Invocation: Explicit vs Semantic

**Explicit Invocation** (user types `/skill_name`)
```
User: "/research_golf_club"
  ↓
Agent intercepts slash command
  ↓
Backend: GET /api/skills/research-golf-club
  ↓
Returns skill definition + parameters
  ↓
Agent executes skill immediately
```

**Semantic Invocation** (agent recognizes when to use)
```
Agent thinking: "User asked to research golf clubs. 
This sounds like the 'research_golf_club' skill."
  ↓
Agent: "I'll research this using my skill knowledge..."
  ↓
Backend: POST /api/skills/invoke
  {
    "skill_name": "research_golf_club",
    "context": "user asked about club amenities",
    "parameters": { ... }
  }
  ↓
Skill executes with provided context
```

### Skill Discovery API

```python
# backend/app/api/skills.py
@router.get("/skills")
async def list_skills(
    current_user: User = Depends(get_current_user),
    scope: str = Query("all")  # "platform", "user", "all"
):
    """
    List available skills for current user.
    Combines platform + user-scoped skills.
    """
    platform_skills = db.query(PlatformSkill)\
        .filter(PlatformSkill.is_published == True)\
        .all()
    
    user_skills = db.query(UserSkill)\
        .filter(
            UserSkill.tenant_id == current_user.tenant_id,
            UserSkill.user_id == current_user.id,
            UserSkill.is_active == True
        )\
        .all()
    
    return {
        "platform_skills": [
            {
                "name": skill.name,
                "slug": skill.slug,
                "description": skill.description,
                "invoke_pattern": skill.invoke_pattern,
                "scope": "platform"
            }
            for skill in platform_skills
        ],
        "user_skills": [
            {
                "name": skill.name,
                "slug": skill.slug,
                "description": skill.description,
                "invoke_pattern": skill.invoke_pattern,
                "scope": "user"
            }
            for skill in user_skills
        ]
    }

@router.post("/skills/{skill_slug}/invoke")
async def invoke_skill(
    skill_slug: str,
    request: SkillInvocationRequest,
    current_user: User = Depends(get_current_user),
):
    """Invoke a skill (platform or user-scoped)"""
    
    # Find skill
    skill = find_skill_by_slug(skill_slug, current_user)
    if not skill:
        raise HTTPException(404, "Skill not found")
    
    # Execute skill logic
    result = await execute_skill(
        skill=skill,
        parameters=request.parameters,
        context=request.context,
        user=current_user
    )
    
    return {"result": result}
```

---

## Part 3: Centralized Knowledge Base & Documentation Layer

### Purpose

Instead of Rory making repeated MCP calls to search, research, or recall error-handling patterns, it queries a centralized knowledge base of:
- Research findings (golf club amenities, booking constraints, pricing)
- Error handling docs (what to do when booking fails, rate limits, timeout patterns)
- Workflow best practices (booking flow checklist, confirmation patterns)
- Resolved issues (past problems + solutions)

### Data Model

```python
class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenant.id"))
    title = Column(String)  # "Golf Club Booking Constraints"
    slug = Column(String)  # "golf-club-booking-constraints"
    category = Column(String)  # "research", "error_handling", "workflow", "resolved_issue"
    content = Column(Text)  # markdown or structured JSON
    tags = Column(JSON)  # ["golf", "booking", "constraints", "brs-api"]
    created_by = Column(Integer, ForeignKey("user.id"))
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    is_verified = Column(Boolean, default=False)  # Admin reviewed
    version = Column(Integer, default=1)  # Track revisions
    
    # Scrubbing strategy
    last_accessed_at = Column(DateTime)  # Track freshness
    confidence_level = Column(String)  # "high", "medium", "low"
    expiration_date = Column(DateTime)  # When to re-verify

class KnowledgeAccess(Base):
    __tablename__ = "knowledge_access"
    
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("knowledge_documents.id"))
    user_id = Column(Integer, ForeignKey("user.id"))
    accessed_at = Column(DateTime)
    context = Column(String)  # What was agent working on
```

### Knowledge Query API

```python
# backend/app/api/knowledge.py
@router.get("/knowledge/search")
async def search_knowledge(
    query: str,
    category: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """
    Search knowledge base for relevant documents.
    Returns ranked results by relevance + recency.
    """
    
    # Full-text search + category filter
    results = db.query(KnowledgeDocument)\
        .filter(
            KnowledgeDocument.tenant_id == current_user.tenant_id,
            KnowledgeDocument.is_verified == True,
            or_(
                KnowledgeDocument.title.ilike(f"%{query}%"),
                KnowledgeDocument.content.ilike(f"%{query}%"),
                KnowledgeDocument.tags.contains([query])
            )
        )
    
    if category:
        results = results.filter(KnowledgeDocument.category == category)
    
    # Rank by: relevance + recency + access frequency
    results = results\
        .order_by(desc(KnowledgeDocument.updated_at))\
        .order_by(desc(KnowledgeDocument.last_accessed_at))\
        .limit(5)
    
    # Log access for analytics
    for doc in results:
        access = KnowledgeAccess(
            document_id=doc.id,
            user_id=current_user.id,
            accessed_at=datetime.now(),
            context=query
        )
        db.add(access)
    db.commit()
    
    return {
        "results": [
            {
                "id": doc.id,
                "title": doc.title,
                "category": doc.category,
                "content": doc.content,
                "tags": doc.tags,
                "confidence": doc.confidence_level,
                "updated_at": doc.updated_at
            }
            for doc in results
        ]
    }

@router.post("/knowledge/create")
async def create_knowledge_doc(
    request: CreateKnowledgeRequest,
    current_user: User = Depends(get_current_user),
):
    """Create a new knowledge document"""
    
    doc = KnowledgeDocument(
        tenant_id=current_user.tenant_id,
        title=request.title,
        slug=slugify(request.title),
        category=request.category,
        content=request.content,
        tags=request.tags,
        created_by=current_user.id,
        is_verified=False,  # Needs admin review
        confidence_level=request.confidence or "medium",
        expiration_date=datetime.now() + timedelta(days=90)  # Re-verify in 90 days
    )
    db.add(doc)
    db.commit()
    
    return doc
```

### Agent Query Flow

```
Agent: "I'm about to book a tee time. Let me check for booking constraints."
  ↓
Backend: GET /api/knowledge/search?query=booking%20constraints&category=workflow
  ↓
Knowledge API returns:
  {
    "results": [
      {
        "title": "Golf Club Booking Constraints",
        "category": "workflow",
        "content": "- Max 7 days in advance\n- Min 2 players, Max 4\n- Cancellation: 24 hours notice\n- Rate: $50 per person",
        "tags": ["golf", "booking", "constraints"],
        "confidence": "high",
        "updated_at": "2026-06-01"
      }
    ]
  }
  ↓
Agent uses this knowledge BEFORE making MCP calls
  ↓
Agent: "Based on this knowledge, I'll book with 4 players on 2026-06-15."
```

### Document Scrubbing Strategy

**Automatic Scrubbing (Scheduled Job)**
```python
# backend/tasks/knowledge_scrubber.py
async def scrub_knowledge_base():
    """
    Daily task to mark documents for re-verification.
    Prevents stale knowledge from misleading agent.
    """
    
    # Mark old documents as needing verification
    old_docs = db.query(KnowledgeDocument)\
        .filter(
            KnowledgeDocument.expiration_date < datetime.now()
        )\
        .all()
    
    for doc in old_docs:
        doc.is_verified = False
        doc.confidence_level = "low"
        doc.expiration_date = None  # Needs re-verification
        db.add(doc)
    
    db.commit()
    
    # Notify admin: "X documents need re-verification"
    notify_admins(len(old_docs))
```

**Manual Verification (Admin Dashboard)**
- Admin reviews documents marked for re-verification
- Confirms accuracy or updates content
- Sets new expiration date
- Re-marks as verified

**Usage Analytics**
- Track which documents agents access most
- Remove frequently contradicted documents
- Identify gaps in knowledge

---

## Part 4: RBAC Through Gateway

### Multi-Layer Authorization

```
┌─ Layer 1: User Authenticated? ──────┐
│  (JWT token valid?)                  │
└─────────────┬───────────────────────┘
              │
┌─────────────▼─── Layer 2: User Approved? ──┐
│  (approval_status = "APPROVED")            │
└─────────────┬────────────────────────────┘
              │
┌─────────────▼─── Layer 3: Tenant Access? ──┐
│  (user.tenant_id matches request.tenant_id) │
└─────────────┬────────────────────────────┘
              │
┌─────────────▼─── Layer 4: Role-Based Tool Access? ──┐
│  (tool requires role, user has that role)           │
│  Example: "book_tee" requires "admin" role          │
└─────────────┬────────────────────────────────────┘
              │
┌─────────────▼─── Layer 5: Credential Access? ──┐
│  (integration credentials exist + decryptable)  │
└─────────────┬───────────────────────────────┘
              │
         Tool executes
```

### Role-Based Tool Access

```python
# backend/app/models/models.py
class MCPTool(Base):
    __tablename__ = "mcp_tools"
    
    id = Column(Integer, primary_key=True)
    integration_id = Column(Integer, ForeignKey("tenant_mcp_integration.id"))
    name = Column(String)  # "book_tee"
    description = Column(String)
    required_roles = Column(JSON)  # ["admin", "booking_agent"]
    schema = Column(JSON)  # OpenAPI schema
    
class UserRole(Base):
    __tablename__ = "user_roles"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"))
    tenant_id = Column(Integer, ForeignKey("tenant.id"))
    role = Column(String)  # "admin", "booking_agent", "view_only"

# Authorization check
def check_tool_access(
    user: User,
    tool: MCPTool,
    db: Session
) -> bool:
    """Verify user can access tool"""
    
    # Get user's roles
    user_roles = db.query(UserRole)\
        .filter(
            UserRole.user_id == user.id,
            UserRole.tenant_id == user.tenant_id
        )\
        .all()
    
    role_names = [r.role for r in user_roles]
    
    # Check if user has any required role
    required_roles = set(tool.required_roles or [])
    user_role_set = set(role_names)
    
    if not required_roles:  # No restriction
        return True
    
    return bool(required_roles & user_role_set)  # Intersection
```

### Encrypted Credentials Management

```python
# backend/app/services/credential_service.py
class CredentialService:
    
    async def store_credential(
        self,
        integration: TenantMCPIntegration,
        credential_data: dict,
        tenant_id: int
    ):
        """Store encrypted credential for MCP integration"""
        
        # Encrypt with tenant-specific key
        encrypted = encrypt_with_tenant_key(
            data=credential_data,
            tenant_id=tenant_id
        )
        
        credential = ExternalCredential(
            integration_id=integration.id,
            credential_type=credential_data.get("type"),
            encrypted_value=encrypted,
            tenant_id=tenant_id
        )
        db.add(credential)
        db.commit()
    
    async def get_credential(
        self,
        integration_id: int,
        tenant_id: int
    ) -> dict:
        """Retrieve and decrypt credential (with audit log)"""
        
        credential = db.query(ExternalCredential)\
            .filter(
                ExternalCredential.integration_id == integration_id,
                ExternalCredential.tenant_id == tenant_id
            )\
            .first()
        
        if not credential:
            raise CredentialNotFound()
        
        # Decrypt with tenant key
        decrypted = decrypt_with_tenant_key(
            encrypted_data=credential.encrypted_value,
            tenant_id=tenant_id
        )
        
        # Log access
        log_credential_access(
            credential_id=credential.id,
            user_id=current_user.id,
            action="decrypt"
        )
        
        return decrypted
```

### Gateway Authorization Flow

```python
# backend/app/services/gateway_mcp.py
async def invoke_tool(
    tool_name: str,
    arguments: dict,
    user: User,
    tenant_id: int,
    db: Session
) -> dict:
    """
    Invoke MCP tool with full authorization checks.
    """
    
    # 1. Verify user is approved
    if user.approval_status != "APPROVED":
        raise UnauthorizedException("User not approved")
    
    # 2. Verify tenant match
    if user.tenant_id != tenant_id:
        raise ForbiddenException("Tenant mismatch")
    
    # 3. Find tool in registry
    tool = db.query(MCPTool)\
        .join(TenantMCPIntegration)\
        .filter(
            MCPTool.name == tool_name,
            TenantMCPIntegration.tenant_id == tenant_id
        )\
        .first()
    
    if not tool:
        raise ToolNotFound(tool_name)
    
    # 4. Check RBAC
    if not check_tool_access(user, tool, db):
        raise ForbiddenException(f"Role mismatch for tool: {tool_name}")
    
    # 5. Get credentials
    credential = credential_service.get_credential(
        tool.integration_id,
        tenant_id
    )
    
    # 6. Create authenticated MCP client
    client = MCPClient(
        url=tool.integration.server_url,
        auth=credential
    )
    
    # 7. Invoke tool
    result = await client.invoke(tool_name, arguments)
    
    # 8. Log invocation for audit
    log_tool_invocation(
        tool_name=tool_name,
        user_id=user.id,
        tenant_id=tenant_id,
        status="success",
        duration=...
    )
    
    return result
```

---

## Implementation Roadmap

### Phase 5.1: Skills Management Backend
- [ ] Implement `PlatformSkill` + `UserSkill` models
- [ ] Implement skills API endpoints (list, create, invoke)
- [ ] Add skill discovery to agent context
- [ ] Add explicit invocation (/skill_name)

### Phase 5.2: Skills Management Frontend
- [ ] Admin dashboard: Create platform skills
- [ ] User dashboard: Create/manage user skills
- [ ] Skill marketplace: Browse + preview skills
- [ ] Skill versioning + rollback

### Phase 6.1: Knowledge Base Backend
- [ ] Implement `KnowledgeDocument` model
- [ ] Implement knowledge API (search, create, verify)
- [ ] Implement doc scrubbing scheduler
- [ ] Admin API for verification

### Phase 6.2: Knowledge Base Frontend
- [ ] Knowledge browser/search UI
- [ ] Document creation wizard
- [ ] Admin verification dashboard
- [ ] Analytics dashboard

---

## Summary

**Gateway Flow**: User adds MCP connection → stored + registered → agent lists tools → agent invokes tool through gateway → response returned

**Skills**: Platform-wide (admin-created, all agents) + Per-user (private)  
**Knowledge**: Centralized docs to reduce MCP calls + scrubbing strategy for freshness  
**RBAC**: Multi-layer: auth → approval → tenant → role → credentials

Ready for engineering implementation.
