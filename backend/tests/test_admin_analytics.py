"""Tests for admin analytics API."""
import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.main import app
from app.db.session import Base, get_db
from app.models.models import (
    User,
    Session as SessionModel,
    Message as MessageModel,
    WorkflowClassification,
    ToolCall,
    Approval,
    WorkflowCategory,
    WorkflowOutcome,
    UserRole,
    ApprovalStatus,
)


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def db_session(tmp_path):
    """Create a test database session."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    TestingSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    session = TestingSessionLocal()
    yield session
    session.close()

    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(db_session):
    """Create an admin user."""
    user = User(
        email="admin@example.com",
        name="Admin User",
        password_hash="hashed",
        role=UserRole.ADMIN,
        approval_status=ApprovalStatus.APPROVED,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def regular_user(db_session):
    """Create a regular user."""
    user = User(
        email="user@example.com",
        name="Regular User",
        password_hash="hashed",
        role=UserRole.USER,
        approval_status=ApprovalStatus.APPROVED,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def pending_user(db_session):
    """Create a pending user."""
    user = User(
        email="pending@example.com",
        name="Pending User",
        password_hash="hashed",
        role=UserRole.USER,
        approval_status=ApprovalStatus.PENDING,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def seeded_data(db_session, admin_user, regular_user, pending_user):
    """Seed database with sample analytics data."""
    # Create sessions
    sessions = []
    for i in range(5):
        session = SessionModel(
            user_id=regular_user.id,
            title=f"Test Session {i}",
        )
        # Make some sessions recent, some old
        if i < 3:
            session.updated_at = datetime.utcnow() - timedelta(days=2)
        else:
            session.updated_at = datetime.utcnow() - timedelta(days=45)

        db_session.add(session)
        sessions.append(session)

    db_session.commit()
    for s in sessions:
        db_session.refresh(s)

    # Create messages
    for session in sessions[:3]:  # Only recent sessions
        for j in range(10):
            message = MessageModel(
                session_id=session.id,
                role="user" if j % 2 == 0 else "assistant",
                content=f"Message {j}",
            )
            db_session.add(message)

    db_session.commit()

    # Create workflow classifications
    classifications_data = [
        (WorkflowCategory.BUG_FIX, WorkflowOutcome.SUCCESS, 80, "debugging", 5),
        (WorkflowCategory.BUG_FIX, WorkflowOutcome.FAILED, 75, "debugging", 2),
        (WorkflowCategory.FEATURE, WorkflowOutcome.SUCCESS, 70, "new_feature", 8),
        (WorkflowCategory.ANALYSIS, WorkflowOutcome.SUCCESS, 85, "code_review", 4),
        (WorkflowCategory.QUESTION, WorkflowOutcome.SUCCESS, 60, "information", 12),
        (WorkflowCategory.UNKNOWN, WorkflowOutcome.PENDING, 20, None, 3),
    ]

    for category, outcome, confidence, subcategory, count in classifications_data:
        for i in range(count):
            # Create a message for each classification
            message = MessageModel(
                session_id=sessions[0].id,
                role="user",
                content=f"Test request {category.value}",
            )
            db_session.add(message)
            db_session.commit()
            db_session.refresh(message)

            classification = WorkflowClassification(
                session_id=sessions[0].id,
                message_id=message.id,
                user_id=regular_user.id,
                category=category,
                subcategory=subcategory,
                confidence=confidence,
                outcome=outcome,
                request_text=f"Test request {category.value}",
                keywords=[category.value],
            )
            db_session.add(classification)

    db_session.commit()

    # Create tool calls
    tool_calls_data = [
        ("calculate", 10, 9),  # 9 success, 1 error
        ("database_query", 15, 13),  # 13 success, 2 errors
        ("api_call", 5, 5),  # All success
    ]

    for tool_name, total, success_count in tool_calls_data:
        for i in range(total):
            tool_call = ToolCall(
                session_id=sessions[0].id,
                tool_name=tool_name,
                parameters={"test": "param"},
                result={"result": "success"} if i < success_count else None,
                error="Tool error" if i >= success_count else None,
            )
            db_session.add(tool_call)

    db_session.commit()

    # Create approvals
    approval_data = [
        ("database_write", 10, 8, 1),  # 8 approved, 1 rejected, 1 pending
        ("file_delete", 5, 3, 2),  # 3 approved, 2 rejected, 0 pending
        ("api_post", 8, 7, 0),  # 7 approved, 0 rejected, 1 pending
    ]

    for request_type, total, approved_count, rejected_count in approval_data:
        for i in range(total):
            approval = Approval(
                session_id=sessions[0].id,
                request_type=request_type,
                request_data={"test": "data"},
                approved=1 if i < approved_count else (0 if i < approved_count + rejected_count else None),
            )
            db_session.add(approval)

    db_session.commit()

    return {
        "admin_user": admin_user,
        "regular_user": regular_user,
        "pending_user": pending_user,
        "sessions": sessions,
    }


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


# ==============================================================================
# Test Admin Access Control
# ==============================================================================

def test_admin_analytics_requires_admin(db_session, regular_user, client):
    """Test that non-admin users cannot access analytics."""
    with patch("app.api.auth_deps.get_approved_user", return_value=regular_user):
        response = client.get("/api/admin/analytics")
        assert response.status_code == 403
        assert "Admin access required" in response.json()["detail"]


def test_admin_analytics_allows_admin(db_session, admin_user, seeded_data, client):
    """Test that admin users can access analytics."""
    with patch("app.api.auth_deps.get_approved_user", return_value=admin_user):
        response = client.get("/api/admin/analytics")
        assert response.status_code == 200


# ==============================================================================
# Test User Statistics
# ==============================================================================

def test_get_user_statistics(db_session, admin_user, seeded_data, client):
    """Test user statistics endpoint."""
    with patch("app.api.auth_deps.get_approved_user", return_value=admin_user):
        response = client.get("/api/admin/analytics/users")
        assert response.status_code == 200

        data = response.json()
        assert data["total_users"] == 3  # admin + regular + pending
        assert data["approved_users"] == 2  # admin + regular
        assert data["pending_users"] == 1
        assert data["admin_users"] == 1


# ==============================================================================
# Test Session Statistics
# ==============================================================================

def test_get_session_statistics(db_session, admin_user, seeded_data, client):
    """Test session statistics endpoint."""
    with patch("app.api.auth_deps.get_approved_user", return_value=admin_user):
        response = client.get("/api/admin/analytics/sessions")
        assert response.status_code == 200

        data = response.json()
        assert data["total_sessions"] == 5
        assert data["active_sessions_7d"] == 3  # Recent sessions
        assert data["active_sessions_30d"] == 3  # Recent sessions
        assert data["avg_messages_per_session"] > 0


# ==============================================================================
# Test Category Statistics
# ==============================================================================

def test_get_category_statistics(db_session, admin_user, seeded_data, client):
    """Test workflow category statistics."""
    with patch("app.api.auth_deps.get_approved_user", return_value=admin_user):
        response = client.get("/api/admin/analytics/categories")
        assert response.status_code == 200

        data = response.json()
        assert len(data) > 0

        # Check that categories are present
        categories = [item["category"] for item in data]
        assert "question" in categories
        assert "feature" in categories
        assert "bug_fix" in categories

        # Check that most common category is first (sorted by count)
        assert data[0]["count"] >= data[-1]["count"]


# ==============================================================================
# Test Outcome Statistics
# ==============================================================================

def test_get_outcome_statistics(db_session, admin_user, seeded_data, client):
    """Test workflow outcome statistics."""
    with patch("app.api.auth_deps.get_approved_user", return_value=admin_user):
        response = client.get("/api/admin/analytics/outcomes")
        assert response.status_code == 200

        data = response.json()
        assert len(data) > 0

        # Check structure
        for item in data:
            assert "category" in item
            assert "success" in item
            assert "failed" in item
            assert "success_rate" in item
            assert item["total"] == (
                item["success"] + item["partial"] + item["failed"] +
                item["escalated"] + item["pending"]
            )

        # Check that success rates are calculated
        for item in data:
            if item["total"] > 0:
                expected_rate = round(item["success"] / item["total"] * 100, 2)
                assert item["success_rate"] == expected_rate


# ==============================================================================
# Test Repeated Workflows (Trends)
# ==============================================================================

def test_get_workflow_trends(db_session, admin_user, seeded_data, client):
    """Test repeated workflow trends."""
    with patch("app.api.auth_deps.get_approved_user", return_value=admin_user):
        response = client.get("/api/admin/analytics/trends?min_count=3")
        assert response.status_code == 200

        data = response.json()
        assert len(data) > 0

        # Check that trends have required fields
        for item in data:
            assert "category" in item
            assert "count" in item
            assert item["count"] >= 3  # Min count filter
            assert "first_seen" in item
            assert "last_seen" in item
            assert "unique_users" in item
            assert "avg_confidence" in item

        # Check that trends are sorted by count (descending)
        counts = [item["count"] for item in data]
        assert counts == sorted(counts, reverse=True)


def test_get_workflow_trends_custom_min_count(db_session, admin_user, seeded_data, client):
    """Test trends with custom minimum count."""
    with patch("app.api.auth_deps.get_approved_user", return_value=admin_user):
        # Get trends with min_count=5
        response = client.get("/api/admin/analytics/trends?min_count=5")
        assert response.status_code == 200

        data = response.json()
        # All returned trends should have count >= 5
        for item in data:
            assert item["count"] >= 5


# ==============================================================================
# Test Tool Usage Statistics
# ==============================================================================

def test_get_tool_usage_statistics(db_session, admin_user, seeded_data, client):
    """Test tool usage statistics."""
    with patch("app.api.auth_deps.get_approved_user", return_value=admin_user):
        response = client.get("/api/admin/analytics/tools")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 3  # calculate, database_query, api_call

        # Check structure
        for item in data:
            assert "tool_name" in item
            assert "call_count" in item
            assert "success_count" in item
            assert "error_count" in item
            assert "success_rate" in item
            assert item["call_count"] == item["success_count"] + item["error_count"]

        # Check specific tools
        tool_names = [item["tool_name"] for item in data]
        assert "calculate" in tool_names
        assert "database_query" in tool_names
        assert "api_call" in tool_names

        # Check api_call has 100% success rate
        api_call_stat = next(item for item in data if item["tool_name"] == "api_call")
        assert api_call_stat["success_rate"] == 100.0


# ==============================================================================
# Test Approval Statistics
# ==============================================================================

def test_get_approval_statistics(db_session, admin_user, seeded_data, client):
    """Test approval statistics."""
    with patch("app.api.auth_deps.get_approved_user", return_value=admin_user):
        response = client.get("/api/admin/analytics/approvals")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 3  # database_write, file_delete, api_post

        # Check structure
        for item in data:
            assert "request_type" in item
            assert "total" in item
            assert "approved" in item
            assert "rejected" in item
            assert "pending" in item
            assert "approval_rate" in item
            assert item["total"] == item["approved"] + item["rejected"] + item["pending"]

        # Check specific approval types
        request_types = [item["request_type"] for item in data]
        assert "database_write" in request_types
        assert "file_delete" in request_types
        assert "api_post" in request_types


# ==============================================================================
# Test Complete Analytics
# ==============================================================================

def test_get_complete_analytics(db_session, admin_user, seeded_data, client):
    """Test complete analytics endpoint."""
    with patch("app.api.auth_deps.get_approved_user", return_value=admin_user):
        response = client.get("/api/admin/analytics")
        assert response.status_code == 200

        data = response.json()

        # Check all sections are present
        assert "user_stats" in data
        assert "session_stats" in data
        assert "top_categories" in data
        assert "outcomes" in data
        assert "repeated_workflows" in data
        assert "workflow_maturity" in data
        assert "tool_usage" in data
        assert "approval_stats" in data
        assert "generated_at" in data

        # Check user stats
        assert data["user_stats"]["total_users"] == 3
        assert data["user_stats"]["approved_users"] == 2

        # Check session stats
        assert data["session_stats"]["total_sessions"] == 5

        # Check categories
        assert len(data["top_categories"]) > 0

        # Check outcomes
        assert len(data["outcomes"]) > 0

        # Check repeated workflows
        assert len(data["repeated_workflows"]) > 0

        # Check workflow maturity
        assert data["workflow_maturity"]["total_workflows"] > 0
        assert data["workflow_maturity"]["known_workflows"] > 0
        assert data["workflow_maturity"]["emerging_workflows"] >= 0

        # Check tool usage
        assert len(data["tool_usage"]) == 3

        # Check approvals
        assert len(data["approval_stats"]) == 3


# ==============================================================================
# Test Date Range Filtering
# ==============================================================================

def test_analytics_with_custom_days(db_session, admin_user, seeded_data, client):
    """Test analytics with custom date range."""
    with patch("app.api.auth_deps.get_approved_user", return_value=admin_user):
        # Get analytics for last 7 days
        response = client.get("/api/admin/analytics?days=7")
        assert response.status_code == 200

        data = response.json()
        assert "generated_at" in data


# ==============================================================================
# Test Empty Database
# ==============================================================================

def test_analytics_with_empty_database(db_session, admin_user, client):
    """Test analytics with no data (except admin user)."""
    with patch("app.api.auth_deps.get_approved_user", return_value=admin_user):
        response = client.get("/api/admin/analytics")
        assert response.status_code == 200

        data = response.json()
        # Should return zeros/empty lists, not error
        assert data["user_stats"]["total_users"] >= 1  # At least admin
        assert data["session_stats"]["total_sessions"] == 0
        assert data["top_categories"] == []
        assert data["tool_usage"] == []
