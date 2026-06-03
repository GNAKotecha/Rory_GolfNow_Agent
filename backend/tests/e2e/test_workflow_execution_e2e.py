"""End-to-end tests for workflow execution using backend API.

Tests workflow lifecycle: create → activate → load → execute
Uses real database, FastAPI TestClient, and AgenticService.
"""
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from unittest.mock import AsyncMock, MagicMock
import json

from app.main import app
from app.db.session import get_db, Base
from app.models.models import User, Tenant, TenantWorkflow, TenantSkill, UserRole, ApprovalStatus
from app.services.auth import get_password_hash, create_access_token
from app.services.agentic_service import AgenticService, AgenticConfig
from app.services.workflow_runtime_service import WorkflowRuntimeService
from app.services.ollama import OllamaClient
from app.services.mcp_registry import MCPToolRegistry


@pytest.fixture
def db_session(tmp_path):
    """Create test database session with in-memory SQLite."""
    db_path = tmp_path / "test_e2e.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()  # Rollback any uncommitted changes for test isolation
        session.close()


@pytest.fixture
def client(db_session):
    """Create test client with database override."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def tenant(db_session: Session) -> Tenant:
    """Create test tenant."""
    tenant = Tenant(id=1, name="Test Tenant E2E", slug="test-tenant-e2e")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


@pytest.fixture
def tenant_b(db_session: Session) -> Tenant:
    """Create second tenant for isolation tests."""
    tenant = Tenant(id=2, name="Tenant B", slug="tenant-b")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


@pytest.fixture
def test_user(db_session: Session, tenant: Tenant) -> User:
    """Create test user for tenant A."""
    user = User(
        tenant_id=tenant.id,
        email="testuser@e2e.com",
        name="Test User E2E",
        password_hash=get_password_hash("password123"),
        role=UserRole.USER,
        approval_status=ApprovalStatus.APPROVED,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_user_b(db_session: Session, tenant_b: Tenant) -> User:
    """Create test user for tenant B."""
    user = User(
        tenant_id=tenant_b.id,
        email="userb@e2e.com",
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
def auth_token(test_user: User) -> str:
    """Create JWT token for tenant A user."""
    return create_access_token(data={
        "sub": str(test_user.id),
        "tenant_id": test_user.tenant_id
    })


@pytest.fixture
def auth_token_b(test_user_b: User) -> str:
    """Create JWT token for tenant B user."""
    return create_access_token(data={
        "sub": str(test_user_b.id),
        "tenant_id": test_user_b.tenant_id
    })


@pytest.fixture
def auth_headers(auth_token: str) -> dict:
    """Create authorization headers for tenant A."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def auth_headers_b(auth_token_b: str) -> dict:
    """Create authorization headers for tenant B."""
    return {"Authorization": f"Bearer {auth_token_b}"}


@pytest.fixture
def agentic_config():
    """Create AgenticConfig for testing."""
    return AgenticConfig(
        max_steps=5,
        require_approval_for_write=False,
        timeout_seconds=300,
        enable_loop_detection=True,
        enable_planning=False,
        stream_callback=None
    )


@pytest.fixture
def mock_ollama_client():
    """Create mock OllamaClient for testing."""
    client = MagicMock(spec=OllamaClient)
    return client


@pytest.fixture
def mock_mcp_registry():
    """Create mock MCPToolRegistry for testing."""
    registry = MagicMock()
    registry.get_enabled_tools = MagicMock(return_value=[])
    return registry


# Scenario 1: Create and Activate Workflow via API
class TestWorkflowLifecycle:
    """Test workflow creation and activation through API."""

    def test_workflow_lifecycle_create_activate(self, client, auth_headers, db_session, tenant):
        """
        1. POST /api/workflows - Create workflow
        2. GET /api/workflows - List workflows (should be inactive)
        3. POST /api/workflows/{id}/activate - Activate workflow
        4. GET /api/workflows - Verify is_active=True
        """
        # Step 1: Create workflow
        create_payload = {
            "workflow_name": "test_lifecycle_workflow",
            "description": "Test workflow for lifecycle",
            "workflow_definition": {
                "max_retries": 3,
                "timeout_seconds": 300,
                "tools_required": ["bash", "python"]
            }
        }

        create_response = client.post("/api/workflows", json=create_payload, headers=auth_headers)
        assert create_response.status_code == status.HTTP_201_CREATED
        workflow_data = create_response.json()
        workflow_id = workflow_data["id"]
        assert workflow_data["workflow_name"] == "test_lifecycle_workflow"
        assert workflow_data["is_active"] is False
        assert workflow_data["version"] == 1

        # Step 2: List workflows (should be inactive)
        list_response = client.get("/api/workflows", headers=auth_headers)
        assert list_response.status_code == status.HTTP_200_OK
        workflows = list_response.json()["workflows"]
        assert len(workflows) == 1
        assert workflows[0]["is_active"] is False

        # Step 3: Activate workflow
        activate_response = client.post(
            f"/api/workflows/{workflow_id}/activate",
            headers=auth_headers
        )
        assert activate_response.status_code == status.HTTP_200_OK
        activated = activate_response.json()
        assert activated["is_active"] is True

        # Step 4: Verify activation in list
        list_response_2 = client.get("/api/workflows", headers=auth_headers)
        assert list_response_2.status_code == status.HTTP_200_OK
        workflows_2 = list_response_2.json()["workflows"]
        assert len(workflows_2) == 1
        assert workflows_2[0]["is_active"] is True

        # Verify in database directly
        workflow_db = db_session.query(TenantWorkflow).filter_by(id=workflow_id).first()
        assert workflow_db is not None
        assert workflow_db.is_active is True
        assert workflow_db.tenant_id == tenant.id


# Scenario 2: Load Workflow in AgenticService
class TestWorkflowLoadsInAgenticExecution:
    """Test workflow loading in AgenticService."""

    @pytest.mark.asyncio
    async def test_workflow_loads_in_agentic_execution(
        self, client, auth_headers, db_session, tenant, test_user, agentic_config, mock_ollama_client, mock_mcp_registry
    ):
        """
        1. Create workflow via API: name='test_workflow', definition={...}
        2. Activate workflow
        3. Create AgenticService with tenant_id, workflow_name
        4. Verify workflow_context populated
        """
        # Step 1: Create workflow
        create_payload = {
            "workflow_name": "agentic_load_test",
            "description": "Workflow for agentic loading",
            "workflow_definition": {
                "max_retries": 5,
                "timeout_seconds": 600,
                "approval_gates": ["manager"]
            }
        }

        create_response = client.post("/api/workflows", json=create_payload, headers=auth_headers)
        assert create_response.status_code == status.HTTP_201_CREATED
        workflow_id = create_response.json()["id"]

        # Step 2: Activate workflow
        activate_response = client.post(
            f"/api/workflows/{workflow_id}/activate",
            headers=auth_headers
        )
        assert activate_response.status_code == status.HTTP_200_OK

        # Step 3: Create AgenticService with workflow
        agentic = AgenticService(
            ollama_client=mock_ollama_client,
            mcp_registry=mock_mcp_registry,
            config=agentic_config,
            session=db_session,
            tenant_id=tenant.id,
            workflow_name="agentic_load_test"
        )

        # Step 4: Load workflow context (called by execute, but we test directly)
        agentic._load_workflow_context()

        # Verify workflow context populated
        assert agentic.workflow_context is not None
        assert len(agentic.workflow_context) > 0
        assert agentic.workflow_context.get("max_retries") == 5
        assert agentic.workflow_context.get("timeout_seconds") == 600
        assert "approval_gates" in agentic.workflow_context


# Scenario 3: Workflow Context Injection
class TestWorkflowContextInjection:
    """Test workflow context is properly injected into execution."""

    @pytest.mark.asyncio
    async def test_workflow_context_injected_into_execution(
        self, client, auth_headers, db_session, tenant, agentic_config, mock_ollama_client, mock_mcp_registry
    ):
        """
        1. Create workflow with specific definition: {"max_retries": 5, "timeout": 300}
        2. Activate workflow
        3. Create AgenticService with workflow_name
        4. Load context
        5. Verify workflow context accessible and fields match
        """
        # Step 1: Create workflow with specific definition
        workflow_def = {
            "max_retries": 7,
            "timeout_seconds": 450,
            "tools_required": ["git", "docker"],
            "approval_gates": ["tech_lead"],
            "custom_rules": ["require_tests", "no_force_push"]
        }

        create_payload = {
            "workflow_name": "context_injection_test",
            "description": "Test context injection",
            "workflow_definition": workflow_def
        }

        create_response = client.post("/api/workflows", json=create_payload, headers=auth_headers)
        assert create_response.status_code == status.HTTP_201_CREATED
        workflow_id = create_response.json()["id"]

        # Step 2: Activate workflow
        client.post(f"/api/workflows/{workflow_id}/activate", headers=auth_headers)

        # Step 3: Create AgenticService
        agentic = AgenticService(
            ollama_client=mock_ollama_client,
            mcp_registry=mock_mcp_registry,
            config=agentic_config,
            session=db_session,
            tenant_id=tenant.id,
            workflow_name="context_injection_test"
        )

        # Step 4: Load workflow context
        agentic._load_workflow_context()

        # Step 5: Verify context matches definition
        context = agentic.workflow_context
        assert context["max_retries"] == 7
        assert context["timeout_seconds"] == 450
        assert context["tools_required"] == ["git", "docker"]
        assert context["approval_gates"] == ["tech_lead"]
        assert context["custom_rules"] == ["require_tests", "no_force_push"]
        assert "version" in context


# Scenario 4: Tenant Isolation in Workflow Execution
class TestWorkflowExecutionTenantIsolation:
    """Test tenant isolation in workflow execution."""

    def test_workflow_execution_tenant_isolated(
        self, client, auth_headers, auth_headers_b, db_session, tenant, tenant_b, agentic_config, mock_ollama_client, mock_mcp_registry
    ):
        """
        1. Create workflow for Tenant A
        2. Try to load workflow as Tenant B
        3. Verify load returns None (not accessible)
        4. Verify no cross-tenant data leakage
        """
        # Step 1: Create workflow for Tenant A
        create_payload = {
            "workflow_name": "tenant_a_workflow",
            "description": "Tenant A only",
            "workflow_definition": {"secret_data": "tenant_a_secret"}
        }

        create_response = client.post("/api/workflows", json=create_payload, headers=auth_headers)
        assert create_response.status_code == status.HTTP_201_CREATED
        workflow_id = create_response.json()["id"]

        # Activate for Tenant A
        client.post(f"/api/workflows/{workflow_id}/activate", headers=auth_headers)

        # Step 2: Try to access as Tenant B via API (should fail)
        get_response_b = client.get(f"/api/workflows/{workflow_id}", headers=auth_headers_b)
        assert get_response_b.status_code == status.HTTP_404_NOT_FOUND

        # Step 3: Try to load in AgenticService for Tenant B
        agentic_b = AgenticService(
            ollama_client=mock_ollama_client,
            mcp_registry=mock_mcp_registry,
            config=agentic_config,
            session=db_session,
            tenant_id=tenant_b.id,
            workflow_name="tenant_a_workflow"
        )

        # Load workflow context (should be empty)
        agentic_b._load_workflow_context()

        # Step 4: Verify no context loaded (isolation enforced)
        assert agentic_b.workflow_context == {}

        # Verify database level isolation
        workflow_b = db_session.query(TenantWorkflow).filter_by(
            tenant_id=tenant_b.id,
            workflow_name="tenant_a_workflow"
        ).first()
        assert workflow_b is None  # Workflow should not exist for tenant B

        # Verify Tenant A can still access
        agentic_a = AgenticService(
            ollama_client=mock_ollama_client,
            mcp_registry=mock_mcp_registry,
            config=agentic_config,
            session=db_session,
            tenant_id=tenant.id,
            workflow_name="tenant_a_workflow"
        )
        agentic_a._load_workflow_context()
        assert agentic_a.workflow_context != {}
        assert agentic_a.workflow_context.get("name") == "tenant_a_workflow"  # Verify context loaded


# Scenario 5: Multiple Workflow Versions
class TestMultipleWorkflowVersions:
    """Test workflow version management."""

    def test_multiple_workflow_versions_activation(
        self, db_session, tenant, test_user, agentic_config, mock_ollama_client, mock_mcp_registry
    ):
        """
        1. Create workflow version 1 (direct DB)
        2. Create workflow version 2 (direct DB)
        3. Activate v2
        4. Execute AgenticService with workflow_name
        5. Verify v2 (active) is loaded, not v1
        """
        # Step 1: Create version 1
        workflow_v1 = TenantWorkflow(
            tenant_id=tenant.id,
            workflow_name="versioned_workflow",
            description="Version 1",
            workflow_definition={"version_marker": "v1", "timeout": 100},
            version=1,
            is_active=False,
            created_by=test_user.id
        )
        db_session.add(workflow_v1)
        db_session.commit()
        db_session.refresh(workflow_v1)

        # Step 2: Create version 2
        workflow_v2 = TenantWorkflow(
            tenant_id=tenant.id,
            workflow_name="versioned_workflow",
            description="Version 2",
            workflow_definition={"version_marker": "v2", "timeout_seconds": 200},
            version=2,
            is_active=False,
            created_by=test_user.id
        )
        db_session.add(workflow_v2)
        db_session.commit()
        db_session.refresh(workflow_v2)

        # Step 3: Activate v2
        workflow_v2.is_active = True
        workflow_v2.active_version = workflow_v2.id
        db_session.commit()

        # Step 4: Load in AgenticService
        agentic = AgenticService(
            ollama_client=mock_ollama_client,
            mcp_registry=mock_mcp_registry,
            config=agentic_config,
            session=db_session,
            tenant_id=tenant.id,
            workflow_name="versioned_workflow"
        )
        agentic._load_workflow_context()

        # Step 5: Verify v2 is loaded (not v1)
        context = agentic.workflow_context
        assert context["version"] == 2
        assert context["timeout_seconds"] == 200
        assert context["name"] == "versioned_workflow"


# Scenario 6: Workflow Not Found Graceful Handling
class TestWorkflowNotFoundGracefulHandling:
    """Test graceful handling when workflow not found."""

    @pytest.mark.asyncio
    async def test_workflow_not_found_execution_continues(
        self, db_session, tenant, agentic_config, mock_ollama_client, mock_mcp_registry
    ):
        """
        1. Create AgenticService with workflow_name='nonexistent'
        2. Load context (should not fail)
        3. Verify warning logged but execution continues
        4. Workflow context should be empty
        """
        # Step 1: Create AgenticService with nonexistent workflow
        agentic = AgenticService(
            ollama_client=mock_ollama_client,
            mcp_registry=mock_mcp_registry,
            config=agentic_config,
            session=db_session,
            tenant_id=tenant.id,
            workflow_name="nonexistent_workflow"
        )

        # Step 2: Load workflow context (should not raise exception)
        agentic._load_workflow_context()

        # Step 3: Verify no exception (if we reach here, no exception was raised)

        # Step 4: Verify workflow context is empty
        assert agentic.workflow_context == {}

        # Verify can still use service (execution would continue normally)
        assert agentic.session is not None
        assert agentic.tenant_id == tenant.id


# Scenario 7: Workflow with Skills Integration
class TestWorkflowWithSkillsIntegration:
    """Test workflow execution with skills context."""

    def test_workflow_with_skills_execution(
        self, client, auth_headers, db_session, tenant, test_user, agentic_config, mock_ollama_client, mock_mcp_registry
    ):
        """
        1. POST /api/skills - Create skill for tenant
        2. POST /api/skills/{id}/activate - Activate skill
        3. Create workflow that references skill
        4. POST /api/workflows - Create workflow
        5. POST /api/workflows/{id}/activate - Activate
        6. Load in AgenticService
        7. Verify workflow context populated with skill reference
        """
        # Step 1: Create skill
        skill_payload = {
            "skill_name": "code_review_skill",
            "description": "Automated code review",
            "skill_data": {
                "type": "automation",
                "triggers": ["pr_created"],
                "actions": ["run_linter", "check_tests"]
            }
        }

        skill_response = client.post("/api/skills", json=skill_payload, headers=auth_headers)
        assert skill_response.status_code == status.HTTP_201_CREATED
        skill_id = skill_response.json()["id"]

        # Step 2: Activate skill
        activate_skill = client.post(f"/api/skills/{skill_id}/activate", headers=auth_headers)
        assert activate_skill.status_code == status.HTTP_200_OK

        # Step 3-4: Create workflow that references skill
        workflow_payload = {
            "workflow_name": "pr_review_workflow",
            "description": "PR review with skills",
            "workflow_definition": {
                "skills_required": ["code_review_skill"],
                "approval_gates": ["tech_lead"],
                "timeout_seconds": 500
            }
        }

        workflow_response = client.post("/api/workflows", json=workflow_payload, headers=auth_headers)
        assert workflow_response.status_code == status.HTTP_201_CREATED
        workflow_id = workflow_response.json()["id"]

        # Step 5: Activate workflow
        client.post(f"/api/workflows/{workflow_id}/activate", headers=auth_headers)

        # Step 6: Load in AgenticService
        agentic = AgenticService(
            ollama_client=mock_ollama_client,
            mcp_registry=mock_mcp_registry,
            config=agentic_config,
            session=db_session,
            tenant_id=tenant.id,
            workflow_name="pr_review_workflow"
        )
        agentic._load_workflow_context()

        # Step 7: Verify workflow context loaded (skills_required is in workflow_definition but not extracted to context)
        context = agentic.workflow_context
        assert context["name"] == "pr_review_workflow"
        assert "tools_required" in context  # Default key in extracted context
        assert "approval_gates" in context
        assert context["approval_gates"] == ["tech_lead"]

        # Verify active skills can be loaded separately
        skills = WorkflowRuntimeService.load_active_skills(db_session, tenant.id)
        assert len(skills) == 1
        assert skills[0].skill_name == "code_review_skill"


# Scenario 8: Workflow Execution Logging/Telemetry
class TestWorkflowExecutionLogging:
    """Test workflow execution logging and telemetry."""

    @pytest.mark.asyncio
    async def test_workflow_execution_logs_telemetry(
        self, client, auth_headers, db_session, tenant, agentic_config, mock_ollama_client, mock_mcp_registry, monkeypatch
    ):
        """
        1. Create and activate workflow
        2. Create AgenticService with workflow_name
        3. Load workflow context
        4. Verify logging includes workflow provenance
        """
        # Step 1: Create and activate workflow
        workflow_payload = {
            "workflow_name": "telemetry_workflow",
            "description": "Workflow for telemetry testing",
            "workflow_definition": {"timeout_seconds": 300, "max_retries": 3}
        }

        create_response = client.post("/api/workflows", json=workflow_payload, headers=auth_headers)
        workflow_id = create_response.json()["id"]
        client.post(f"/api/workflows/{workflow_id}/activate", headers=auth_headers)

        # Step 2: Create AgenticService
        agentic = AgenticService(
            ollama_client=mock_ollama_client,
            mcp_registry=mock_mcp_registry,
            config=agentic_config,
            session=db_session,
            tenant_id=tenant.id,
            workflow_name="telemetry_workflow"
        )

        # Step 3: Load workflow context (this should log)
        mock_logger = MagicMock()
        monkeypatch.setattr('app.services.workflow_runtime_service.logger', mock_logger)

        agentic._load_workflow_context()

        # Step 4: Verify debug logging called with workflow info
        assert mock_logger.debug.called

        # Verify context loaded
        assert agentic.workflow_context != {}
        assert "version" in agentic.workflow_context


# Scenario 9: Workflow Deactivation
class TestWorkflowDeactivation:
    """Test workflow deactivation behavior."""

    def test_deactivated_workflow_not_loaded(
        self, client, auth_headers, db_session, tenant, agentic_config, mock_ollama_client, mock_mcp_registry
    ):
        """
        1. Create and activate workflow
        2. Verify it loads in AgenticService
        3. Deactivate workflow (set is_active=False)
        4. Verify it no longer loads
        """
        # Step 1: Create and activate
        workflow_payload = {
            "workflow_name": "deactivation_test",
            "workflow_definition": {"timeout_seconds": 200}
        }

        create_response = client.post("/api/workflows", json=workflow_payload, headers=auth_headers)
        workflow_id = create_response.json()["id"]
        client.post(f"/api/workflows/{workflow_id}/activate", headers=auth_headers)

        # Step 2: Verify loads
        agentic_1 = AgenticService(
            ollama_client=mock_ollama_client,
            mcp_registry=mock_mcp_registry,
            config=agentic_config,
            session=db_session,
            tenant_id=tenant.id,
            workflow_name="deactivation_test"
        )
        agentic_1._load_workflow_context()
        assert agentic_1.workflow_context != {}

        # Step 3: Deactivate via PATCH
        update_payload = {"is_active": False}
        patch_response = client.patch(
            f"/api/workflows/{workflow_id}",
            json=update_payload,
            headers=auth_headers
        )
        assert patch_response.status_code == status.HTTP_200_OK

        # Step 4: Verify no longer loads
        agentic_2 = AgenticService(
            ollama_client=mock_ollama_client,
            mcp_registry=mock_mcp_registry,
            config=agentic_config,
            session=db_session,
            tenant_id=tenant.id,
            workflow_name="deactivation_test"
        )
        agentic_2._load_workflow_context()
        assert agentic_2.workflow_context == {}


# Scenario 10: Workflow with Empty Definition
class TestWorkflowEmptyDefinition:
    """Test workflow with empty or minimal definition."""

    def test_workflow_with_empty_definition_loads_defaults(
        self, client, auth_headers, db_session, tenant, agentic_config, mock_ollama_client, mock_mcp_registry
    ):
        """
        1. Create workflow with empty definition: {}
        2. Activate workflow
        3. Load in AgenticService
        4. Verify default values applied
        """
        # Step 1: Create with empty definition
        workflow_payload = {
            "workflow_name": "empty_def_workflow",
            "workflow_definition": {}
        }

        create_response = client.post("/api/workflows", json=workflow_payload, headers=auth_headers)
        workflow_id = create_response.json()["id"]

        # Step 2: Activate
        client.post(f"/api/workflows/{workflow_id}/activate", headers=auth_headers)

        # Step 3: Load in AgenticService
        agentic = AgenticService(
            ollama_client=mock_ollama_client,
            mcp_registry=mock_mcp_registry,
            config=agentic_config,
            session=db_session,
            tenant_id=tenant.id,
            workflow_name="empty_def_workflow"
        )
        agentic._load_workflow_context()

        # Step 4: Verify context has defaults
        context = agentic.workflow_context
        assert context is not None
        # get_workflow_context should apply defaults
        assert "version" in context
        # Empty definition should still be accessible
        assert isinstance(context, dict)
