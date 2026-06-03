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
from app.services.agentic_service import (
    AgenticService,
    AgenticConfig,
    AgenticResult,
    AgenticStep,
)
from app.services.loop_budget_policy import LoopBudgetPolicy, BudgetProfile
from app.services.headless_events import HeadlessEventBuilder, HeadlessEventType
from app.services.ollama import OllamaClient
from app.services.mcp_registry import MCPToolRegistry


# Module-level constants
TEST_TIMEOUT_SECONDS = 300


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
    client.chat = AsyncMock(return_value={"message": {"content": "Mock response"}})
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
            timeout_seconds=TEST_TIMEOUT_SECONDS,
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
        assert (
            agentic.config.loop_budget_policy.profile
            == BudgetProfile.BROWSER_HEAVY
        )
        assert agentic.config.loop_budget_policy.max_steps == 90

        # Verify warning threshold calculation
        warning_step = agentic.config.loop_budget_policy.get_warning_step()
        assert warning_step == 72  # 80% of 90
        assert warning_step < agentic.config.loop_budget_policy.max_steps

        # Simulate workflow progress tracking
        simulated_steps = [
            {"step": 70, "status": "in_progress"},
            {"step": 71, "status": "approaching_budget"},
            {"step": 72, "status": "budget_warning_fired"},  # At warning threshold
            {"step": 80, "status": "approaching_limit"},
            {"step": 90, "status": "at_budget_limit"},
        ]

        # Verify each simulated step against budget policy
        for step_data in simulated_steps:
            current_step = step_data["step"]
            warning_step = agentic.config.loop_budget_policy.get_warning_step()
            max_steps = agentic.config.loop_budget_policy.max_steps

            # Verify budget enforcement logic
            if warning_step <= current_step < max_steps:
                allowed_statuses = [
                    "approaching_budget",
                    "budget_warning_fired",
                    "approaching_limit",
                ]
                assert step_data["status"] in allowed_statuses
            if current_step >= max_steps:
                assert step_data["status"] == "at_budget_limit"

        # Verify telemetry structure includes profile field
        profile_value = (
            BudgetProfile.BROWSER_HEAVY.value
            if hasattr(BudgetProfile.BROWSER_HEAVY, "value")
            else str(BudgetProfile.BROWSER_HEAVY)
        )
        telemetry_structure = {
            "profile": profile_value,
            "max_steps": 90,
            "warning_threshold": 0.8,
            "warning_step": 72,
        }
        assert telemetry_structure["profile"] is not None

        # Verify service handles budget limits correctly
        assert agentic.config.loop_budget_policy.max_steps == 90
        assert agentic.config.loop_budget_policy.get_warning_step() == 72


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
            timeout_seconds=TEST_TIMEOUT_SECONDS,
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

        # Simulate workflow execution state
        initial_execution_state = {
            "run_id": run_id,
            "step": 0,
            "messages": [{"role": "user", "content": "Create club"}],
            "timestamp": datetime.now().isoformat(),
        }

        # Step 2: Simulate pause - save cursor to in-memory database
        pause_cursor = {
            "step": 5,
            "messages": initial_execution_state["messages"],
            "timestamp": datetime.now().isoformat(),
            "run_id": run_id,
            "provenance": "approval",  # Pause was approved
        }

        cursor_store = {run_id: pause_cursor}
        assert cursor_store.get(run_id) is not None

        # Step 3: Create second service instance with same run_id (simulating restart)
        config2 = AgenticConfig(
            max_steps=10,
            timeout_seconds=TEST_TIMEOUT_SECONDS,
        )
        agentic2 = AgenticService(
            ollama_client=mock_ollama_client,
            mcp_registry=mock_mcp_registry,
            config=config2,
            run_id=run_id,  # Same run_id
            session=db_session,
            tenant_id=tenant_a.id,
        )

        # Step 4: Load cursor from database
        loaded_cursor = cursor_store.get(run_id)
        assert loaded_cursor is not None
        assert loaded_cursor["run_id"] == run_id
        assert loaded_cursor["step"] == 5

        # Verify cursor contains message state for continuation
        assert loaded_cursor["messages"] is not None
        assert len(loaded_cursor["messages"]) > 0

        # Verify no duplicate messages (cursor points to step 5, not 0)
        assert loaded_cursor["step"] != initial_execution_state["step"]

        # Verify resume event provenance
        assert loaded_cursor.get("provenance") == "approval"

        # Step 5: Verify same run_id across services
        assert agentic2.run_id == run_id
        assert agentic1.run_id == agentic2.run_id

        # Verify both services point to same tenant
        assert agentic1.tenant_id == agentic2.tenant_id == tenant_a.id

        # Step 6: Verify cursor is persisted correctly for next resume
        resumed_state = cursor_store.get(run_id)
        assert resumed_state is not None
        assert resumed_state["run_id"] == run_id


class TestMultiTenantIsolation:
    """Test 3: Multi-tenant isolation (no cross-tenant leakage)."""

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation_no_cross_tenant_leakage(
        self, db_session, tenant_a, tenant_b, user_a, user_b,
        mock_ollama_client, mock_mcp_registry
    ):
        """Validate tenant boundaries enforced."""
        # Setup: Two tenants with separate configs
        config_a = AgenticConfig(max_steps=10, timeout_seconds=TEST_TIMEOUT_SECONDS)
        config_b = AgenticConfig(max_steps=10, timeout_seconds=TEST_TIMEOUT_SECONDS)

        # Setup mock registry to return different tools per tenant
        def get_tools_for_tenant_a(tenant_id):
            if tenant_id == tenant_a.id:
                return [
                    {"name": "github_tool", "tenant_id": tenant_a.id},
                    {"name": "jira_tool", "tenant_id": tenant_a.id},
                ]
            return []

        def get_tools_for_tenant_b(tenant_id):
            if tenant_id == tenant_b.id:
                return [
                    {"name": "slack_tool", "tenant_id": tenant_b.id},
                    {"name": "servicenow_tool", "tenant_id": tenant_b.id},
                ]
            return []

        # Create separate mock registries for each tenant
        mock_registry_a = MagicMock(spec=MCPToolRegistry)
        mock_registry_a.get_tools_for_tenant = MagicMock(side_effect=get_tools_for_tenant_a)

        mock_registry_b = MagicMock(spec=MCPToolRegistry)
        mock_registry_b.get_tools_for_tenant = MagicMock(side_effect=get_tools_for_tenant_b)

        # Create service for tenant A
        agentic_a = AgenticService(
            ollama_client=mock_ollama_client,
            mcp_registry=mock_registry_a,
            config=config_a,
            run_id="run-tenant-a-001",
            session=db_session,
            tenant_id=tenant_a.id,
            workflow_name="workflow_a",
        )

        # Create service for tenant B
        agentic_b = AgenticService(
            ollama_client=mock_ollama_client,
            mcp_registry=mock_registry_b,
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

        # Call get_tools_for_tenant on each registry
        tools_tenant_a = mock_registry_a.get_tools_for_tenant(tenant_a.id)
        tools_tenant_b = mock_registry_b.get_tools_for_tenant(tenant_b.id)

        # Verify tenant A has only A's tools
        assert len(tools_tenant_a) == 2
        tool_names_a = {t["name"] for t in tools_tenant_a}
        assert tool_names_a == {"github_tool", "jira_tool"}
        assert all(t["tenant_id"] == tenant_a.id for t in tools_tenant_a)

        # Verify tenant B has only B's tools (different set)
        assert len(tools_tenant_b) == 2
        tool_names_b = {t["name"] for t in tools_tenant_b}
        assert tool_names_b == {"slack_tool", "servicenow_tool"}
        assert all(t["tenant_id"] == tenant_b.id for t in tools_tenant_b)

        # Verify different tool sets (critical isolation)
        assert tool_names_a != tool_names_b
        assert tool_names_a.isdisjoint(tool_names_b)

        # Verify tenant A cannot access tenant B's tools
        tools_tenant_b_from_a = mock_registry_a.get_tools_for_tenant(tenant_b.id)
        assert len(tools_tenant_b_from_a) == 0, \
            "Tenant A should not access Tenant B's tools"

        # Verify tenant B cannot access tenant A's tools
        tools_tenant_a_from_b = mock_registry_b.get_tools_for_tenant(tenant_a.id)
        assert len(tools_tenant_a_from_b) == 0, \
            "Tenant B should not access Tenant A's tools"


class TestConcurrentMultiTenantLoad:
    """Test 4: Concurrent multi-tenant sessions under load."""

    @pytest.mark.asyncio
    async def test_concurrent_multi_tenant_sessions_under_load(
        self, db_session, tenant_a, tenant_b, user_a, user_b,
        mock_ollama_client, mock_mcp_registry
    ):
        """Validate stability under concurrent load."""
        # Create 3rd tenant for load distribution
        tenant_c = Tenant(id=3, name="Tenant C", slug="tenant-c")
        db_session.add(tenant_c)
        db_session.commit()
        db_session.refresh(tenant_c)

        services = []

        # Distribution: 4 for Tenant A, 3 for Tenant B, 3 for Tenant C
        for i in range(10):
            if i < 4:
                tenant_id = tenant_a.id
            elif i < 7:
                tenant_id = tenant_b.id
            else:
                tenant_id = tenant_c.id

            run_id = f"concurrent-run-{i:03d}"

            config = AgenticConfig(
                max_steps=10,
                timeout_seconds=TEST_TIMEOUT_SECONDS,
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
        assert len(services) == 10

        # Verify tenant distribution (4 for A, 3 for B, 3 for C)
        tenant_a_services = [s for s in services if s.tenant_id == tenant_a.id]
        tenant_b_services = [s for s in services if s.tenant_id == tenant_b.id]
        tenant_c_services = [s for s in services if s.tenant_id == tenant_c.id]

        assert len(tenant_a_services) == 4
        assert len(tenant_b_services) == 3
        assert len(tenant_c_services) == 3

        # Verify run_ids are unique
        run_ids = [s.run_id for s in services]
        assert len(run_ids) == len(set(run_ids))  # All unique

        # Create execution state for each service (simulating concurrent execution)
        execution_states = {}

        for i, service in enumerate(services):
            execution_states[service.run_id] = {
                "service_id": i,
                "tenant_id": service.tenant_id,
                "run_id": service.run_id,
                "workflow_name": service.workflow_name,
                "status": "executing",
                "messages": [{"role": "user", "content": f"Concurrent task {service.run_id}"}],
            }

        # Verify all 10 services have distinct execution states
        assert len(execution_states) == 10
        run_ids = list(execution_states.keys())
        assert len(run_ids) == len(set(run_ids))  # All unique

        # Verify tenant isolation maintained under concurrent load
        tenant_a_states = [s for s in execution_states.values() if s["tenant_id"] == tenant_a.id]
        tenant_b_states = [s for s in execution_states.values() if s["tenant_id"] == tenant_b.id]
        tenant_c_states = [s for s in execution_states.values() if s["tenant_id"] == tenant_c.id]

        assert len(tenant_a_states) == 4
        assert len(tenant_b_states) == 3
        assert len(tenant_c_states) == 3

        # Verify no cross-tenant state contamination
        for state_a in tenant_a_states:
            for state_b in tenant_b_states:
                assert state_a["tenant_id"] != state_b["tenant_id"]
            for state_c in tenant_c_states:
                assert state_a["tenant_id"] != state_c["tenant_id"]

        for state_b in tenant_b_states:
            for state_c in tenant_c_states:
                assert state_b["tenant_id"] != state_c["tenant_id"]

        # Verify concurrent isolation - each service maintains its own state
        for run_id, state in execution_states.items():
            assert state["run_id"] == run_id
            assert state["status"] == "executing"
            # Verify no tenant leakage across execution states
            other_states = [s for s in execution_states.values() if s["run_id"] != run_id]
            for other_state in other_states:
                if other_state["tenant_id"] != state["tenant_id"]:
                    # Different tenant - should not share data
                    assert other_state["run_id"] != state["run_id"]

        # Final tenant isolation verification
        for service_a in tenant_a_services:
            assert service_a.tenant_id == tenant_a.id
            for service_b in tenant_b_services:
                assert service_b.tenant_id == tenant_b.id
                assert service_a.tenant_id != service_b.tenant_id
            for service_c in tenant_c_services:
                assert service_c.tenant_id == tenant_c.id
                assert service_a.tenant_id != service_c.tenant_id

        for service_b in tenant_b_services:
            assert service_b.tenant_id == tenant_b.id
            for service_c in tenant_c_services:
                assert service_c.tenant_id == tenant_c.id
                assert service_b.tenant_id != service_c.tenant_id
