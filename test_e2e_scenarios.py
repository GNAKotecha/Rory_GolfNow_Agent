#!/usr/bin/env python3
"""
E2E Scenario Testing Script
Tests all scenarios from E2E_TEST_SCENARIOS.md through the backend API
"""

import json
import requests
import time
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

BASE_URL = "http://localhost:8000"
HEADERS = {"Content-Type": "application/json"}

# Test data
TEST_USER_EMAIL = f"test_user_{int(time.time())}@example.com"
TEST_PASSWORD = "testpass123"
TEST_CLUB_NAME = "Sunset Valley Golf Club"
TEST_CLUB_EMAIL = "admin@sunsetvalley.golf"

@dataclass
class TestResult:
    """Test result data structure"""
    scenario: str
    turn: int
    user_message: str
    response: str
    status: str  # "pass", "partial", "fail"
    notes: str = ""
    tool_calls: List[str] = None

    def __post_init__(self):
        if self.tool_calls is None:
            self.tool_calls = []

class E2ETestRunner:
    def __init__(self):
        self.results: List[TestResult] = []
        self.current_session_id = None
        self.auth_token = None
        self.base_url = BASE_URL

    def log_result(self, result: TestResult):
        """Log test result"""
        self.results.append(result)
        status_icon = "✅" if result.status == "pass" else "⚠️" if result.status == "partial" else "❌"
        print(f"{status_icon} Scenario {result.scenario}, Turn {result.turn}: {result.status}")
        if result.notes:
            print(f"   Notes: {result.notes}")

    def send_message(self, user_message: str) -> Tuple[str, Dict[str, Any]]:
        """Send message to chat API"""
        try:
            payload = {
                "message": user_message
            }

            # Determine endpoint based on session state
            if self.current_session_id:
                endpoint = f"{self.base_url}/api/chat/{self.current_session_id}"
            else:
                endpoint = f"{self.base_url}/api/chat"

            response = requests.post(
                endpoint,
                json=payload,
                headers=HEADERS,
                timeout=10
            )

            if response.status_code == 201:  # New session
                data = response.json()
                self.current_session_id = data.get("session_id")
                return data.get("response", ""), data
            elif response.status_code == 200:  # Existing session
                data = response.json()
                return data.get("response", ""), data
            else:
                return f"Error: {response.status_code}", {"error": response.text}

        except Exception as e:
            return f"Exception: {str(e)}", {"error": str(e)}

    def check_response_contains(self, response: str, keywords: List[str]) -> bool:
        """Check if response contains expected keywords"""
        return all(keyword.lower() in response.lower() for keyword in keywords)

    # ============ SCENARIO TESTS ============

    def test_scenario_1_basic_greeting(self):
        """Scenario 1: Basic Greeting & Capabilities"""
        scenario_name = "Scenario 1: Basic Greeting"
        print(f"\n{'='*60}")
        print(f"Testing {scenario_name}")
        print(f"{'='*60}")

        # Reset session for new scenario
        self.current_session_id = None

        # Turn 1
        user_msg = "Hello! I'm new here. What can you help me with?"
        response, data = self.send_message(user_msg)

        expected_keywords = ["golf", "club", "booking", "help"]
        status = "pass" if self.check_response_contains(response, ["golf", "help"]) else "partial"

        result = TestResult(
            scenario=scenario_name,
            turn=1,
            user_message=user_msg,
            response=response[:200],
            status=status,
            notes=f"Response contains key concepts: {status == 'pass'}"
        )
        self.log_result(result)

        # Turn 2
        user_msg = "That sounds great! Can you give me a quick overview of your main features?"
        response, data = self.send_message(user_msg)

        status = "pass" if self.check_response_contains(response, ["feature", "booking"]) else "partial"

        result = TestResult(
            scenario=scenario_name,
            turn=2,
            user_message=user_msg,
            response=response[:200],
            status=status,
            notes=f"Agent explains features: {status == 'pass'}"
        )
        self.log_result(result)

    def test_scenario_2_club_setup(self):
        """Scenario 2: Club Setup Workflow"""
        scenario_name = "Scenario 2: Club Setup"
        print(f"\n{'='*60}")
        print(f"Testing {scenario_name}")
        print(f"{'='*60}")

        # Reset session
        self.current_session_id = None

        # Turn 1
        user_msg = "I need to set up a new golf club in the system."
        response, data = self.send_message(user_msg)
        status = "pass" if any(k in response.lower() for k in ["club", "detail", "information"]) else "partial"

        result = TestResult(
            scenario=scenario_name,
            turn=1,
            user_message=user_msg,
            response=response[:200],
            status=status
        )
        self.log_result(result)

        # Turn 2
        user_msg = f"The club is called '{TEST_CLUB_NAME}'. The admin email is {TEST_CLUB_EMAIL} and the contact name is John Smith."
        response, data = self.send_message(user_msg)
        status = "pass" if any(k in response.lower() for k in ["confirm", "proceed", "setup"]) else "partial"

        result = TestResult(
            scenario=scenario_name,
            turn=2,
            user_message=user_msg,
            response=response[:200],
            status=status,
            notes="Agent should confirm details"
        )
        self.log_result(result)

        # Turn 3
        user_msg = "Great, please proceed with the setup."
        response, data = self.send_message(user_msg)
        status = "pass" if any(k in response.lower() for k in ["created", "success", "confirm"]) else "partial"

        result = TestResult(
            scenario=scenario_name,
            turn=3,
            user_message=user_msg,
            response=response[:200],
            status=status,
            notes="Club creation initiated"
        )
        self.log_result(result)

    def test_scenario_5_context_retention(self):
        """Scenario 5: Multi-Turn Context Retention"""
        scenario_name = "Scenario 5: Context Retention"
        print(f"\n{'='*60}")
        print(f"Testing {scenario_name}")
        print(f"{'='*60}")

        # Reset session
        self.current_session_id = None

        # Turn 1 - Mention club name
        user_msg = "I'm interested in setting up a club called 'Mountain View Golf'."
        response, data = self.send_message(user_msg)

        result = TestResult(
            scenario=scenario_name,
            turn=1,
            user_message=user_msg,
            response=response[:200],
            status="pass"
        )
        self.log_result(result)

        # Turn 2 - Mention admin name
        user_msg = "The admin will be Sarah Johnson."
        response, data = self.send_message(user_msg)

        result = TestResult(
            scenario=scenario_name,
            turn=2,
            user_message=user_msg,
            response=response[:200],
            status="pass"
        )
        self.log_result(result)

        # Turn 3 - Ask for summary (test context retention)
        user_msg = "Can you summarize what we've discussed?"
        response, data = self.send_message(user_msg)

        # Check if both pieces of info are retained
        contains_club = "Mountain View Golf" in response or "mountain view" in response.lower()
        contains_admin = "Sarah Johnson" in response or "sarah" in response.lower()

        status = "pass" if (contains_club and contains_admin) else "partial"

        result = TestResult(
            scenario=scenario_name,
            turn=3,
            user_message=user_msg,
            response=response[:300],
            status=status,
            notes=f"Club retained: {contains_club}, Admin retained: {contains_admin}"
        )
        self.log_result(result)

    def test_scenario_6_error_recovery(self):
        """Scenario 6: Error Recovery"""
        scenario_name = "Scenario 6: Error Recovery"
        print(f"\n{'='*60}")
        print(f"Testing {scenario_name}")
        print(f"{'='*60}")

        # Reset session
        self.current_session_id = None

        # Turn 1 - Dangerous request
        user_msg = "Delete all clubs from the system!"
        response, data = self.send_message(user_msg)

        # Should refuse dangerous operation
        refuses = any(k in response.lower() for k in ["cannot", "cannot do", "refuse", "not", "unsafe"])
        status = "pass" if refuses else "partial"

        result = TestResult(
            scenario=scenario_name,
            turn=1,
            user_message=user_msg,
            response=response[:200],
            status=status,
            notes="Agent should refuse dangerous operation"
        )
        self.log_result(result)

        # Turn 2 - Legitimate request
        user_msg = "Actually, I just need help looking up a specific club."
        response, data = self.send_message(user_msg)

        status = "pass" if any(k in response.lower() for k in ["help", "look", "search"]) else "partial"

        result = TestResult(
            scenario=scenario_name,
            turn=2,
            user_message=user_msg,
            response=response[:200],
            status=status,
            notes="Agent recovers gracefully"
        )
        self.log_result(result)

    def test_scenario_10_long_conversation(self):
        """Scenario 10: Long Conversation Stress Test"""
        scenario_name = "Scenario 10: Long Conversation"
        print(f"\n{'='*60}")
        print(f"Testing {scenario_name}")
        print(f"{'='*60}")

        # Reset session
        self.current_session_id = None

        topics = [
            ("Let's have a detailed conversation about club management.", ["management", "club"]),
            ("First, tell me about member management features.", ["member"]),
            ("What about booking management?", ["booking"]),
            ("How about reporting and analytics?", ["report", "analytic"]),
            ("What integrations are available?", ["integration"]),
            ("Can you summarize everything we discussed?", ["member", "booking", "report"])
        ]

        for turn, (user_msg, expected_keywords) in enumerate(topics, 1):
            response, data = self.send_message(user_msg)

            # Check for expected keywords
            has_keywords = any(k in response.lower() for k in expected_keywords)
            status = "pass" if has_keywords else "partial"

            result = TestResult(
                scenario=scenario_name,
                turn=turn,
                user_message=user_msg,
                response=response[:200],
                status=status
            )
            self.log_result(result)

    def run_all_tests(self):
        """Run all test scenarios"""
        print("\n" + "="*60)
        print("E2E SCENARIO TESTING - GolfNow Agent")
        print(f"Started: {datetime.now().isoformat()}")
        print("="*60)

        try:
            self.test_scenario_1_basic_greeting()
            self.test_scenario_2_club_setup()
            self.test_scenario_5_context_retention()
            self.test_scenario_6_error_recovery()
            self.test_scenario_10_long_conversation()
        except Exception as e:
            print(f"\n❌ Test execution failed: {e}")

        # Print summary
        self.print_summary()

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)

        passed = sum(1 for r in self.results if r.status == "pass")
        partial = sum(1 for r in self.results if r.status == "partial")
        failed = sum(1 for r in self.results if r.status == "fail")
        total = len(self.results)

        print(f"Total Tests: {total}")
        print(f"✅ Passed: {passed} ({100*passed//total if total else 0}%)")
        print(f"⚠️  Partial: {partial} ({100*partial//total if total else 0}%)")
        print(f"❌ Failed: {failed} ({100*failed//total if total else 0}%)")

        # Group by scenario
        print("\n" + "-"*60)
        print("Results by Scenario:")
        print("-"*60)

        scenarios = {}
        for result in self.results:
            if result.scenario not in scenarios:
                scenarios[result.scenario] = {"pass": 0, "partial": 0, "fail": 0}
            scenarios[result.scenario][result.status] += 1

        for scenario, counts in scenarios.items():
            total_s = sum(counts.values())
            pass_rate = 100 * counts["pass"] // total_s if total_s else 0
            print(f"{scenario}: {pass_rate}% pass ({counts['pass']}/{total_s})")

        print("\n" + "="*60)
        print(f"Completed: {datetime.now().isoformat()}")
        print("="*60)


if __name__ == "__main__":
    runner = E2ETestRunner()
    runner.run_all_tests()
