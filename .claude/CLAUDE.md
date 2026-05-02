Build a lightweight MVP for a hosted internal agent using this architecture:

- Frontend: Open WebUI as the chat shell
- Backend: custom service that owns product logic
- Model runtime: Ollama on a GPU VM
- Tools: remote MCP servers + company docs
- Storage: database for users, conversations, workflow analytics

## Prior Context (Reference Only)
- Phase 1 completed: See `PHASE_1_HANDOVER.md` for workflow engine foundation

## Execution rule

Each task must be handled in this order:

1. Read `PHASE_2_HANDOVER.md` using `ctx_index` or `ctx_execute_file`
   - Understand current project state
   - Check completed work
   - Check blockers, assumptions, and previous decisions

2. Read the Plan File using `ctx_index` or `ctx_execute_file`
   - Identify the next unchecked task
   - Confirm the task scope and acceptance criteria
   - Do not start unrelated future tasks

3. Execute using `/subagent-driven-development`
   - Follow the implement → review → fix → re-review flow
   - Apply the maximum 2-iteration review policy
   - Stop and escalate if a review fails twice

4. Verify the task
   - Run relevant tests/checks
   - Confirm acceptance criteria are met
   - Keep implementation minimal and clean

5. Update project tracking
   - Add a clear entry to `PHASE_2_HANDOVER.md` explaining:
     - what was changed
     - files touched
     - tests run
     - remaining risks/blockers
     - suggested next task
     - Anything important learned
   - Update the checklist in the Plan File: 
   - Mark only the completed task as done

6. Stop
   - Do not automatically continue to the next task
   - Wait for the user to approve the next task

## Looping policy

Maximum 2 iterations per review stage:

- Spec review: Implement → Review → Fix → Re-Review  
  STOP if still failing and escalate to user.

- Code quality review: Review → Fix → Re-Review  
  STOP if still failing and escalate to user.

If a review fails twice:

1. Document what is blocking
2. Present the issue to the user with options:
   - Accept implementation as-is
   - Provide clarification and retry
   - Skip this quality check for now
3. Do not continue review loops without user decision

## MVP intent

This is not a full platform yet. The MVP should prove:

1. A hosted agent can support a real workflow
2. The backend can enforce tool/rule/prompt layers
3. Conversations and workflow data can be stored and analyzed
4. The system can be extended later with more roles, skills, and tools

## Paths

Working Directory:
`/Users/206887576@bwt3.com/Documents/GitHub/Rory_GolfNow_Agent/backend`

Plan File:
`/Users/206887576@bwt3.com/Documents/GitHub/Rory_GolfNow_Agent/docs/superpowers/plans/2026-05-01-phase-2-brs-tools-observability.md`

Handover File:
`/Users/206887576@bwt3.com/Documents/GitHub/Rory_GolfNow_Agent/PHASE_2_HANDOVER.md`

Branch:
`phase-2-brs-observability`
