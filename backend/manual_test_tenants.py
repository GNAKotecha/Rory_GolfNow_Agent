#!/usr/bin/env python3
"""Manual test script for tenant admin APIs."""
import sys
import requests
from app.services.auth import create_access_token
from app.db.session import SessionLocal
from app.models.models import User, Tenant, UserRole, ApprovalStatus
from app.services.auth import get_password_hash

BASE_URL = "http://localhost:8000"

def setup_test_users():
    """Create test admin and regular users."""
    db = SessionLocal()
    try:
        # Ensure default tenant exists
        tenant = db.query(Tenant).filter(Tenant.id == 1).first()
        if not tenant:
            tenant = Tenant(id=1, name="Default Organization", slug="default")
            db.add(tenant)
            db.commit()
            print("✓ Created default tenant")

        # Create admin user
        admin = db.query(User).filter(User.email == "admin@test.com").first()
        if not admin:
            admin = User(
                tenant_id=1,
                email="admin@test.com",
                name="Admin User",
                password_hash=get_password_hash("password123"),
                role=UserRole.ADMIN,
                approval_status=ApprovalStatus.APPROVED,
            )
            db.add(admin)
            db.commit()
            print("✓ Created admin user")

        # Create regular user
        user = db.query(User).filter(User.email == "user@test.com").first()
        if not user:
            user = User(
                tenant_id=1,
                email="user@test.com",
                name="Regular User",
                password_hash=get_password_hash("password123"),
                role=UserRole.USER,
                approval_status=ApprovalStatus.APPROVED,
            )
            db.add(user)
            db.commit()
            print("✓ Created regular user")

        # Generate tokens
        db.refresh(admin)
        db.refresh(user)
        admin_token = create_access_token(user_id=admin.id, tenant_id=admin.tenant_id)
        user_token = create_access_token(user_id=user.id, tenant_id=user.tenant_id)

        return admin_token, user_token
    finally:
        db.close()


def test_create_tenant(admin_token):
    """Test POST /api/admin/tenants."""
    print("\n=== Test: Create Tenant ===")

    # Success case
    response = requests.post(
        f"{BASE_URL}/api/admin/tenants",
        json={"name": "Test Organization", "slug": "test-org"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    print(f"Create tenant (admin): {response.status_code}")
    if response.status_code == 201:
        print(f"✓ Created tenant: {response.json()['name']}")
    else:
        print(f"✗ Failed: {response.text}")

    # Invalid slug
    response = requests.post(
        f"{BASE_URL}/api/admin/tenants",
        json={"name": "Invalid", "slug": "Invalid Slug!"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    print(f"Create tenant (invalid slug): {response.status_code}")
    if response.status_code == 422:
        print("✓ Rejected invalid slug")

    # Duplicate
    response = requests.post(
        f"{BASE_URL}/api/admin/tenants",
        json={"name": "Test Organization", "slug": "another-slug"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    print(f"Create tenant (duplicate name): {response.status_code}")
    if response.status_code == 409:
        print("✓ Rejected duplicate")


def test_list_tenants(admin_token, user_token):
    """Test GET /api/admin/tenants."""
    print("\n=== Test: List Tenants ===")

    # Admin can list
    response = requests.get(
        f"{BASE_URL}/api/admin/tenants",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    print(f"List tenants (admin): {response.status_code}")
    if response.status_code == 200:
        tenants = response.json()
        print(f"✓ Found {len(tenants)} tenants")

    # Regular user cannot
    response = requests.get(
        f"{BASE_URL}/api/admin/tenants",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    print(f"List tenants (user): {response.status_code}")
    if response.status_code == 403:
        print("✓ Regular user blocked")


def test_get_tenant(admin_token):
    """Test GET /api/admin/tenants/{tenant_id}."""
    print("\n=== Test: Get Tenant ===")

    # Get existing tenant
    response = requests.get(
        f"{BASE_URL}/api/admin/tenants/1",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    print(f"Get tenant (id=1): {response.status_code}")
    if response.status_code == 200:
        tenant = response.json()
        print(f"✓ Got tenant: {tenant['name']}")

    # Non-existent tenant
    response = requests.get(
        f"{BASE_URL}/api/admin/tenants/99999",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    print(f"Get tenant (id=99999): {response.status_code}")
    if response.status_code == 404:
        print("✓ 404 for non-existent tenant")


def test_update_tenant(admin_token):
    """Test PATCH /api/admin/tenants/{tenant_id}."""
    print("\n=== Test: Update Tenant ===")

    # Create tenant to update
    response = requests.post(
        f"{BASE_URL}/api/admin/tenants",
        json={"name": "Update Test Org", "slug": "update-test"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    if response.status_code != 201:
        print("✗ Failed to create test tenant")
        return

    tenant_id = response.json()['id']

    # Update name
    response = requests.patch(
        f"{BASE_URL}/api/admin/tenants/{tenant_id}",
        json={"name": "Updated Name"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    print(f"Update tenant name: {response.status_code}")
    if response.status_code == 200:
        print(f"✓ Updated name to: {response.json()['name']}")

    # Update slug
    response = requests.patch(
        f"{BASE_URL}/api/admin/tenants/{tenant_id}",
        json={"slug": "new-slug"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    print(f"Update tenant slug: {response.status_code}")
    if response.status_code == 200:
        print(f"✓ Updated slug to: {response.json()['slug']}")

    # Invalid slug
    response = requests.patch(
        f"{BASE_URL}/api/admin/tenants/{tenant_id}",
        json={"slug": "Invalid Slug!"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    print(f"Update tenant (invalid slug): {response.status_code}")
    if response.status_code == 422:
        print("✓ Rejected invalid slug")


def main():
    """Run all tests."""
    print("=== Tenant Admin API Manual Tests ===")
    print("Make sure the backend is running on http://localhost:8000")
    print()

    try:
        admin_token, user_token = setup_test_users()
        print(f"\nAdmin token: {admin_token[:50]}...")
        print(f"User token: {user_token[:50]}...")

        test_create_tenant(admin_token)
        test_list_tenants(admin_token, user_token)
        test_get_tenant(admin_token)
        test_update_tenant(admin_token)

        print("\n=== Tests Complete ===")
    except requests.exceptions.ConnectionError:
        print("✗ ERROR: Cannot connect to backend. Is it running?")
        sys.exit(1)
    except Exception as e:
        print(f"✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
