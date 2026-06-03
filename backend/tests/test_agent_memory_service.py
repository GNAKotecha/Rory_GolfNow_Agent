"""Unit tests for AgentMemoryService."""
import json
import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.models import Tenant, User, Session, SessionMemorySummary
from app.services.agent_memory import AgentMemoryService


@pytest.fixture
def db():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def tenant_and_user(db):
    """Create test tenant and user."""
    tenant = Tenant(id=1, name="Test Tenant", slug="test-tenant")
    user = User(id=1, tenant_id=1, email="test@example.com", name="Test User", password_hash="hash")
    db.add(tenant)
    db.add(user)
    db.commit()
    return tenant, user


@pytest.fixture
def test_session(db, tenant_and_user):
    """Create test session."""
    tenant, user = tenant_and_user
    session = Session(
        id=1,
        tenant_id=tenant.id,
        user_id=user.id,
        title="Test Session",
        session_working_memory={}
    )
    db.add(session)
    db.commit()
    return session


class TestWorkingMemoryGet:
    """Test get_working_memory method."""

    def test_get_empty_memory(self, db, test_session):
        """Test retrieving empty working memory."""
        memory = AgentMemoryService.get_working_memory(test_session.id, test_session.tenant_id, db)
        assert memory == {}

    def test_get_existing_memory(self, db, test_session):
        """Test retrieving existing working memory."""
        test_session.session_working_memory = {"fact1": "value1", "fact2": "value2"}
        db.commit()
        memory = AgentMemoryService.get_working_memory(test_session.id, test_session.tenant_id, db)
        assert memory == {"fact1": "value1", "fact2": "value2"}

    def test_get_memory_cross_tenant_denied(self, db, tenant_and_user):
        """Test that cross-tenant access is denied."""
        tenant, user = tenant_and_user
        session = Session(
            id=2,
            tenant_id=tenant.id,
            user_id=user.id,
            title="Test Session 2",
            session_working_memory={"fact": "value"}
        )
        db.add(session)
        db.commit()

        # Try to access with different tenant_id
        memory = AgentMemoryService.get_working_memory(session.id, 999, db)
        assert memory is None or memory == {}


class TestWorkingMemoryUpdate:
    """Test update_working_memory method."""

    def test_update_simple_merge(self, db, test_session):
        """Test simple merge of updates."""
        test_session.session_working_memory = {"key1": "value1"}
        db.commit()

        result = AgentMemoryService.update_working_memory(
            test_session.id, test_session.tenant_id, {"key2": "value2"}, db
        )
        assert result == {"key1": "value1", "key2": "value2"}

    def test_update_overwrite_key(self, db, test_session):
        """Test that update overwrites existing keys."""
        test_session.session_working_memory = {"key1": "old"}
        db.commit()

        result = AgentMemoryService.update_working_memory(
            test_session.id, test_session.tenant_id, {"key1": "new"}, db
        )
        assert result == {"key1": "new"}

    def test_update_persists_to_db(self, db, test_session):
        """Test that updates persist to database."""
        AgentMemoryService.update_working_memory(
            test_session.id, test_session.tenant_id, {"key": "value"}, db
        )

        # Refresh session from DB
        db.refresh(test_session)
        assert test_session.session_working_memory == {"key": "value"}

    def test_update_respects_2kb_limit(self, db, test_session):
        """Test that update enforces 2KB size limit."""
        # Create large value that would exceed 2KB when encoded
        large_value = "x" * 2500

        result = AgentMemoryService.update_working_memory(
            test_session.id, test_session.tenant_id, {"large": large_value}, db
        )

        # Should still work but be trimmed
        size = len(json.dumps(result).encode('utf-8'))
        assert size < 2048

    def test_update_empty_on_cross_tenant(self, db, tenant_and_user):
        """Test that cross-tenant update returns None/empty."""
        tenant, user = tenant_and_user
        session = Session(
            id=3,
            tenant_id=tenant.id,
            user_id=user.id,
            title="Test",
            session_working_memory={}
        )
        db.add(session)
        db.commit()

        result = AgentMemoryService.update_working_memory(
            session.id, 999, {"key": "value"}, db
        )
        assert result is None


class TestSessionSummaryStorage:
    """Test store_session_summary method."""

    def test_store_summary_creates_record(self, db, test_session):
        """Test that storing summary creates database record."""
        result = AgentMemoryService.store_session_summary(
            test_session.id, test_session.tenant_id, "Summary content", db
        )

        assert result is not None
        assert result.session_id == test_session.id
        assert result.tenant_id == test_session.tenant_id
        assert result.content == "Summary content"

    def test_store_summary_sets_timestamp(self, db, test_session):
        """Test that timestamp is set on creation."""
        before = datetime.utcnow()
        result = AgentMemoryService.store_session_summary(
            test_session.id, test_session.tenant_id, "Content", db
        )
        after = datetime.utcnow()

        assert before <= result.created_at <= after

    def test_store_summary_persists(self, db, test_session):
        """Test that summary persists in database."""
        AgentMemoryService.store_session_summary(
            test_session.id, test_session.tenant_id, "Content", db
        )

        summary = db.query(SessionMemorySummary).filter_by(
            session_id=test_session.id,
            tenant_id=test_session.tenant_id
        ).first()

        assert summary is not None
        assert summary.content == "Content"


class TestHistoricalRetrieval:
    """Test retrieve_historical_context method."""

    def test_retrieve_empty_results(self, db, test_session):
        """Test retrieval with no summaries."""
        results = AgentMemoryService.retrieve_historical_context(
            test_session.tenant_id, "nonexistent", db
        )
        assert results == []

    def test_retrieve_keyword_match(self, db, test_session):
        """Test retrieval with keyword matching."""
        AgentMemoryService.store_session_summary(
            test_session.id, test_session.tenant_id, "User booked golf club", db
        )

        results = AgentMemoryService.retrieve_historical_context(
            test_session.tenant_id, "golf", db
        )

        assert len(results) == 1
        assert "golf" in results[0].content

    def test_retrieve_case_insensitive(self, db, test_session):
        """Test that keyword search is case-insensitive."""
        AgentMemoryService.store_session_summary(
            test_session.id, test_session.tenant_id, "BOOKING CONFIRMED", db
        )

        results = AgentMemoryService.retrieve_historical_context(
            test_session.tenant_id, "booking", db
        )

        assert len(results) == 1

    def test_retrieve_limit(self, db, test_session):
        """Test that result limit is respected."""
        for i in range(10):
            AgentMemoryService.store_session_summary(
                test_session.id, test_session.tenant_id, f"Summary {i} with keyword", db
            )

        results = AgentMemoryService.retrieve_historical_context(
            test_session.tenant_id, "keyword", db, limit=3
        )

        assert len(results) == 3

    def test_retrieve_newest_first(self, db, test_session):
        """Test that results are ordered by newest first."""
        for i in range(3):
            AgentMemoryService.store_session_summary(
                test_session.id, test_session.tenant_id, f"Summary {i}", db
            )

        results = AgentMemoryService.retrieve_historical_context(
            test_session.tenant_id, "Summary", db, limit=10
        )

        # Should be in reverse chronological order
        assert len(results) == 3
        assert results[0].content == "Summary 2"
        assert results[1].content == "Summary 1"
        assert results[2].content == "Summary 0"


class TestTenantIsolation:
    """Test tenant isolation across all operations."""

    def test_isolation_separate_sessions(self, db):
        """Test that different tenants have separate memory."""
        # Create two tenants
        tenant1 = Tenant(id=1, name="Tenant 1", slug="tenant-1")
        tenant2 = Tenant(id=2, name="Tenant 2", slug="tenant-2")
        db.add(tenant1)
        db.add(tenant2)

        user1 = User(id=1, tenant_id=1, email="user1@example.com", name="User 1", password_hash="hash")
        user2 = User(id=2, tenant_id=2, email="user2@example.com", name="User 2", password_hash="hash")
        db.add(user1)
        db.add(user2)

        session1 = Session(id=1, tenant_id=1, user_id=1, title="S1", session_working_memory={})
        session2 = Session(id=2, tenant_id=2, user_id=2, title="S2", session_working_memory={})
        db.add(session1)
        db.add(session2)
        db.commit()

        # Update memory for each tenant
        AgentMemoryService.update_working_memory(1, 1, {"key": "tenant1"}, db)
        AgentMemoryService.update_working_memory(2, 2, {"key": "tenant2"}, db)

        # Verify isolation
        memory1 = AgentMemoryService.get_working_memory(1, 1, db)
        memory2 = AgentMemoryService.get_working_memory(2, 2, db)

        assert memory1 == {"key": "tenant1"}
        assert memory2 == {"key": "tenant2"}

    def test_isolation_historical_retrieval(self, db):
        """Test that historical retrieval is tenant-isolated."""
        tenant1 = Tenant(id=1, name="Tenant 1", slug="tenant-1")
        tenant2 = Tenant(id=2, name="Tenant 2", slug="tenant-2")
        db.add(tenant1)
        db.add(tenant2)

        user1 = User(id=1, tenant_id=1, email="user1@example.com", name="User 1", password_hash="hash")
        user2 = User(id=2, tenant_id=2, email="user2@example.com", name="User 2", password_hash="hash")
        db.add(user1)
        db.add(user2)

        session1 = Session(id=1, tenant_id=1, user_id=1, title="S1")
        session2 = Session(id=2, tenant_id=2, user_id=2, title="S2")
        db.add(session1)
        db.add(session2)
        db.commit()

        # Store summaries for each tenant
        AgentMemoryService.store_session_summary(1, 1, "Tenant 1 booked golf", db)
        AgentMemoryService.store_session_summary(2, 2, "Tenant 2 booked golf", db)

        # Retrieve for each tenant
        results1 = AgentMemoryService.retrieve_historical_context(1, "golf", db)
        results2 = AgentMemoryService.retrieve_historical_context(2, "golf", db)

        assert len(results1) == 1
        assert len(results2) == 1
        assert results1[0].tenant_id == 1
        assert results2[0].tenant_id == 2
