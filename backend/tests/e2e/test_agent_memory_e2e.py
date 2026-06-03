"""E2E tests for agent memory workflows."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.models import Tenant, User, Session
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
def setup_e2e(db):
    """Setup for E2E test."""
    tenant = Tenant(id=1, name="Test Tenant", slug="test")
    user = User(id=1, tenant_id=1, email="user@test.com", name="User", password_hash="hash")
    session = Session(id=1, tenant_id=1, user_id=1, title="Test")
    db.add(tenant)
    db.add(user)
    db.add(session)
    db.commit()
    return {"tenant": tenant, "user": user, "session": session}


class TestMemoryWorkflow:
    """Test complete memory workflow."""

    def test_create_session_update_memory_store_summary_retrieve(self, db, setup_e2e):
        """Test end-to-end: create → update memory → store summary → retrieve."""
        session = setup_e2e["session"]

        # Update working memory during session
        mem = AgentMemoryService.update_working_memory(
            session.id, session.tenant_id,
            {"user_id": "123", "action": "booking"},
            db
        )
        assert mem == {"user_id": "123", "action": "booking"}

        # Store summary at end of session
        summary = AgentMemoryService.store_session_summary(
            session.id, session.tenant_id,
            "User successfully booked golf club Pebble Beach on June 5",
            db
        )
        assert summary.content is not None

        # Retrieve historical context (new workflow)
        results = AgentMemoryService.retrieve_historical_context(
            session.tenant_id, "Pebble Beach", db
        )
        assert len(results) >= 1
        assert any("Pebble Beach" in r.content for r in results)

    def test_multi_session_workflow_isolation(self, db):
        """Test workflow across multiple sessions."""
        # Setup two sessions in same tenant
        tenant = Tenant(id=1, name="Tenant", slug="t")
        user = User(id=1, tenant_id=1, email="u@test.com", name="U", password_hash="h")
        s1 = Session(id=1, tenant_id=1, user_id=1, title="S1")
        s2 = Session(id=2, tenant_id=1, user_id=1, title="S2")
        db.add(tenant)
        db.add(user)
        db.add(s1)
        db.add(s2)
        db.commit()

        # Session 1: Working memory + summary
        AgentMemoryService.update_working_memory(s1.id, 1, {"golf_club": "Augusta"}, db)
        AgentMemoryService.store_session_summary(s1.id, 1, "User booked Augusta National", db)

        # Session 2: New memory, same keyword in summary
        AgentMemoryService.update_working_memory(s2.id, 1, {"golf_club": "Torrey Pines"}, db)
        AgentMemoryService.store_session_summary(s2.id, 1, "User investigating golf options", db)

        # Verify separate memories
        mem1 = AgentMemoryService.get_working_memory(s1.id, 1, db)
        mem2 = AgentMemoryService.get_working_memory(s2.id, 1, db)
        assert mem1 == {"golf_club": "Augusta"}
        assert mem2 == {"golf_club": "Torrey Pines"}

        # Verify retrieval gets summaries
        results = AgentMemoryService.retrieve_historical_context(1, "golf", db, limit=10)
        assert len(results) >= 1

    def test_memory_accumulation_with_size_limit(self, db, setup_e2e):
        """Test memory accumulation respects size limit."""
        session = setup_e2e["session"]

        # Accumulate facts over workflow
        facts = [
            {"step": "1", "action": "search"},
            {"step": "2", "result": "found_clubs"},
            {"step": "3", "club": "pebble_beach"},
            {"step": "4", "date": "2026-06-15"},
            {"step": "5", "confirmation": "booking_confirmed"}
        ]

        for fact in facts:
            result = AgentMemoryService.update_working_memory(session.id, session.tenant_id, fact, db)
            # Verify never exceeds limit
            import json
            size = len(json.dumps(result).encode('utf-8'))
            assert size <= 2048

        # Final memory should contain some facts
        final = AgentMemoryService.get_working_memory(session.id, session.tenant_id, db)
        assert final is not None
        assert len(final) > 0
