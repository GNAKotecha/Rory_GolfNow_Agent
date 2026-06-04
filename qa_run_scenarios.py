#!/usr/bin/env python3
"""Execute QA scenarios with full trace capture and auth."""

import json
import httpx
import sys
import os
from datetime import datetime

# Get token from setup
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI5IiwidGVuYW50X2lkIjoiMSIsImV4cCI6MTc4MTE4NDgyNH0.Zs4JjfiqubcvtudW9JGIgg0qfs6JUklD8g44x8BSkm0"
BASE_URL = "http://localhost:8000"

scenarios = [
    {
        "num": 1,
        "name": "Basic Greeting & Capabilities",
        "turns": [
            "Hello, who are you and what can you do?",
            "List all available tools"
        ]
    },
    {
        "num": 2,
        "name": "Club Setup (Existing Club)",
        "turns": [
            "Show information about brsgolfclubsales club",
            "What configuration options are available?"
        ]
    },
    {
        "num": 4,
        "name": "Booking Query",
        "turns": [
            "What tee times are available next Saturday?",
            "Show times between 9am and 11am"
        ]
    },
    {
        "num": 16,
        "name": "Reinstate Deleted User",
        "turns": [
            "How do I reinstate a deleted user?",
            "Walk me through the approval workflow"
        ]
    },
    {
        "num": 999,
        "name": "Infrastructure: MCP Health Check",
        "turns": [
            "Check if all MCP servers are healthy and connected"
        ]
    }
]

def create_session():
    """Create a new chat session."""
    headers = {"Authorization": f"Bearer {TOKEN}"}
    try:
        response = httpx.post(
            f"{BASE_URL}/api/sessions",
            json={"name": f"QA Session {datetime.now().isoformat()}"},
            headers=headers,
            timeout=10.0
        )
        response.raise_for_status()
        data = response.json()
        return data.get("id")
    except Exception as e:
        print(f"Failed to create session: {e}")
        return None

def run_scenario(scenario_num, scenario_name, turns):
    """Run one scenario."""
    print(f"\n{'='*70}")
    print(f"Scenario {scenario_num}: {scenario_name}")
    print(f"{'='*70}")

    scenario_data = {
        "scenario_num": scenario_num,
        "name": scenario_name,
        "start_time": datetime.now().isoformat(),
        "turns": [],
        "status": "PENDING",
        "errors": [],
        "session_id": None
    }

    headers = {"Authorization": f"Bearer {TOKEN}"}

    # Create session for scenario
    session_id = create_session()
    if not session_id:
        scenario_data["status"] = "FAILED"
        scenario_data["errors"].append("Failed to create session")
        return scenario_data

    scenario_data["session_id"] = session_id
    print(f"  Session ID: {session_id}")

    for turn_num, msg in enumerate(turns, 1):
        turn_data = {
            "turn": turn_num,
            "user_message": msg,
            "timestamp": datetime.now().isoformat(),
            "ai_response": None,
            "trace_id": None,
            "status": "PENDING"
        }

        print(f"\n  Turn {turn_num}:")
        print(f"    User: {msg[:80]}")

        try:
            response = httpx.post(
                f"{BASE_URL}/api/chat",
                json={"session_id": session_id, "message": msg},
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()

            # Store full response for debugging
            turn_data["full_response"] = data
            turn_data["ai_response"] = data.get("response") or data.get("content") or data.get("message") or str(data)[:200]
            turn_data["trace_id"] = data.get("trace_id")
            turn_data["status"] = "PASSED"
            turn_data["tool_calls"] = data.get("tool_calls", [])

            print(f"    AI: {(data.get('response', 'N/A'))[:100]}...")
            if data.get("tool_calls"):
                print(f"    Tools: {[t.get('name') for t in data.get('tool_calls', [])]}")

        except Exception as e:
            error_msg = f"Turn {turn_num} failed: {str(e)}"
            turn_data["error"] = error_msg
            turn_data["status"] = "FAILED"
            print(f"    ERROR: {error_msg}")
            scenario_data["errors"].append(error_msg)

        scenario_data["turns"].append(turn_data)

    scenario_data["end_time"] = datetime.now().isoformat()
    scenario_data["status"] = "PASSED" if not scenario_data["errors"] else "FAILED"

    return scenario_data

def main():
    print(f"\n{'*'*70}")
    print(f"QA Execution - Full Scenario Run with Trace Capture")
    print(f"{'*'*70}")
    print(f"Start Time: {datetime.now().isoformat()}")
    print(f"Base URL: {BASE_URL}")

    exec_id = f"qa_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    results = {
        "execution_id": exec_id,
        "start_time": datetime.now().isoformat(),
        "scenarios": [],
        "summary": {}
    }

    for scenario in scenarios:
        result = run_scenario(scenario["num"], scenario["name"], scenario["turns"])
        results["scenarios"].append(result)

    results["end_time"] = datetime.now().isoformat()
    results["summary"] = {
        "total_scenarios": len(results["scenarios"]),
        "passed": sum(1 for s in results["scenarios"] if s["status"] == "PASSED"),
        "failed": sum(1 for s in results["scenarios"] if s["status"] == "FAILED"),
        "total_turns": sum(len(s["turns"]) for s in results["scenarios"]),
        "total_tool_calls": sum(
            sum(len(t.get("tool_calls", [])) for t in s["turns"])
            for s in results["scenarios"]
        )
    }

    output_file = f"qa_results_{exec_id}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*70}")
    print(f"QA Execution Complete")
    print(f"{'='*70}")
    print(f"Execution ID: {exec_id}")
    print(f"Scenarios: {results['summary']['total_scenarios']}")
    print(f"Passed: {results['summary']['passed']}")
    print(f"Failed: {results['summary']['failed']}")
    print(f"Total Turns: {results['summary']['total_turns']}")
    print(f"Total Tool Calls: {results['summary']['total_tool_calls']}")
    print(f"\nResults saved to: {output_file}")

if __name__ == "__main__":
    main()
