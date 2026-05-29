# Harness Loop, Resume, and Memory Spec (Lightweight)

**Date:** 2026-05-21  
**Status:** Draft for review  
**Owner:** Backend Team

## Goal

Improve the internal agent harness so it can:
1. Handle high tool-call workflows (for example Playwright-heavy runs) without premature stop.
2. Resume reliably after interruption/user input/approval with full run continuity.
3. Persist useful memory across messages and sessions.
4. Support frontend-managed MCP integrations (internal and external APIs).
5. Support frontend-managed skills and workflows for multi-company onboarding.

## Non-Goals

- Replatforming to Hermes or Pi.
- Building a full memory knowledge graph in this phase.
- Redesigning frontend chat UX beyond minimal controls needed for this behavior.

## Current Gaps

- Step budget is effectively too low for tool-heavy workflows (`max_steps=10` defaults and hardcoded call sites).
- Approval resume path is not fully end-to-end in all API paths.
- Memory is partially persisted, but not yet structured into "always-load context" + "searchable long-term history" layers.
- MCP/tool onboarding is mostly backend-configured, not productized for frontend self-service.
- Skills/workflows are not yet managed as tenant-configurable resources.

## Requirements

### R1. Adaptive Loop Budget

- Replace fixed step budget behavior with policy-based budgets by workflow/tool profile.
- Add budget-pressure warnings before exhaustion (for example at ~70% and ~90%).
- Preserve hard stop behavior when budget is exhausted, with explicit stop reason and telemetry.

### R2. Interruption-Safe Resume

- Resume must continue the same run context (same `run_id`) after:
  - `ask_user` remediation
  - approval decision
  - user interruption + continue
- Resume state must be durable (survives process restart).
- Resumed execution must preserve pending context, not restart from scratch.

### R3. Persistent Memory Model

- Add two memory layers:
  1. **Working Memory (compact, always injected):** user preferences + session/workflow essentials.
  2. **Historical Memory (searchable):** prior outcomes, tool traces, and relevant session history.
- Memory retrieval must be scoped by user and workflow context.

### R4. Frontend MCP Integration Management

- Add tenant-safe MCP connection management in frontend + backend API:
  - create/edit/disable/test MCP connections
  - auth mode support (OAuth, PAT/API key, service account where applicable)
  - scoped tool exposure per tenant/workflow/risk policy
- New integrations must be usable without backend code edits in normal cases.

### R5. Frontend Skills and Workflow Management

- Add skill/workflow registry managed from frontend:
  - create/version/activate/deactivate skills
  - compose workflows from tools + skills + approval gates
  - publish workflow to selected tenant/environment
- Support white-label deployment model:
  - core harness reusable across clients
  - tenant-specific integrations, prompts, and workflows isolated by configuration

## Minimal Design

- Introduce `LoopBudgetPolicy` mapping workflow/tool classes to:
  - `max_steps`
  - warning thresholds
  - timeout defaults
- Persist run cursor/state after each turn boundary and tool batch completion.
- Unify resume flow across WebSocket and REST approval endpoints.
- Add memory retrieval service that returns:
  - compact context block for prompt injection
  - optional top-k historical recalls for relevant workflow type
- Add Integration Registry service:
  - `MCPConnection` (tenant_id, provider, auth_type, scopes, status, health)
  - `ToolPolicyBinding` (workflow_type, risk_level, allow/deny)
- Add Skill/Workflow Registry service:
  - `SkillDefinition` (tenant_id, name, version, prompt/rules, active)
  - `WorkflowTemplate` (tenant_id, steps, required tools, approval checkpoints)
- Add tenant configuration boundary:
  - `platform-core` (generic harness runtime)
  - `tenant-config` (integrations, skills, workflow templates)
  - optional sanitized distribution repo with no BRS-specific assets

## Acceptance Criteria

1. A Playwright-heavy workflow can run with higher budget (configured by policy) without code changes per request.
2. On interruption or approval, continuing the run keeps `run_id` continuity and execution state continuity.
3. If service restarts mid-run, resume token + run state can still continue the workflow.
4. Prompt input includes compact persisted memory and can retrieve relevant prior outcomes by workflow type.
5. Telemetry records: budget warnings emitted, stop reason, resumed vs fresh run, and memory retrieval usage.
6. A tenant admin can add an MCP integration from frontend, complete auth, and use its tools in a workflow without redeploy.
7. A tenant admin can create/update/activate a skill or workflow from frontend and run it in chat/runtime.
8. Tenant A integrations/skills/workflows are isolated from Tenant B by policy and data boundaries.

## Suggested Implementation Order

1. Loop budget policy + warning events.
2. Durable run cursor persistence + unified resume endpoints.
3. Memory layering (compact injection + historical recall).
4. Frontend MCP Integration Registry + auth flows + policy binding.
5. Frontend Skill/Workflow Registry + runtime loader.

## Risks

- Larger budgets can increase cost and latency without stronger loop safety.
- Resume correctness can regress if tool side effects are not idempotent.
- Memory recall quality may degrade if retrieval is too broad.
- Multi-tenant isolation mistakes can cause cross-client data leakage if boundaries are weak.
- Dynamic integration onboarding increases auth/security complexity (token lifecycle, scope drift, revocation).

## Open Questions

1. Default high-budget profile for browser automation: 60, 90, or 120 steps?
2. Should approval resume execute automatically on approve, or require explicit "continue"?
3. What is the minimum memory token budget reserved for compact working memory?
4. Do we keep this repo as primary and add a sanitized template export, or spin a dedicated generic harness repo now?
