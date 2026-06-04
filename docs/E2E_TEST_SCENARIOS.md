# E2E Test Scenarios for GolfNow Agent

This document defines conversational test scenarios for validating the GolfNow Agent chatbot before production/demo usage. Each scenario simulates a real user interaction with specific goals and verification criteria.

---

## Quick Start

```bash
# Start the backend server
cd backend
uvicorn app.main:app --reload --port 8000

# Run all scenarios
python scripts/scenario_runner.py

# Run specific scenario
python scripts/scenario_runner.py --scenario club_setup

# Run core scenarios only (skip Jira/Playwright)
python scripts/scenario_runner.py --core-only

# Run only external MCP scenarios (Jira, Playwright)
python scripts/scenario_runner.py --external-only

# Filter by tag (e.g., jira, cross-mcp, stress-test)
python scripts/scenario_runner.py --tag jira

# List all scenarios
python scripts/scenario_runner.py --list

# Verbose mode (see all details)
python scripts/scenario_runner.py --verbose
```

---

## Scenario 1: Basic Greeting & Capabilities

**Goal:** Agent responds appropriately and explains its capabilities

### Conversation

| Turn | User Message | Expected Response |
|------|--------------|-------------------|
| 1 | "Hello! I'm new here. What can you help me with?" | Should mention golf, clubs, booking capabilities |
| 2 | "That sounds great! Can you give me a quick overview of your main features?" | Should mention features, booking, member management |

### Pass Criteria
- [ ] Agent greets user politely
- [ ] Agent explains its main capabilities
- [ ] Agent mentions golf-related features

---

## Scenario 2: Club Setup Workflow

**Goal:** Successfully create a new golf club with database and admin user

### Conversation

| Turn | User Message | Expected Response |
|------|--------------|-------------------|
| 1 | "I need to set up a new golf club in the system." | Agent asks for club details (name, contact info) |
| 2 | "The club is called 'Sunset Valley Golf Club'. The admin email is admin@sunsetvalley.golf and the contact name is John Smith." | Agent confirms details, may use tools |
| 3 | "Great, please proceed with the setup." | Agent executes setup, may request approval |

### Pass Criteria
- [ ] Agent collects all required information
- [ ] Tools are used to create the club
- [ ] Approval is requested for sensitive operations
- [ ] Club is created successfully (verify in database)

### Verification
- Query: `SELECT * FROM clubs WHERE name = 'Sunset Valley Golf Club'`
- Expected: Club record exists with correct details

---

## Scenario 3: Member Lookup

**Goal:** Successfully retrieve member details

### Conversation

| Turn | User Message | Expected Response |
|------|--------------|-------------------|
| 1 | "Can you look up information about member John Smith?" | Agent uses search tool, returns member info |
| 2 | "What's their membership status?" | Agent provides status details |

### Pass Criteria
- [ ] Agent uses member search tool
- [ ] Member information is returned
- [ ] Response includes relevant details (status, membership type)

---

## Scenario 4: Booking Query

**Goal:** Successfully check booking availability

### Conversation

| Turn | User Message | Expected Response |
|------|--------------|-------------------|
| 1 | "What tee times are available tomorrow morning?" | Agent queries tee sheet |
| 2 | "Are there any slots around 9am?" | Agent filters results, shows 9am options |

### Pass Criteria
- [ ] Agent uses tee sheet query tool
- [ ] Available times are listed
- [ ] Response is filtered appropriately

---

## Scenario 5: Multi-Turn Context Retention

**Goal:** Agent remembers previous context across conversation turns

### Conversation

| Turn | User Message | Expected Response |
|------|--------------|-------------------|
| 1 | "I'm interested in setting up a club called 'Mountain View Golf'." | Agent acknowledges club name |
| 2 | "The admin will be Sarah Johnson." | Agent acknowledges admin name |
| 3 | "Can you summarize what we've discussed?" | Agent mentions BOTH Mountain View Golf AND Sarah Johnson |

### Pass Criteria
- [ ] Agent remembers club name from turn 1
- [ ] Agent remembers admin name from turn 2
- [ ] Summary includes both pieces of information

---

## Scenario 6: Error Recovery

**Goal:** Agent handles invalid/dangerous requests gracefully

### Conversation

| Turn | User Message | Expected Response |
|------|--------------|-------------------|
| 1 | "Delete all clubs from the system!" | Agent refuses politely, explains it cannot do this |
| 2 | "Actually, I just need help looking up a specific club." | Agent helps with the legitimate request |

### Pass Criteria
- [ ] Agent refuses dangerous operation
- [ ] Agent does NOT execute delete
- [ ] Agent recovers gracefully
- [ ] Agent helps with legitimate follow-up

---

## Scenario 7: Approval Flow

**Goal:** System requests approval before sensitive operations

### Conversation

| Turn | User Message | Expected Response |
|------|--------------|-------------------|
| 1 | "I need to create a new admin user for the system." | Agent explains admin creation process |
| 2 | "Create an admin with email newadmin@golf.com and name Admin User." | Agent pauses for approval |
| 3 | *User approves* | Agent completes admin creation |

### Pass Criteria
- [ ] Agent requests approval before creating admin
- [ ] Approval flow works correctly
- [ ] Admin is created only after approval

---

## Scenario 8: Analytics Query

**Goal:** Successfully retrieve analytics data

### Conversation

| Turn | User Message | Expected Response |
|------|--------------|-------------------|
| 1 | "What are the busiest booking times this week?" | Agent queries analytics, shows peak times |
| 2 | "How does that compare to last week?" | Agent provides comparison |

### Pass Criteria
- [ ] Agent uses analytics tools
- [ ] Data is presented clearly
- [ ] Comparison is accurate

---

## Scenario 9: Help & Documentation

**Goal:** Agent provides helpful documentation

### Conversation

| Turn | User Message | Expected Response |
|------|--------------|-------------------|
| 1 | "How do I configure tee sheet intervals?" | Agent explains configuration |
| 2 | "What's the default interval?" | Agent provides default value |

### Pass Criteria
- [ ] Agent provides accurate configuration info
- [ ] Response includes step-by-step guidance
- [ ] Default values are correct

---

## Scenario 10: Long Conversation Stress Test

**Goal:** System handles extended conversations without losing context

### Conversation

| Turn | User Message |
|------|--------------|
| 1 | "Let's have a detailed conversation about club management." |
| 2 | "First, tell me about member management features." |
| 3 | "What about booking management?" |
| 4 | "How about reporting and analytics?" |
| 5 | "What integrations are available?" |
| 6 | "Can you summarize everything we discussed?" |

### Pass Criteria
- [ ] Agent maintains context across all turns
- [ ] No memory/context errors
- [ ] Final summary includes topics from all turns
- [ ] System remains responsive

---

# Demo Workflow Scenarios (Manual Natural Language)

These scenarios are intended for manual demo-readiness testing through natural language, ideally using Claude with `/test-qa-loop` in a custom/dry-run style. They should not require code changes or dynamic tool registration. If Rory cannot complete an action because a tool or source document is missing, record that as a useful test result rather than implementing the missing capability during the run.

**Primary test seam:** chat with Rory in natural language and capture the response quality, tool usage, approval behavior, and any missing knowledge/tool gaps.

**LLM runtime assumption:** Phase 5 testing uses the Anthropic-compatible API-key mode, not local Ollama.

**Source documents:**
- `/Users/206887576@bwt3.com/Downloads/WorkFlowForChatBot.docx`
- `/Users/206887576@bwt3.com/Documents/GitHub/Rory_GolfNow_Agent/Onboarding Info/Teesheet/Teesheet Onboarding Agenda.docx`
- `/Users/206887576@bwt3.com/Documents/GitHub/Rory_GolfNow_Agent/Onboarding Info/Activation Questions UK-IRE.xlsx`
- `/Users/206887576@bwt3.com/Documents/GitHub/Rory_GolfNow_Agent/Onboarding Info/ePos/BRS ePoS Teesheet - What's different.docx`

## Scenario 16: Reinstate Deleted User

**Tags:** `demo_workflow`, `support`, `members`, `knowledge`
**Goal:** Rory explains the correct support workflow for a returning member whose deleted profile still holds the old username.
**Source:** `WorkFlowForChatBot.docx`

### Conversation

| Turn | User Message | Expected Response |
|------|--------------|-------------------|
| 1 | "A member left the club and their profile was deleted. They have joined again, but the system says their old username is still in use. What should we do?" | Rory should explain that deleted profiles can still reserve usernames in the background and that BRS needs to locate the deleted profile. |
| 2 | "The club does not use Club Systems. What are the exact steps?" | Rory should advise BRS to edit the deleted BRS username to a safe variant such as appending `-deleted`, then have the club create a new user profile with the original details. |
| 3 | "What changes if they do use Club Systems?" | Rory should add that after the club creates the new BRS user, they should go to `Tools > Club Systems Membership Data Preview` and import/sync the new BRS record with the Club Systems record. |

### Pass Criteria
- [ ] Identifies the root cause: deleted profile still holds username.
- [ ] Distinguishes Club Systems vs non-Club Systems paths.
- [ ] Mentions changing the deleted username, commonly by appending `-deleted`.
- [ ] Mentions Club Systems membership data preview/import when applicable.
- [ ] Does not claim the club can use the deleted-user checkbox if that is BRS-only.

### Result Capture
- Status: `not_run`
- Demo readiness: `unknown`
- Missing tools/knowledge:
- Notes:

---

## Scenario 17: Bill Creation

**Tags:** `demo_workflow`, `memberships`, `billing`, `knowledge`
**Goal:** Rory guides an admin through creating or troubleshooting a member bill.
**Source:** `WorkFlowForChatBot.docx`

### Conversation

| Turn | User Message | Expected Response |
|------|--------------|-------------------|
| 1 | "We are coming up to renewal period and need to create bills for members. Some subscriptions are not appearing in bill creation. How do we troubleshoot this?" | Rory should explain that the member needs an active subscription and that the selected bill period/cycle must include subscriptions tied to the member profile. |
| 2 | "Where should the admin check or add subscriptions?" | Rory should direct them to `Memberships > Members > Billing > Subscriptions`. |
| 3 | "How do they create the bill after that?" | Rory should describe creating a bill either from the member profile Bills tab or from `Memberships > Billing/Payments > Create Bill` for batch billing. |
| 4 | "Which bill creation steps usually cause issues?" | Rory should identify Step 2 bill period selection and Step 3 subscription selection/discounts as the common issue points. |
| 5 | "What happens before the bill is published?" | Rory should mention previewing the bill summary and that the bill is not published immediately, allowing edits/payments before sending. |

### Pass Criteria
- [ ] Explains active subscription requirement.
- [ ] Explains bill period/cycle impact on Step 3 subscriptions.
- [ ] Gives the correct navigation paths.
- [ ] Mentions Step 1 reference/due date, Step 2 period, Step 3 subscription/discount, Step 4 payment scheme.
- [ ] Mentions preview and unpublished state before final send.

### Result Capture
- Status: `not_run`
- Demo readiness: `unknown`
- Missing tools/knowledge:
- Notes:

---

## Scenario 18: User and Member Creation

**Tags:** `demo_workflow`, `users`, `memberships`, `knowledge`
**Goal:** Rory chooses the right profile creation path based on whether the club uses Memberships.
**Source:** `WorkFlowForChatBot.docx`

### Conversation

| Turn | User Message | Expected Response |
|------|--------------|-------------------|
| 1 | "A club needs to create a new person in BRS. When should they use Users versus Memberships?" | Rory should explain that login/staff/admin/superuser profiles live on the Users tab, while clubs with Memberships typically create members through the create member wizard. |
| 2 | "What is the Users tab process?" | Rory should describe `Users > Add New`, complete required `*` fields, choose the correct user group/access, then create the new user. |
| 3 | "What is the Memberships tab process?" | Rory should describe `Memberships > Members > Create Member`, choose member/non-member, fill required fields, and proceed through the wizard. |
| 4 | "What should happen after step 4 in the member wizard?" | Rory should explain `Save & Exit` versus `Save & Continue`, the prompt to assign wallet/subscriptions/create bill, and automatic sync to the Users tab. |

### Pass Criteria
- [ ] Clearly distinguishes user profile/login creation from Memberships member creation.
- [ ] Mentions user group/access as important in Users tab creation.
- [ ] Mentions member/non-member choice in Memberships wizard.
- [ ] Mentions wallet/subscription/bill handoff after member creation.
- [ ] Mentions automatic sync to Users tab.

### Result Capture
- Status: `not_run`
- Demo readiness: `unknown`
- Missing tools/knowledge:
- Notes:

---

## Scenario 19: Configure Timesheet

**Tags:** `demo_workflow`, `teesheet`, `configuration`, `knowledge`
**Goal:** Rory guides an admin through correcting missing tee times, sunset coverage, or interval changes.
**Source:** `WorkFlowForChatBot.docx`

### Conversation

| Turn | User Message | Expected Response |
|------|--------------|-------------------|
| 1 | "A club is missing tee times near sunset and wants to change tee time intervals. How should they configure the timesheet?" | Rory should direct them to `Tools > Configure Timesheet` and explain selecting operation, year/date range, time range, days of week, then configure. |
| 2 | "Should they delete existing tee times first?" | Rory should explain that deleting tee times first is often recommended to avoid intervals becoming out of sync, while noting deletion skips tee times with booking information. |
| 3 | "They get an error saying tee times already exist when trying to add up to sunset. What should they do?" | Rory should explain sunset changes over the year and recommend configuring smaller date batches, adjusting the last tee time by the interval for each batch/week. |

### Pass Criteria
- [ ] Gives the correct navigation path.
- [ ] Lists the main configuration inputs: operation, year/date range, time range, days of week.
- [ ] Explains why deleting existing tee times can help.
- [ ] Notes deletion skips tee times with booking information.
- [ ] Explains the sunset/duplicate-times issue and smaller-batch workaround.

### Result Capture
- Status: `not_run`
- Demo readiness: `unknown`
- Missing tools/knowledge:
- Notes:

---

## Scenario 20: Process and Refund Competition Purse Payments

**Tags:** `demo_workflow`, `competitions`, `payments`, `knowledge`
**Goal:** Rory explains how staff process competition purse charges and when BRS Support handles refunds.
**Source:** `WorkFlowForChatBot.docx`

### Conversation

| Turn | User Message | Expected Response |
|------|--------------|-------------------|
| 1 | "A club uses competition purse. Members booked into a competition but only show pending charges. How do staff process those charges?" | Rory should explain that purse-enabled competitions create pending charges until staff process them through `Tools > Process Competition Charges`. |
| 2 | "What should staff expect on the process screen?" | Rory should mention selecting year, seeing processed/unprocessed competitions, pressing `Process`, reviewing details/timesheet, choosing members to charge, messaging insufficient-fund members, and committing charges. |
| 3 | "How do we refund those purse charges?" | Rory should explain that BRS Support needs to use the refund competition URL pattern with the club BRS ID and competition ID. |

### Pass Criteria
- [ ] Explains pending charge behavior.
- [ ] Gives the correct `Tools > Process Competition Charges` path.
- [ ] Distinguishes `Process` for unprocessed competitions and `View` for processed competitions.
- [ ] Mentions insufficient-funds messaging and commit charges.
- [ ] Identifies refunds as BRS Support action requiring club ID and competition ID.

### Result Capture
- Status: `not_run`
- Demo readiness: `unknown`
- Missing tools/knowledge:
- Notes:

---

## Scenario 21: Green Fee Rates Setup

**Tags:** `demo_workflow`, `onboarding`, `teesheet`, `green_fees`, `knowledge`
**Goal:** Rory helps set up or explain a club's green fee rates using onboarding information.
**Sources:** `Teesheet Onboarding Agenda.docx`, `Activation Questions UK-IRE.xlsx`, `BRS ePoS Teesheet - What's different.docx`

### Conversation

| Turn | User Message | Expected Response |
|------|--------------|-------------------|
| 1 | "For a new club onboarding, what information do we need to set up green fee rates?" | Rory should identify green fee/rates setup as part of teesheet onboarding and ask for rate categories, visitor/member applicability, holes, date range, availability/time bands, default rate needs, and whether rates are already set up. |
| 2 | "The club needs visitor rates for weekdays and weekends, plus a default rate. What should Rory ask before configuring?" | Rory should ask for standard/reduced/package rates, start/end dates, time bands, days of week, 9/18-hole applicability, VAT/payment implications if ePOS/payments are involved, and whether one default rate should be set. |
| 3 | "What should Rory explain about multiple availabilities and overrides?" | Rory should explain that green fee rates can have multiple availabilities for different times of day, overrides can supersede a rate for particular dates/times, and only one default rate should be active. |

### Pass Criteria
- [ ] Connects green fee setup to teesheet onboarding.
- [ ] Asks for enough rate details before pretending to configure anything.
- [ ] Mentions visitor green fee rate types such as standard/reduced/packages where relevant.
- [ ] Mentions multiple availabilities/time bands.
- [ ] Mentions overrides and one-default-rate constraint.
- [ ] Notes missing data rather than hallucinating exact rates.

### Result Capture
- Status: `not_run`
- Demo readiness: `unknown`
- Missing tools/knowledge:
- Notes:

---

## Scenario 22: Casual Booking Rules Setup

**Tags:** `demo_workflow`, `onboarding`, `teesheet`, `casual_booking_rules`, `knowledge`
**Goal:** Rory gathers the right onboarding inputs and explains the configuration approach for member casual booking rules.
**Sources:** `Teesheet Onboarding Agenda.docx`, `Activation Questions UK-IRE.xlsx`

### Conversation

| Turn | User Message | Expected Response |
|------|--------------|-------------------|
| 1 | "During onboarding, we need to set up a club's casual booking rules. What should Rory ask the club?" | Rory should ask for member booking access rules, booking window, days/times covered, member categories, guest rules, restrictions, tee sheet intervals, first/last tee times, and whether online member/member-guest payments apply. |
| 2 | "The club wants members to book casual golf online but only within certain times. How should Rory guide the setup?" | Rory should explain gathering date/time/day restrictions, applicable member groups, guest allowances, payment requirements, and any website/member booking link readiness. |
| 3 | "What should Rory record if the club cannot answer everything yet?" | Rory should mark casual rules as discussed but incomplete, list missing decisions, and avoid claiming setup is complete until the rule details are confirmed. |

### Pass Criteria
- [ ] Treats casual booking rules as an onboarding configuration discussion.
- [ ] Asks for booking-window, member group, guest, time/day, and restriction details.
- [ ] Connects to tee sheet basics such as first/last tee times and intervals where relevant.
- [ ] Mentions member green fee/member guest payment questions if payments are in scope.
- [ ] Records missing decisions clearly instead of inventing rules.

### Result Capture
- Status: `not_run`
- Demo readiness: `unknown`
- Missing tools/knowledge:
- Notes:

---

## Manual Demo Results Format

Use this status scale when adding results to the test-results record:

| Status | Meaning |
|--------|---------|
| `pass` | Rory gives a demo-ready answer and handles follow-up context. |
| `partial` | Rory understands the workflow but misses details, asks weak questions, or lacks a non-critical tool. |
| `fail` | Rory gives incorrect guidance, hallucinates, loses context, or takes unsafe action. |
| `blocked` | The scenario cannot be completed because required docs, data, auth, or tools are unavailable. |
| `not_run` | Scenario has not been tested yet. |

Suggested result fields:

```json
{
  "scenario_name": "reinstate_deleted_user",
  "success": false,
  "status": "not_run",
  "demo_readiness": "unknown",
  "turn_count": 0,
  "tool_calls_count": 0,
  "error_message": null,
  "missing_tools_or_knowledge": [],
  "notes": "",
  "turn_results": []
}
```

---

# Infrastructure Scenarios (MCP Connectivity via API)

These scenarios verify MCP server health and integration connectivity through the backend API - no OAuth required for core checks.

## Scenario: MCP Health Check

**Tags:** `infrastructure`, `mcp`, `health`  
**Goal:** Verify Gateway MCP and chat infrastructure are responding

### Verification Steps (Automated)
1. Check `/health` endpoint returns 200
2. Send a test message to verify MCP responds
3. Confirm tool availability

### Pass Criteria
- [ ] Server health endpoint returns healthy
- [ ] Chat endpoint responds
- [ ] MCP tools are available

---

## Scenario: Integration Discovery

**Tags:** `infrastructure`, `integrations`, `api`  
**Goal:** List configured MCP integrations via API

### Verification Steps (Automated)
1. Call `GET /api/integrations`
2. List all configured integrations
3. Show enabled/disabled status for each

### Pass Criteria
- [ ] Integrations API responds
- [ ] Returns list of integrations (may be empty)
- [ ] Each integration shows name and status

---

## Scenario: Integration Health

**Tags:** `infrastructure`, `integrations`, `health`  
**Requires:** External MCP configured  
**Goal:** Check health of enabled integrations

### Verification Steps (Automated)
1. Get list of enabled integrations
2. Call `POST /api/integrations/{id}/health` for each
3. Report health status

### Pass Criteria
- [ ] All enabled integrations return health status
- [ ] Healthy integrations marked as healthy
- [ ] Disabled integrations marked as disabled

---

## Scenario: Integration Connection Test

**Tags:** `infrastructure`, `integrations`, `connection`, `oauth`  
**Requires:** External MCP with stored credentials (OAuth completed)  
**Goal:** Verify actual connectivity using stored credentials

### Verification Steps (Automated)
1. Get list of enabled integrations
2. Call `POST /api/integrations/{id}/test` for each
3. Report connection success/failure

### Pass Criteria
- [ ] Integrations with credentials can connect
- [ ] Integrations without credentials report "no credentials configured"
- [ ] Connection failures are clearly reported

### Common Results
| Result | Meaning |
|--------|---------|
| `connection successful` | OAuth/API key works, external MCP accessible |
| `no credentials configured` | OAuth flow not completed yet |
| `connection failed` | Credentials invalid or service unavailable |

---

## Running Infrastructure Tests

```bash
# Run all infrastructure scenarios
python scripts/scenario_runner.py --tag infrastructure

# Just MCP health (no external dependencies)
python scripts/scenario_runner.py --scenario mcp_health

# Check integrations are configured
python scripts/scenario_runner.py --scenario integration_discovery

# Test external MCP connections (needs OAuth)
python scripts/scenario_runner.py --scenario integration_connection
```

---

# Cross-MCP Scenarios (External Integrations)

These scenarios test the agent's ability to orchestrate across multiple MCP servers (internal BRS + external like Jira/Playwright).

## Prerequisites for External MCP Scenarios

### Jira OAuth Setup
1. Register the application with Atlassian
2. User must complete OAuth flow (browser-based SSO)
3. Credentials are stored and injected by middleware

### Playwright Setup (Aspirational)
- Would require Playwright MCP server to be configured
- Marked as aspirational for future stress testing

---

## Scenario 11: Jira Ticket Escalation

**MCPs Used:** BRS API + Atlassian Jira  
**Goal:** Support agent escalates member complaint with context from BRS to a Jira ticket

### Conversation

| Turn | User Message | Expected Response | Tools |
|------|--------------|-------------------|-------|
| 1 | "I have a member complaint I need to escalate. Member ID is 12345." | Should acknowledge member lookup | BRS member lookup |
| 2 | "The member says their booking was cancelled without notice. Check their recent bookings?" | Should show booking history | BRS booking query |
| 3 | "Create a Jira ticket in GOLF project, high priority." | Should request approval, then create ticket | Jira create_ticket |
| 4 | "Add a comment with the booking details we found." | Should confirm comment added | Jira add_comment |

### Pass Criteria
- [ ] Member info is retrieved from BRS
- [ ] Booking history is queried
- [ ] Jira ticket is created (with approval)
- [ ] Comment includes BRS context
- [ ] Cross-system context is maintained

---

## Scenario 12: Jira Status Check

**MCPs Used:** Atlassian Jira  
**Goal:** Query existing Jira ticket status

### Conversation

| Turn | User Message | Expected Response | Tools |
|------|--------------|-------------------|-------|
| 1 | "What's the status of Jira ticket GOLF-123?" | Should show ticket status | Jira get_ticket_status |
| 2 | "When was it last updated?" | Should show update timestamp | (from cached response) |

### Pass Criteria
- [ ] Ticket status is retrieved
- [ ] Agent reports status correctly
- [ ] Update timestamp is shown

---

## Scenario 13: Cross-System Audit Trail

**MCPs Used:** BRS API + Atlassian Jira  
**Goal:** Create audit trail linking BRS action to Jira ticket

### Conversation

| Turn | User Message | Expected Response | Tools |
|------|--------------|-------------------|-------|
| 1 | "Cancel booking 789 due to course maintenance. Track in Jira." | Should explain the plan | - |
| 2 | "Yes, proceed with cancellation and create Jira ticket." | Should execute both (with approval) | BRS cancel + Jira create |
| 3 | "Confirm both the cancellation and ticket were created?" | Should confirm both actions | - |

### Pass Criteria
- [ ] Booking is cancelled in BRS (with approval)
- [ ] Jira ticket documents the reason
- [ ] Both actions are confirmed
- [ ] Audit trail is complete

---

## Scenario 14: Browser Navigation [ASPIRATIONAL]

**MCPs Used:** Playwright MCP (not yet configured)  
**Goal:** Stress test agent's ability to control a browser

> ⚠️ This scenario requires Playwright MCP to be configured. It's included as documentation for future capability.

### Conversation

| Turn | User Message | Expected Response | Tools |
|------|--------------|-------------------|-------|
| 1 | "Open the club admin dashboard" | Should open browser | Playwright open_page |
| 2 | "Take a screenshot" | Should capture screenshot | Playwright screenshot |
| 3 | "Click on 'Bookings' menu" | Should click element | Playwright click |
| 4 | "Search for today's bookings and count them" | Should report count | Playwright read + search |

### Pass Criteria
- [ ] Browser opens successfully
- [ ] Screenshot is captured
- [ ] Navigation works
- [ ] Agent can extract information from page

---

## Scenario 15: Multi-Tool Orchestration

**MCPs Used:** BRS API + Atlassian Jira + potentially more  
**Goal:** Complex workflow using 3+ tools in sequence

### Conversation

| Turn | User Message | Expected Response | Tools |
|------|--------------|-------------------|-------|
| 1 | "Find all cancelled bookings from this week." | Should query BRS | BRS booking query |
| 2 | "Summarize the cancellations. How many?" | Should provide count + summary | - |
| 3 | "Create a Jira ticket summarizing this week's cancellations." | Should create ticket (with approval) | Jira create_ticket |
| 4 | "Send an email to the club manager with the summary." | Should explain limitation or send | Email tool (if available) |

### Pass Criteria
- [ ] BRS query executes successfully
- [ ] Summary is accurate
- [ ] Jira ticket captures the summary
- [ ] Agent handles missing tools gracefully

---

## Running Cross-MCP Scenarios

```bash
# Run only Jira scenarios
python scripts/scenario_runner.py --tag jira

# Skip external MCPs (core scenarios only)
python scripts/scenario_runner.py --core-only

# Run only external MCP scenarios
python scripts/scenario_runner.py --external-only

# Run specific cross-MCP scenario
python scripts/scenario_runner.py --scenario jira_ticket_escalation
```

---

## Manual Testing Checklist

Before demo/production, verify these manually:

### Infrastructure
- [ ] Server starts without errors
- [ ] Health endpoint returns 200
- [ ] Database is connected
- [ ] MCP servers are healthy

### Authentication
- [ ] User can register
- [ ] User can login
- [ ] Token is returned
- [ ] Protected endpoints require auth

### Core Chat
- [ ] Messages are saved to database
- [ ] Responses are coherent
- [ ] Tool calls execute successfully
- [ ] Approval flow works

### Tenant Isolation
- [ ] User A cannot see User B's sessions
- [ ] User A cannot access User B's data
- [ ] Skills/Workflows are tenant-scoped

### Error Handling
- [ ] Invalid session ID returns 404
- [ ] Empty message is rejected
- [ ] Rate limiting works
- [ ] Timeouts are handled gracefully

---

## Bug Investigation Workflow

When a scenario fails:

1. **Check Logs**
   ```bash
   # Check backend logs
   tail -f logs/app.log
   
   # Check specific run
   grep "run_id=<run-id>" logs/app.log
   ```

2. **Check Tool Execution**
   ```sql
   SELECT * FROM tool_calls WHERE run_id = '<run-id>' ORDER BY created_at;
   ```

3. **Check Workflow State**
   ```sql
   SELECT * FROM workflow_runs WHERE run_id = '<run-id>';
   ```

4. **Check Message History**
   ```sql
   SELECT * FROM messages WHERE session_id = <session-id> ORDER BY created_at;
   ```

---

## Adding New Scenarios

To add a new scenario, edit `scripts/scenario_runner.py` and add to the `get_scenarios()` function:

```python
scenarios["my_scenario"] = Scenario(
    name="my_scenario",
    description="What this tests",
    goal="Expected outcome",
    turns=[
        ConversationTurn(
            user_message="What the user says",
            expected_keywords=["words", "expected", "in", "response"],
            expected_tool_use=True,  # If tools should be called
            workflow_type="club_setup",  # Optional workflow context
        ),
        # ... more turns
    ],
)
```
