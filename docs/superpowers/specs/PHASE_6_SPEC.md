# Phase 6 Plan: SSO, Embedded Auth, and Role-Based Tool Access

## Summary
Create Phase 6 as a focused auth/RBAC phase that adds:
- SSO login from the current Next login page.
- Modular embedded auth for `brs-teesheet` using signed JWT exchange.
- A unified RBAC layer across local users, SSO `Job_Role`, and teesheet club roles.
- Tool visibility/enforcement driven by effective permissions, not only legacy `admin/user`.

## Phase Artifacts
- Create `/Users/206887576@bwt3.com/Documents/GitHub/Rory_GolfNow_Agent/PHASE_6_HANDOVER.md`.
- Create `/Users/206887576@bwt3.com/Documents/GitHub/Rory_GolfNow_Agent/docs/superpowers/plans/2026-06-05-phase-6-sso-embedded-auth-rbac.md`.
- Update future AGENTS/task references to use PHASE_6 when this phase starts.

## Task Checklist
- [x] **Task 1:** Define principal/RBAC model for local, SSO, and teesheet users.
- [x] **Task 2:** Add database fields for auth source, external identity, SSO claims, club context, and last login.
- [ ] **Task 3:** Add SSO login/callback endpoints and config for `https://sso.golfnow.com/app/`.
- [ ] **Task 4:** Add `Sign in with SSO` button to current Next login page.
- [ ] **Task 5:** Add modular embedded auth exchange for `brs-teesheet` signed JWTs.
- [ ] **Task 6:** Refactor tool allowlists into permission-based RBAC profiles.
- [ ] **Task 7:** Wire effective RBAC into MCP tool discovery, execution, and prompt layers.
- [ ] **Task 8:** Add tests for auth flows, role mapping, and tool access.
- [ ] **Task 9:** Document setup, claims contract, embed token contract, and remaining production risks.

## Public Interfaces
- `GET /api/auth/sso/login` starts SSO redirect.
- `GET /api/auth/sso/callback` validates SSO response, upserts user, and mints Rory JWT.
- `POST /api/auth/embed/exchange` accepts a signed embed token and returns Rory JWT.
- `GET /api/auth/me` should include effective auth source, mapped roles, club context, and permissions.
- RBAC service exposes one effective permission profile consumed by chat, MCP registry, and prompt layers.

## Role Model
- Local `admin` and `user` keep current behavior.
- SSO `Job_Role` maps roles like `support`, `implementation`, and `sales` to internal permission profiles.
- Teesheet roles like `brs_superuser`, `superuser`, and `admin` map to club-scoped permission profiles.
- Unknown external roles default to least-privilege read-only access unless explicitly configured.

## Test Plan
- Unit test role mapping for all local, SSO, and teesheet roles.
- API test SSO callback success, invalid state, invalid token, and unknown role fallback.
- API test embed exchange success, expired token, bad signature, missing club context, and replay rejection.
- Tool tests prove each effective role only sees and executes allowed tools.
- Regression tests confirm current email/password login and admin approval still work.

## Assumptions
- Start with OIDC-style SSO; if `sso.golfnow.com` is SAML-only, swap adapter before implementing callback validation.
- `brs-teesheet` can issue short-lived signed JWTs with user, club, role, issuer, audience, expiry, and nonce/JTI.
- Phase 6 should stop after each completed checklist task, update `PHASE_6_HANDOVER.md`, mark only that task complete, and wait for approval.
