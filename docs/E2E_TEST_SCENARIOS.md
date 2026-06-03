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
