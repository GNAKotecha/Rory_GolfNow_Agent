---
name: ai-audit
description: Run a structured AI opportunity audit for a company, identifying internal agents, customer-facing agents, MCP/API opportunities, workflow automation, and build-vs-buy recommendations.
---

# AI Audit Skill

## Purpose

Use this skill to audit a company for practical AI opportunities.

**The goal is to identify:**

- Repeatable workflows AI can assist or automate
- Internal copilots/agents that help staff
- Customer-facing AI experiences
- MCP/API opportunities for exposing safe business actions
- Areas where buying existing tools is better than custom building
- Ranked prototype opportunities with clear MVP scope

> This skill should produce a structured audit report, not a vague AI idea list.

---

## When to Use

Use this skill when asked to:

- Find AI opportunities in a business
- Audit workflows for automation potential
- Identify agent/MCP use cases
- Recommend AI prototypes
- Assess whether a company should build or buy AI tools
- Map business workflows into AI-enabled solutions
- Create an AI roadmap for a company

---

## Core Principle

**Do not start by suggesting AI.**

Start by understanding:

1. How the business works
2. Where work is repeated
3. Where information is fragmented
4. Where systems already contain useful data/actions
5. Where customers or staff experience friction
6. Where AI can safely assist, prepare, or execute work

> AI should be mapped to real workflow pain, not added for novelty.

---

# Audit Workflow

## Step 1: Understand the Business

Collect the minimum business context required.

**Identify:**

- Company type
- Customers/users
- Core product or service
- Main teams
- Main workflows
- Main systems/tools
- Current bottlenecks
- Customer friction points

**Output Template:**

\`\`\`markdown
## Business Context

- **Company:**
- **Sector:**
- **Customers:**
- **Core product/service:**
- **Main teams:**
- **Main systems:**
- **Known pain points:**
\`\`\`

---

## Step 2: Map Workflows

For each important workflow, document the current process.

**Use this structure:**

\`\`\`markdown
## Workflow: [Name]

- **Owner:**
- **Trigger:**
- **Current steps:**
- **Systems used:**
- **Inputs:**
- **Outputs:**
- **Frequency:**
- **Current pain:**
- **Decision points:**
- **Failure points:**
- **Customer/staff impact:**
\`\`\`

**Look especially for workflows that involve:**

- Repeated manual effort
- Copy-pasting between systems
- Checking multiple tools
- Repetitive customer questions
- Document review
- Scheduling
- Reporting
- Support triage
- Compliance checks
- Quote/invoice generation
- Account/customer research
- Onboarding

---

## Step 3: Identify AI Opportunity Type

Classify each workflow into one or more opportunity types.

**Use only the relevant labels:**

| Label | Description |
|-------|-------------|
| Knowledge/RAG | Answer questions from documents/data |
| Drafting | Generate text content |
| Classification | Categorize or route items |
| Data extraction | Pull structured data from unstructured sources |
| Decision support | Provide recommendations |
| Tool orchestration | Coordinate multiple system actions |
| Reporting/analytics | Generate insights and reports |
| Customer self-service | Enable direct customer interaction |
| MCP/API exposure | Expose business actions as tools |
| Autonomous workflow | End-to-end automation |

**Examples:**

| Workflow | AI Opportunity Types |
|----------|---------------------|
| Support ticket triage | Knowledge/RAG, Classification, Drafting, Tool orchestration |
| Appointment booking | Customer self-service, Tool orchestration, MCP/API exposure |
| Compliance report generation | Data extraction, Reporting/analytics, Decision support |

---

## Step 4: Assign Automation Level

Every opportunity must be assigned one safety level.

| Level | Name | Description |
|-------|------|-------------|
| **Level 1** | Assist | AI suggests, human acts |
| **Level 2** | Approve | AI prepares the action, human approves before execution |
| **Level 3** | Automate | AI executes the action automatically within strict rules |

**Defaults:**

- Level 1 for early prototypes
- Level 2 for write actions
- Level 3 only for low-risk, reversible, deterministic actions

**Examples:**

| Action | Level |
|--------|-------|
| Draft customer reply | Level 1 |
| Create support ticket | Level 2 |
| Send meeting reminder | Level 3 |
| Cancel booking | Level 2 |
| Issue refund | Level 2 or avoid |

---

## Step 5: Identify MCP/API Opportunities

Look for systems where AI could safely call tools or expose actions.

**An MCP/API opportunity exists when:**

- Useful data/actions exist in a system
- Users want natural language access
- The workflow is currently UI-heavy or manual
- Actions can be wrapped safely as tools
- Permissions and audit logs can be enforced

**Template for each MCP opportunity:**

\`\`\`markdown
## MCP/API Opportunity: [Name]

**Purpose:**
**Users:**
**Systems connected:**

### Candidate Tools

- \`get_[resource]\`
- \`search_[resource]\`
- \`create_[resource]\`
- \`update_[resource]\`
- \`generate_[report]\`
- \`send_[message]\`

### Safety Rules

- **Read actions:**
- **Draft actions:**
- **Write actions:**
- **Blocked actions:**
\`\`\`

**Example:**

\`\`\`markdown
## MCP/API Opportunity: Appointment Booking

**Purpose:** Allow staff or authenticated customers to check availability 
and book appointments through AI tools.

### Candidate Tools

- \`search_available_slots\`
- \`get_service_types\`
- \`book_appointment\`
- \`reschedule_appointment\`
- \`cancel_appointment\`
- \`send_confirmation\`

### Safety Rules

- **Read actions:** Searching availability is automatic
- **Write actions:** Booking requires customer confirmation
- **Write actions:** Cancelling requires confirmation
- **Blocked actions:** Refunds require human approval
\`\`\`

---

## Step 6: Score Opportunities

Score each opportunity from 1–5.

| Opportunity | Business Value | Frequency | Time Saved | Customer Impact | Feasibility | Risk | Complexity | Recommendation |
|-------------|:--------------:|:---------:|:----------:|:---------------:|:-----------:|:----:|:----------:|----------------|
| *Example*   | 4              | 5         | 4          | 3               | 4           | 2    | 3          | Quick Win      |

**Scoring Guidance:**

| Criterion | What to Assess |
|-----------|----------------|
| Business Value | Revenue, cost saving, strategic value |
| Frequency | How often the workflow happens |
| Time Saved | Manual effort reduced |
| Customer Impact | Improves customer speed/experience |
| Feasibility | Data/API/process readiness |
| Risk | Potential damage if wrong |
| Complexity | Implementation difficulty |

**Classifications:**

| Classification | Criteria |
|----------------|----------|
| **Quick Win** | High value, high feasibility, low/medium risk |
| **Strategic Prototype** | High value, medium/high complexity, needs careful design |
| **Later** | Useful but not urgent |
| **Avoid** | Low value, high risk, poor data, unclear workflow |

---

## Step 7: Build vs Buy Recommendation

For each opportunity, decide whether to:

- **Buy/configure** existing AI tool
- **Build** custom workflow agent
- **Build MCP/API** integration layer
- **Hybrid:** buy AI interface, build custom tools/MCP
- **Avoid** for now

**When to Buy/Configure (generic needs):**

- Document Q&A
- Meeting summaries
- Generic support chatbot
- CRM drafting
- Simple automations
- Standard helpdesk workflows

**When to Build/Customise (proprietary needs):**

- Proprietary systems
- Custom APIs
- Domain-specific rules
- Complex permissions
- Customer-facing product actions
- Workflow-specific approvals
- Audit requirements
- Cross-system orchestration

> **Preferred recommendation:** Buy the generic AI interface where possible. Build the proprietary workflow/tool/MCP layer where needed.

---

## Step 8: Define Prototype Candidates

For the top 1–3 opportunities, define a prototype.

**Template:**

\`\`\`markdown
## Prototype Candidate: [Name]

- **Goal:**
- **Users:**
- **Workflow:**
- **Systems connected:**
- **Data required:**
- **Tools required:**
- **Automation level:**
- **Approval rules:**
- **Demo flow:**
- **Success criteria:**
- **Risks:**
- **MVP scope:**
- **Future expansion:**
\`\`\`

> Prototype should be small enough to demo quickly. Avoid proposing a large platform as the first step.

---

# Final Output Format

Produce the audit report using this structure:

\`\`\`markdown
# AI Opportunity Audit: [Company]

## 1. Executive Summary

Briefly explain:
- Strongest AI opportunities
- Recommended first prototype
- Build-vs-buy position
- Main risks or dependencies

## 2. Business Context

- **Company:**
- **Sector:**
- **Customers:**
- **Core workflows:**
- **Main systems:**
- **Known pain points:**

## 3. Workflow Map

| Workflow | Owner | Systems | Pain | Frequency | AI Opportunity |
|----------|-------|---------|------|-----------|----------------|

## 4. Opportunity Matrix

| Opportunity | Type | Automation Level | Value | Feasibility | Risk | Recommendation |
|-------------|------|:----------------:|:-----:|:-----------:|:----:|----------------|

## 5. MCP/API Opportunities

For each relevant system:
- Proposed MCP tools
- Users
- Permissions
- Approval rules
- Risks

## 6. Build vs Buy Recommendation

Classify opportunities into:
- Buy/configure
- Custom build
- MCP/API layer
- Hybrid
- Avoid for now

## 7. Recommended Prototypes

Include the top 1–3 prototypes with:
- Goal
- MVP scope
- Tools needed
- Demo flow
- Success criteria
- Risk controls

## 8. Roadmap

### Phase 1 — Discovery / Quick Wins
### Phase 2 — Prototype
### Phase 3 — Pilot
### Phase 4 — Production Hardening

## 9. Next Steps

List concrete actions required to proceed.
\`\`\`

---

# Guardrails

## Do

- Anchor every AI idea to a real workflow
- Separate assist, approve, and automate
- Identify required tools/data/systems
- Highlight MCP/API opportunities clearly
- Recommend buying where appropriate
- Prioritise small prototypes
- Include risks and approval rules
- Be specific about demo flows

## Do Not

- Suggest AI for everything
- Recommend full automation for high-risk workflows
- Ignore permissions, audit logs, or approval gates
- Assume APIs exist without checking
- Build a platform before proving one workflow
- Replace existing tools when configuration would solve the problem
- Pitch MCP unless there are real data/actions worth exposing

---

# Common Opportunity Patterns

## Internal Agent Patterns

| Agent | Capabilities |
|-------|--------------|
| **Support Copilot** | Diagnose issues, search docs/tickets, draft replies, recommend escalation |
| **Sales Agent** | Prepare account briefings, summarise CRM activity, draft follow-ups |
| **QA Agent** | Generate test plans from tickets/diffs, run tests, create QA reports |
| **Ops Agent** | Handle repetitive admin, document checks, approvals, reminders |
| **Knowledge Agent** | Answer internal questions using trusted company sources |

## Customer-Facing Agent Patterns

| Agent | Capabilities |
|-------|--------------|
| **Booking Agent** | Check availability, book/reschedule appointments, send confirmations |
| **Quote Agent** | Collect requirements, estimate price, draft quote, request approval |
| **Support Agent** | Answer product questions, check account state, create tickets |
| **Account Assistant** | Let customers ask about invoices, jobs, reports, usage, or status |
| **Onboarding Agent** | Guide customers through setup and collect missing information |

## MCP/API Patterns

| Category | Example Tools |
|----------|---------------|
| **Read tools** | \`get_customer\`, \`search_records\`, \`list_bookings\`, \`get_invoice\`, \`get_account_status\` |
| **Draft tools** | \`draft_email\`, \`draft_quote\`, \`generate_report\`, \`prepare_ticket\` |
| **Write tools** | \`create_booking\`, \`update_record\`, \`create_ticket\`, \`send_message\`, \`assign_task\` |
| **High-risk tools** | \`cancel_booking\`, \`issue_refund\`, \`delete_record\`, \`change_permissions\` |

---

# Example Output

## Opportunity: Customer Appointment Booking

**Current workflow:**
Customers call or email to book appointments. Staff manually check availability, ask follow-up questions, create the appointment, and send confirmation.

**AI type:**
- Customer self-service
- Tool orchestration
- MCP/API exposure

**Automation level:**
Level 2 — AI prepares booking, customer confirms before final action.

**Candidate tools:**
- \`search_available_slots\`
- \`get_service_types\`
- \`book_appointment\`
- \`reschedule_appointment\`
- \`send_confirmation\`

**Recommendation:** Strategic prototype

**Reason:** High customer impact and clear workflow, but requires reliable availability data, authentication, confirmation rules, and audit logging.
