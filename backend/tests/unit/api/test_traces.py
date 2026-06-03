"""Unit tests for trace exploration API."""
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import httpx

from app.main import app
from app.db.session import Base, get_db
from app.api.traces import (
    verify_admin,
    sanitize_preview,
    filter_by_tenant,
    TracePreview,
    TraceListResponse,
)
from app.models.models import User, UserRole, Tenant
from app.services.auth import create_access_token, get_password_hash


@pytest.fixture
def test_db_session(tmp_path):
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
def client(test_db_session):
    """Create test client with test database."""
    def override_get_db():
        try:
            yield test_db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(test_db_session: Session) -> User:
    """Create admin user for testing."""
    tenant = Tenant(id=1, name="Test Org", slug="test")
    test_db_session.add(tenant)
    test_db_session.commit()

    user = User(
        id=1,
        tenant_id=1,
        email="admin@test.com",
        name="Admin User",
        password_hash=get_password_hash("password123"),
        role=UserRole.ADMIN,
        approval_status="approved",
    )
    test_db_session.add(user)
    test_db_session.commit()
    return user


@pytest.fixture
def normal_user(test_db_session: Session) -> User:
    """Create normal user for testing."""
    tenant = test_db_session.query(Tenant).filter(Tenant.id == 1).first()
    if not tenant:
        tenant = Tenant(id=1, name="Test Org", slug="test")
        test_db_session.add(tenant)
        test_db_session.commit()

    user = User(
        id=2,
        tenant_id=1,
        email="user@test.com",
        name="Normal User",
        password_hash=get_password_hash("password123"),
        role=UserRole.USER,
        approval_status="approved",
    )
    test_db_session.add(user)
    test_db_session.commit()
    return user


@pytest.fixture
def admin_user_token(admin_user: User) -> str:
    """Create JWT token for admin user."""
    return create_access_token(data={"sub": str(admin_user.id)})


@pytest.fixture
def normal_user_token(normal_user: User) -> str:
    """Create JWT token for normal user."""
    return create_access_token(data={"sub": str(normal_user.id)})


class TestVerifyAdmin:
    """Test admin verification."""

    def test_verify_admin_success(self):
        """Admin users should pass verification."""
        user = User(id=1, email="admin@test.com", role=UserRole.ADMIN)
        # Should not raise
        verify_admin(user)

    def test_verify_admin_failure(self):
        """Non-admin users should fail verification."""
        user = User(id=2, email="user@test.com", role=UserRole.USER)
        with pytest.raises(HTTPException) as exc_info:
            verify_admin(user)
        assert exc_info.value.status_code == 403
        assert "Admin access required" in exc_info.value.detail


class TestSanitizePreview:
    """Test preview sanitization."""

    def test_sanitize_none(self):
        """None input should return None."""
        assert sanitize_preview(None) is None

    def test_sanitize_short_text(self):
        """Short text should be unchanged."""
        text = "Short text"
        assert sanitize_preview(text) == text

    def test_sanitize_long_text(self):
        """Long text should be truncated."""
        text = "x" * 300
        result = sanitize_preview(text, max_length=200)
        assert len(result) <= 203  # 200 + "..."
        assert result.endswith("...")

    def test_sanitize_email(self):
        """Emails should be redacted."""
        text = "Contact user@example.com for help"
        result = sanitize_preview(text)
        assert "[EMAIL]" in result
        assert "user@example.com" not in result

    def test_sanitize_phone(self):
        """Phone numbers should be redacted."""
        text = "Call 555-123-4567 for support"
        result = sanitize_preview(text)
        assert "[PHONE]" in result
        assert "555-123-4567" not in result


class TestFilterByTenant:
    """Test tenant filtering."""

    def test_filter_no_tenant(self, test_db_session):
        """User with no tenant should get empty list."""
        user = User(id=1, tenant_id=None)
        traces = [{"id": "trace1", "userId": "1"}]
        result = filter_by_tenant(traces, user, test_db_session)
        assert result == traces  # No filtering when user has no tenant

    def test_filter_by_tenant(self, test_db_session):
        """Should filter traces to only tenant members."""
        # Create tenant and users
        tenant = Tenant(id=1, name="Test", slug="test")
        test_db_session.add(tenant)
        test_db_session.commit()

        user1 = User(id=1, tenant_id=1, email="user1@test.com", name="User 1", password_hash="hash1")
        user2 = User(id=2, tenant_id=1, email="user2@test.com", name="User 2", password_hash="hash2")
        user3 = User(id=3, tenant_id=2, email="user3@test.com", name="User 3", password_hash="hash3")

        test_db_session.add_all([user1, user2, user3])
        test_db_session.commit()

        admin = User(id=999, tenant_id=1, role=UserRole.ADMIN, name="Admin", password_hash="hash999")

        traces = [
            {"id": "trace1", "userId": "1"},  # In tenant
            {"id": "trace2", "userId": "2"},  # In tenant
            {"id": "trace3", "userId": "3"},  # Different tenant
        ]

        result = filter_by_tenant(traces, admin, test_db_session)

        assert len(result) == 2
        assert result[0]["id"] == "trace1"
        assert result[1]["id"] == "trace2"


class TestListTracesEndpoint:
    """Test list traces endpoint."""

    def test_list_traces_requires_admin(self, client, normal_user_token):
        """Non-admin users should be denied."""
        response = client.get(
            "/api/admin/traces",
            headers={"Authorization": f"Bearer {normal_user_token}"}
        )
        assert response.status_code == 403

    def test_list_traces_success(self, client, admin_user_token):
        """Admin users should be able to list traces."""
        mock_response_data = {
            "data": [
                {
                    "id": "trace-123",
                    "userId": "1",
                    "sessionId": "session-1",
                    "name": "test_workflow",
                    "timestamp": "2024-01-01T00:00:00Z",
                    "updatedAt": "2024-01-01T00:05:00Z",
                    "duration": 5000,
                    "input": "test input",
                    "output": "test output",
                    "tags": ["test"],
                }
            ],
            "meta": {"totalItems": 1}
        }

        with patch("app.api.traces.get_langfuse_client") as mock_client_factory:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_response = MagicMock()
            mock_response.json.return_value = mock_response_data
            mock_client.get.return_value = mock_response
            mock_client_factory.return_value = mock_client

            response = client.get(
                "/api/admin/traces",
                headers={"Authorization": f"Bearer {admin_user_token}"}
            )

        assert response.status_code == 200
        data = response.json()
        assert "traces" in data
        assert len(data["traces"]) == 1
        assert data["traces"][0]["trace_id"] == "trace-123"
        assert "has_more" in data

    def test_list_traces_with_pagination(self, client, admin_user_token):
        """Should support pagination parameters."""
        mock_response_data = {
            "data": [],
            "meta": {"totalItems": 100}
        }

        with patch("app.api.traces.get_langfuse_client") as mock_client_factory:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_response = MagicMock()
            mock_response.json.return_value = mock_response_data
            mock_client.get.return_value = mock_response
            mock_client_factory.return_value = mock_client

            response = client.get(
                "/api/admin/traces?limit=10&offset=20",
                headers={"Authorization": f"Bearer {admin_user_token}"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 10
        assert data["offset"] == 20
        assert data["has_more"] is True  # 20 + 0 < 100


class TestGetTraceEndpoint:
    """Test get single trace endpoint."""

    def test_get_trace_not_found(self, client, admin_user_token):
        """Should return 404 for non-existent trace."""
        with patch("app.api.traces.get_langfuse_client") as mock_client_factory:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None

            # Simulate 404 response
            error_response = MagicMock()
            error_response.status_code = 404
            error = httpx.HTTPStatusError("Not found", request=MagicMock(), response=error_response)
            mock_client.get.side_effect = error
            mock_client_factory.return_value = mock_client

            response = client.get(
                "/api/admin/traces/nonexistent",
                headers={"Authorization": f"Bearer {admin_user_token}"}
            )

        assert response.status_code == 404

    def test_get_trace_success(self, client, admin_user_token):
        """Should return trace details."""
        mock_response_data = {
            "id": "trace-123",
            "userId": "1",
            "sessionId": "session-1",
            "name": "test_workflow",
            "timestamp": "2024-01-01T00:00:00Z",
            "updatedAt": "2024-01-01T00:05:00Z",
            "duration": 5000,
            "input": {"key": "value"},
            "output": {"result": "success"},
            "observations": [],
            "tags": ["test"],
        }

        with patch("app.api.traces.get_langfuse_client") as mock_client_factory:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_response = MagicMock()
            mock_response.json.return_value = mock_response_data
            mock_client.get.return_value = mock_response
            mock_client_factory.return_value = mock_client

            response = client.get(
                "/api/admin/traces/trace-123",
                headers={"Authorization": f"Bearer {admin_user_token}"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["trace_id"] == "trace-123"
        assert data["user_id"] == "1"


class TestSearchTracesEndpoint:
    """Test search traces endpoint."""

    def test_search_traces_with_filters(self, client, admin_user_token):
        """Should accept search filters in request body."""
        search_request = {
            "user_id": "1",
            "status": "success",
            "limit": 10,
            "offset": 0
        }

        mock_response_data = {
            "data": [],
            "meta": {"totalItems": 0}
        }

        with patch("app.api.traces.get_langfuse_client") as mock_client_factory:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_response = MagicMock()
            mock_response.json.return_value = mock_response_data
            mock_client.get.return_value = mock_response
            mock_client_factory.return_value = mock_client

            response = client.post(
                "/api/admin/traces/search",
                json=search_request,
                headers={"Authorization": f"Bearer {admin_user_token}"}
            )

        assert response.status_code == 200
        data = response.json()
        assert "traces" in data
        assert data["limit"] == 10
