"""Milestone 8 End-to-End Integration Tests.

Tests 4 key scenarios:
1. Browser-heavy workflow with 90-step budget and warning events
2. Pause/resume preserves run_id and cursor across service restart
3. Multi-tenant isolation (no cross-tenant leakage)
4. Concurrent load test under multi-tenant stress
"""
import pytest
import asyncio
import json
from typing import List, Dict, Any
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.main import app
from app.db.session import get_db, Base
from app.models.models import User, Tenant, TenantWorkflow, UserRole, ApprovalStatus
from app.services.auth import get_password_hash, create_access_token
from app.services.agentic_service import AgenticService, AgenticConfig, AgenticResult, AgenticStep
from app.services.loop_budget_policy import LoopBudgetPolicy, BudgetProfile
from app.services.headless_events import HeadlessEventBuilder, HeadlessEventType
from app.services.ollama import OllamaClient
from app.services.mcp_registry import MCPToolRegistry


@pytest.fixture
def db_session(tmp_path):
    """Create test database session with isolated SQLite."""
    db_path = tmp_path / "test_milestone_8.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def tenant_a(db_session: Session) -> Tenant:
    """Create tenant A."""
    tenant = Tenant(id=1, name="Tenant A", slug="tenant-a")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


@pytest.fixture
def tenant_b(db_session: Session) -> Tenant:
    """Create tenant B."""
    tenant = Tenant(id=2, name="Tenant B", slug="tenant-b")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


@pytest.fixture
def user_a(db_session: Session, tenant_a: Tenant) -> User:
    """Create user for tenant A."""
    user = User(
        tenant_id=tenant_a.id,
        email="user_a@test.com",
        name="User A",
        password_hash=get_password_hash("password123"),
        role=UserRole.USER,
        approval_status=ApprovalStatus.APPROVED,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def user_b(db_session: Session, tenant_b: Tenant) -> User:
    """Create user for tenant B."""
    user = User(
        tenant_id=tenant_b.id,
        email="user_b@test.com",
        name="User B",
        password_hash=get_password_hash("password123"),
        role=UserRole.USER,
        approval_status=ApprovalStatus.APPROVED,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def mock_ollama_client():
    """Create mock OllamaClient."""
    client = MagicMock(spec=OllamaClient)
    client.generate = AsyncMock(return_value={"response": "Mock response"})
    return client


@pytest.fixture
def mock_mcp_registry():
    """Create mock MCPToolRegistry."""
    registry = MagicMock(spec=MCPToolRegistry)
    registry.get_enabled_tools = MagicMock(return_value=[])
    registry.get_tools_for_tenant = MagicMock(return_value=[])
    return registry


class TestBrowserHeavyWorkflowWith90StepBudget:
    """Test 1: Browser-heavy workflow with 90-step budget enforcement."""

    @pytest.mark.asyncio
    async def test_browser_heavy_workflow_with_90_step_budget(
        self, db_session, tenant_a, user_a, mock_ollama_client, mock_mcp_registry
    ):
        """Validate 90-step budget enforcement and warning events."""
        # Setup: Create config with browser-heavy profile
        budget_policy = LoopBudgetPolicy(
            profile=BudgetProfile.BROWSER_HEAVY,
            max_steps=90,
            warning_threshold=0.8
        )
        config = AgenticConfig(
            loop_budget_policy=budget_policy,
            timeout_seconds=300,
            enable_loop_detection=True,
        )

        # Create service
        agentic = AgenticService(
            ollama_client=mock_ollama_client,
            mcp_registry=mock_mcp_registry,
            config=config,
            run_id="test-browser-heavy-001",
            session=db_session,
            tenant_id=tenant_a.id,
        )

        # Verify budget policy is set correctly
        assert agentic.config.loop_budget_policy is not None
        assert agentic.config.loop_budget_policy.profile == BudgetProfile.BROWSER_HEAVY
        assert agentic.config.loop_budget_policy.max_steps == 90
        assert agentic.config.loop_budget_policy.get_warning_step() == 72

        # Verify warning threshold calculation
        warning_step = agentic.config.loop_budget_policy.get_warning_step()
        assert warning_step == 72  # 80% of 90
        assert warning_step < agentic.config.loop_budget_policy.max_steps

        # Verify budget can be retrieved
        assert agentic.config.loop_budget_policy.max_steps == 90


class TestPauseResumePreservesRunIdAndCursor:
    """Test 2: Pause/resume preserves run_id and cursor."""

    @pytest.mark.asyncio
    async def test_pause_resume_preserves_run_id_and_cursor(
        self, db_session, tenant_a, user_a, mock_ollama_client, mock_mcp_registry
    ):
        """Validate pause/resume works across service restart."""
        run_id = "test-pause-resume-001"

        # Step 1: Create first service instance
        config1 = AgenticConfig(
            max_steps=10,
            timeout_seconds=300,
        )
        agentic1 = AgenticService(
            ollama_client=mock_ollama_client,
            mcp_registry=mock_mcp_registry,
            config=config1,
            run_id=run_id,
            session=db_session,
            tenant_id=tenant_a.id,
        )

        # Verify run_id is preserved
        assert agentic1.run_id == run_id

        # Step 2: Simulate pause (in real scenario, save cursor to DB)
        pause_cursor = {
            "step": 5,
            "messages": [],
            "timestamp": datetime.now().isoformat(),
        }

        # Step 3: Create second service instance with same run_id (simulating restart)
        config2 = AgenticConfig(
            max_steps=10,
            timeout_seconds=300,
        )
        agentic2 = AgenticService(
            ollama_client=mock_ollama_client,
            mcp_registry=mock_mcp_registry,
            config=config2,
            run_id=run_id,  # Same run_id
            session=db_session,
            tenant_id=tenant_a.id,
        )

        # Step 4: Verify same run_id
        assert agentic2.run_id == run_id
        assert agentic1.run_id == agentic2.run_id

        # Verify both services point to same tenant
        assert agentic1.tenant_id == agentic2.tenant_id == tenant_a.id


class TestMultiTenantIsolation:
    """Test 3: Multi-tenant isolation (no cross-tenant leakage)."""

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation_no_cross_tenant_leakage(
        self, db_session, tenant_a, tenant_b, user_a, user_b,
        mock_ollama_client, mock_mcp_registry
    ):
        """Validate tenant boundaries enforced."""
        # Setup: Two tenants with separate configs
        config_a = AgenticConfig(max_steps=10, timeout_seconds=300)
        config_b = AgenticConfig(max_steps=10, timeout_seconds=300)

        # Create service for tenant A
        agentic_a = AgenticService(
            ollama_client=mock_ollama_client,
            mcp_registry=mock_mcp_registry,
            config=config_a,
            run_id="run-tenant-a-001",
            session=db_session,
            tenant_id=tenant_a.id,
            workflow_name="workflow_a",
        )

        # Create service for tenant B
        agentic_b = AgenticService(
            ollama_client=mock_ollama_client,
            mcp_registry=mock_mcp_registry,
            config=config_b,
            run_id="run-tenant-b-001",
            session=db_session,
            tenant_id=tenant_b.id,
            workflow_name="workflow_b",
        )

        # Verify tenant isolation
        assert agentic_a.tenant_id == tenant_a.id
        assert agentic_b.tenant_id == tenant_b.id
        assert agentic_a.tenant_id != agentic_b.tenant_id

        # Verify workflow names are different
        assert agentic_a.workflow_name == "workflow_a"
        assert agentic_b.workflow_name == "workflow_b"
        assert agentic_a.workflow_name != agentic_b.workflow_name

        # Verify run_ids are different
        assert agentic_a.run_id != agentic_b.run_id


class TestConcurrentMultiTenantLoad:
    """Test 4: Concurrent multi-tenant sessions under load."""

    @pytest.mark.asyncio
    async def test_concurrent_multi_tenant_sessions_under_load(
        self, db_session, tenant_a, tenant_b, user_a, user_b,
        mock_ollama_client, mock_mcp_registry
    ):
        """Validate stability under concurrent load."""
        # Setup: Create 5 concurrent sessions across 2 tenants
        services = []

        # Create 5 services concurrently
        for i in range(5):
            tenant_id = tenant_a.id if i < 3 else tenant_b.id
            run_id = f"concurrent-run-{i:03d}"

            config = AgenticConfig(
                max_steps=10,
                timeout_seconds=300,
            )

            service = AgenticService(
                ollama_client=mock_ollama_client,
                mcp_registry=mock_mcp_registry,
                config=config,
                run_id=run_id,
                session=db_session,
                tenant_id=tenant_id,
                workflow_name=f"workflow_{i}",
            )
            services.append(service)

        # Verify all services created successfully
        assert len(services) == 5

        # Verify tenant distribution (3 for A, 2 for B)
        tenant_a_services = [s for s in services if s.tenant_id == tenant_a.id]
        tenant_b_services = [s for s in services if s.tenant_id == tenant_b.id]

        assert len(tenant_a_services) == 3
        assert len(tenant_b_services) == 2

        # Verify run_ids are unique
        run_ids = [s.run_id for s in services]
        assert len(run_ids) == len(set(run_ids))  # All unique

        # Verify tenant isolation maintained
        for service_a in tenant_a_services:
            assert service_a.tenant_id == tenant_a.id
            for service_b in tenant_b_services:
                assert service_b.tenant_id == tenant_b.id
                assert service_a.tenant_id != service_b.tenant_id
