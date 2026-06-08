#!/usr/bin/env python3
"""
Test script for skill execution via WebSocket.
Run this to test "Reinstate user 98765432" skill execution.
"""
import asyncio
import websockets
import json


async def test_skill_execution():
    uri = "ws://localhost:8000/api/ws/chat"

    print("🔌 Connecting to WebSocket...")
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected to WebSocket")

            # Send test message
            message = {
                "message": "Reinstate user 98765432",
                "session_id": "test-skill-execution-123"
            }

            print(f"📤 Sending: {message['message']}")
            await websocket.send(json.dumps(message))

            # Receive responses
            print("\n📥 Receiving responses:")
            print("-" * 60)

            async for response in websocket:
                data = json.loads(response)

                # Print response
                if data.get("type") == "content":
                    print(f"Content: {data.get('content', '')}")
                elif data.get("type") == "done":
                    print("\n✅ Response complete")
                    break
                else:
                    print(f"Type: {data.get('type')}")

                # Check for skill execution markers
                content = str(data.get("content", ""))
                if "Executed skill" in content:
                    print("\n🎯 SKILL EXECUTED!")
                if "Tools Used:" in content:
                    print("🔧 TOOLS WERE CALLED!")
                if "Could you provide" in content or "clarifying question" in content.lower():
                    print("\n❌ WARNING: LLM is asking questions instead of executing!")

            print("-" * 60)

    except websockets.exceptions.WebSocketException as e:
        print(f"❌ WebSocket error: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")


async def check_backend_logs():
    """Check backend logs for skill execution evidence."""
    print("\n\n📋 Checking backend logs...")
    print("=" * 60)

    try:
        with open("/tmp/backend.log", "r") as f:
            lines = f.readlines()

        # Get last 100 lines and filter for skill-related entries
        recent = lines[-100:]
        skill_lines = [l for l in recent if any(
            keyword in l for keyword in
            ["skill", "Skill", "tool", "Tool", "23 tools", "Calling tool"]
        )]

        print("Recent skill-related log entries:")
        for line in skill_lines[-20:]:
            print(line.rstrip())

    except FileNotFoundError:
        print("⚠️ Backend log not found at /tmp/backend.log")
    except Exception as e:
        print(f"❌ Error reading logs: {e}")

    print("=" * 60)


async def main():
    print("🧪 Testing Skill Execution Implementation")
    print("=" * 60)
    print("Test: Send 'Reinstate user 98765432'")
    print("Expected: Skill executes with tool calls (not questions)")
    print("=" * 60)
    print()

    await test_skill_execution()
    await check_backend_logs()

    print("\n\n📊 Summary:")
    print("1. Check if response shows '✅ Executed skill'")
    print("2. Check if 'Tools Used:' section is present")
    print("3. Check logs show 'Calling tool: run_sql' and 'call_api'")
    print("4. Verify NO clarifying questions were asked")


if __name__ == "__main__":
    asyncio.run(main())
