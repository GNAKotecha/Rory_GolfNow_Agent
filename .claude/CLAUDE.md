Build a lightweight MVP for a hosted internal agent using this architecture:

- **Frontend:** Open WebUI as the chat shell
- **Backend:** custom service that owns product logic
- **Model runtime:** Ollama on a GPU VM
- **Tools:** remote MCP servers + company docs
- **Storage:** database for users, conversations, workflow analytics
- **Goal:** ship a usable prototype quickly, build in small verified steps, and keep the architecture extensible

## Product intent

This is not a full platform yet.

It is an MVP that proves:
1. a hosted agent can support a real workflow,
2. the backend can enforce tool/rule/prompt layers,
3. conversations and workflow data can be stored and analyzed,
4. the system can be extended later with more roles, skills, and tools.

## Build rules

- Work in small tickets only
- After each ticket:
  - implement
  - test
  - verify acceptance criteria
  - summarize what changed
  - stop before moving to the next ticket
- Keep the implementation minimal and clean
- Prefer simple architecture over abstraction-heavy architecture
- Do not build speculative features early
- Keep one clear path working end-to-end before expanding

## Code review rules (subagent-driven-development)

**Maximum 2 iterations per review stage:**

- **Spec review**: Implement → Review → Fix → Re-Review (STOP if still fails - escalate to user)
- **Code quality review**: Review → Fix → Re-Review (STOP if still fails - escalate to user)

**If a review fails twice:**
1. Document what's blocking
2. Present the issue to user with options:
   - Accept the implementation as-is
   - Provide clarification and retry
   - Skip this quality check for now
3. Do NOT continue review loops without user decision

**Rationale**: Prevents perfectionism paralysis. Forces better initial implementations. User is the final decision maker on quality tradeoffs.

## Initial MVP scope

For v1, support:
- authenticated access
- one hosted chat flow
- stored conversations
- backend-owned orchestration
- Ollama integration
- remote MCP integration
- workflow classification / repeated workflow tracking
- one simple admin view for usage

Do not overbuild:
- advanced memory systems
- complex role editing UIs
- multi-role feature completeness
- broad skill marketplaces
- many workflows at once