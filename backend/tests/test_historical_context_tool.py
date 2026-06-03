"""Tests for retrieve_historical_context tool in SimpleTool."""
import pytest
import asyncio
from datetime import datetime
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


@pytest.fixture
def simple_tool_with_context(db, test_session):
    """Create SimpleTool with database context."""
    tool = SimpleTool()
    tool.set_context(
        db_session=db,
        tenant_id=test_session.tenant_id,
        session_id=test_session.id
    )
    return tool


class TestRetrieveHistoricalContextTool:
    """Test retrieve_historical_context tool in SimpleTool."""

    def test_tool_definition_exists(self):
        """Test that tool definition is in the catalog."""
        definitions = SimpleTool.get_tool_definitions()
        tool_names = [d["function"]["name"] for d in definitions]
        assert "retrieve_historical_context" in tool_names

    def test_tool_definition_structure(self):
        """Test that tool definition has correct structure."""
        definitions = SimpleTool.get_tool_definitions()
        tool_def = next(d for d in definitions if d["function"]["name"] == "retrieve_historical_context")
        assert tool_def["type"] == "function"
        assert "description" in tool_def["function"]
        assert "parameters" in tool_def["function"]

    def test_retrieve_no_matches(self, db, simple_tool_with_context):
        """Test retrieving when no historical context matches."""
        result = asyncio.run(simple_tool_with_context.execute_tool(
            "retrieve_historical_context",
            {"query": "nonexistent_keyword"}
        ))
        assert result["success"] is True
        assert "No historical context found" in result["result"]

    def test_retrieve_with_matches(self, db, test_session, simple_tool_with_context):
        """Test retrieving historical context with matching summaries."""
        summary1 = SessionMemorySummary(
            tenant_id=test_session.tenant_id,
            session_id=1,
            content="Club setup workflow completed for member John Doe"
        )
        summary2 = SessionMemorySummary(
            tenant_id=test_session.tenant_id,
            session_id=2,
            content="Member booking created for Lara Brown"
        )
        db.add(summary1)
        db.add(summary2)
        db.commit()

        result = asyncio.run(simple_tool_with_context.execute_tool(
            "retrieve_historical_context",
            {"query": "member"}
        ))
        assert result["success"] is True
        assert "[1]" in result["result"]
        assert "[2]" in result["result"]

    def test_retrieve_tenant_isolation(self, db, tenant_and_user, simple_tool_with_context):
        """Test that tenant isolation is enforced."""
        tenant2 = Tenant(id=2, name="Other Tenant", slug="other-tenant")
        user2 = User(id=2, tenant_id=2, email="other@example.com", name="Other User", password_hash="hash")
        db.add(tenant2)
        db.add(user2)
        db.commit()

        session2 = Session(
            id=2,
            tenant_id=tenant2.id,
            user_id=user2.id,
            title="Other Session",
            session_working_memory={}
        )
        db.add(session2)
        db.commit()

        summary = SessionMemorySummary(
            tenant_id=tenant2.id,
            session_id=2,
            content="Secret club setup data"
        )
        db.add(summary)
        db.commit()

        result = asyncio.run(simple_tool_with_context.execute_tool(
            "retrieve_historical_context",
            {"query": "Secret"}
        ))
        assert result["success"] is True
        assert "No historical context found" in result["result"]

    def test_retrieve_limit_parameter(self, db, test_session, simple_tool_with_context):
        """Test that limit parameter works correctly."""
        for i in range(10):
            summary = SessionMemorySummary(
                tenant_id=test_session.tenant_id,
                session_id=i + 1,
                content=f"Session {i + 1}: Important booking data"
            )
            db.add(summary)
        db.commit()

        result = asyncio.run(simple_tool_with_context.execute_tool(
            "retrieve_historical_context",
            {"query": "booking", "limit": 3}
        ))
        assert result["success"] is True
        assert "[1]" in result["result"]
        assert "[2]" in result["result"]
        assert "[3]" in result["result"]

    def test_retrieve_missing_context(self):
        """Test that tool returns error when context is not set."""
        tool = SimpleTool()
        result = asyncio.run(tool.execute_tool(
            "retrieve_historical_context",
            {"query": "test"}
        ))
        assert result["success"] is False
        assert "requires database session" in result["error"]

    def test_context_setting(self, db, test_session):
        """Test that context can be set and used."""
        tool = SimpleTool()
        assert tool._db_session is None
        tool.set_context(
            db_session=db,
            tenant_id=test_session.tenant_id,
            session_id=test_session.id
        )
        assert tool._db_session is db
        assert tool._tenant_id == test_session.tenant_id
        assert tool._session_id == test_session.id
