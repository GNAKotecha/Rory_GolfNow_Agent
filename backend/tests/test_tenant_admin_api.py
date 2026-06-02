"""Tests for tenant management admin APIs."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import create_engine

from app.main import app
from app.db.session import Base, get_db
from app.models.models import User, Tenant, UserRole, ApprovalStatus
from app.services.auth import create_access_token, get_password_hash


@pytest.fixture
def db_session(tmp_path):
    """Create a test database session."""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)

    from sqlalchemy.orm import sessionmaker
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session):
    """Create test client with test database."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(db_session: Session) -> User:
    """Create admin user for testing."""
    # Ensure default tenant exists
    tenant = db.query(Tenant).filter(Tenant.id == 1).first()
    if not tenant:
        tenant = Tenant(id=1, name="Default Organization", slug="default")
        db.add(tenant)
        db.commit()

    user = User(
        tenant_id=1,
        email="admin@test.com",
        name="Admin User",
        password_hash=get_password_hash("password123"),
        role=UserRole.ADMIN,
        approval_status=ApprovalStatus.APPROVED,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def regular_user(db_session: Session) -> User:
    """Create regular user for testing."""
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
    db.refresh(user)
    return user


@pytest.fixture
def admin_token(admin_user: User) -> str:
    """Create JWT token for admin user."""
    return create_access_token(user_id=admin_user.id, tenant_id=admin_user.tenant_id)


@pytest.fixture
def user_token(regular_user: User) -> str:
    """Create JWT token for regular user."""
    return create_access_token(user_id=regular_user.id, tenant_id=regular_user.tenant_id)


class TestCreateTenant:
    """Tests for POST /api/admin/tenants."""

    def test_create_tenant_success(self, client, admin_token):
        """Admin can create tenant with valid data."""
        response = client.post(
            "/api/admin/tenants",
            json={"name": "New Organization", "slug": "new-org"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Organization"
        assert data["slug"] == "new-org"
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_tenant_invalid_slug(self, client, admin_token):
        """Reject slug with invalid characters."""
        response = client.post(
            "/api/admin/tenants",
            json={"name": "Test Org", "slug": "Test Org"},  # spaces not allowed
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 422
        assert "lowercase alphanumeric with hyphens" in response.text.lower()

    def test_create_tenant_duplicate_name(self, client, admin_token, db_session):
        """Reject duplicate tenant name."""
        # Create first tenant
        tenant = Tenant(name="Existing Org", slug="existing-org")
        db.add(tenant)
        db.commit()

        # Try to create with same name
        response = client.post(
            "/api/admin/tenants",
            json={"name": "Existing Org", "slug": "different-slug"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    def test_create_tenant_duplicate_slug(self, client, admin_token, db_session):
        """Reject duplicate tenant slug."""
        # Create first tenant
        tenant = Tenant(name="First Org", slug="shared-slug")
        db.add(tenant)
        db.commit()

        # Try to create with same slug
        response = client.post(
            "/api/admin/tenants",
            json={"name": "Second Org", "slug": "shared-slug"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    def test_create_tenant_requires_admin(self, client, user_token):
        """Regular user cannot create tenant."""
        response = client.post(
            "/api/admin/tenants",
            json={"name": "Test Org", "slug": "test-org"},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403
        assert "Admin" in response.json()["detail"]

    def test_create_tenant_requires_auth(self, client):
        """Unauthenticated request is rejected."""
        response = client.post(
            "/api/admin/tenants",
            json={"name": "Test Org", "slug": "test-org"},
        )
        assert response.status_code == 403


class TestListTenants:
    """Tests for GET /api/admin/tenants."""

    def test_list_tenants_success(self, client, admin_token, db_session):
        """Admin can list all tenants."""
        # Create test tenants
        db.add(Tenant(name="Tenant A", slug="tenant-a"))
        db.add(Tenant(name="Tenant B", slug="tenant-b"))
        db.commit()

        response = client.get(
            "/api/admin/tenants",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2
        tenant_names = [t["name"] for t in data]
        assert "Tenant A" in tenant_names
        assert "Tenant B" in tenant_names

    def test_list_tenants_requires_admin(self, client, user_token):
        """Regular user cannot list tenants."""
        response = client.get(
            "/api/admin/tenants",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403

    def test_list_tenants_requires_auth(self, client):
        """Unauthenticated request is rejected."""
        response = client.get("/api/admin/tenants")
        assert response.status_code == 403


class TestGetTenant:
    """Tests for GET /api/admin/tenants/{tenant_id}."""

    def test_get_tenant_success(self, client, admin_token, db_session):
        """Admin can get tenant by ID."""
        tenant = Tenant(name="Test Org", slug="test-org")
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        response = client.get(
            f"/api/admin/tenants/{tenant.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == tenant.id
        assert data["name"] == "Test Org"
        assert data["slug"] == "test-org"

    def test_get_tenant_not_found(self, client, admin_token):
        """Return 404 for non-existent tenant."""
        response = client.get(
            "/api/admin/tenants/99999",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404

    def test_get_tenant_requires_admin(self, client, user_token, db_session):
        """Regular user cannot get tenant."""
        tenant = Tenant(name="Test Org", slug="test-org")
        db.add(tenant)
        db.commit()

        response = client.get(
            f"/api/admin/tenants/{tenant.id}",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403


class TestUpdateTenant:
    """Tests for PATCH /api/admin/tenants/{tenant_id}."""

    def test_update_tenant_name(self, client, admin_token, db_session):
        """Admin can update tenant name."""
        tenant = Tenant(name="Old Name", slug="test-org")
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        response = client.patch(
            f"/api/admin/tenants/{tenant.id}",
            json={"name": "New Name"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name"
        assert data["slug"] == "test-org"  # unchanged

    def test_update_tenant_slug(self, client, admin_token, db_session):
        """Admin can update tenant slug."""
        tenant = Tenant(name="Test Org", slug="old-slug")
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        response = client.patch(
            f"/api/admin/tenants/{tenant.id}",
            json={"slug": "new-slug"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["slug"] == "new-slug"
        assert data["name"] == "Test Org"  # unchanged

    def test_update_tenant_invalid_slug(self, client, admin_token, db_session):
        """Reject invalid slug format."""
        tenant = Tenant(name="Test Org", slug="test-org")
        db.add(tenant)
        db.commit()

        response = client.patch(
            f"/api/admin/tenants/{tenant.id}",
            json={"slug": "Invalid Slug!"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 422

    def test_update_tenant_duplicate_name(self, client, admin_token, db_session):
        """Reject update to duplicate name."""
        db.add(Tenant(name="Existing Org", slug="existing"))
        tenant = Tenant(name="Test Org", slug="test")
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        response = client.patch(
            f"/api/admin/tenants/{tenant.id}",
            json={"name": "Existing Org"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 409

    def test_update_tenant_duplicate_slug(self, client, admin_token, db_session):
        """Reject update to duplicate slug."""
        db.add(Tenant(name="Org A", slug="existing-slug"))
        tenant = Tenant(name="Org B", slug="test-slug")
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        response = client.patch(
            f"/api/admin/tenants/{tenant.id}",
            json={"slug": "existing-slug"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 409

    def test_update_tenant_not_found(self, client, admin_token):
        """Return 404 for non-existent tenant."""
        response = client.patch(
            "/api/admin/tenants/99999",
            json={"name": "New Name"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404

    def test_update_tenant_requires_admin(self, client, user_token, db_session):
        """Regular user cannot update tenant."""
        tenant = Tenant(name="Test Org", slug="test-org")
        db.add(tenant)
        db.commit()

        response = client.patch(
            f"/api/admin/tenants/{tenant.id}",
            json={"name": "New Name"},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403
