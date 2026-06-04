# Demo Workflow Test Results

Manual natural-language test log for Rory demo workflows.

**Scope:** Scenarios 16-22 in `docs/E2E_TEST_SCENARIOS.md`
**Method:** Run each scenario conversationally with Rory, ideally through Claude `/test-qa-loop --scope custom --dry-run`.
**Runtime assumption:** Anthropic-compatible API-key mode.
**Last updated:** 2026-06-04

## Status Scale

| Status | Meaning |
|--------|---------|
| `pass` | Demo-ready answer; handles follow-up context correctly. |
| `partial` | Understands workflow but misses details or has a non-critical gap. |
| `fail` | Incorrect guidance, hallucination, unsafe action, or context failure. |
| `blocked` | Missing docs, data, auth, or tools prevent completion. |
| `not_run` | Scenario has not been tested yet. |

## Summary

| Scenario | Status | Demo Readiness | Key Gap |
|----------|--------|----------------|---------|
| Reinstate Deleted User | `not_run` | `unknown` | |
| Bill Creation | `not_run` | `unknown` | |
| User and Member Creation | `not_run` | `unknown` | |
| Configure Timesheet | `not_run` | `unknown` | |
| Process and Refund Competition Purse Payments | `not_run` | `unknown` | |
| Green Fee Rates Setup | `not_run` | `unknown` | |
| Casual Booking Rules Setup | `not_run` | `unknown` | |

## Results JSON Draft

This structure matches the intent of the test-results API while keeping the manual evidence readable.

```json
{
  "timestamp": "2026-06-04T00:00:00",
  "environment": "manual-demo",
  "total_scenarios": 7,
  "passed": 0,
  "failed": 0,
  "duration_seconds": 0,
  "tags": ["demo_workflow", "manual", "anthropic"],
  "scenarios": [
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
    },
    {
      "scenario_name": "bill_creation",
      "success": false,
      "status": "not_run",
      "demo_readiness": "unknown",
      "turn_count": 0,
      "tool_calls_count": 0,
      "error_message": null,
      "missing_tools_or_knowledge": [],
      "notes": "",
      "turn_results": []
    },
    {
      "scenario_name": "user_member_creation",
      "success": false,
      "status": "not_run",
      "demo_readiness": "unknown",
      "turn_count": 0,
      "tool_calls_count": 0,
      "error_message": null,
      "missing_tools_or_knowledge": [],
      "notes": "",
      "turn_results": []
    },
    {
      "scenario_name": "configure_timesheet",
      "success": false,
      "status": "not_run",
      "demo_readiness": "unknown",
      "turn_count": 0,
      "tool_calls_count": 0,
      "error_message": null,
      "missing_tools_or_knowledge": [],
      "notes": "",
      "turn_results": []
    },
    {
      "scenario_name": "process_refund_competition_purse_payments",
      "success": false,
      "status": "not_run",
      "demo_readiness": "unknown",
      "turn_count": 0,
      "tool_calls_count": 0,
      "error_message": null,
      "missing_tools_or_knowledge": [],
      "notes": "",
      "turn_results": []
    },
    {
      "scenario_name": "green_fee_rates_setup",
      "success": false,
      "status": "not_run",
      "demo_readiness": "unknown",
      "turn_count": 0,
      "tool_calls_count": 0,
      "error_message": null,
      "missing_tools_or_knowledge": [],
      "notes": "",
      "turn_results": []
    },
    {
      "scenario_name": "casual_booking_rules_setup",
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
  ]
}
```

## Run Notes

### Reinstate Deleted User

- Status: `not_run`
- Demo readiness: `unknown`
- Evidence:
- Missing tools/knowledge:
- Follow-up:

### Bill Creation

- Status: `not_run`
- Demo readiness: `unknown`
- Evidence:
- Missing tools/knowledge:
- Follow-up:

### User and Member Creation

- Status: `not_run`
- Demo readiness: `unknown`
- Evidence:
- Missing tools/knowledge:
- Follow-up:

### Configure Timesheet

- Status: `not_run`
- Demo readiness: `unknown`
- Evidence:
- Missing tools/knowledge:
- Follow-up:

### Process and Refund Competition Purse Payments

- Status: `not_run`
- Demo readiness: `unknown`
- Evidence:
- Missing tools/knowledge:
- Follow-up:

### Green Fee Rates Setup

- Status: `not_run`
- Demo readiness: `unknown`
- Evidence:
- Missing tools/knowledge:
- Follow-up:

### Casual Booking Rules Setup

- Status: `not_run`
- Demo readiness: `unknown`
- Evidence:
- Missing tools/knowledge:
- Follow-up:
