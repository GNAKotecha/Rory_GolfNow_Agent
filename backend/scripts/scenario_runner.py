#!/usr/bin/env python3
"""
Scenario-based E2E testing for the GolfNow Agent chatbot.

This runner executes conversational test scenarios against a live server,
simulating real user interactions and verifying outcomes.

Usage:
    # Start the server first
    cd backend && uvicorn app.main:app --reload --port 8000
    
    # Run all scenarios
    python scripts/scenario_runner.py
    
    # Run specific scenario
    python scripts/scenario_runner.py --scenario club_setup
    
    # Verbose mode
    python scripts/scenario_runner.py --verbose

Environment Variables:
    BACKEND_URL: Server URL (default: http://localhost:8000)
    TEST_EMAIL: Test user email (default: admin@demo.golf)
    TEST_PASSWORD: Test user password (default: admin123)
"""

import os
import sys
import json
import time
import argparse
import requests
from typing import Dict, Any, List, Optional, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from scenario_results import ResultExporter, TestRunSummary

# =============================================================================
# CONFIGURATION
# =============================================================================

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
API_BASE = f"{BACKEND_URL}/api"
TEST_EMAIL = os.environ.get("TEST_EMAIL", "admin@demo.golf")
TEST_PASSWORD = os.environ.get("TEST_PASSWORD", "admin123")

# ANSI Colors
GREEN = "\033[92m"
RED = "\033[91m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
END = "\033[0m"


# =============================================================================
# LOGGING HELPERS
# =============================================================================

VERBOSE = False

def log_user(msg: str):
    """Log user message."""
    print(f"\n{CYAN}👤 User:{END} {msg}")

def log_agent(msg: str):
    """Log agent response."""
    # Truncate long responses
    display = msg[:500] + "..." if len(msg) > 500 else msg
    print(f"{BLUE}🤖 Agent:{END} {display}")

def log_tool(name: str, result: str = None):
    """Log tool execution."""
    if result:
        print(f"{DIM}   🔧 Tool: {name} → {result[:100]}...{END}")
    else:
        print(f"{DIM}   🔧 Tool: {name}{END}")

def log_step(msg: str):
    """Log scenario step."""
    print(f"\n{BOLD}{YELLOW}━━━ {msg} ━━━{END}")

def log_pass(msg: str):
    """Log pass."""
    print(f"{GREEN}✅ {msg}{END}")

def log_fail(msg: str):
    """Log failure."""
    print(f"{RED}❌ {msg}{END}")

def log_info(msg: str):
    """Log info."""
    if VERBOSE:
        print(f"{DIM}   ℹ️  {msg}{END}")

def log_debug(msg: str):
    """Log debug."""
    if VERBOSE:
        print(f"{DIM}   🔍 {msg}{END}")

def is_transient_error(error: str) -> bool:
    """Check if error is transient (worth retrying)."""
    transient_indicators = [
        "timeout", "connection", "reset", "refused", "unavailable",
        "500", "502", "503", "504", "429"  # HTTP server errors
    ]
    error_lower = error.lower()
    return any(indicator in error_lower for indicator in transient_indicators)


# =============================================================================
# API CLIENT
# =============================================================================

class ChatClient:
    """Client for interacting with the chat API."""
    
    def __init__(self, base_url: str = API_BASE):
        self.base_url = base_url
        self.token: Optional[str] = None
        self.session_id: Optional[int] = None
        self.last_response: Optional[Dict] = None
        self.conversation_history: List[Dict] = []
        self.tool_calls: List[Dict] = []
    
    def login(self, email: str, password: str) -> bool:
        """Authenticate and get token."""
        try:
            resp = requests.post(
                f"{self.base_url}/auth/login",
                json={"email": email, "password": password},
                timeout=30
            )
            if resp.status_code == 200:
                self.token = resp.json()["access_token"]
                log_info(f"Logged in as {email}")
                return True
            else:
                log_fail(f"Login failed: {resp.status_code} - {resp.text}")
                return False
        except Exception as e:
            log_fail(f"Login error: {e}")
            return False
    
    def create_session(self, title: str = "Test Session") -> bool:
        """Create a new chat session."""
        try:
            resp = requests.post(
                f"{self.base_url}/sessions",
                json={"title": f"{title} - {datetime.now().isoformat()}"},
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=30
            )
            if resp.status_code == 200:
                self.session_id = resp.json()["id"]
                self.conversation_history = []
                self.tool_calls = []
                log_info(f"Created session {self.session_id}")
                return True
            else:
                log_fail(f"Session creation failed: {resp.status_code}")
                return False
        except Exception as e:
            log_fail(f"Session error: {e}")
            return False
    
    def send_message(self, message: str, workflow_type: str = None) -> Dict:
        """Send a message and get response."""
        log_user(message)
        
        payload = {
            "session_id": self.session_id,
            "message": message,
        }
        if workflow_type:
            payload["workflow_type"] = workflow_type
        
        try:
            resp = requests.post(
                f"{self.base_url}/chat",
                json=payload,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=120  # Chat can be slow with tool calls
            )
            
            if resp.status_code == 200:
                data = resp.json()
                self.last_response = data
                
                # Log response
                log_agent(data.get("assistant_message", ""))
                
                # Track tool calls
                if data.get("tool_calls_count", 0) > 0:
                    log_tool(f"{data['tool_calls_count']} tool(s) executed")
                    self.tool_calls.append({
                        "turn": len(self.conversation_history) + 1,
                        "count": data["tool_calls_count"]
                    })
                
                # Track conversation
                self.conversation_history.append({
                    "role": "user",
                    "content": message
                })
                self.conversation_history.append({
                    "role": "assistant",
                    "content": data.get("assistant_message", "")
                })
                
                return data
            else:
                log_fail(f"Chat error: {resp.status_code} - {resp.text[:200]}")
                return {"error": resp.text}
                
        except Exception as e:
            log_fail(f"Chat exception: {e}")
            return {"error": str(e)}
    
    def get_pending_approvals(self) -> List[Dict]:
        """Get pending tool approvals."""
        try:
            resp = requests.get(
                f"{self.base_url}/chat/pending-approvals",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=30
            )
            if resp.status_code == 200:
                return resp.json()
            return []
        except:
            return []
    
    def approve(self, approval_id: int, approved: bool = True) -> bool:
        """Approve or reject a pending tool call."""
        try:
            resp = requests.post(
                f"{self.base_url}/chat/approve",
                json={
                    "approval_id": approval_id,
                    "approved": approved,
                },
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=60
            )
            return resp.status_code == 200
        except:
            return False

    # =========================================================================
    # MCP Integration Methods (Phase 5)
    # =========================================================================
    
    def list_integrations(self) -> List[Dict]:
        """List all MCP integrations for the tenant."""
        try:
            resp = requests.get(
                f"{self.base_url}/integrations",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=30
            )
            if resp.status_code == 200:
                return resp.json()
            log_debug(f"List integrations: {resp.status_code}")
            return []
        except Exception as e:
            log_debug(f"List integrations error: {e}")
            return []
    
    def check_integration_health(self, integration_id: int) -> Dict:
        """Check health of a specific integration."""
        try:
            resp = requests.post(
                f"{self.base_url}/integrations/{integration_id}/health",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=30
            )
            if resp.status_code == 200:
                return resp.json()
            return {"status": "error", "code": resp.status_code}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def test_integration_connection(self, integration_id: int) -> Dict:
        """Test connection for an integration (uses stored credentials)."""
        try:
            resp = requests.post(
                f"{self.base_url}/integrations/{integration_id}/test",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=60
            )
            return {
                "status_code": resp.status_code,
                "success": resp.status_code == 200,
                "response": resp.json() if resp.status_code in [200, 400, 404] else resp.text[:200]
            }
        except Exception as e:
            return {"status_code": 0, "success": False, "error": str(e)}
    
    def check_server_health(self) -> Dict:
        """Check overall server health via /health endpoint."""
        try:
            resp = requests.get(
                f"{BACKEND_URL}/health",
                timeout=10
            )
            return {
                "status_code": resp.status_code,
                "healthy": resp.status_code == 200,
                "response": resp.json() if resp.status_code == 200 else resp.text[:200]
            }
        except Exception as e:
            return {"status_code": 0, "healthy": False, "error": str(e)}
    
    def get_mcp_server_status(self) -> Dict:
        """Get MCP server status (may require internal endpoint)."""
        # Try chat endpoint to trigger MCP initialization and get info
        try:
            # Create a temp session and send a simple message to verify MCP is up
            if not self.session_id:
                self.create_session("MCP Health Check")
            
            # Send a message that would use tools
            resp = self.send_message("What tools do you have available?")
            
            return {
                "mcp_responding": "error" not in resp,
                "tool_calls": resp.get("tool_calls_count", 0),
                "response_received": bool(resp.get("assistant_message"))
            }
        except Exception as e:
            return {"mcp_responding": False, "error": str(e)}


# =============================================================================
# SCENARIO DEFINITION
# =============================================================================

@dataclass
class ConversationTurn:
    """A single turn in the conversation."""
    user_message: str
    expected_keywords: List[str] = field(default_factory=list)
    expected_tool_use: bool = False
    workflow_type: Optional[str] = None
    wait_for_approval: bool = False
    approve: bool = True  # Auto-approve if approval requested


@dataclass
class Scenario:
    """A complete test scenario."""
    name: str
    description: str
    goal: str
    turns: List[ConversationTurn]
    verification: Optional[Callable[[ChatClient], bool]] = None
    setup: Optional[Callable[[ChatClient], None]] = None
    teardown: Optional[Callable[[ChatClient], None]] = None
    # Tags to categorize scenarios
    tags: List[str] = field(default_factory=list)  # e.g., ["jira", "browser", "core"]
    requires_external_mcp: bool = False  # True if needs external MCP (Jira, Playwright)


# =============================================================================
# VERIFICATION HELPERS
# =============================================================================

def verify_response_contains(response: Dict, keywords: List[str]) -> bool:
    """Check if response contains expected keywords."""
    text = response.get("assistant_message", "").lower()
    for keyword in keywords:
        if keyword.lower() not in text:
            log_debug(f"Missing keyword: {keyword}")
            return False
    return True


def verify_tools_used(response: Dict) -> bool:
    """Check if tools were used in response."""
    return response.get("tool_calls_count", 0) > 0


# =============================================================================
# SCENARIO DEFINITIONS
# =============================================================================

def get_scenarios() -> Dict[str, Scenario]:
    """Define all test scenarios."""
    
    scenarios = {}
    
    # =========================================================================
    # SCENARIO 1: Basic Greeting & Capabilities
    # =========================================================================
    scenarios["greeting"] = Scenario(
        name="greeting",
        description="Test basic greeting and capability discovery",
        goal="Agent responds appropriately and explains capabilities",
        turns=[
            ConversationTurn(
                user_message="Hello! I'm new here. What can you help me with?",
                expected_keywords=["help", "assistant", "work"],
            ),
            ConversationTurn(
                user_message="That sounds great! Can you give me a quick overview of your main features?",
                expected_keywords=["features", "calculation", "memory"],
            ),
        ],
    )
    
    # =========================================================================
    # SCENARIO 2: Club Setup Workflow
    # =========================================================================
    scenarios["club_setup"] = Scenario(
        name="club_setup",
        description="Complete club onboarding workflow",
        goal="Successfully create a new golf club with database and admin user",
        turns=[
            ConversationTurn(
                user_message="I need to set up a new golf club in the system.",
                expected_keywords=["club", "name", "setup"],
                workflow_type="club_setup",
            ),
            ConversationTurn(
                user_message="The club is called 'Sunset Valley Golf Club'. The admin email is admin@sunsetvalley.golf and the contact name is John Smith.",
                expected_keywords=["sunset", "valley"],
                expected_tool_use=True,
                workflow_type="club_setup",
            ),
            ConversationTurn(
                user_message="Great, please proceed with the setup.",
                expected_tool_use=True,
                wait_for_approval=True,
                approve=True,
                workflow_type="club_setup",
            ),
        ],
    )
    
    # =========================================================================
    # SCENARIO 3: Member Lookup
    # =========================================================================
    scenarios["member_lookup"] = Scenario(
        name="member_lookup",
        description="Look up member information",
        goal="Successfully retrieve member details",
        turns=[
            ConversationTurn(
                user_message="Can you look up information about member John Smith?",
                expected_tool_use=True,
            ),
            ConversationTurn(
                user_message="What's their membership status?",
                expected_keywords=["member", "status"],
            ),
        ],
    )
    
    # =========================================================================
    # SCENARIO 4: Booking Query
    # =========================================================================
    scenarios["booking_query"] = Scenario(
        name="booking_query",
        description="Query tee time availability",
        goal="Successfully check booking availability",
        turns=[
            ConversationTurn(
                user_message="What tee times are available tomorrow morning?",
                expected_tool_use=True,
            ),
            ConversationTurn(
                user_message="Are there any slots around 9am?",
                expected_keywords=["9", "available", "time"],
            ),
        ],
    )
    
    # =========================================================================
    # SCENARIO 5: Multi-Turn Context
    # =========================================================================
    scenarios["context_retention"] = Scenario(
        name="context_retention",
        description="Test conversation context is maintained",
        goal="Agent remembers previous context across turns",
        turns=[
            ConversationTurn(
                user_message="I'm interested in setting up a club called 'Mountain View Golf'.",
                expected_keywords=["mountain", "view"],
            ),
            ConversationTurn(
                user_message="The admin will be Sarah Johnson.",
                expected_keywords=["sarah", "johnson"],
            ),
            ConversationTurn(
                user_message="Can you summarize what we've discussed?",
                expected_keywords=["mountain", "view", "sarah", "johnson"],
            ),
        ],
    )
    
    # =========================================================================
    # SCENARIO 6: Error Recovery
    # =========================================================================
    scenarios["error_recovery"] = Scenario(
        name="error_recovery",
        description="Test graceful error handling",
        goal="Agent handles invalid requests gracefully",
        turns=[
            ConversationTurn(
                user_message="Delete all clubs from the system!",
                expected_keywords=["cannot", "sorry", "help"],  # Should refuse
            ),
            ConversationTurn(
                user_message="Actually, I just need help looking up a specific club.",
                expected_keywords=["help", "club", "look"],
            ),
        ],
    )
    
    # =========================================================================
    # SCENARIO 7: Complex Workflow with Approval
    # =========================================================================
    scenarios["approval_flow"] = Scenario(
        name="approval_flow",
        description="Test approval flow for sensitive operations",
        goal="System requests approval before sensitive operations",
        turns=[
            ConversationTurn(
                user_message="I need to create a new admin user for the system.",
                expected_keywords=["admin", "user"],
                workflow_type="admin",
            ),
            ConversationTurn(
                user_message="Create an admin with email newadmin@golf.com and name Admin User.",
                expected_tool_use=True,
                wait_for_approval=True,
                approve=True,
                workflow_type="admin",
            ),
        ],
    )
    
    # =========================================================================
    # SCENARIO 8: Analytics Query
    # =========================================================================
    scenarios["analytics"] = Scenario(
        name="analytics",
        description="Query system analytics",
        goal="Successfully retrieve analytics data",
        turns=[
            ConversationTurn(
                user_message="What are the busiest booking times this week?",
                expected_tool_use=True,
            ),
            ConversationTurn(
                user_message="How does that compare to last week?",
                expected_keywords=["week", "compare"],
            ),
        ],
    )
    
    # =========================================================================
    # SCENARIO 9: Help & Documentation
    # =========================================================================
    scenarios["help"] = Scenario(
        name="help",
        description="Test help and documentation queries",
        goal="Agent provides helpful documentation",
        turns=[
            ConversationTurn(
                user_message="How do I configure tee sheet intervals?",
                expected_keywords=["tee", "sheet", "interval"],
            ),
            ConversationTurn(
                user_message="What's the default interval?",
                expected_keywords=["minute", "default"],
            ),
        ],
    )
    
    # =========================================================================
    # SCENARIO 10: Long Conversation Stress Test
    # =========================================================================
    scenarios["stress_test"] = Scenario(
        name="stress_test",
        description="Test long conversation handling",
        goal="System handles extended conversations",
        turns=[
            ConversationTurn(user_message="Let's have a detailed conversation about club management."),
            ConversationTurn(user_message="First, tell me about member management features."),
            ConversationTurn(user_message="What about booking management?"),
            ConversationTurn(user_message="How about reporting and analytics?"),
            ConversationTurn(user_message="What integrations are available?"),
            ConversationTurn(user_message="Can you summarize everything we discussed?",
                           expected_keywords=["member", "booking", "analytics"]),
        ],
    )
    
    # =========================================================================
    # INFRASTRUCTURE SCENARIOS (MCP Connectivity via Backend API)
    # =========================================================================
    
    # =========================================================================
    # SCENARIO: MCP Health Check (No conversation, just API checks)
    # =========================================================================
    def verify_mcp_health(client: ChatClient) -> bool:
        """Verify MCP infrastructure is healthy via API."""
        log_step("Checking server health")
        health = client.check_server_health()
        if health.get("healthy"):
            log_pass(f"Server healthy: {health.get('response', {})}")
        else:
            log_fail(f"Server unhealthy: {health}")
            return False
        
        log_step("Checking MCP connectivity")
        mcp_status = client.get_mcp_server_status()
        if mcp_status.get("mcp_responding"):
            log_pass(f"MCP responding, got response: {mcp_status.get('response_received')}")
        else:
            log_fail(f"MCP not responding: {mcp_status}")
            return False
        
        return True
    
    scenarios["mcp_health"] = Scenario(
        name="mcp_health",
        description="Verify MCP servers are healthy via backend API",
        goal="Confirm Gateway MCP and chat infrastructure are responding",
        tags=["infrastructure", "mcp", "health"],
        turns=[
            ConversationTurn(
                user_message="Hello, can you confirm you have access to tools?",
                expected_keywords=["tool", "help"],
            ),
        ],
        verification=verify_mcp_health,
    )
    
    # =========================================================================
    # SCENARIO: Integration Discovery (List configured integrations)
    # =========================================================================
    def verify_integrations_api(client: ChatClient) -> bool:
        """Verify integrations API is accessible."""
        log_step("Listing MCP integrations via API")
        integrations = client.list_integrations()
        
        if isinstance(integrations, list):
            log_pass(f"Found {len(integrations)} integration(s)")
            for integ in integrations:
                name = integ.get("integration_name", "unknown")
                enabled = integ.get("is_enabled", False)
                status = "✓ enabled" if enabled else "○ disabled"
                log_info(f"  {name}: {status}")
            return True
        else:
            log_fail("Failed to list integrations")
            return False
    
    scenarios["integration_discovery"] = Scenario(
        name="integration_discovery",
        description="List and verify configured MCP integrations",
        goal="Confirm integrations API works and shows configured MCPs",
        tags=["infrastructure", "integrations", "api"],
        turns=[
            ConversationTurn(
                user_message="What external integrations do you have configured?",
                expected_keywords=["integrat"],  # integration/integrated/integrations
            ),
        ],
        verification=verify_integrations_api,
    )
    
    # =========================================================================
    # SCENARIO: Integration Health Checks (Test each configured integration)
    # =========================================================================
    def verify_integration_health(client: ChatClient) -> bool:
        """Check health of all enabled integrations."""
        integrations = client.list_integrations()
        
        if not integrations:
            log_info("No integrations configured")
            return True  # Not a failure if none configured
        
        enabled_integrations = [i for i in integrations if i.get("is_enabled")]
        
        if not enabled_integrations:
            log_info("No enabled integrations to check")
            return True
        
        all_healthy = True
        for integ in enabled_integrations:
            integ_id = integ.get("id")
            name = integ.get("integration_name", "unknown")
            
            log_step(f"Checking health: {name}")
            health = client.check_integration_health(integ_id)
            
            if health.get("status") == "healthy":
                log_pass(f"{name}: healthy")
            elif health.get("status") == "disabled":
                log_info(f"{name}: disabled")
            else:
                log_fail(f"{name}: {health}")
                all_healthy = False
        
        return all_healthy
    
    scenarios["integration_health"] = Scenario(
        name="integration_health",
        description="Check health of all enabled MCP integrations",
        goal="Verify each configured integration is accessible",
        tags=["infrastructure", "integrations", "health"],
        requires_external_mcp=True,
        turns=[
            ConversationTurn(
                user_message="Can you check if all your integrations are working?",
                expected_keywords=["integrat", "check"],
            ),
        ],
        verification=verify_integration_health,
    )
    
    # =========================================================================
    # SCENARIO: Integration Connection Test (Test actual connectivity)
    # =========================================================================
    def verify_integration_connection(client: ChatClient) -> bool:
        """Test actual connection for integrations with credentials."""
        integrations = client.list_integrations()
        
        if not integrations:
            log_info("No integrations configured")
            return True
        
        enabled_integrations = [i for i in integrations if i.get("is_enabled")]
        
        if not enabled_integrations:
            log_info("No enabled integrations to test")
            return True
        
        results = []
        for integ in enabled_integrations:
            integ_id = integ.get("id")
            name = integ.get("integration_name", "unknown")
            
            log_step(f"Testing connection: {name}")
            result = client.test_integration_connection(integ_id)
            
            if result.get("success"):
                log_pass(f"{name}: connection successful")
                results.append(True)
            elif result.get("status_code") == 404 and "credential" in str(result.get("response", "")).lower():
                log_info(f"{name}: no credentials configured (OAuth required)")
                results.append(True)  # Expected for unconfigured OAuth
            else:
                log_fail(f"{name}: connection failed - {result}")
                results.append(False)
        
        return all(results) if results else True
    
    scenarios["integration_connection"] = Scenario(
        name="integration_connection",
        description="Test actual connection for integrations with stored credentials",
        goal="Verify OAuth/API key credentials work for external MCPs",
        tags=["infrastructure", "integrations", "connection", "oauth"],
        requires_external_mcp=True,
        turns=[
            ConversationTurn(
                user_message="Test the connection to your external systems.",
                expected_keywords=["connect", "test"],
            ),
        ],
        verification=verify_integration_connection,
    )
    
    # =========================================================================
    # CROSS-MCP SCENARIOS (External Integrations)
    # =========================================================================
    
    # =========================================================================
    # SCENARIO 11: Jira Ticket Escalation (BRS + Jira)
    # =========================================================================
    scenarios["jira_ticket_escalation"] = Scenario(
        name="jira_ticket_escalation",
        description="Support agent escalates member issue to Jira",
        goal="Create a Jira ticket with member/booking context from BRS",
        tags=["jira", "cross-mcp", "support"],
        requires_external_mcp=True,
        turns=[
            ConversationTurn(
                user_message="I have a member complaint I need to escalate. Member ID is 12345.",
                expected_keywords=["member", "complaint"],
                expected_tool_use=True,  # Should look up member info
            ),
            ConversationTurn(
                user_message="The member says their booking for tomorrow was cancelled without notice. Can you check their recent bookings?",
                expected_keywords=["booking", "cancel"],
                expected_tool_use=True,  # Should check booking history
            ),
            ConversationTurn(
                user_message="Please create a Jira ticket in the GOLF project to track this complaint. Set it as high priority.",
                expected_keywords=["jira", "ticket", "created"],
                expected_tool_use=True,  # Should call create_ticket
                wait_for_approval=True,
                approve=True,
            ),
            ConversationTurn(
                user_message="Add a comment to the ticket with the booking details we found.",
                expected_keywords=["comment", "added"],
                expected_tool_use=True,  # Should call add_comment
            ),
        ],
    )
    
    # =========================================================================
    # SCENARIO 12: Jira Status Check (Jira standalone)
    # =========================================================================
    scenarios["jira_status_check"] = Scenario(
        name="jira_status_check",
        description="Check status of existing Jira ticket",
        goal="Retrieve and report on Jira ticket status",
        tags=["jira", "cross-mcp"],
        requires_external_mcp=True,
        turns=[
            ConversationTurn(
                user_message="What's the status of Jira ticket GOLF-123?",
                expected_keywords=["status", "GOLF-123"],
                expected_tool_use=True,  # Should call get_ticket_status
            ),
            ConversationTurn(
                user_message="When was it last updated?",
                expected_keywords=["update", "last"],
            ),
        ],
    )
    
    # =========================================================================
    # SCENARIO 13: Cross-System Audit Trail (BRS + Jira)
    # =========================================================================
    scenarios["cross_system_audit"] = Scenario(
        name="cross_system_audit",
        description="Link booking cancellation to Jira for audit",
        goal="Create audit trail across BRS and Jira",
        tags=["jira", "cross-mcp", "audit"],
        requires_external_mcp=True,
        turns=[
            ConversationTurn(
                user_message="I need to cancel booking 789 due to course maintenance. This needs to be tracked in Jira.",
                expected_keywords=["cancel", "booking"],
            ),
            ConversationTurn(
                user_message="Yes, please proceed with the cancellation and create a Jira ticket documenting why.",
                expected_tool_use=True,
                wait_for_approval=True,
                approve=True,
            ),
            ConversationTurn(
                user_message="Can you confirm both the cancellation and the ticket were created?",
                expected_keywords=["cancelled", "ticket"],
            ),
        ],
    )
    
    # =========================================================================
    # SCENARIO 14: Browser Navigation Stress Test (Playwright)
    # [ASPIRATIONAL - Requires Playwright MCP to be configured]
    # =========================================================================
    scenarios["browser_navigation"] = Scenario(
        name="browser_navigation",
        description="[ASPIRATIONAL] Navigate browser to verify UI state",
        goal="Agent can control browser for UI verification",
        tags=["browser", "playwright", "stress-test", "aspirational"],
        requires_external_mcp=True,
        turns=[
            ConversationTurn(
                user_message="Open the club admin dashboard at https://admin.demo.golf",
                expected_keywords=["open", "browser", "dashboard"],
                expected_tool_use=True,  # Should use Playwright open_page
            ),
            ConversationTurn(
                user_message="Take a screenshot of the current page.",
                expected_keywords=["screenshot"],
                expected_tool_use=True,  # Should use Playwright screenshot
            ),
            ConversationTurn(
                user_message="Click on the 'Bookings' menu item.",
                expected_keywords=["click", "booking"],
                expected_tool_use=True,  # Should use Playwright click
            ),
            ConversationTurn(
                user_message="Search for bookings from today and tell me how many are listed.",
                expected_keywords=["booking", "found", "today"],
                expected_tool_use=True,  # Multiple Playwright actions
            ),
        ],
    )
    
    # =========================================================================
    # SCENARIO 15: Multi-Tool Orchestration (BRS + Jira + potentially more)
    # =========================================================================
    scenarios["multi_tool_orchestration"] = Scenario(
        name="multi_tool_orchestration",
        description="Complex workflow using multiple MCPs in sequence",
        goal="Test agent's ability to orchestrate across 3+ tools in one conversation",
        tags=["cross-mcp", "stress-test", "orchestration"],
        requires_external_mcp=True,
        turns=[
            ConversationTurn(
                user_message="I need a full audit report: find all cancelled bookings from this week.",
                expected_tool_use=True,  # BRS query
            ),
            ConversationTurn(
                user_message="For each cancellation, create a summary. How many cancellations were there?",
                expected_keywords=["cancel", "summary"],
            ),
            ConversationTurn(
                user_message="Create a Jira ticket summarizing this week's cancellations with the count and reasons.",
                expected_tool_use=True,  # Jira create_ticket
                wait_for_approval=True,
                approve=True,
            ),
            ConversationTurn(
                user_message="Now send an email to the club manager summarizing what we found.",
                expected_keywords=["email", "manager"],  # May need email tool or explain limitation
            ),
        ],
    )
    
    return scenarios


# =============================================================================
# SCENARIO RUNNER
# =============================================================================

class ScenarioRunner:
    """Runs scenarios and tracks results."""

    def __init__(self, retry_on_flake: bool = False, save_results: bool = False):
        self.client = ChatClient()
        self.results: Dict[str, Dict] = {}
        self.retry_on_flake = retry_on_flake
        self.save_results = save_results
        self.start_time = None
    
    def setup(self) -> bool:
        """Initialize client with auth."""
        log_step("Setting up test client")
        
        if not self.client.login(TEST_EMAIL, TEST_PASSWORD):
            log_fail("Failed to authenticate")
            return False
        
        log_pass("Authentication successful")
        return True
    
    def run_scenario(self, scenario: Scenario, retry_attempt: int = 0) -> Tuple[bool, Dict]:
        """Execute a single scenario with retry logic. Returns (success, turn_results)."""
        print(f"\n{'='*60}")
        print(f"{BOLD}SCENARIO: {scenario.name}{END}")
        if retry_attempt > 0:
            print(f"{YELLOW}Retry attempt {retry_attempt}{END}")
        print(f"Goal: {scenario.goal}")
        print(f"{'='*60}")
        
        # Create fresh session
        if not self.client.create_session(f"Scenario: {scenario.name} - Attempt {retry_attempt + 1}"):
            log_fail("Failed to create session")
            return False, {"error": "session_creation_failed"}

        # Run setup if provided
        if scenario.setup:
            scenario.setup(self.client)

        success = True
        turn_results = []
        start_turn_time = time.time()

        for i, turn in enumerate(scenario.turns, 1):
            log_step(f"Turn {i}")
            turn_start = time.time()

            # Send message
            response = self.client.send_message(
                turn.user_message,
                workflow_type=turn.workflow_type
            )

            turn_duration = time.time() - turn_start

            if "error" in response:
                error_msg = response['error']
                log_fail(f"Turn {i} failed: {error_msg}")

                # Check if error is transient
                if self.retry_on_flake and retry_attempt < 2 and is_transient_error(error_msg):
                    log_info(f"Transient error detected, will retry scenario")
                    turn_results.append({
                        "turn": i,
                        "success": False,
                        "error": error_msg,
                        "transient": True,
                        "duration_seconds": turn_duration
                    })
                    # Return early to trigger retry
                    return False, {"transient_error": True}

                success = False
                turn_results.append({
                    "turn": i,
                    "success": False,
                    "error": error_msg,
                    "transient": False,
                    "duration_seconds": turn_duration
                })
                continue
            
            # Check expected keywords
            keywords_matched = False
            if turn.expected_keywords:
                keywords_matched = verify_response_contains(response, turn.expected_keywords)
                if keywords_matched:
                    log_pass(f"Response contains expected keywords")
                else:
                    log_fail(f"Missing expected keywords: {turn.expected_keywords}")
                    success = False

            # Check tool usage
            tool_used = False
            if turn.expected_tool_use:
                tool_used = verify_tools_used(response)
                if tool_used:
                    log_pass(f"Tools were used as expected")
                else:
                    log_fail("Expected tool use but none occurred")
                    success = False

            turn_results.append({
                "turn": i,
                "success": True,
                "keywords_matched": keywords_matched if turn.expected_keywords else None,
                "tool_used": tool_used if turn.expected_tool_use else None,
                "duration_seconds": turn_duration
            })

            # Handle approval flow
            if turn.wait_for_approval:
                pending = response.get("pending_approval")
                if pending:
                    log_info(f"Approval requested for: {pending.get('tool_name', 'unknown')}")
                    if turn.approve:
                        if self.client.approve(pending["approval_id"], True):
                            log_pass("Approved and resumed")
                        else:
                            log_fail("Approval failed")
                            success = False

            # Small delay between turns
            time.sleep(0.5)

        # Run verification if provided
        if scenario.verification and success:
            if scenario.verification(self.client):
                log_pass("Verification passed")
            else:
                log_fail("Verification failed")
                success = False

        # Run teardown if provided
        if scenario.teardown:
            scenario.teardown(self.client)

        total_duration = time.time() - start_turn_time

        # Record results
        self.results[scenario.name] = {
            "success": success,
            "turns": turn_results,
            "total_tool_calls": sum(t.get("count", 0) for t in self.client.tool_calls),
            "duration_seconds": total_duration,
            "retry_attempt": retry_attempt
        }

        if success:
            log_pass(f"SCENARIO PASSED: {scenario.name}")
        else:
            log_fail(f"SCENARIO FAILED: {scenario.name}")

        return success, self.results[scenario.name]
    
    def run_all(self, scenario_names: List[str] = None) -> Dict:
        """Run multiple scenarios with optional retry logic."""
        scenarios = get_scenarios()

        if scenario_names:
            scenarios = {k: v for k, v in scenarios.items() if k in scenario_names}

        total = len(scenarios)
        passed = 0
        self.start_time = time.time()

        for name, scenario in scenarios.items():
            success = False
            for attempt in range(3 if self.retry_on_flake else 1):
                scenario_success, result = self.run_scenario(scenario, retry_attempt=attempt)

                if scenario_success:
                    success = True
                    break
                elif result.get("transient_error") and attempt < 2:
                    # Transient error, will retry
                    backoff = 2 ** attempt  # 1, 2, 4 seconds
                    log_info(f"Waiting {backoff}s before retry...")
                    time.sleep(backoff)
                    continue
                else:
                    # Non-transient error or final attempt failed
                    break

            if success:
                passed += 1

        total_duration = time.time() - self.start_time

        # Save results if requested
        if self.save_results:
            scenario_results = []
            for name, result in self.results.items():
                scenario_results.append(
                    ResultExporter.format_scenario_result(
                        scenario_name=name,
                        success=result.get("success", False),
                        turns=result.get("turns", []),
                        tool_calls_count=result.get("total_tool_calls", 0),
                        error=result.get("turns", [{}])[0].get("error") if result.get("turns") else None
                    )
                )

            test_run = ResultExporter.format_test_run(
                timestamp=datetime.now().isoformat(),
                environment=os.environ.get("TEST_ENV", "dev"),
                scenarios=scenario_results,
                duration_seconds=total_duration,
                tags=["core"] if "--core-only" in sys.argv else (["external"] if "--external-only" in sys.argv else ["all"])
            )

            filepath = ResultExporter.save_to_json(test_run)
            log_pass(f"Results saved to {filepath}")

        return {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "duration_seconds": total_duration,
            "results": self.results,
        }
    
    def print_summary(self, results: Dict):
        """Print final summary."""
        print(f"\n{'='*60}")
        print(f"{BOLD}TEST SUMMARY{END}")
        print(f"{'='*60}")
        print(f"Total:  {results['total']}")
        print(f"Passed: {GREEN}{results['passed']}{END}")
        print(f"Failed: {RED}{results['failed']}{END}")
        
        if results["failed"] > 0:
            print(f"\n{RED}Failed Scenarios:{END}")
            for name, result in results["results"].items():
                if not result["success"]:
                    print(f"  - {name}")
        
        print(f"{'='*60}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    global VERBOSE
    
    parser = argparse.ArgumentParser(description="Run chatbot test scenarios")
    parser.add_argument("--scenario", "-s", help="Run specific scenario")
    parser.add_argument("--list", "-l", action="store_true", help="List available scenarios")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--core-only", action="store_true", help="Skip scenarios requiring external MCPs (Jira, Playwright)")
    parser.add_argument("--external-only", action="store_true", help="Only run scenarios requiring external MCPs")
    parser.add_argument("--tag", "-t", help="Only run scenarios with this tag")
    parser.add_argument("--retry-on-flake", action="store_true", help="Auto-retry transient failures (up to 2 times)")
    parser.add_argument("--save-results", action="store_true", help="Save results to JSON file")
    args = parser.parse_args()
    
    VERBOSE = args.verbose
    
    if args.list:
        scenarios = get_scenarios()
        print(f"\n{BOLD}Available Scenarios:{END}")
        print(f"\n{YELLOW}Core Scenarios (no external MCP required):{END}")
        for name, scenario in scenarios.items():
            if not scenario.requires_external_mcp:
                tags = f" [{', '.join(scenario.tags)}]" if scenario.tags else ""
                print(f"  {name}: {scenario.description}{DIM}{tags}{END}")
        
        print(f"\n{YELLOW}External MCP Scenarios (Jira, Playwright, etc.):{END}")
        for name, scenario in scenarios.items():
            if scenario.requires_external_mcp:
                tags = f" [{', '.join(scenario.tags)}]" if scenario.tags else ""
                marker = f"{RED}[ASPIRATIONAL]{END}" if "aspirational" in scenario.tags else ""
                print(f"  {name}: {scenario.description} {marker}{DIM}{tags}{END}")
        
        print(f"\n{DIM}Usage: --core-only to skip external MCPs, --tag jira for specific tags{END}")
        return 0
    
    print(f"\n{BOLD}{'='*60}{END}")
    print(f"{BOLD}GOLFNOW AGENT SCENARIO TESTS{END}")
    print(f"{'='*60}")
    print(f"Server: {BACKEND_URL}")
    print(f"Time: {datetime.now().isoformat()}")
    
    runner = ScenarioRunner(
        retry_on_flake=args.retry_on_flake,
        save_results=args.save_results
    )

    if not runner.setup():
        return 1
    
    scenarios = get_scenarios()
    
    # Filter scenarios based on flags
    if args.scenario:
        if args.scenario not in scenarios:
            log_fail(f"Unknown scenario: {args.scenario}")
            return 1
        scenario_names = [args.scenario]
    else:
        scenario_names = list(scenarios.keys())
    
    # Apply filters
    if args.core_only:
        scenario_names = [n for n in scenario_names if not scenarios[n].requires_external_mcp]
        print(f"{YELLOW}Running core scenarios only (skipping external MCPs){END}")
    elif args.external_only:
        scenario_names = [n for n in scenario_names if scenarios[n].requires_external_mcp]
        print(f"{YELLOW}Running external MCP scenarios only{END}")
    
    if args.tag:
        scenario_names = [n for n in scenario_names if args.tag in scenarios[n].tags]
        print(f"{YELLOW}Filtering by tag: {args.tag}{END}")
    
    if not scenario_names:
        log_fail("No scenarios match the specified filters")
        return 1
    
    results = runner.run_all(scenario_names)
    
    runner.print_summary(results)
    
    return 0 if results["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
