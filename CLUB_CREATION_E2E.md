You are helping test and improve an agent/tool harness for BRS/GolfNow club onboarding workflows.

Goal:
Run an end-to-end “happy path” proof of concept through the agent, starting from club creation and ending with a bookable tee sheet, rates, casual bookings, competition entry, and validation bookings.

Important principle:
Do NOT hardcode this workflow into the agent. Improvements should make the tools, schemas, descriptions, error handling, and harness more flexible and generally useful. The agent should become better at discovering required fields, understanding tool capabilities, retrying with corrected inputs, and surfacing missing tool support — not specifically optimized only for creating clubs.

Scenario to attempt:

1. Create club shell
- Club name, address, contact
- Course type: 18-hole
- Default timezone and currency
- Enable BRS Tee Sheet

Checklist:
- [ ] Club created
- [ ] Course created/configured as 18-hole
- [ ] Timezone/currency set
- [ ] BRS Tee Sheet enabled

2. Configure core tee sheet
- First tee time: 07:00
- Last tee time: 18:00
- Interval: 10 minutes
- Playing time: 4h 00m
- Week template: Monday–Sunday open
- Publish tee sheet for next 30 days

Checklist:
- [ ] Timesheet configured
- [ ] Tee sheet published
- [ ] Tee sheet visible/bookable for next 30 days

3. Configure general system settings
- Club display name
- Booking confirmation email from address
- Legal/T&Cs message
- Visitor booking enabled
- Member booking enabled
- Cancellation window: 24 hours
- Max players per tee time: 4

Checklist:
- [ ] Display name set
- [ ] Confirmation email configured
- [ ] Legal/T&Cs configured
- [ ] Visitor booking enabled
- [ ] Member booking enabled
- [ ] Cancellation rules configured
- [ ] Max players configured

4. Create green fee rates
Use the green_fee_rates table/API where appropriate.

Required rates:
- Visitor weekday: £40
- Visitor weekend: £50
- Member guest: £25
- Junior: £15
- Optional buggy/service rate: £20

Known context:
The green_fee_rates table includes fields such as:
- green_fee_id
- course_id
- startDate, endDate
- startTime, endTime
- holes
- Category, SubCategory, CategoryCode
- RateMon through RateSun
- RateType

The API endpoint `/api/v3/clubs/{clubId}/visitor-green-fee-rates` appears to require additional fields the current tool may not fully support, including channel information and package details.

Checklist:
- [ ] Visitor weekday rate created
- [ ] Visitor weekend rate created
- [ ] Member guest rate created
- [ ] Junior rate created
- [ ] Buggy/service rate created or clearly reported as unsupported
- [ ] Missing fields/tool gaps documented

5. Configure casual booking rules
- Members can book 14 days ahead
- Visitors can book 7 days ahead
- Visitors must pay online, or allow pay-at-course for POC
- Minimum players: 1
- Maximum players: 4
- Cancellation cutoff: 24 hours
- Apply visitor rates to visitor bookings

Checklist:
- [ ] Member booking window configured
- [ ] Visitor booking window configured
- [ ] Payment behaviour configured
- [ ] Player min/max configured
- [ ] Cancellation cutoff configured
- [ ] Visitor rates applied to visitor bookings

6. Create basic competition config
- Enable competitions
- Create open competition:
  - Name: Saturday Stableford
  - Date: next Saturday
  - Entry window opens now
  - Entry window closes 24h before
  - Entry fee: £5
  - Handicap limit broad/optional
  - Allow member entry
  - Online competition payment optional for later

Checklist:
- [ ] Competitions enabled
- [ ] Competition created
- [ ] Entry window configured
- [ ] Entry fee configured
- [ ] Member entry allowed
- [ ] Payment support verified or gap documented

7. Create/import one member
- Name: Alice Member
- Email present
- Membership type: Adult Member
- Enable online booking

Checklist:
- [ ] Member created/imported
- [ ] Membership type assigned
- [ ] Online booking enabled
- [ ] Member can be used for booking validation

8. Validation bookings
Attempt:
- Member books a casual tee time
- Visitor books a tee time and receives correct green fee
- Member enters the competition
- Admin views booking on tee sheet
- Admin moves or cancels booking
- Booking confirmation email is generated

Checklist:
- [ ] Member casual booking works
- [ ] Visitor booking works
- [ ] Correct green fee applied
- [ ] Competition entry works
- [ ] Admin can view booking
- [ ] Admin can move/cancel booking
- [ ] Confirmation email generated

Execution instructions:
- Use the existing agent and tools as-is first.
- For each step, record:
  - Tool/action attempted
  - Inputs used
  - Result
  - Whether it passed, failed, or partially worked
  - Error message, if any
  - Retry attempted
  - Final status
- When a tool fails, use the agent’s existing error-handling capabilities to inspect the error, infer missing/incorrect fields, retry with corrected inputs, and continue where safe.
- Do not silently skip failures.
- Do not tailor the agent specifically to this club-creation flow.
- If tool support is missing, propose general improvements such as:
  - clearer tool descriptions
  - richer schemas
  - required/optional field documentation
  - enum documentation
  - better validation errors
  - discoverability of related tools
  - harness support for multi-step workflows
  - automatic retry strategies
  - better logging of attempted tool calls
  - reusable fixtures/test data
  - ability to dry-run or rollback setup data

Expected output:
Produce a structured test report with:

1. Executive summary
2. Overall verdict: Pass / Partial / Fail
3. Step-by-step checklist with status
4. Tool calls attempted and outcomes
5. Errors encountered and retries performed
6. Data created, including club/member/rate/competition IDs where available
7. Gaps in current tool coverage
8. Recommended generic tool/harness improvements
9. Suggested follow-up tests, especially around:
   - green fee rate channels/packages
   - visitor payments
   - tee sheet publication
   - competition entry/payment
   - booking confirmation emails
   - moving/cancelling bookings

Critical interaction requirement:
The agent should be tested primarily through natural-language conversation, not by giving it every parameter upfront.

Do not invoke the agent with a fully structured payload that contains all fields needed for club setup. That defeats the purpose of the agent.

Instead, start with a realistic user request, for example:

“I want to set up a new 18-hole club for a POC and get it to the point where members and visitors can book tee times.”

The agent should then:
- Infer the next sensible onboarding steps.
- Ask follow-up questions only when required.
- Guide the user conversationally through missing information.
- Explain what information it needs and why.
- Use defaults where safe and explicitly state them.
- Confirm before making important changes.
- Continue making progress without demanding every detail upfront.
- Use tools incrementally as information becomes available.
- Recover from tool errors by clarifying, retrying, or explaining the gap.

The test should evaluate whether the agent can drive the workflow through back-and-forth conversation, not whether it can execute a pre-filled API contract.

The harness should therefore support:
- Multi-turn natural-language test scripts.
- Simulated user replies.
- Assertions after each turn.
- Checks that the agent asks appropriate clarifying questions.
- Checks that the agent does not over-ask for unnecessary parameters.
- Checks that the agent uses sensible defaults when appropriate.
- Checks that the agent converts conversational answers into valid tool calls.
- Checks that errors lead to useful follow-up questions or retries.

Preferred test shape:
1. Start with a vague natural-language onboarding request.
2. Let the agent ask for missing essentials.
3. Provide only the information it asks for.
4. Observe whether it progresses step by step.
5. Validate each completed checkpoint.
6. Record where the agent got stuck, over-required fields, or exposed raw API complexity to the user.

Important success criteria:
The agent should feel like an onboarding assistant, not a thin wrapper around API schemas.  