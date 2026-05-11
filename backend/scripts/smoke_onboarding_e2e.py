"""Smoke E2E: Teesheet onboarding with mock BRS tools.

Runs the full onboarding tool sequence using MockBRSToolExecutor and
asserts the call order, parameters, and structured outputs.

Usage:
    cd backend
    python scripts/smoke_onboarding_e2e.py

Exit code 0 = pass, 1 = fail.
"""

import asyncio
import sys
from pathlib import Path

# Ensure backend/ is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.brs_tools.registry import BRSToolRegistry
from app.services.brs_tools.mock import MockBRSToolExecutor
from app.services.brs_tools.parser import BRSToolOutputParser
from app.services.brs_tools.schemas import (
    TeesheetInitOutput,
    SuperuserCreateOutput,
)


# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
END = "\033[0m"


def ok(msg: str) -> None:
    print(f"{GREEN}[OK]{END} {msg}")


def fail(msg: str) -> None:
    print(f"{RED}[FAIL]{END} {msg}")


def step(msg: str) -> None:
    print(f"\n{BOLD}{BLUE}-> {msg}{END}")


def info(msg: str) -> None:
    print(f"{YELLOW}   {msg}{END}")


async def run_onboarding_e2e() -> bool:
    """Execute the onboarding tool sequence and verify each call.

    Returns True on success, False otherwise.
    """
    club = {
        "club_name": "Pebble Beach Golf Links",
        "club_id": "PB001",
        "contact_email": "admin@pebblebeach.com",
        "contact_name": "John Smith",
        "facility_type": "golf_course",
        "modules": ["member", "sms"],
    }

    registry = BRSToolRegistry()
    executor = MockBRSToolExecutor(registry)
    parser = BRSToolOutputParser(instructor_client=None)  # fallback mode

    failures = 0

    # ---- Step 1: init database ------------------------------------------
    step("Step 1: brs_teesheet_init")
    process = await executor.execute_tool(
        "brs_teesheet_init",
        {"club_name": club["club_name"], "club_id": club["club_id"]},
    )
    result = await parser.parse_output(
        process=process,
        output_schema=TeesheetInitOutput,
        tool_name="brs_teesheet_init",
    )

    if isinstance(result, TeesheetInitOutput) and result.success:
        ok(f"init_database succeeded (stdout len={len(result.stdout)})")
    else:
        fail(f"init_database unexpected result: {result}")
        failures += 1

    # ---- Step 2: create superuser ---------------------------------------
    step("Step 2: brs_create_superuser")
    process = await executor.execute_tool(
        "brs_create_superuser",
        {
            "club_name": club["club_name"],
            "email": club["contact_email"],
            "name": club["contact_name"],
        },
    )
    result = await parser.parse_output(
        process=process,
        output_schema=SuperuserCreateOutput,
        tool_name="brs_create_superuser",
    )

    if isinstance(result, SuperuserCreateOutput) and result.success:
        ok("create_superuser succeeded")
    else:
        fail(f"create_superuser unexpected result: {result}")
        failures += 1

    # ---- Step 3: config validate (post-approval) ------------------------
    # Approval gate would pause here in the real orchestrator. In this
    # smoke test we assume approval has been granted and proceed.
    step("Step 3: brs_config_validate (post-approval)")
    try:
        process = await executor.execute_tool(
            "brs_config_validate",
            {"club_id": club["club_id"]},
        )
        ok(f"config_validate returncode={process.returncode}")
    except Exception as exc:
        fail(f"config_validate raised: {exc}")
        failures += 1

    # ---- Verify call history --------------------------------------------
    step("Verify MockBRSToolExecutor.call_history")
    expected_order = [
        "brs_teesheet_init",
        "brs_create_superuser",
        "brs_config_validate",
    ]
    actual_order = [c["tool_name"] for c in executor.call_history]

    if actual_order == expected_order:
        ok(f"call order matches: {actual_order}")
    else:
        fail(f"call order mismatch.\n  expected: {expected_order}\n  actual:   {actual_order}")
        failures += 1

    # Verify parameters on each call
    init_params = executor.call_history[0]["parameters"]
    if init_params.get("club_id") == club["club_id"]:
        ok("init_database received correct club_id")
    else:
        fail(f"init_database params: {init_params}")
        failures += 1

    su_params = executor.call_history[1]["parameters"]
    if su_params.get("email") == club["contact_email"]:
        ok("create_superuser received correct email")
    else:
        fail(f"create_superuser params: {su_params}")
        failures += 1

    # ---- Summary --------------------------------------------------------
    print()
    info(f"Total tool invocations: {len(executor.call_history)}")
    for i, call in enumerate(executor.call_history, 1):
        info(f"  {i}. {call['tool_name']}  params={list(call['parameters'].keys())}")

    print()
    if failures == 0:
        print(f"{GREEN}{BOLD}SMOKE TEST PASSED{END}")
        return True
    print(f"{RED}{BOLD}SMOKE TEST FAILED ({failures} errors){END}")
    return False


def main() -> int:
    passed = asyncio.run(run_onboarding_e2e())
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
