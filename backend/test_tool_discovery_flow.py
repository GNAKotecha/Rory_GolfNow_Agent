#!/usr/bin/env python3
"""Test tool discovery flow to verify cache population."""
import asyncio
import logging
from app.services.mcp_registry import MCPToolRegistry
from app.config.mcp_config import Environment

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_discovery_flow():
    """Test the complete tool discovery flow."""
    print("\n=== Testing Tool Discovery Flow ===\n")

    # Create registry
    registry = MCPToolRegistry(environment=Environment.DEVELOPMENT)

    # Initialize (creates MCPClient instances)
    print("1. Initializing registry...")
    await registry.initialize()
    print(f"   Initialized {len(registry.clients)} clients")

    # Check initial cache state
    print("\n2. Initial cache state:")
    for server_name, client in registry.clients.items():
        cache_size = len(client._tools_cache) if client._tools_cache else 0
        print(f"   {server_name}: cache_size={cache_size}, has_cache={client._tools_cache is not None}")

    # Create run catalog (should populate cache)
    print("\n3. Creating run catalog...")
    catalog = await registry.create_run_catalog()
    print(f"   Catalog created with {len(catalog.tools)} tools")
    print(f"   Tool names: {[t.name for t in catalog.tools[:5]]}")

    # Check cache after catalog creation
    print("\n4. Cache state after catalog creation:")
    for server_name, client in registry.clients.items():
        cache_size = len(client._tools_cache) if client._tools_cache else 0
        tool_names = [t.name for t in client._tools_cache[:3]] if client._tools_cache else []
        print(f"   {server_name}: cache_size={cache_size}, has_cache={client._tools_cache is not None}")
        if tool_names:
            print(f"      First 3 tools: {tool_names}")

    # Get available tools for admin role
    print("\n5. Getting available tools for admin role...")
    available_tools = registry.get_available_tools("admin")
    print(f"   Available tools count: {len(available_tools)}")
    print(f"   First 5 tools: {available_tools[:5]}")

    # Close registry
    await registry.close()

    print("\n=== Test Complete ===\n")

if __name__ == "__main__":
    asyncio.run(test_discovery_flow())
