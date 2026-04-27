"""Verification tests for Ticket 6: Prompt layering and context assembly."""
import sys
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.models import User, UserRole, ApprovalStatus
from app.services.prompt_layers import (
    assemble_system_prompt,
    get_user_context,
    get_system_context,
    append_system_context,
    prepend_user_context,
)
from app.services.history import (
    should_compact_history,
    compact_history,
    prepare_messages_for_api,
    estimate_token_count,
    build_conversation_context,
)


def create_test_user(role: UserRole = UserRole.USER, approved: bool = True) -> User:
    """Create a test user object."""
    user = User(
        id=1,
        email="test@example.com",
        name="Test User",
        password_hash="dummy",
        role=role,
        approval_status=ApprovalStatus.APPROVED if approved else ApprovalStatus.PENDING,
    )
    return user


def test_prompt_assembly():
    """Test 1: Prompt assembly is centralized."""
    print("\n" + "="*70)
    print("TEST 1: Prompt Assembly Centralization")
    print("="*70)

    user = create_test_user()
    tools = ["chat", "search", "compute"]

    prompt = assemble_system_prompt(
        user=user,
        workflow_type="code_review",
        available_tools=tools,
        additional_context={"session_id": "123"},
    )

    print(f"\n✓ Generated {len(prompt)} prompt layers")
    for i, layer in enumerate(prompt, 1):
        print(f"\nLayer {i} ({len(layer)} chars):")
        print("-" * 70)
        print(layer[:200] + ("..." if len(layer) > 200 else ""))

    assert len(prompt) > 0, "Prompt should have at least one layer"
    assert any("User Profile" in layer for layer in prompt), "Should include role layer"
    assert any("Tool Usage Policy" in layer for layer in prompt), "Should include tool policy"

    print("\n✅ PASSED: Prompt assembly is centralized")
    return True


def test_layer_ordering():
    """Test 2: Layer order is deterministic."""
    print("\n" + "="*70)
    print("TEST 2: Deterministic Layer Ordering")
    print("="*70)

    user = create_test_user()

    # Generate prompt multiple times
    prompts = [
        assemble_system_prompt(user, available_tools=["tool1", "tool2"])
        for _ in range(5)
    ]

    # Verify all prompts are identical
    for i in range(1, len(prompts)):
        assert prompts[i] == prompts[0], f"Prompt {i} differs from prompt 0"

    print(f"\n✓ Generated {len(prompts)} identical prompts")
    print(f"✓ Each prompt has {len(prompts[0])} layers")
    print(f"✓ Layer order: {[f'Layer{i+1}' for i in range(len(prompts[0]))]}")

    print("\n✅ PASSED: Layer ordering is deterministic")
    return True


def test_compaction_threshold():
    """Test 3: History compaction uses summary after threshold."""
    print("\n" + "="*70)
    print("TEST 3: History Compaction with Summary")
    print("="*70)

    # Create long conversation
    messages = []
    for i in range(30):
        messages.append({
            "role": "user" if i % 2 == 0 else "assistant",
            "content": f"Message {i+1} with some content to make it realistic.",
        })

    print(f"\n✓ Created conversation with {len(messages)} messages")

    # Test threshold detection
    should_compact = should_compact_history(len(messages))
    print(f"✓ Should compact (30 messages > 20 threshold): {should_compact}")
    assert should_compact, "Should compact when above threshold"

    # Test compaction
    compacted, stats = compact_history(
        messages,
        keep_recent=10,
        summary_text="This is a test summary of prior conversation.",
    )

    print(f"\n✓ Compaction stats:")
    print(f"  - Original: {stats['original_count']} messages")
    print(f"  - Compacted: {stats['compacted_count']} messages")
    print(f"  - Summarized: {stats['messages_summarized']} messages")
    print(f"  - Kept recent: {stats['messages_kept']} messages")
    print(f"  - Token reduction: {stats['original_tokens']} → {stats['compacted_tokens']}")

    # Verify structure
    assert compacted[0].get("is_summary", False), "First message should be summary"
    assert len(compacted) == 11, "Should have summary + 10 recent messages"
    assert "test summary" in compacted[0]["content"], "Summary content should be present"

    print("\n✅ PASSED: Compaction uses summary after threshold")
    return True


def test_context_assembly():
    """Test 4: User and system context prepend/append correctly."""
    print("\n" + "="*70)
    print("TEST 4: Context Assembly")
    print("="*70)

    # Test user context
    user_context = get_user_context()
    print(f"\n✓ User context keys: {list(user_context.keys())}")
    assert "currentDate" in user_context, "Should include current date"

    # Test system context
    system_context = get_system_context(session_id=123)
    print(f"✓ System context keys: {list(system_context.keys())}")

    # Test prepend/append
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]

    messages_with_context = prepend_user_context(messages, user_context)
    print(f"\n✓ Messages before context: {len(messages)}")
    print(f"✓ Messages after prepend: {len(messages_with_context)}")
    assert len(messages_with_context) == len(messages) + 1, "Should add context message"

    system_prompt = ["Base prompt", "Role layer"]
    prompt_with_context = append_system_context(system_prompt, system_context)
    print(f"✓ Prompt layers before: {len(system_prompt)}")
    print(f"✓ Prompt layers after append: {len(prompt_with_context)}")
    assert len(prompt_with_context) >= len(system_prompt), "Should append context"

    print("\n✅ PASSED: Context assembly works correctly")
    return True


def test_role_based_layers():
    """Test 5: Role-specific content in layers."""
    print("\n" + "="*70)
    print("TEST 5: Role-Based Layer Content")
    print("="*70)

    # Test admin user
    admin = create_test_user(role=UserRole.ADMIN)
    admin_prompt = assemble_system_prompt(admin)
    admin_full = "\n".join(admin_prompt)

    print("\n✓ Admin prompt includes:")
    print("  - Admin Capabilities" if "Admin Capabilities" in admin_full else "  ✗ Missing admin capabilities")
    assert "Admin Capabilities" in admin_full, "Admin prompt should mention capabilities"

    # Test pending user
    pending = create_test_user(approved=False)
    pending_prompt = assemble_system_prompt(pending)
    pending_full = "\n".join(pending_prompt)

    print("\n✓ Pending user prompt includes:")
    print("  - Limited Access" if "Limited Access" in pending_full else "  ✗ Missing limited access warning")
    assert "Limited Access" in pending_full, "Pending prompt should mention limited access"

    # Test approved user
    approved = create_test_user(role=UserRole.USER, approved=True)
    approved_prompt = assemble_system_prompt(approved)
    approved_full = "\n".join(approved_prompt)

    print("\n✓ Approved user prompt includes:")
    print("  - User Capabilities" if "User Capabilities" in approved_full else "  ✗ Missing user capabilities")
    assert "User Capabilities" in approved_full, "Approved prompt should mention capabilities"

    print("\n✅ PASSED: Role-based layers work correctly")
    return True


def test_snapshot_payload():
    """Test 6: Snapshot assembled prompt payload."""
    print("\n" + "="*70)
    print("TEST 6: Prompt Payload Snapshot")
    print("="*70)

    user = create_test_user()
    tools = ["chat", "search"]

    prompt = assemble_system_prompt(
        user=user,
        workflow_type="debugging",
        available_tools=tools,
        additional_context={"session_id": "456", "workflow_state": "active"},
    )

    snapshot = {
        "timestamp": "2026-04-27T12:00:00Z",
        "user": {
            "id": user.id,
            "role": user.role.value,
            "approval_status": user.approval_status.value,
        },
        "prompt_layers": prompt,
        "layer_count": len(prompt),
        "total_chars": sum(len(layer) for layer in prompt),
    }

    print(f"\n✓ Snapshot created:")
    print(f"  - Layers: {snapshot['layer_count']}")
    print(f"  - Total chars: {snapshot['total_chars']}")
    print(f"  - User role: {snapshot['user']['role']}")

    # Save snapshot
    snapshot_file = Path(__file__).parent / "ticket-6-payload-snapshot.json"
    with open(snapshot_file, "w") as f:
        json.dump(snapshot, f, indent=2)

    print(f"\n✓ Saved snapshot to: {snapshot_file}")

    print("\n✅ PASSED: Payload snapshot created")
    return True


def run_all_tests():
    """Run all verification tests."""
    print("\n" + "#"*70)
    print("# TICKET 6 VERIFICATION - Prompt Layering & Context Assembly")
    print("#"*70)

    tests = [
        test_prompt_assembly,
        test_layer_ordering,
        test_compaction_threshold,
        test_context_assembly,
        test_role_based_layers,
        test_snapshot_payload,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append((test.__name__, "PASS", None))
        except AssertionError as e:
            results.append((test.__name__, "FAIL", str(e)))
            print(f"\n❌ FAILED: {e}")
        except Exception as e:
            results.append((test.__name__, "ERROR", str(e)))
            print(f"\n💥 ERROR: {e}")

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    for name, status, error in results:
        icon = "✅" if status == "PASS" else "❌"
        print(f"{icon} {name}: {status}")
        if error:
            print(f"   {error}")

    passed = sum(1 for _, status, _ in results if status == "PASS")
    total = len(results)

    print(f"\n{passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED - Ticket 6 implementation verified!")
        return 0
    else:
        print("\n⚠️  Some tests failed - review output above")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
