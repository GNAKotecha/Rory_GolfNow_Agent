"""
Smoke Test: Gateway MCP Server

Runs basic health checks and tool listing for the Gateway MCP server.

Usage:
    cd backend
    python -m gateway_mcp.scripts.smoke_gateway

Exit code 0 = pass, 1 = fail.
"""

import asyncio
import os
import sys
from pathlib import Path

import httpx

# Ensure backend/ is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


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


GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8090")


async def check_health() -> bool:
    """Check /health endpoint."""
    step("Checking /health endpoint")
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.get(f"{GATEWAY_URL}/health")
            
            if response.status_code == 200:
                data = response.json()
                ok(f"Health check passed: status={data.get('status')}, version={data.get('version')}")
                return True
            else:
                fail(f"Health check failed: status_code={response.status_code}")
                return False
        except Exception as e:
            fail(f"Health check error: {e}")
            return False


async def check_readiness() -> bool:
    """Check /ready endpoint."""
    step("Checking /ready endpoint")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f"{GATEWAY_URL}/ready")
            data = response.json()
            
            if response.status_code == 200:
                ok(f"Readiness check passed: status={data.get('status')}, env={data.get('env')}")
                return True
            else:
                # 503 means not ready but endpoint works
                info(f"Not ready (expected in some envs): {data}")
                return True  # Endpoint works, just not ready
        except Exception as e:
            fail(f"Readiness check error: {e}")
            return False


async def check_tools_list() -> bool:
    """Check /tools endpoint."""
    step("Checking /tools endpoint")
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.get(f"{GATEWAY_URL}/tools")
            
            if response.status_code == 200:
                data = response.json()
                tools = data.get("tools", [])
                count = data.get("count", 0)
                
                ok(f"Tools list: {count} tools registered")
                
                # List tool names
                for tool in tools:
                    info(f"  - {tool.get('name')}: {tool.get('description', '')[:50]}...")
                
                # Verify MVP tools present
                mvp_tools = {
                    # BRS Tools (6)
                    "create_club",
                    "get_club_by_name",
                    "verify_club_setup",
                    "get_club_config",
                    "create_admin_user",
                    "call_internal_api",
                    # Jira Tools (3)
                    "create_ticket",
                    "get_ticket_status",
                    "add_comment",
                }
                
                tool_names = {t.get("name") for t in tools}
                missing = mvp_tools - tool_names
                
                if missing:
                    fail(f"Missing MVP tools: {missing}")
                    return False
                
                ok(f"All {len(mvp_tools)} MVP tools present")
                return True
            else:
                fail(f"Tools list failed: status_code={response.status_code}")
                return False
        except Exception as e:
            fail(f"Tools list error: {e}")
            return False


async def check_mcp_tools_list() -> bool:
    """Check MCP tools/list endpoint."""
    step("Checking MCP tools/list endpoint")
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.post(
                f"{GATEWAY_URL}/mcp/tools/list",
                json={},  # Empty body - cursor optional
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Response is direct Pydantic model, not JSON-RPC wrapped
                tools = data.get("tools", [])
                if tools:
                    ok(f"MCP tools/list: {len(tools)} tools")
                    return True
                else:
                    fail("MCP tools/list returned no tools")
                    return False
            else:
                fail(f"MCP tools/list failed: status_code={response.status_code}")
                return False
        except Exception as e:
            fail(f"MCP tools/list error: {e}")
            return False


async def run_smoke_tests() -> bool:
    """Run all smoke tests."""
    print(f"\n{BOLD}Gateway MCP Smoke Tests{END}")
    print(f"Target: {GATEWAY_URL}\n")
    
    results = []
    
    results.append(await check_health())
    results.append(await check_readiness())
    results.append(await check_tools_list())
    results.append(await check_mcp_tools_list())
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print(f"\n{BOLD}Summary: {passed}/{total} checks passed{END}")
    
    return all(results)


def main() -> int:
    """Entry point."""
    try:
        success = asyncio.run(run_smoke_tests())
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\nInterrupted")
        return 1
    except Exception as e:
        print(f"\n{RED}Unexpected error: {e}{END}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
