# Agent Runtime Hardening + Scale Spec (Copilot Execution Plan)

**Date:** 2026-05-12  
**Owner:** Backend + Gateway MCP  
**Status:** Ready for implementation  
**Primary Goal:** Make agent execution reliable, fast, and scalable for real BRS workflows (local first, then Runpod/hosted), while avoiding brittle patch stacking.

---

## Why this spec exists

Current behavior shows repeated tool retries, occasional tool-not-found drift, and high latency from duplicated discovery/retry paths. The system needs:

1. Deterministic error recovery with human-in-the-loop.
2. Lower latency and less retry amplification.
3. Strong architecture boundaries so fixes in one layer do not break others.
4. A path to scale into many MCP/internal/external tools and a CLI-like interaction model.

---

## Non-negotiable guardrails (anti "code piled on code")

Copilot must follow these rules on every task:

1. **Single owner per concern:**
   - Retries: one layer owns a retry class (transport vs orchestration), never both.
   - Tool discovery/routing: one source of truth cache path.
   - Error classification: one canonical mapping with structured categories.

2. **No hidden behavior changes:**
   - Any policy change must be behind a named config flag with a safe default.
   - Add migration notes for defaults if behavior changes.

3. **Contract-first changes:**
   - Update typed contracts before implementation (`MCPToolResult`, event payloads, error category enums).
   - Add tests that fail first on contract mismatch.

4. **Stop-the-line checks per task:**
   - Unit + targeted integration tests must pass before moving to next task.
   - If a task fails twice, stop and produce a blocker note rather than patching around it.

5. **No cross-layer leakage:**
   - `gateway_mcp/tools/*` must not introduce raw subprocess/http usage.
   - `agentic_service` should not parse provider-specific raw errors when structured data exists.

6. **Traceability:**
   - Every task must update this spec checklist and add a short handover note in `PHASE_3_HANDOVER.md` with files changed, tests run, and residual risk.

---

## Baseline success criteria

By completion:

1. Agent never retries the same terminal failure indefinitely.
2. Validation/auth/tool-not-found errors trigger one model remediation turn or explicit `ask_user` stop.
3. P95 tool-call latency decreases via connection reuse and reduced redundant discovery.
4. Tool availability/routing is deterministic across a run.
5. System can scale to additional MCP/internal/external providers via a tool-catalog boundary.
6. A minimal headless/CLI execution mode is defined and testable (without full UI coupling).

---

## Execution order (one task at a time)

> **Rule:** Copilot should implement only the next unchecked task, run listed checks, then stop for review.

### Phase A: Stabilize loop + retries

- [x] **Task A1: Introduce canonical action fingerprint and run-scoped retry budget**
  - Replace `retry_key = f"{step_num}:{tool_name}"` with fingerprint based on normalized `{tool_name, tool_args}`.
  - Track attempts per fingerprint across entire run (not per step).
  - Ensure budget survives step increments.
  - **Files likely:**
    - `backend/app/services/agentic_service.py`
    - `backend/app/services/agent_state.py`
  - **Acceptance:**
    - Same tool+args cannot exceed configured retry budget across steps.
    - Loop detection triggers earlier on repeated identical failures.
  - **Checks:**
    - Add/extend unit tests for retry-key behavior and budget enforcement.

- [x] **Task A2: Single retry-owner policy (remove retry amplification)**
  - Define retry ownership matrix:
    - Transport errors (timeout/connection): MCP client retry.
    - Semantic tool failures (`isError`, validation/auth/not-found): agent layer recovery, no transport replays.
  - Implement explicit guard to prevent both layers retrying same semantic failure.
  - **Files likely:**
    - `backend/app/services/mcp_client.py`
    - `backend/app/services/agentic_service.py`
    - `backend/app/services/error_handler.py`
  - **Acceptance:**
    - Total attempts for semantic failure follow agent budget only.
  - **Checks:**
    - Integration test counting effective attempts per error type.

- [x] **Task A3: Error reflection turn before terminal stop**
  - For recoverable user-fixable failures (validation, missing args, wrong tool name), add one reflection turn:
    1. Write structured tool error result into conversation.
    2. Allow model one corrective turn.
    3. If same fingerprint fails again, emit `ask_user` or abort per policy.
  - **Files likely:**
    - `backend/app/services/agentic_service.py`
    - `backend/app/services/error_handler.py`
  - **Acceptance:**
    - User sees contextual correction prompt, not repeated blind retries.
  - **Checks:**
    - Integration tests for validation correction + repeated failure escalation.

### Phase B: Make tool routing deterministic and fast

- [ ] **Task B1: Deterministic tool catalog cache for run lifecycle**
  - Build run-scoped tool catalog snapshot at workflow start.
  - Avoid repeated full discovery during same run unless explicit invalidation.
  - Add optional TTL refresh and forced refresh path.
  - **Files likely:**
    - `backend/app/services/mcp_registry.py`
    - `backend/app/services/agentic_service.py`
  - **Acceptance:**
    - Tool lookup does not re-list all servers on each miss in steady state.
  - **Checks:**
    - Unit test ensuring one discovery call per run path unless invalidated.

- [ ] **Task B2: Structured tool-not-found semantics**
  - Distinguish:
    - Catalog-miss (tool never exposed)
    - Transient-server-unavailable
    - Permission-denied
  - Propagate a structured category field and map recovery strategy deterministically.
  - **Files likely:**
    - `backend/app/services/mcp_client.py`
    - `backend/app/services/mcp_registry.py`
    - `backend/app/services/error_handler.py`
  - **Acceptance:**
    - No ambiguous "tool not found" when server degraded or auth denied.
  - **Checks:**
    - Unit tests for classification precedence.

### Phase C: Performance + protocol alignment

- [ ] **Task C1: Reuse HTTP clients (Ollama and MCP)**
  - Replace per-call `httpx.AsyncClient()` creation with long-lived pooled client(s) + proper shutdown.
  - Keep timeout controls and ensure no session leaks.
  - **Files likely:**
    - `backend/app/services/ollama.py`
    - any startup/lifecycle wiring in backend app init
  - **Acceptance:**
    - Reduced request overhead and fewer connection churn spikes.
  - **Checks:**
    - Unit test for client reuse behavior.

- [ ] **Task C2: MCP error envelope enrichment**
  - Extend `MCPToolResult` contract with structured fields (`error_category`, `upstream_status`, `terminal_hint`).
  - Update classifier to prefer structured fields over fragile string parsing.
  - **Files likely:**
    - `backend/app/services/mcp_client.py`
    - `backend/app/services/error_handler.py`
    - `backend/app/services/agentic_service.py`
  - **Acceptance:**
    - Infra/auth/validation errors classify correctly without regex-only logic.
  - **Checks:**
    - Contract tests on `MCPToolResult` serialization/consumption.

- [ ] **Task C3: Tool-call protocol normalizer hardening (Qwen/Ollama variants)**
  - Keep native `tool_calls` as source of truth.
  - Maintain fallback parsers but gate by strict schema validation to reduce false positives.
  - Add telemetry counters for fallback parser usage.
  - **Files likely:**
    - `backend/app/services/ollama.py`
    - `backend/tests/test_tool_protocol_alignment.py`
  - **Acceptance:**
    - No raw `create_club { ... }` leaked to final chat when parsable.
  - **Checks:**
    - Expanded protocol tests for prefixed/tagged/json tool formats.

### Phase D: Scalable architecture for many integrations

- [ ] **Task D1: Introduce Tool Catalog abstraction (Gateway-facing)**
  - Add a dedicated abstraction that represents tool metadata, risk, scopes, provider, and health state.
  - Agent consumes filtered catalog instead of ad-hoc flattened lists.
  - **Files likely:**
    - `backend/app/services/mcp_registry.py` (or new module)
    - `backend/app/services/agentic_service.py`
  - **Acceptance:**
    - Easy to filter tools by workflow intent and reduce context overload.
  - **Checks:**
    - Unit tests for catalog filtering by role/risk/provider/availability.

- [ ] **Task D2: Workflow-scoped tool exposure policy**
  - Implement a policy function that exposes only relevant tools per run/workflow type.
  - Include safe defaults and override hook.
  - **Files likely:**
    - `backend/app/services/agentic_service.py`
    - possibly `backend/app/config/*`
  - **Acceptance:**
    - Tool list passed to model is minimal and contextual.
  - **Checks:**
    - Integration test showing reduced tool surface for club-setup workflow.

- [ ] **Task D3: Gateway/Backend boundary hardening doc + checks**
  - Create architecture tests or lint checks ensuring:
    - Backend does not directly use external provider secrets.
    - Gateway remains policy/credential boundary.
  - **Files likely:**
    - new architecture test module
    - docs updates
  - **Acceptance:**
    - Regressions that cross boundaries fail CI quickly.

### Phase E: CLI/headless readiness (Claude Code style trajectory)

- [ ] **Task E1: Headless run contract**
  - Define stable request/response event contract for headless/CLI mode:
    - `workflow_start`, `step`, `tool_executing`, `tool_result`, `tool_error`, `ask_user`, `final_response`.
  - Add run correlation id to all events.
  - **Files likely:**
    - `backend/app/services/agentic_service.py`
    - frontend websocket type definitions
  - **Acceptance:**
    - Clients can reliably stream and reconcile multi-run events.
  - **Checks:**
    - Contract test for required fields per event type.

- [ ] **Task E2: Human-in-the-loop command channel**
  - Standardize `ask_user` remediation payload so CLI/UI can render structured options and resume.
  - Add response envelope for corrected input continuation.
  - **Files likely:**
    - `backend/app/services/error_handler.py`
    - transport/websocket schema code
  - **Acceptance:**
    - Same HITL flow works in UI and future CLI.

---

## Testing matrix (must run per phase)

Minimum suite after each task:

1. Targeted unit tests for changed modules.
2. `backend/tests/test_tool_protocol_alignment.py`
3. `backend/tests/test_error_handling.py`
4. `backend/tests/test_error_handling_integration.py`
5. Any new contract tests introduced by task.

At end of each phase (A-E), run a focused smoke scenario:

1. Club creation happy path.
2. Club creation with missing parameters (expects correction prompt).
3. Club creation with infra dependency down (expects deterministic `ask_user`, no infinite loop).
4. Tool-not-found scenario (expects clear classification and stop policy).

---

## Implementation notes for Copilot

1. Keep commits small and phase-scoped.
2. Do not refactor unrelated modules in the same task.
3. Prefer introducing small composable helpers over large rewrites.
4. When behavior changes, include:
   - old behavior
   - new behavior
   - rollout flag/default
5. Add metrics counters for:
   - retry attempts by category
   - loop detection triggers
   - `ask_user` emits
   - fallback parser invocations

---

## Rollout strategy

1. Ship Phase A+B behind feature flags where needed.
2. Validate on local + Runpod development mode first.
3. Enable for club-setup workflow only (canary) before broad rollout.
4. Promote defaults after stability window and telemetry review.

---

## Out of scope for this spec

1. Full SSE bidirectional transport implementation in gateway.
2. Full multi-tenant billing/rate-limit productization.
3. Enterprise auth federation redesign.

---

## Completion checklist

- [ ] All phase tasks completed with tests passing.
- [ ] No known infinite retry path for repeated tool failures.
- [ ] Documented architecture boundaries with automated checks.
- [ ] Club setup workflow validates successfully in Runpod dev mode.
- [ ] Handover updated with results, risks, and next-step recommendation.

