"""Tests for Skills REST API endpoints."""
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.main import app
from app.db.session import get_db, Base
from app.models.models import User, Tenant, TenantSkill, UserRole, ApprovalStatus
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


class TestSkillsCreate:
    """Test POST /api/skills - Create new skill."""

    def test_create_skill_success(self, client, auth_headers):
        """Successfully create a skill."""
        payload = {
            "skill_name": "test_skill",
            "description": "A test skill",
            "skill_data": {"type": "workflow", "steps": []}
        }

        response = client.post("/api/skills", json=payload, headers=auth_headers)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["skill_name"] == "test_skill"
        assert data["description"] == "A test skill"
        assert data["skill_data"] == {"type": "workflow", "steps": []}
        assert data["version"] == 1
        assert data["is_active"] is False
        assert "id" in data
        assert "created_at" in data

    def test_create_skill_duplicate_name(self, client, auth_headers):
        """Creating skill with duplicate name returns 409."""
        payload = {
            "skill_name": "duplicate_skill",
            "skill_data": {}
        }

        # Create first
        response1 = client.post("/api/skills", json=payload, headers=auth_headers)
        assert response1.status_code == status.HTTP_201_CREATED

        # Try duplicate
        response2 = client.post("/api/skills", json=payload, headers=auth_headers)
        assert response2.status_code == status.HTTP_409_CONFLICT
        assert "already exists" in response2.json()["detail"]

    def test_create_skill_unauthorized(self, client):
        """Creating skill without auth returns 401."""
        payload = {
            "skill_name": "test_skill",
            "skill_data": {}
        }

        response = client.post("/api/skills", json=payload)
        # 401 Unauthorized for missing auth (not 403 Forbidden)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestSkillsList:
    """Test GET /api/skills - List skills."""

    def test_list_skills_empty(self, client, auth_headers):
        """List skills when none exist."""
        response = client.get("/api/skills", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["skills"] == []

    def test_list_skills_multiple(self, client, auth_headers):
        """List multiple skills."""
        # Create skills
        for i in range(3):
            payload = {
                "skill_name": f"skill_{i}",
                "skill_data": {"index": i}
            }
            client.post("/api/skills", json=payload, headers=auth_headers)

        response = client.get("/api/skills", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["skills"]) == 3

    def test_list_skills_active_only(self, client, auth_headers):
        """List only active skills."""
        # Create inactive skill
        payload1 = {"skill_name": "inactive_skill", "skill_data": {}}
        response1 = client.post("/api/skills", json=payload1, headers=auth_headers)
        skill1_id = response1.json()["id"]

        # Create and activate skill
        payload2 = {"skill_name": "active_skill", "skill_data": {}}
        response2 = client.post("/api/skills", json=payload2, headers=auth_headers)
        skill2_id = response2.json()["id"]
        client.post(f"/api/skills/{skill2_id}/activate", headers=auth_headers)

        # List active only
        response = client.get("/api/skills?active_only=true", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["skills"]) == 1
        assert data["skills"][0]["skill_name"] == "active_skill"
        assert data["skills"][0]["is_active"] is True


class TestSkillsGet:
    """Test GET /api/skills/{id} - Get skill by ID."""

    def test_get_skill_success(self, client, auth_headers):
        """Successfully get a skill."""
        # Create skill
        payload = {
            "skill_name": "get_skill",
            "description": "Test description",
            "skill_data": {"key": "value"}
        }
        create_response = client.post("/api/skills", json=payload, headers=auth_headers)
        skill_id = create_response.json()["id"]

        # Get skill
        response = client.get(f"/api/skills/{skill_id}", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == skill_id
        assert data["skill_name"] == "get_skill"
        assert data["description"] == "Test description"
        assert data["skill_data"] == {"key": "value"}

    def test_get_skill_not_found(self, client, auth_headers):
        """Getting non-existent skill returns 404."""
        response = client.get("/api/skills/99999", headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"]


class TestSkillsUpdate:
    """Test PATCH /api/skills/{id} - Update skill."""

    def test_update_skill_description(self, client, auth_headers):
        """Successfully update skill description."""
        # Create skill
        payload = {"skill_name": "update_skill", "skill_data": {"old": "data"}}
        create_response = client.post("/api/skills", json=payload, headers=auth_headers)
        skill_id = create_response.json()["id"]

        # Update description only
        update_payload = {"description": "Updated description"}
        response = client.patch(f"/api/skills/{skill_id}", json=update_payload, headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["description"] == "Updated description"
        assert data["skill_data"] == {"old": "data"}  # Unchanged

    def test_update_skill_data(self, client, auth_headers):
        """Successfully update skill_data."""
        # Create skill
        payload = {"skill_name": "update_skill", "skill_data": {"old": "data"}}
        create_response = client.post("/api/skills", json=payload, headers=auth_headers)
        skill_id = create_response.json()["id"]

        # Update skill_data
        update_payload = {"skill_data": {"new": "data"}}
        response = client.patch(f"/api/skills/{skill_id}", json=update_payload, headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["skill_data"] == {"new": "data"}

    def test_update_skill_not_found(self, client, auth_headers):
        """Updating non-existent skill returns 404."""
        update_payload = {"description": "New description"}
        response = client.patch("/api/skills/99999", json=update_payload, headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestSkillsDelete:
    """Test DELETE /api/skills/{id} - Delete skill."""

    def test_delete_skill_success(self, client, auth_headers):
        """Successfully delete a skill."""
        # Create skill
        payload = {"skill_name": "delete_skill", "skill_data": {}}
        create_response = client.post("/api/skills", json=payload, headers=auth_headers)
        skill_id = create_response.json()["id"]

        # Delete skill
        response = client.delete(f"/api/skills/{skill_id}", headers=auth_headers)

        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify deletion
        get_response = client.get(f"/api/skills/{skill_id}", headers=auth_headers)
        assert get_response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_skill_not_found(self, client, auth_headers):
        """Deleting non-existent skill returns 404."""
        response = client.delete("/api/skills/99999", headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestSkillsActivate:
    """Test POST /api/skills/{id}/activate - Activate skill version."""

    def test_activate_skill_success(self, client, auth_headers):
        """Successfully activate a skill."""
        # Create skill
        payload = {"skill_name": "activate_skill", "skill_data": {}}
        create_response = client.post("/api/skills", json=payload, headers=auth_headers)
        skill_id = create_response.json()["id"]

        # Activate skill
        response = client.post(f"/api/skills/{skill_id}/activate", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["is_active"] is True
        assert data["id"] == skill_id

    def test_activate_skill_not_found(self, client, auth_headers):
        """Activating non-existent skill returns 404."""
        response = client.post("/api/skills/99999/activate", headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestSkillsTenantIsolation:
    """Test tenant isolation for skills."""

    def test_cannot_access_other_tenant_skill(self, client, db_session, test_user):
        """Users cannot access skills from other tenants."""
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

        # Create skill for tenant1
        token1 = create_access_token(data={"sub": str(test_user.id), "tenant_id": test_user.tenant_id})
        headers1 = {"Authorization": f"Bearer {token1}"}
        payload = {"skill_name": "tenant1_skill", "skill_data": {}}
        create_response = client.post("/api/skills", json=payload, headers=headers1)
        skill_id = create_response.json()["id"]

        # Try to access with tenant2 user
        token2 = create_access_token(data={"sub": str(user2.id), "tenant_id": user2.tenant_id})
        headers2 = {"Authorization": f"Bearer {token2}"}
        response = client.get(f"/api/skills/{skill_id}", headers=headers2)

        assert response.status_code == status.HTTP_404_NOT_FOUND
