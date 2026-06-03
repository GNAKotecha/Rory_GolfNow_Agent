"""Tests for Workflows REST API endpoints."""
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.main import app
from app.db.session import get_db, Base
from app.models.models import User, Tenant, TenantWorkflow, UserRole, ApprovalStatus
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
def tenant(db_session: Session) -> Tenant:
    """Create test tenant."""
    tenant = Tenant(id=1, name="Test Tenant", slug="test-tenant")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


@pytest.fixture
def test_user(db_session: Session, tenant: Tenant) -> User:
    """Create test user."""
    user = User(
        tenant_id=tenant.id,
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
    """Create authorization headers."""
    return {"Authorization": f"Bearer {auth_token}"}


class TestWorkflowsCreate:
    """Test POST /api/workflows - Create new workflow."""

    def test_create_workflow_success(self, client, auth_headers):
        """Successfully create a workflow."""
        payload = {
            "workflow_name": "test_workflow",
            "description": "A test workflow",
            "workflow_definition": {"steps": [{"action": "approve"}]}
        }

        response = client.post("/api/workflows", json=payload, headers=auth_headers)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["workflow_name"] == "test_workflow"
        assert data["description"] == "A test workflow"
        assert data["workflow_definition"] == {"steps": [{"action": "approve"}]}
        assert data["version"] == 1
        assert data["is_active"] is False
        assert data["active_version"] is None
        assert "id" in data
        assert "created_at" in data

    def test_create_workflow_duplicate_name(self, client, auth_headers):
        """Creating workflow with duplicate name returns 409."""
        payload = {
            "workflow_name": "duplicate_workflow",
            "workflow_definition": {}
        }

        # Create first
        response1 = client.post("/api/workflows", json=payload, headers=auth_headers)
        assert response1.status_code == status.HTTP_201_CREATED

        # Try duplicate
        response2 = client.post("/api/workflows", json=payload, headers=auth_headers)
        assert response2.status_code == status.HTTP_409_CONFLICT
        assert "already exists" in response2.json()["detail"]

    def test_create_workflow_unauthorized(self, client):
        """Creating workflow without auth returns 401."""
        payload = {
            "workflow_name": "test_workflow",
            "workflow_definition": {}
        }

        response = client.post("/api/workflows", json=payload)
        # 401 Unauthorized for missing auth (not 403 Forbidden)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestWorkflowsList:
    """Test GET /api/workflows - List workflows."""

    def test_list_workflows_empty(self, client, auth_headers):
        """List workflows when none exist."""
        response = client.get("/api/workflows", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["workflows"] == []

    def test_list_workflows_multiple(self, client, auth_headers):
        """List multiple workflows."""
        # Create workflows
        for i in range(3):
            payload = {
                "workflow_name": f"workflow_{i}",
                "workflow_definition": {"index": i}
            }
            client.post("/api/workflows", json=payload, headers=auth_headers)

        response = client.get("/api/workflows", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["workflows"]) == 3

    def test_list_workflows_active_only(self, client, auth_headers):
        """List only active workflows."""
        # Create inactive workflow
        payload1 = {"workflow_name": "inactive_workflow", "workflow_definition": {}}
        response1 = client.post("/api/workflows", json=payload1, headers=auth_headers)
        workflow1_id = response1.json()["id"]

        # Create and activate workflow
        payload2 = {"workflow_name": "active_workflow", "workflow_definition": {}}
        response2 = client.post("/api/workflows", json=payload2, headers=auth_headers)
        workflow2_id = response2.json()["id"]
        client.post(f"/api/workflows/{workflow2_id}/activate", headers=auth_headers)

        # List active only
        response = client.get("/api/workflows?active_only=true", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["workflows"]) == 1
        assert data["workflows"][0]["workflow_name"] == "active_workflow"
        assert data["workflows"][0]["is_active"] is True


class TestWorkflowsGet:
    """Test GET /api/workflows/{id} - Get workflow by ID."""

    def test_get_workflow_success(self, client, auth_headers):
        """Successfully get a workflow."""
        # Create workflow
        payload = {
            "workflow_name": "get_workflow",
            "description": "Test description",
            "workflow_definition": {"key": "value"}
        }
        create_response = client.post("/api/workflows", json=payload, headers=auth_headers)
        workflow_id = create_response.json()["id"]

        # Get workflow
        response = client.get(f"/api/workflows/{workflow_id}", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == workflow_id
        assert data["workflow_name"] == "get_workflow"
        assert data["description"] == "Test description"
        assert data["workflow_definition"] == {"key": "value"}

    def test_get_workflow_not_found(self, client, auth_headers):
        """Getting non-existent workflow returns 404."""
        response = client.get("/api/workflows/99999", headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"]


class TestWorkflowsUpdate:
    """Test PATCH /api/workflows/{id} - Update workflow."""

    def test_update_workflow_description(self, client, auth_headers):
        """Successfully update workflow description."""
        # Create workflow
        payload = {"workflow_name": "update_workflow", "workflow_definition": {"old": "data"}}
        create_response = client.post("/api/workflows", json=payload, headers=auth_headers)
        workflow_id = create_response.json()["id"]

        # Update description only
        update_payload = {"description": "Updated description"}
        response = client.patch(f"/api/workflows/{workflow_id}", json=update_payload, headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["description"] == "Updated description"
        assert data["workflow_definition"] == {"old": "data"}  # Unchanged

    def test_update_workflow_definition(self, client, auth_headers):
        """Successfully update workflow_definition."""
        # Create workflow
        payload = {"workflow_name": "update_workflow", "workflow_definition": {"old": "data"}}
        create_response = client.post("/api/workflows", json=payload, headers=auth_headers)
        workflow_id = create_response.json()["id"]

        # Update workflow_definition
        update_payload = {"workflow_definition": {"new": "data"}}
        response = client.patch(f"/api/workflows/{workflow_id}", json=update_payload, headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["workflow_definition"] == {"new": "data"}

    def test_update_workflow_not_found(self, client, auth_headers):
        """Updating non-existent workflow returns 404."""
        update_payload = {"description": "New description"}
        response = client.patch("/api/workflows/99999", json=update_payload, headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestWorkflowsDelete:
    """Test DELETE /api/workflows/{id} - Delete workflow."""

    def test_delete_workflow_success(self, client, auth_headers):
        """Successfully delete a workflow."""
        # Create workflow
        payload = {"workflow_name": "delete_workflow", "workflow_definition": {}}
        create_response = client.post("/api/workflows", json=payload, headers=auth_headers)
        workflow_id = create_response.json()["id"]

        # Delete workflow
        response = client.delete(f"/api/workflows/{workflow_id}", headers=auth_headers)

        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify deletion
        get_response = client.get(f"/api/workflows/{workflow_id}", headers=auth_headers)
        assert get_response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_workflow_not_found(self, client, auth_headers):
        """Deleting non-existent workflow returns 404."""
        response = client.delete("/api/workflows/99999", headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestWorkflowsActivate:
    """Test POST /api/workflows/{id}/activate - Activate workflow version."""

    def test_activate_workflow_success(self, client, auth_headers):
        """Successfully activate a workflow."""
        # Create workflow
        payload = {"workflow_name": "activate_workflow", "workflow_definition": {}}
        create_response = client.post("/api/workflows", json=payload, headers=auth_headers)
        workflow_id = create_response.json()["id"]

        # Activate workflow
        response = client.post(f"/api/workflows/{workflow_id}/activate", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["is_active"] is True
        assert data["active_version"] == workflow_id
        assert data["id"] == workflow_id

    def test_activate_workflow_not_found(self, client, auth_headers):
        """Activating non-existent workflow returns 404."""
        response = client.post("/api/workflows/99999/activate", headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestWorkflowsTenantIsolation:
    """Test tenant isolation for workflows."""

    def test_cannot_access_other_tenant_workflow(self, client, db_session, test_user):
        """Users cannot access workflows from other tenants."""
        # Create second tenant and user
        tenant2 = Tenant(id=2, name="Other Tenant", slug="other-tenant")
        db_session.add(tenant2)
        db_session.commit()

        user2 = User(
            tenant_id=tenant2.id,
            email="user2@test.com",
            name="User 2",
            password_hash=get_password_hash("password123"),
            role=UserRole.USER,
            approval_status=ApprovalStatus.APPROVED,
        )
        db_session.add(user2)
        db_session.commit()

        # Create workflow for tenant1
        token1 = create_access_token(data={"sub": str(test_user.id), "tenant_id": test_user.tenant_id})
        headers1 = {"Authorization": f"Bearer {token1}"}
        payload = {"workflow_name": "tenant1_workflow", "workflow_definition": {}}
        create_response = client.post("/api/workflows", json=payload, headers=headers1)
        workflow_id = create_response.json()["id"]

        # Try to access with tenant2 user
        token2 = create_access_token(data={"sub": str(user2.id), "tenant_id": user2.tenant_id})
        headers2 = {"Authorization": f"Bearer {token2}"}
        response = client.get(f"/api/workflows/{workflow_id}", headers=headers2)

        assert response.status_code == status.HTTP_404_NOT_FOUND
