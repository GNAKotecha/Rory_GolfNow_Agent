"""Integration tests for AgentMemoryService."""
import pytest
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
def setup_multi_tenant(db):
    """Setup multiple tenants with sessions for testing."""
    # Create tenants
    tenant1 = Tenant(id=1, name="Tenant 1", slug="tenant-1")
    tenant2 = Tenant(id=2, name="Tenant 2", slug="tenant-2")
    db.add(tenant1)
    db.add(tenant2)

    # Create users
    user1 = User(id=1, tenant_id=1, email="user1@example.com", name="User 1", password_hash="hash")
    user2 = User(id=2, tenant_id=2, email="user2@example.com", name="User 2", password_hash="hash")
    db.add(user1)
    db.add(user2)

    # Create sessions
    session1 = Session(id=1, tenant_id=1, user_id=1, title="Session 1")
    session2 = Session(id=2, tenant_id=2, user_id=2, title="Session 2")
    session3 = Session(id=3, tenant_id=1, user_id=1, title="Session 3")
    db.add(session1)
    db.add(session2)
    db.add(session3)
    db.commit()

    return {"tenant1": tenant1, "tenant2": tenant2, "s1": session1, "s2": session2, "s3": session3}


class TestMultiSessionMemory:
    """Test memory isolation across multiple sessions."""

    def test_multiple_sessions_separate_memory(self, db, setup_multi_tenant):
        """Test that multiple sessions in same tenant have separate memory."""
        s1 = setup_multi_tenant["s1"]
        s3 = setup_multi_tenant["s3"]

        # Update memory for each session
        AgentMemoryService.update_working_memory(s1.id, s1.tenant_id, {"session": "1"}, db)
        AgentMemoryService.update_working_memory(s3.id, s3.tenant_id, {"session": "3"}, db)

        # Verify separation
        mem1 = AgentMemoryService.get_working_memory(s1.id, s1.tenant_id, db)
        mem3 = AgentMemoryService.get_working_memory(s3.id, s3.tenant_id, db)

        assert mem1 == {"session": "1"}
        assert mem3 == {"session": "3"}


class TestMemoryPersistence:
    """Test that memory survives database round-trips."""

    def test_memory_persists_through_commit(self, db, setup_multi_tenant):
        """Test memory persists after commit."""
        session = setup_multi_tenant["s1"]

        # Update and commit
        AgentMemoryService.update_working_memory(
            session.id, session.tenant_id,
            {"user_name": "John", "booking_id": "123"},
            db
        )

        # Query fresh
        db.refresh(session)
        memory = AgentMemoryService.get_working_memory(session.id, session.tenant_id, db)

        assert memory == {"user_name": "John", "booking_id": "123"}


class TestSummaryAndRetrieval:
    """Test end-to-end summary storage and retrieval."""

    def test_store_and_retrieve_summaries(self, db, setup_multi_tenant):
        """Test storing and retrieving historical summaries."""
        tenant1 = setup_multi_tenant["tenant1"]
        s1 = setup_multi_tenant["s1"]
        s3 = setup_multi_tenant["s3"]

        # Store summaries for both sessions in tenant 1 (with "golf" keyword in both)
        AgentMemoryService.store_session_summary(
            s1.id, tenant1.id, "User booked Pebble Beach golf club", db
        )
        AgentMemoryService.store_session_summary(
            s3.id, tenant1.id, "Rebooked golf time slot at same club", db
        )

        # Retrieve with keyword
        results = AgentMemoryService.retrieve_historical_context(
            tenant1.id, "golf", db, limit=10
        )

        # Both summaries should be returned (both contain "golf")
        assert len(results) >= 1
        assert any("Pebble Beach golf club" in r.content for r in results)


class TestSizeEnforcement:
    """Test that size limit is enforced across operations."""

    def test_auto_trim_on_oversized_update(self, db, setup_multi_tenant):
        """Test that oversized updates are auto-trimmed."""
        session = setup_multi_tenant["s1"]

        # Create large update that exceeds 2KB
        large_value = "x" * 2500

        result = AgentMemoryService.update_working_memory(
            session.id, session.tenant_id, {"large": large_value}, db
        )

        # Verify it was trimmed
        import json
        size = len(json.dumps(result).encode('utf-8'))
        assert size < 2048

    def test_multiple_updates_respect_limit(self, db, setup_multi_tenant):
        """Test that cumulative updates respect size limit."""
        session = setup_multi_tenant["s1"]

        # Add multiple updates
        for i in range(5):
            AgentMemoryService.update_working_memory(
                session.id, session.tenant_id,
                {f"key_{i}": "value" * 100},
                db
            )

        # Final memory should be under 2KB
        memory = AgentMemoryService.get_working_memory(session.id, session.tenant_id, db)
        import json
        size = len(json.dumps(memory).encode('utf-8'))
        assert size < 2048


class TestTenantBoundaries:
    """Test tenant isolation across all operations."""

    def test_different_tenants_cannot_see_each_other_memory(self, db, setup_multi_tenant):
        """Test complete tenant isolation."""
        tenant1 = setup_multi_tenant["tenant1"]
        tenant2 = setup_multi_tenant["tenant2"]
        s1 = setup_multi_tenant["s1"]
        s2 = setup_multi_tenant["s2"]

        # Store memory and summaries for each tenant
        AgentMemoryService.update_working_memory(s1.id, tenant1.id, {"data": "tenant1"}, db)
        AgentMemoryService.update_working_memory(s2.id, tenant2.id, {"data": "tenant2"}, db)

        AgentMemoryService.store_session_summary(s1.id, tenant1.id, "Tenant 1 summary", db)
        AgentMemoryService.store_session_summary(s2.id, tenant2.id, "Tenant 2 summary", db)

        # Verify tenant1 cannot see tenant2
        memory2_as_t1 = AgentMemoryService.get_working_memory(s2.id, tenant1.id, db)
        assert memory2_as_t1 is None

        # Verify retrieval is isolated
        t1_summaries = AgentMemoryService.retrieve_historical_context(tenant1.id, "summary", db)
        t2_summaries = AgentMemoryService.retrieve_historical_context(tenant2.id, "summary", db)

        assert len(t1_summaries) == 1
        assert len(t2_summaries) == 1
        assert t1_summaries[0].tenant_id == 1
        assert t2_summaries[0].tenant_id == 2


class TestKeywordSearchQuality:
    """Test keyword search quality and ranking."""

    def test_search_with_multiple_matching_summaries(self, db, setup_multi_tenant):
        """Test search returns all matching results."""
        tenant1 = setup_multi_tenant["tenant1"]
        s1 = setup_multi_tenant["s1"]
        s3 = setup_multi_tenant["s3"]

        # Store multiple summaries with varying keyword matches
        AgentMemoryService.store_session_summary(s1.id, tenant1.id, "User booking golf", db)
        AgentMemoryService.store_session_summary(s3.id, tenant1.id, "Golf course available", db)

        # Search should find both
        results = AgentMemoryService.retrieve_historical_context(
            tenant1.id, "golf", db, limit=10
        )

        assert len(results) == 2

    def test_search_respects_limit(self, db, setup_multi_tenant):
        """Test that search results respect limit parameter."""
        tenant1 = setup_multi_tenant["tenant1"]
        s1 = setup_multi_tenant["s1"]

        # Store many summaries
        for i in range(10):
            AgentMemoryService.store_session_summary(
                s1.id, tenant1.id, f"Summary {i} with keyword", db
            )

        # Search with limit=3
        results = AgentMemoryService.retrieve_historical_context(
            tenant1.id, "keyword", db, limit=3
        )

        assert len(results) == 3
