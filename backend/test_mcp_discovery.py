#!/usr/bin/env python3
"""Test script to verify MCP gateway tool discovery."""
import asyncio
import logging
import sys
from app.config.mcp_config import Environment
from app.services.mcp_registry import MCPToolRegistry

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_discovery():
    """Test MCP tool discovery from gateway."""
    print("=" * 60)
    print("Testing MCP Gateway Tool Discovery")
    print("=" * 60)

    # Create registry
    registry = MCPToolRegistry(Environment.DEVELOPMENT)
    await registry.initialize()

    print(f"\n✅ Registry initialized with {len(registry.clients)} clients")
    for name in registry.clients.keys():
        print(f"   - {name}")

    # Create catalog
    print("\n🔍 Creating run catalog...")
    catalog = await registry.create_run_catalog()

    print(f"\n📊 Catalog Summary:")
    print(f"   Total tools: {len(catalog.tools)}")
    print(f"   Total servers: {catalog.total_servers}")
    print(f"   Failed servers: {catalog.failed_servers}")
    print(f"   Server health: {catalog.server_health}")

    if catalog.tools:
        print(f"\n🔧 Tool Names:")
        for tool in catalog.tools:
            server = catalog.tool_to_server.get(tool.name, "unknown")
            print(f"   - {tool.name} (from {server})")
    else:
        print("\n❌ NO TOOLS FOUND!")
        print("\nChecking individual clients:")
        for server_name, client in registry.clients.items():
            print(f"\n   Server: {server_name}")
            print(f"   URL: {client.config.url}")
            try:
                tools = await client.list_tools(force_refresh=True)
                print(f"   Tools: {len(tools)}")
                if tools:
                    for t in tools[:5]:
                        print(f"      - {t.name}")
            except Exception as e:
                print(f"   ERROR: {e}")

    await registry.close()
    print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(test_discovery())
