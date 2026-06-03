"""Integration test: Agent calling retrieve_historical_context tool."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.models import Tenant, User, Session, SessionMemorySummary
from app.services.simple_tools import SimpleTool


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
def test_setup(db):
    """Setup tenant, user, session, and historical data."""
    tenant = Tenant(id=1, name="Test Tenant", slug="test-tenant")
    user = User(id=1, tenant_id=1, email="test@example.com", name="Test User", password_hash="hash")
    db.add(tenant)
    db.add(user)
    db.commit()

    session = Session(
        id=1,
        tenant_id=tenant.id,
        user_id=user.id,
        title="Test Session",
        session_working_memory={}
    )
    db.add(session)
    db.commit()

    # Add historical context
    for i in range(3):
        summary = SessionMemorySummary(
            tenant_id=tenant.id,
            session_id=i + 1,
            content=f"Session {i+1}: Club setup workflow for member {i+1}"
        )
        db.add(summary)
    db.commit()

    return {"tenant": tenant, "user": user, "session": session, "db": db}


class TestAgentHistoricalContextIntegration:
    """Integration tests for agent calling retrieve_historical_context."""

    def test_agent_tool_callable_from_definitions(self):
        """Verify tool is in definitions that agent receives."""
        tool = SimpleTool()
        definitions = tool.get_tool_definitions()
        tool_names = [d["function"]["name"] for d in definitions]

        assert "retrieve_historical_context" in tool_names
        assert "store_memory" in tool_names
        assert "retrieve_memory" in tool_names

    def test_agent_can_execute_retrieve_historical_context(self, test_setup):
        """Verify agent can call retrieve_historical_context tool."""
        setup = test_setup

        tool = SimpleTool()
        tool.set_context(
            db_session=setup["db"],
            tenant_id=setup["tenant"].id,
            session_id=setup["session"].id
        )

        # Simulate agent calling the tool
        import asyncio
        result = asyncio.run(tool.execute_tool(
            "retrieve_historical_context",
            {"query": "club setup"}
        ))

        assert result["success"] is True
        assert "Club setup workflow" in result["result"]
        assert "[1]" in result["result"]
        assert "[2]" in result["result"]
        assert "[3]" in result["result"]

    def test_agent_retrieves_relevant_context_only(self, test_setup):
        """Verify agent gets contextual results matching query."""
        setup = test_setup
        db = setup["db"]

        # Add more summaries with different content
        summary = SessionMemorySummary(
            tenant_id=setup["tenant"].id,
            session_id=10,
            content="Session 10: Tee time booking for visitor"
        )
        db.add(summary)
        db.commit()

        tool = SimpleTool()
        tool.set_context(
            db_session=db,
            tenant_id=setup["tenant"].id,
            session_id=setup["session"].id
        )

        import asyncio

        # Query for club setup
        result_club = asyncio.run(tool.execute_tool(
            "retrieve_historical_context",
            {"query": "club"}
        ))
        assert "club" in result_club["result"].lower()

        # Query for booking
        result_booking = asyncio.run(tool.execute_tool(
            "retrieve_historical_context",
            {"query": "booking"}
        ))
        assert "booking" in result_booking["result"].lower()

    def test_agent_respects_limit_parameter(self, test_setup):
        """Verify agent limit parameter is respected."""
        setup = test_setup
        db = setup["db"]

        # Add many summaries
        for i in range(10):
            summary = SessionMemorySummary(
                tenant_id=setup["tenant"].id,
                session_id=i + 20,
                content=f"Session {i+20}: Important context about booking"
            )
            db.add(summary)
        db.commit()

        tool = SimpleTool()
        tool.set_context(
            db_session=db,
            tenant_id=setup["tenant"].id,
            session_id=setup["session"].id
        )

        import asyncio
        result = asyncio.run(tool.execute_tool(
            "retrieve_historical_context",
            {"query": "booking", "limit": 2}
        ))

        assert result["success"] is True
        assert "[1]" in result["result"]
        assert "[2]" in result["result"]
        assert "[3]" not in result["result"]

    def test_agent_gets_formatted_output(self, test_setup):
        """Verify agent receives properly formatted output."""
        setup = test_setup

        tool = SimpleTool()
        tool.set_context(
            db_session=setup["db"],
            tenant_id=setup["tenant"].id,
            session_id=setup["session"].id
        )

        import asyncio
        result = asyncio.run(tool.execute_tool(
            "retrieve_historical_context",
            {"query": "workflow"}
        ))

        assert result["success"] is True
        # Verify formatting includes numbering and session info
        assert "[1]" in result["result"]
        assert "Session" in result["result"]
        assert ":" in result["result"]  # Format: [N] (Session X, timestamp): content
