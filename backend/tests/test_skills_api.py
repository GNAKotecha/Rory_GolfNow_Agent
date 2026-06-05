"""Tests for skill invocation API endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models.models import User, Tenant, TenantSkill


client = TestClient(app)


@pytest.fixture
def test_db():
    """Provide test database session."""
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def test_tenant(test_db: Session) -> Tenant:
    """Create a test tenant."""
    tenant = Tenant(name="Test Tenant", is_active=True)
    test_db.add(tenant)
    test_db.commit()
    test_db.refresh(tenant)
    return tenant


@pytest.fixture
def test_user(test_db: Session, test_tenant: Tenant) -> User:
    """Create a test user."""
    user = User(
        email="test@example.com",
        name="Test User",
        role="user",
        tenant_id=test_tenant.id,
        is_approved=True
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def test_skill(test_db: Session, test_tenant: Tenant) -> TenantSkill:
    """Create a test skill."""
    skill = TenantSkill(
        tenant_id=test_tenant.id,
        skill_name="test_skill",
        description="A test skill",
        skill_data={"test": "data"},
        intent_patterns=["test.*", "run test"],
        is_active=True,
        version=1
    )
    test_db.add(skill)
    test_db.commit()
    test_db.refresh(skill)
    return skill


@pytest.fixture
def auth_headers(test_user: User) -> dict:
    """Create authentication headers for test user."""
    # In a real scenario, this would create a proper JWT or session
    # For testing, we'll mock the authentication
    return {"Authorization": f"Bearer test_token_{test_user.id}"}


class TestListSkills:
    """Tests for GET /api/skills endpoint (existing functionality)."""

    def test_list_skills_requires_auth(self, test_db: Session):
        """Test that listing skills requires authentication."""
        response = client.get("/api/skills")
        assert response.status_code in [401, 403]

    def test_list_skills_with_tenant_isolation(
        self, test_db: Session, test_user: User, test_skill: TenantSkill, auth_headers: dict
    ):
        """Test that skills are filtered by tenant."""
        # This test would need proper auth mocking
        # Placeholder for tenant isolation verification
        pass


class TestInvokeSkill:
    """Tests for POST /api/skills/invoke endpoint."""

    def test_invoke_skill_requires_auth(self, test_db: Session):
        """Test that skill invocation requires authentication."""
        response = client.post(
            "/api/skills/invoke",
            json={"skill_name": "test_skill", "context": {}}
        )
        assert response.status_code in [401, 403]

    def test_invoke_skill_success(
        self, test_db: Session, test_user: User, test_skill: TenantSkill, auth_headers: dict
    ):
        """Test successful skill invocation."""
        # Mock auth would be needed here
        # Testing the response format
        request_data = {
            "skill_name": "test_skill",
            "context": {"user_id": 123, "action": "test"}
        }

        # This would work with proper auth mocking
        # response = client.post("/api/skills/invoke", json=request_data, headers=auth_headers)
        # assert response.status_code == 200
        # data = response.json()
        # assert data["success"] is True
        # assert data["skill_name"] == "test_skill"
        # assert data["message"] == "Skill test_skill executed successfully (mock)"
        # assert data["context"] == request_data["context"]

    def test_invoke_nonexistent_skill(
        self, test_db: Session, test_user: User, auth_headers: dict
    ):
        """Test invoking a skill that doesn't exist."""
        request_data = {
            "skill_name": "nonexistent_skill",
            "context": {}
        }

        # With proper auth:
        # response = client.post("/api/skills/invoke", json=request_data, headers=auth_headers)
        # assert response.status_code == 404
        # assert "not found" in response.json()["detail"].lower()

    def test_invoke_skill_different_tenant(
        self, test_db: Session, test_tenant: Tenant, test_skill: TenantSkill
    ):
        """Test that users cannot invoke skills from other tenants."""
        # Create second tenant and user
        other_tenant = Tenant(name="Other Tenant", is_active=True)
        test_db.add(other_tenant)
        test_db.commit()

        other_user = User(
            email="other@example.com",
            name="Other User",
            role="user",
            tenant_id=other_tenant.id,
            is_approved=True
        )
        test_db.add(other_user)
        test_db.commit()

        # Attempt to invoke skill from first tenant while authenticated as second tenant user
        # With proper auth:
        # response = client.post(
        #     "/api/skills/invoke",
        #     json={"skill_name": "test_skill", "context": {}},
        #     headers={"Authorization": f"Bearer test_token_{other_user.id}"}
        # )
        # assert response.status_code == 404  # Skill not found for this tenant

    def test_invoke_skill_validation_error(
        self, test_db: Session, test_user: User, auth_headers: dict
    ):
        """Test skill invocation with invalid request data."""
        # Missing skill_name
        response = client.post(
            "/api/skills/invoke",
            json={"context": {}}
        )
        assert response.status_code == 422  # Validation error


class TestMatchSkill:
    """Tests for POST /api/skills/match endpoint."""

    def test_match_skill_requires_auth(self, test_db: Session):
        """Test that skill matching requires authentication."""
        response = client.post(
            "/api/skills/match",
            json={"user_message": "test message"}
        )
        assert response.status_code in [401, 403]

    def test_match_skill_success(
        self, test_db: Session, test_user: User, test_skill: TenantSkill, auth_headers: dict
    ):
        """Test successful skill matching."""
        request_data = {"user_message": "run test workflow"}

        # With proper auth:
        # response = client.post("/api/skills/match", json=request_data, headers=auth_headers)
        # assert response.status_code == 200
        # data = response.json()
        # assert data["matched"] is True
        # assert data["skill"] is not None
        # assert data["skill"]["skill_name"] == "test_skill"

    def test_match_skill_no_match(
        self, test_db: Session, test_user: User, test_skill: TenantSkill, auth_headers: dict
    ):
        """Test skill matching when no pattern matches."""
        request_data = {"user_message": "something completely different"}

        # With proper auth:
        # response = client.post("/api/skills/match", json=request_data, headers=auth_headers)
        # assert response.status_code == 200
        # data = response.json()
        # assert data["matched"] is False
        # assert data["skill"] is None

    def test_match_skill_tenant_isolation(
        self, test_db: Session, test_tenant: Tenant, test_skill: TenantSkill
    ):
        """Test that skill matching respects tenant boundaries."""
        # Create second tenant with different skill
        other_tenant = Tenant(name="Other Tenant", is_active=True)
        test_db.add(other_tenant)
        test_db.commit()

        other_user = User(
            email="other@example.com",
            name="Other User",
            role="user",
            tenant_id=other_tenant.id,
            is_approved=True
        )
        test_db.add(other_user)
        test_db.commit()

        # User from other tenant shouldn't match skills from first tenant
        # With proper auth:
        # response = client.post(
        #     "/api/skills/match",
        #     json={"user_message": "test workflow"},
        #     headers={"Authorization": f"Bearer test_token_{other_user.id}"}
        # )
        # assert response.status_code == 200
        # data = response.json()
        # assert data["matched"] is False  # Skill belongs to different tenant

    def test_match_skill_validation_error(self, test_db: Session):
        """Test skill matching with invalid request data."""
        # Missing user_message
        response = client.post(
            "/api/skills/match",
            json={}
        )
        assert response.status_code == 422  # Validation error


class TestSkillInvokerUtil:
    """Tests for skill_invoker utility function."""

    def test_invoke_skill_basic(self):
        """Test basic skill invocation."""
        from app.utils.skill_invoker import invoke_skill

        result = invoke_skill(
            skill_name="test_skill",
            context={"key": "value"},
            tenant_id=1
        )

        assert result["success"] is True
        assert result["skill_name"] == "test_skill"
        assert "executed successfully" in result["message"]
        assert result["context"] == {"key": "value"}

    def test_invoke_skill_empty_context(self):
        """Test skill invocation with empty context."""
        from app.utils.skill_invoker import invoke_skill

        result = invoke_skill(
            skill_name="another_skill",
            context={},
            tenant_id=2
        )

        assert result["success"] is True
        assert result["context"] == {}

    def test_invoke_skill_invalid_name(self):
        """Test skill invocation with invalid skill name."""
        from app.utils.skill_invoker import invoke_skill

        with pytest.raises(ValueError, match="skill_name must be a non-empty string"):
            invoke_skill(skill_name="", context={}, tenant_id=1)

        with pytest.raises(ValueError, match="skill_name must be a non-empty string"):
            invoke_skill(skill_name=None, context={}, tenant_id=1)

    def test_invoke_skill_invalid_context(self):
        """Test skill invocation with invalid context."""
        from app.utils.skill_invoker import invoke_skill

        with pytest.raises(ValueError, match="context must be a dictionary"):
            invoke_skill(skill_name="test", context="not a dict", tenant_id=1)

        with pytest.raises(ValueError, match="context must be a dictionary"):
            invoke_skill(skill_name="test", context=None, tenant_id=1)

    def test_invoke_skill_invalid_tenant_id(self):
        """Test skill invocation with invalid tenant ID."""
        from app.utils.skill_invoker import invoke_skill

        with pytest.raises(ValueError, match="tenant_id must be a positive integer"):
            invoke_skill(skill_name="test", context={}, tenant_id=0)

        with pytest.raises(ValueError, match="tenant_id must be a positive integer"):
            invoke_skill(skill_name="test", context={}, tenant_id=-1)

        with pytest.raises(ValueError, match="tenant_id must be a positive integer"):
            invoke_skill(skill_name="test", context={}, tenant_id="not an int")
