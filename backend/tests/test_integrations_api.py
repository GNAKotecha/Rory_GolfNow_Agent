"""Tests for MCP Integrations REST API endpoints."""
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.main import app
from app.db.session import get_db, Base
from app.models.models import User, Tenant, TenantMCPIntegration, UserRole, ApprovalStatus
from app.services.auth import get_password_hash, create_access_token


@pytest.fixture
def db_session(tmp_path):
    """Create a test database session."""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)

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
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def db(db_session):
    """Alias for db_session (consistency with other tests)."""
    return db_session


@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create test user for testing."""
    # Ensure default tenant exists
    tenant = db_session.query(Tenant).filter(Tenant.id == 1).first()
    if not tenant:
        tenant = Tenant(id=1, name="Default Organization", slug="default")
        db_session.add(tenant)
        db_session.commit()

    user = User(
        tenant_id=1,
        email="testuser@test.com",
        name="Test User",
        password_hash=get_password_hash("password123"),
        role=UserRole.USER,
        approval_status=ApprovalStatus.APPROVED,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_token(test_user: User) -> str:
    """Create JWT token for test user."""
    return create_access_token(data={
        "sub": str(test_user.id),
        "tenant_id": test_user.tenant_id
    })


@pytest.fixture
def auth_headers(auth_token: str) -> dict:
    """Create authorization headers for test user."""
    return {"Authorization": f"Bearer {auth_token}"}


class TestIntegrationsCreate:
    """Test POST /api/integrations - Create new integration."""

    def test_create_integration_success(self, client, auth_headers, db):
        """Successfully create an MCP integration."""
        payload = {
            "integration_name": "github",
            "auth_type": "oauth",
            "config": {"base_url": "https://api.github.com"}
        }
        response = client.post("/api/integrations", json=payload, headers=auth_headers)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["integration_name"] == "github"
        assert data["auth_type"] == "oauth"
        assert data["config"] == {"base_url": "https://api.github.com"}
        assert data["is_enabled"] is True
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_integration_missing_fields(self, client, auth_headers):
        """Fail to create integration with missing required fields."""
        payload = {"integration_name": "github"}  # Missing auth_type
        response = client.post("/api/integrations", json=payload, headers=auth_headers)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_create_integration_invalid_auth_type(self, client, auth_headers):
        """Fail to create integration with invalid auth_type."""
        payload = {
            "integration_name": "github",
            "auth_type": "invalid_type",
            "config": {}
        }
        response = client.post("/api/integrations", json=payload, headers=auth_headers)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        # Pydantic validator returns detailed error in body
        response_data = response.json()
        assert "detail" in response_data

    def test_create_duplicate_integration_same_tenant(self, client, auth_headers, db, test_user):
        """Fail to create duplicate integration in same tenant."""
        tenant_id = test_user.tenant_id

        # Create first integration
        integration = TenantMCPIntegration(
            tenant_id=tenant_id,
            integration_name="github",
            auth_type="oauth",
            config={}
        )
        db.add(integration)
        db.commit()

        # Attempt duplicate
        payload = {
            "integration_name": "github",
            "auth_type": "oauth",
            "config": {}
        }
        response = client.post("/api/integrations", json=payload, headers=auth_headers)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "already exists" in response.json()["detail"].lower()

    def test_create_integration_unauthenticated(self, client):
        """Fail to create integration without authentication."""
        payload = {
            "integration_name": "github",
            "auth_type": "oauth",
            "config": {}
        }
        response = client.post("/api/integrations", json=payload)

        # 401 Unauthorized for missing auth (not 403 Forbidden)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestIntegrationsList:
    """Test GET /api/integrations - List tenant's integrations."""

    def test_list_integrations_success(self, client, auth_headers, db, test_user):
        """Successfully list all integrations for tenant."""
        tenant_id = test_user.tenant_id

        # Create 2 integrations for test user's tenant
        for name in ["github", "jira"]:
            integration = TenantMCPIntegration(
                tenant_id=tenant_id,
                integration_name=name,
                auth_type="oauth",
                config={}
            )
            db.add(integration)
        db.commit()

        response = client.get("/api/integrations", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 2
        assert {item["integration_name"] for item in data} == {"github", "jira"}

    def test_list_integrations_tenant_isolation(self, client, auth_headers, db, test_user):
        """Only return integrations for current tenant."""
        tenant_id = test_user.tenant_id

        # Create integration for test user's tenant
        integration1 = TenantMCPIntegration(
            tenant_id=tenant_id,
            integration_name="github",
            auth_type="oauth",
            config={}
        )
        db.add(integration1)

        # Create integration for different tenant
        other_tenant = Tenant(name="Other Org", slug="other-org")
        db.add(other_tenant)
        db.flush()

        integration2 = TenantMCPIntegration(
            tenant_id=other_tenant.id,
            integration_name="jira",
            auth_type="oauth",
            config={}
        )
        db.add(integration2)
        db.commit()

        response = client.get("/api/integrations", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1
        assert data[0]["integration_name"] == "github"

    def test_list_integrations_empty(self, client, auth_headers):
        """Return empty list when tenant has no integrations."""
        response = client.get("/api/integrations", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    def test_list_integrations_unauthenticated(self, client):
        """Fail to list integrations without authentication."""
        response = client.get("/api/integrations")

        # 401 Unauthorized for missing auth (not 403 Forbidden)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestIntegrationsGet:
    """Test GET /api/integrations/{integration_id} - Get integration details."""

    def test_get_integration_success(self, client, auth_headers, db, test_user):
        """Successfully retrieve an integration by ID."""
        tenant_id = test_user.tenant_id

        integration = TenantMCPIntegration(
            tenant_id=tenant_id,
            integration_name="github",
            auth_type="oauth",
            config={"base_url": "https://api.github.com"}
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        response = client.get(f"/api/integrations/{integration.id}", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == integration.id
        assert data["integration_name"] == "github"
        assert data["auth_type"] == "oauth"
        assert data["config"] == {"base_url": "https://api.github.com"}

    def test_get_integration_cross_tenant_denied(self, client, auth_headers, db, test_user):
        """Fail to retrieve integration from different tenant."""
        # Create different tenant with integration
        other_tenant = Tenant(name="Other Org", slug="other-org")
        db.add(other_tenant)
        db.flush()

        integration = TenantMCPIntegration(
            tenant_id=other_tenant.id,
            integration_name="github",
            auth_type="oauth",
            config={}
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        response = client.get(f"/api/integrations/{integration.id}", headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_integration_not_found(self, client, auth_headers):
        """Return 404 when integration doesn't exist."""
        response = client.get("/api/integrations/999999", headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_integration_unauthenticated(self, client):
        """Fail to get integration without authentication."""
        response = client.get("/api/integrations/1")

        # 401 Unauthorized for missing auth (not 403 Forbidden)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestIntegrationsUpdate:
    """Test PATCH /api/integrations/{integration_id} - Update integration."""

    def test_update_integration_name(self, client, auth_headers, db, test_user):
        """Successfully update integration name."""
        tenant_id = test_user.tenant_id

        integration = TenantMCPIntegration(
            tenant_id=tenant_id,
            integration_name="github",
            auth_type="oauth",
            config={}
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        payload = {"integration_name": "github-enterprise"}
        response = client.patch(f"/api/integrations/{integration.id}", json=payload, headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["integration_name"] == "github-enterprise"

    def test_update_integration_config(self, client, auth_headers, db, test_user):
        """Successfully update integration config."""
        tenant_id = test_user.tenant_id

        integration = TenantMCPIntegration(
            tenant_id=tenant_id,
            integration_name="github",
            auth_type="oauth",
            config={"timeout": 30}
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        new_config = {"timeout": 60, "base_url": "https://github.enterprise.com"}
        payload = {"config": new_config}
        response = client.patch(f"/api/integrations/{integration.id}", json=payload, headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["config"] == new_config

    def test_update_integration_enabled_status(self, client, auth_headers, db, test_user):
        """Successfully update integration enabled status."""
        tenant_id = test_user.tenant_id

        integration = TenantMCPIntegration(
            tenant_id=tenant_id,
            integration_name="github",
            auth_type="oauth",
            config={},
            is_enabled=True
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        payload = {"is_enabled": False}
        response = client.patch(f"/api/integrations/{integration.id}", json=payload, headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["is_enabled"] is False

    def test_update_integration_cross_tenant_denied(self, client, auth_headers, db, test_user):
        """Fail to update integration from different tenant."""
        other_tenant = Tenant(name="Other Org", slug="other-org")
        db.add(other_tenant)
        db.flush()

        integration = TenantMCPIntegration(
            tenant_id=other_tenant.id,
            integration_name="github",
            auth_type="oauth",
            config={}
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        payload = {"integration_name": "updated"}
        response = client.patch(f"/api/integrations/{integration.id}", json=payload, headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_integration_not_found(self, client, auth_headers):
        """Return 404 when updating non-existent integration."""
        payload = {"integration_name": "updated"}
        response = client.patch("/api/integrations/999999", json=payload, headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestIntegrationsDelete:
    """Test DELETE /api/integrations/{integration_id} - Remove integration."""

    def test_delete_integration_success(self, client, auth_headers, db, test_user):
        """Successfully delete an integration."""
        tenant_id = test_user.tenant_id

        integration = TenantMCPIntegration(
            tenant_id=tenant_id,
            integration_name="github",
            auth_type="oauth",
            config={}
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)
        integration_id = integration.id

        response = client.delete(f"/api/integrations/{integration_id}", headers=auth_headers)

        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify deletion
        deleted = db.query(TenantMCPIntegration).filter_by(id=integration_id).first()
        assert deleted is None

    def test_delete_integration_cross_tenant_denied(self, client, auth_headers, db, test_user):
        """Fail to delete integration from different tenant."""
        other_tenant = Tenant(name="Other Org", slug="other-org")
        db.add(other_tenant)
        db.flush()

        integration = TenantMCPIntegration(
            tenant_id=other_tenant.id,
            integration_name="github",
            auth_type="oauth",
            config={}
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        response = client.delete(f"/api/integrations/{integration.id}", headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_integration_not_found(self, client, auth_headers):
        """Return 404 when deleting non-existent integration."""
        response = client.delete("/api/integrations/999999", headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestIntegrationsEnable:
    """Test POST /api/integrations/{integration_id}/enable - Enable integration."""

    def test_enable_integration_success(self, client, auth_headers, db, test_user):
        """Successfully enable a disabled integration."""
        tenant_id = test_user.tenant_id

        integration = TenantMCPIntegration(
            tenant_id=tenant_id,
            integration_name="github",
            auth_type="oauth",
            config={},
            is_enabled=False
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        response = client.post(f"/api/integrations/{integration.id}/enable", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["is_enabled"] is True

    def test_enable_integration_cross_tenant_denied(self, client, auth_headers, db, test_user):
        """Fail to enable integration from different tenant."""
        other_tenant = Tenant(name="Other Org", slug="other-org")
        db.add(other_tenant)
        db.flush()

        integration = TenantMCPIntegration(
            tenant_id=other_tenant.id,
            integration_name="github",
            auth_type="oauth",
            config={},
            is_enabled=False
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        response = client.post(f"/api/integrations/{integration.id}/enable", headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestIntegrationsDisable:
    """Test POST /api/integrations/{integration_id}/disable - Disable integration."""

    def test_disable_integration_success(self, client, auth_headers, db, test_user):
        """Successfully disable an enabled integration."""
        tenant_id = test_user.tenant_id

        integration = TenantMCPIntegration(
            tenant_id=tenant_id,
            integration_name="github",
            auth_type="oauth",
            config={},
            is_enabled=True
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        response = client.post(f"/api/integrations/{integration.id}/disable", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["is_enabled"] is False

    def test_disable_integration_cross_tenant_denied(self, client, auth_headers, db, test_user):
        """Fail to disable integration from different tenant."""
        other_tenant = Tenant(name="Other Org", slug="other-org")
        db.add(other_tenant)
        db.flush()

        integration = TenantMCPIntegration(
            tenant_id=other_tenant.id,
            integration_name="github",
            auth_type="oauth",
            config={},
            is_enabled=True
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        response = client.post(f"/api/integrations/{integration.id}/disable", headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestIntegrationsHealth:
    """Test POST /api/integrations/{integration_id}/health - Health check."""

    def test_health_check_success(self, client, auth_headers, db, test_user):
        """Successfully perform health check on integration."""
        tenant_id = test_user.tenant_id

        integration = TenantMCPIntegration(
            tenant_id=tenant_id,
            integration_name="github",
            auth_type="oauth",
            config={},
            is_enabled=True
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        response = client.post(f"/api/integrations/{integration.id}/health", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "status" in data
        assert "integration_id" in data
        assert data["integration_id"] == integration.id

    def test_health_check_cross_tenant_denied(self, client, auth_headers, db, test_user):
        """Fail to perform health check on integration from different tenant."""
        other_tenant = Tenant(name="Other Org", slug="other-org")
        db.add(other_tenant)
        db.flush()

        integration = TenantMCPIntegration(
            tenant_id=other_tenant.id,
            integration_name="github",
            auth_type="oauth",
            config={},
            is_enabled=True
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        response = client.post(f"/api/integrations/{integration.id}/health", headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND
