#!/usr/bin/env python3
"""
QA Execution Script - Captures full conversation traces, tool calls, and session data.
Runs 5 scenarios with Langfuse integration.
"""

import json
import os
import sys
import httpx
from datetime import datetime
from typing import Dict, List, Any, Optional

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.models.models import User, UserRole, Tenant
from app.db.session import SessionLocal
from app.services.mcp_client import MCPClient
from app.core.config import settings


class QATraceCapture:
    """Captures QA execution traces with full conversation logging."""

    def __init__(self):
        self.session = SessionLocal()
        self.execution_id = f"qa_exec_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.scenarios_run = []
        self.langfuse_traces = []
        self.start_time = datetime.now()

    def get_test_user(self) -> User:
        """Get or create test user for QA."""
        user = self.session.query(User).filter(User.username == "qa_test_user").first()
        if not user:
            tenant = self.session.query(Tenant).first()
            if not tenant:
                raise RuntimeError("No tenant found in database")

            user = User(
                username="qa_test_user",
                email="qa@test.local",
                tenant_id=tenant.id,
                role=UserRole.ADMIN,
                is_active=True
            )
            self.session.add(user)
            self.session.commit()
        return user

    def capture_scenario(self, scenario_num: int, scenario_name: str,
                        conversation_turns: List[Dict[str, str]]) -> Dict[str, Any]:
        """Execute scenario and capture all traces."""
        print(f"\n{'='*60}")
        print(f"Scenario {scenario_num}: {scenario_name}")
        print(f"{'='*60}")

        scenario_data = {
            "scenario_num": scenario_num,
            "name": scenario_name,
            "start_time": datetime.now().isoformat(),
            "turns": [],
            "status": "PENDING",
            "traces": [],
            "tool_calls": [],
            "errors": []
        }

        for turn_num, turn in enumerate(conversation_turns, 1):
            turn_data = {
                "turn": turn_num,
                "user_message": turn.get("user"),
                "timestamp": datetime.now().isoformat(),
                "ai_response": None,
                "tool_calls": [],
                "trace_id": None,
                "session_id": None
            }

            print(f"\nTurn {turn_num}:")
            print(f"  User: {turn.get('user')[:100]}...")

            # Simulate API call to chat endpoint
            try:
                response = self._call_chat_api(turn.get("user"))
                turn_data["ai_response"] = response.get("response")
                turn_data["trace_id"] = response.get("trace_id")
                turn_data["session_id"] = response.get("session_id")
                turn_data["tool_calls"] = response.get("tool_calls", [])

                print(f"  AI: {response.get('response', 'N/A')[:100]}...")
                if response.get("tool_calls"):
                    print(f"  Tools: {[tc.get('name') for tc in response.get('tool_calls', [])]}")

                scenario_data["tool_calls"].extend(response.get("tool_calls", []))

            except Exception as e:
                error_msg = f"Turn {turn_num} failed: {str(e)}"
                print(f"  ERROR: {error_msg}")
                turn_data["error"] = error_msg
                scenario_data["errors"].append(error_msg)

            scenario_data["turns"].append(turn_data)

        scenario_data["end_time"] = datetime.now().isoformat()
        scenario_data["status"] = "PASSED" if not scenario_data["errors"] else "FAILED"

        self.scenarios_run.append(scenario_data)
        return scenario_data

    def _call_chat_api(self, message: str) -> Dict[str, Any]:
        """Call chat API and capture response."""
        try:
            response = httpx.post(
                "http://localhost:8000/api/chat",
                json={"message": message},
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {
                "response": f"Error: {str(e)}",
                "error": True,
                "trace_id": None,
                "session_id": None
            }

    def query_langfuse_traces(self) -> List[Dict[str, Any]]:
        """Query Langfuse for recent traces."""
        langfuse_host = os.getenv("LANGFUSE_HOST", "http://localhost:3001")
        public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
        secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")

        if not public_key or not secret_key:
            print("⚠️  Langfuse credentials not configured, skipping trace query")
            return []

        try:
            with httpx.Client(auth=(public_key, secret_key)) as client:
                response = client.get(
                    f"{langfuse_host}/api/public/traces",
                    params={"limit": 100, "fromTimestamp": self.start_time.isoformat()},
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                self.langfuse_traces = data.get("data", [])
                return self.langfuse_traces
        except Exception as e:
            print(f"⚠️  Failed to query Langfuse: {e}")
            return []

    def generate_report(self, output_file: str):
        """Generate comprehensive execution report."""
        report = {
            "execution_id": self.execution_id,
            "timestamp": datetime.now().isoformat(),
            "duration_ms": int((datetime.now() - self.start_time).total_seconds() * 1000),
            "scenarios": self.scenarios_run,
            "summary": {
                "total_scenarios": len(self.scenarios_run),
                "passed": sum(1 for s in self.scenarios_run if s["status"] == "PASSED"),
                "failed": sum(1 for s in self.scenarios_run if s["status"] == "FAILED"),
                "total_turns": sum(len(s["turns"]) for s in self.scenarios_run),
                "total_tool_calls": sum(len(s["tool_calls"]) for s in self.scenarios_run),
            },
            "langfuse_traces": self.langfuse_traces
        }

        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)

        print(f"\n✅ Report written to {output_file}")
        return report


def main():
    """Run QA execution."""
    qa = QATraceCapture()

    scenarios = [
        {
            "num": 1,
            "name": "Basic Greeting & Capabilities",
            "turns": [
                {"user": "Hello, who are you?"},
                {"user": "What can you help me with?"}
            ]
        },
        {
            "num": 2,
            "name": "Club Setup (Existing Club)",
            "turns": [
                {"user": "Can you show me information about brsgolfclubsales club?"},
                {"user": "What configuration options are available for this club?"}
            ]
        },
        {
            "num": 4,
            "name": "Booking Query",
            "turns": [
                {"user": "What tee times are available next Saturday?"},
                {"user": "Show me available times between 9am and 11am"}
            ]
        },
        {
            "num": 16,
            "name": "Reinstate Deleted User",
            "turns": [
                {"user": "How do I reinstate a deleted user?"},
                {"user": "Can you walk me through the admin workflow?"}
            ]
        },
        {
            "num": 999,
            "name": "Infrastructure: MCP Health Check",
            "turns": [
                {"user": "Are all systems healthy? Check MCP servers."}
            ]
        }
    ]

    for scenario in scenarios:
        qa.capture_scenario(scenario["num"], scenario["name"], scenario["turns"])

    # Query Langfuse for traces
    print("\n📊 Querying Langfuse for execution traces...")
    qa.query_langfuse_traces()

    # Generate report
    output_file = f"qa_execution_results_{qa.execution_id}.json"
    report = qa.generate_report(output_file)

    print(f"\n{'='*60}")
    print(f"QA Execution Complete")
    print(f"{'='*60}")
    print(f"Execution ID: {qa.execution_id}")
    print(f"Scenarios: {report['summary']['total_scenarios']}")
    print(f"Passed: {report['summary']['passed']}")
    print(f"Failed: {report['summary']['failed']}")
    print(f"Total Turns: {report['summary']['total_turns']}")
    print(f"Total Tool Calls: {report['summary']['total_tool_calls']}")
    print(f"Langfuse Traces Captured: {len(qa.langfuse_traces)}")
    print(f"\nResults: {output_file}")


if __name__ == "__main__":
    main()
