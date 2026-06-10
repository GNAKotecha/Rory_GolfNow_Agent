#!/usr/bin/env python3
"""
Direct test for REINSTATE_USER workflow - Iteration 3
Validates Bug #11 (timeout) and Bug #10 (state machine) fixes
"""
import sys
import os
import asyncio
import time
from datetime import datetime

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.agentic_service import AgenticService
from app.services.ollama import OllamaService
from app.services.mcp_registry import MCPRegistry
from app.config.mcp_config import Environment
from app.models.models import TenantSkill
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


# Test configuration
TEST_USERNAME = "98765432"
DB_URL = os.environ.get("DATABASE_URL", "postgresql://rory:rory@localhost:5432/rory")


class TestResults:
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.tool_calls = []
        self.state_transitions = []
        self.errors = []
        self.success = False
        self.timeout_occurred = False

    def add_tool_call(self, tool_name, args, result):
        self.tool_calls.append({
            'tool': tool_name,
            'args': args,
            'result': str(result)[:200],  # Truncate for readability
            'timestamp': time.time()
        })

    def add_state_transition(self, from_state, to_state):
        self.state_transitions.append({
            'from': from_state,
            'to': to_state,
            'timestamp': time.time()
        })

    def report(self):
        duration = (self.end_time - self.start_time) if self.start_time and self.end_time else 0

        print("\n" + "="*80)
        print(f"REINSTATE_USER WORKFLOW TEST - ITERATION 3")
        print(f"Testing Bug #11 (timeout) and Bug #10 (state machine) fixes")
        print("="*80)

        print(f"\n⏱️  EXECUTION TIME: {duration:.2f}s")
        if duration > 180:
            print(f"   ❌ TIMEOUT: Exceeded 180s limit")
            self.timeout_occurred = True
        else:
            print(f"   ✅ Under 180s timeout limit")

        print(f"\n🔧 TOOL CALLS: {len(self.tool_calls)} total")
        tool_sequence = [t['tool'] for t in self.tool_calls]
        print(f"   Sequence: {' → '.join(tool_sequence)}")

        # Check for repeated calls (Bug #10 symptom)
        from collections import Counter
        tool_counts = Counter(tool_sequence)
        repeated = {k: v for k, v in tool_counts.items() if v > 2}
        if repeated:
            print(f"   ⚠️  REPEATED CALLS: {repeated}")
        else:
            print(f"   ✅ No excessive repetition")

        print(f"\n🔄 STATE TRANSITIONS: {len(self.state_transitions)} total")
        for trans in self.state_transitions:
            print(f"   {trans['from']} → {trans['to']}")

        # Check state machine progression (Bug #10 validation)
        expected_states = ['initial', 'after_read', 'after_write', 'complete']
        actual_states = [t['to'] for t in self.state_transitions]
        if actual_states == expected_states:
            print(f"   ✅ Correct state progression")
        else:
            print(f"   ❌ Unexpected state progression")
            print(f"      Expected: {expected_states}")
            print(f"      Actual: {actual_states}")

        if self.errors:
            print(f"\n❌ ERRORS: {len(self.errors)}")
            for err in self.errors:
                print(f"   - {err}")
        else:
            print(f"\n✅ NO ERRORS")

        print(f"\n📊 FINAL RESULT: {'✅ PASS' if self.success and not self.timeout_occurred and not self.errors else '❌ FAIL'}")
        print("="*80)

        return self.success and not self.timeout_occurred and not self.errors


async def test_reinstate_user():
    """Test REINSTATE_USER workflow directly"""
    results = TestResults()
    results.start_time = time.time()

    try:
        # Initialize services
        print("Initializing services...")
        engine = create_engine(DB_URL)
        Session = sessionmaker(bind=engine)
        db = Session()

        # Get REINSTATE_USER skill
        skill = db.query(TenantSkill).filter(
            TenantSkill.skill_name == "REINSTATE_USER"
        ).first()

        if not skill:
            results.errors.append("REINSTATE_USER skill not found in database")
            return results

        print(f"Found skill: {skill.skill_name} (timeout: {skill.timeout_seconds}s)")

        # Initialize MCP registry
        mcp_registry = MCPRegistry(environment=Environment.DEVELOPMENT)
        await mcp_registry.initialize()

        # Initialize Ollama
        ollama = OllamaService()

        # Initialize Agentic Service
        agentic = AgenticService(
            ollama=ollama,
            mcp_registry=mcp_registry,
            db=db
        )

        # Execute workflow
        print(f"\nExecuting REINSTATE_USER for username: {TEST_USERNAME}")
        print(f"Monitoring: timeouts, tool sequence, state transitions\n")

        result = await agentic.execute(
            skill_name="REINSTATE_USER",
            context={"username": TEST_USERNAME},
            tenant_id=1,
            user_id=1
        )

        results.end_time = time.time()

        # Parse result
        if result.get("status") == "success":
            results.success = True
            print(f"✅ Workflow completed successfully")
        else:
            results.errors.append(f"Workflow failed: {result.get('error', 'Unknown error')}")

        # Extract tool calls and state transitions from result
        if "execution_log" in result:
            for entry in result["execution_log"]:
                if entry.get("type") == "tool_call":
                    results.add_tool_call(
                        entry.get("tool"),
                        entry.get("args"),
                        entry.get("result")
                    )
                elif entry.get("type") == "state_transition":
                    results.add_state_transition(
                        entry.get("from_state"),
                        entry.get("to_state")
                    )

    except asyncio.TimeoutError:
        results.end_time = time.time()
        results.timeout_occurred = True
        results.errors.append("LLM request timed out (Bug #11 regression)")

    except Exception as e:
        results.end_time = time.time()
        results.errors.append(f"Unexpected error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()

    finally:
        # Generate report
        return results.report()


if __name__ == "__main__":
    print(f"REINSTATE_USER Workflow Test - Iteration 3")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"Target username: {TEST_USERNAME}\n")

    success = asyncio.run(test_reinstate_user())
    sys.exit(0 if success else 1)
