"""Integration tests for workflow classification in chat flow."""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import Base
from app.api.auth_deps import get_approved_user
from app.models.models import (
    Tenant,
    User,
    Session as SessionModel,
    WorkflowClassification,
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
    from app.db.session import get_db

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

    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def tenant(db_session):
    """Create a test tenant."""
    tenant = Tenant(name="Test Tenant", slug="test-tenant")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


@pytest.fixture
def test_user(db_session, tenant):
    """Create and authenticate a test user."""
    user = User(
        tenant_id=tenant.id,
        email="test@example.com",
        name="Test User",
        password_hash="hashed",
        role=UserRole.USER,
        approval_status=ApprovalStatus.APPROVED,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_session(db_session, test_user, tenant):
    """Create a test session."""
    session = SessionModel(
        tenant_id=tenant.id,
        user_id=test_user.id,
        title="Test Session",
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def auth_as_user(test_user):
    """Override auth dependency to return test user."""
    app.dependency_overrides[get_approved_user] = lambda: test_user
    yield
    app.dependency_overrides.pop(get_approved_user, None)


# ==============================================================================
# Integration Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_chat_creates_classification(db_session, test_user, test_session, auth_as_user, client):
    """Test that chat endpoint creates workflow classification."""
    with patch("app.api.chat.OllamaClient") as mock_ollama:
        mock_client = AsyncMock()
        mock_client.generate_chat_completion = AsyncMock(return_value="Test response")
        mock_ollama.return_value = mock_client

        response = client.post(
            "/api/v1/chat",
            json={
                "session_id": test_session.id,
                "message": "Fix the login bug",
            }
        )

        assert response.status_code == 200

        # Check that classification was created
        classification = db_session.query(WorkflowClassification).first()
        assert classification is not None
        assert classification.user_id == test_user.id
        assert classification.session_id == test_session.id
        assert classification.category == WorkflowCategory.BUG_FIX
        assert classification.outcome == WorkflowOutcome.SUCCESS
        assert classification.request_text == "Fix the login bug"
        assert classification.confidence > 0


@pytest.mark.asyncio
async def test_chat_classification_categories(db_session, test_user, test_session, auth_as_user, client):
    """Test different workflow categories are classified correctly."""
    test_cases = [
        ("Fix the authentication error", WorkflowCategory.BUG_FIX),
        ("Create a new user dashboard", WorkflowCategory.FEATURE),
        ("Review the code for issues", WorkflowCategory.ANALYSIS),
        ("What is the current status?", WorkflowCategory.QUESTION),
    ]

    with patch("app.api.chat.OllamaClient") as mock_ollama:
        mock_client = AsyncMock()
        mock_client.generate_chat_completion = AsyncMock(return_value="Test response")
        mock_ollama.return_value = mock_client

        for message, expected_category in test_cases:
            response = client.post(
                "/api/v1/chat",
                json={
                    "session_id": test_session.id,
                    "message": message,
                }
            )

            assert response.status_code == 200

            # Get the latest classification
            classification = (
                db_session.query(WorkflowClassification)
                .filter(WorkflowClassification.request_text == message)
                .first()
            )

            assert classification is not None
            assert classification.category == expected_category
            assert classification.outcome == WorkflowOutcome.SUCCESS


@pytest.mark.asyncio
async def test_chat_failure_marks_outcome_failed(db_session, test_user, test_session, auth_as_user, client):
    """Test that failed chat marks outcome as FAILED."""
    with patch("app.api.chat.OllamaClient") as mock_ollama:
        mock_client = AsyncMock()
        from app.services.ollama import OllamaError
        mock_client.generate_chat_completion = AsyncMock(
            side_effect=OllamaError("Ollama service unavailable")
        )
        mock_ollama.return_value = mock_client

        response = client.post(
            "/api/v1/chat",
            json={
                "session_id": test_session.id,
                "message": "Fix the bug",
            }
        )

        assert response.status_code == 503

        # Check that classification was marked as FAILED
        classification = db_session.query(WorkflowClassification).first()
        assert classification is not None
        assert classification.outcome == WorkflowOutcome.FAILED
        assert classification.completed_at is not None


@pytest.mark.asyncio
async def test_repeated_requests_increment_count(db_session, test_user, test_session, auth_as_user, client):
    """Test that repeated requests are tracked."""
    with patch("app.api.chat.OllamaClient") as mock_ollama:
        mock_client = AsyncMock()
        mock_client.generate_chat_completion = AsyncMock(return_value="Test response")
        mock_ollama.return_value = mock_client

        # Send same type of request multiple times
        for _ in range(3):
            response = client.post(
                "/api/v1/chat",
                json={
                    "session_id": test_session.id,
                    "message": "Fix the login bug",
                }
            )
            assert response.status_code == 200

        # Check count
        count = (
            db_session.query(WorkflowClassification)
            .filter(WorkflowClassification.category == WorkflowCategory.BUG_FIX)
            .count()
        )
        assert count == 3


@pytest.mark.asyncio
async def test_unknown_workflow_logged(db_session, test_user, test_session, auth_as_user, client, caplog):
    """Test that unknown workflows are logged."""
    import logging

    with patch("app.api.chat.OllamaClient") as mock_ollama:
        mock_client = AsyncMock()
        mock_client.generate_chat_completion = AsyncMock(return_value="Test response")
        mock_ollama.return_value = mock_client

        # Send ambiguous request
        with caplog.at_level(logging.WARNING):
            response = client.post(
                "/api/v1/chat",
                json={
                    "session_id": test_session.id,
                    "message": "asdfghjkl",  # Random text
                }
            )

            assert response.status_code == 200

        # Check classification
        classification = db_session.query(WorkflowClassification).first()
        assert classification.category == WorkflowCategory.UNKNOWN

        # Check that warning was logged
        assert "Unknown workflow detected" in caplog.text


@pytest.mark.asyncio
async def test_subcategory_tracked(db_session, test_user, test_session, auth_as_user, client):
    """Test that subcategories are tracked."""
    with patch("app.api.chat.OllamaClient") as mock_ollama:
        mock_client = AsyncMock()
        mock_client.generate_chat_completion = AsyncMock(return_value="Test response")
        mock_ollama.return_value = mock_client

        response = client.post(
            "/api/v1/chat",
            json={
                "session_id": test_session.id,
                "message": "Debug the authentication error",
            }
        )

        assert response.status_code == 200

        # Check subcategory
        classification = db_session.query(WorkflowClassification).first()
        assert classification.subcategory in ["error_investigation", "debugging"]


@pytest.mark.asyncio
async def test_keywords_stored(db_session, test_user, test_session, auth_as_user, client):
    """Test that keywords are stored."""
    with patch("app.api.chat.OllamaClient") as mock_ollama:
        mock_client = AsyncMock()
        mock_client.generate_chat_completion = AsyncMock(return_value="Test response")
        mock_ollama.return_value = mock_client

        response = client.post(
            "/api/v1/chat",
            json={
                "session_id": test_session.id,
                "message": "Fix the bug in the error handler",
            }
        )

        assert response.status_code == 200

        # Check keywords
        classification = db_session.query(WorkflowClassification).first()
        assert classification.keywords is not None
        assert len(classification.keywords) > 0
        assert "fix" in classification.keywords or "bug" in classification.keywords


@pytest.mark.asyncio
async def test_confidence_stored(db_session, test_user, test_session, auth_as_user, client):
    """Test that confidence scores are stored."""
    with patch("app.api.chat.OllamaClient") as mock_ollama:
        mock_client = AsyncMock()
        mock_client.generate_chat_completion = AsyncMock(return_value="Test response")
        mock_ollama.return_value = mock_client

        response = client.post(
            "/api/v1/chat",
            json={
                "session_id": test_session.id,
                "message": "Fix the critical bug in authentication",
            }
        )

        assert response.status_code == 200

        # Check confidence
        classification = db_session.query(WorkflowClassification).first()
        assert classification.confidence > 0
        assert classification.confidence <= 100
