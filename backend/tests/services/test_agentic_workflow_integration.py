"""Integration test for AgenticService with workflow runtime."""
import pytest
from unittest.mock import Mock, AsyncMock
from sqlalchemy.orm import Session

from app.services.agentic_service import AgenticService, AgenticConfig
from app.services.workflow_runtime_service import WorkflowRuntimeService
from app.models.models import Tenant, TenantWorkflow, User, UserRole


class TestAgenticServiceWorkflowIntegration:
    """Test AgenticService integration with workflow runtime."""

    def test_agentic_service_instantiation_without_workflow(self):
        """Test AgenticService can be instantiated without workflow parameters (backward compatibility)."""
        mock_ollama = Mock()
        mock_registry = Mock()
        config = AgenticConfig()

        service = AgenticService(
            ollama_client=mock_ollama,
            mcp_registry=mock_registry,
            config=config
        )

        assert service.session is None
        assert service.tenant_id is None
        assert service.workflow_name is None
        assert service.workflow_context == {}
        assert service.skills_context == {}

    def test_agentic_service_instantiation_with_workflow_params(self, db_session: Session):
        """Test AgenticService can be instantiated with workflow parameters."""
        mock_ollama = Mock()
        mock_registry = Mock()
        config = AgenticConfig()

        service = AgenticService(
            ollama_client=mock_ollama,
            mcp_registry=mock_registry,
            config=config,
            session=db_session,
            tenant_id=1,
            workflow_name="test_workflow"
        )

        assert service.session == db_session
        assert service.tenant_id == 1
        assert service.workflow_name == "test_workflow"
        assert service.workflow_context == {}  # Not loaded yet
        assert service.skills_context == {}

    def test_load_workflow_context_with_no_params(self):
        """Test _load_workflow_context does nothing when params not provided."""
        mock_ollama = Mock()
        mock_registry = Mock()
        config = AgenticConfig()

        service = AgenticService(
            ollama_client=mock_ollama,
            mcp_registry=mock_registry,
            config=config
        )

        # Should not raise any errors
        service._load_workflow_context()

        assert service.workflow_context == {}

    def test_load_workflow_context_with_active_workflow(self, db_session: Session):
        """Test _load_workflow_context loads active workflow."""
        # Create tenant
        tenant = Tenant(name="Test Tenant", slug="test-tenant")
        db_session.add(tenant)
        db_session.commit()

        # Create active workflow
        workflow = TenantWorkflow(
            tenant_id=tenant.id,
            workflow_name="test_workflow",
            description="Test workflow",
            workflow_definition={
                "approval_gates": ["manager"],
                "tools_required": ["github"],
                "max_retries": 5,
                "timeout_seconds": 600
            },
            version=1,
            is_active=True
        )
        db_session.add(workflow)
        db_session.commit()

        # Create service with workflow params
        mock_ollama = Mock()
        mock_registry = Mock()
        config = AgenticConfig()

        service = AgenticService(
            ollama_client=mock_ollama,
            mcp_registry=mock_registry,
            config=config,
            session=db_session,
            tenant_id=tenant.id,
            workflow_name="test_workflow"
        )

        # Load workflow context
        service._load_workflow_context()

        # Verify context was loaded
        assert service.workflow_context != {}
        assert service.workflow_context["name"] == "test_workflow"
        assert service.workflow_context["version"] == 1
        assert service.workflow_context["approval_gates"] == ["manager"]
        assert service.workflow_context["tools_required"] == ["github"]
        assert service.workflow_context["max_retries"] == 5
        assert service.workflow_context["timeout_seconds"] == 600

    def test_load_workflow_context_with_missing_workflow(self, db_session: Session, caplog):
        """Test _load_workflow_context handles missing workflow gracefully."""
        import logging
        caplog.set_level(logging.WARNING)

        # Create tenant (but no workflow)
        tenant = Tenant(name="Test Tenant", slug="test-tenant")
        db_session.add(tenant)
        db_session.commit()

        # Create service with workflow params
        mock_ollama = Mock()
        mock_registry = Mock()
        config = AgenticConfig()

        service = AgenticService(
            ollama_client=mock_ollama,
            mcp_registry=mock_registry,
            config=config,
            session=db_session,
            tenant_id=tenant.id,
            workflow_name="nonexistent_workflow"
        )

        # Load workflow context
        service._load_workflow_context()

        # Verify warning was logged
        assert any("Workflow not found" in record.message for record in caplog.records)

        # Verify context is empty
        assert service.workflow_context == {}

    def test_load_workflow_context_tenant_isolation(self, db_session: Session):
        """Test _load_workflow_context enforces tenant isolation."""
        # Create two tenants
        tenant1 = Tenant(name="Tenant 1", slug="tenant-1")
        tenant2 = Tenant(name="Tenant 2", slug="tenant-2")
        db_session.add_all([tenant1, tenant2])
        db_session.commit()

        # Create workflow for tenant1
        workflow = TenantWorkflow(
            tenant_id=tenant1.id,
            workflow_name="tenant1_workflow",
            description="Tenant 1 workflow",
            workflow_definition={"test": "data"},
            version=1,
            is_active=True
        )
        db_session.add(workflow)
        db_session.commit()

        # Try to load tenant1's workflow using tenant2's ID
        mock_ollama = Mock()
        mock_registry = Mock()
        config = AgenticConfig()

        service = AgenticService(
            ollama_client=mock_ollama,
            mcp_registry=mock_registry,
            config=config,
            session=db_session,
            tenant_id=tenant2.id,
            workflow_name="tenant1_workflow"
        )

        service._load_workflow_context()

        # Should not load the workflow (tenant isolation)
        assert service.workflow_context == {}


@pytest.mark.asyncio
async def test_workflow_loads_during_async_execute():
    """
    CRITICAL TEST: Verify that _load_workflow_context() is called during async execute()
    and that workflow context is properly initialized.

    This test verifies workflow loading happens at runtime during execute(),
    not just during service instantiation.
    """
    # Create in-memory database session
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.session import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db_session = SessionLocal()

    try:
        # Setup: Create tenant, workflow, user
        tenant = Tenant(name="Test Tenant", slug="test-tenant")
        db_session.add(tenant)
        db_session.commit()

        # Create active workflow with all fields
        workflow = TenantWorkflow(
            tenant_id=tenant.id,
            workflow_name="test_workflow",
            description="Test workflow for async execution",
            workflow_definition={
                "approval_gates": ["manager", "admin"],
                "tools_required": ["github", "jira"],
                "max_retries": 5,
                "timeout_seconds": 600,
                "custom_rules": {"rule1": "value1"}
            },
            version=1,
            is_active=True
        )
        db_session.add(workflow)
        db_session.commit()

        # Create test user
        user = User(
            email="test@example.com",
            full_name="Test User",
            tenant_id=tenant.id,
            role=UserRole.ADMIN
        )
        db_session.add(user)
        db_session.commit()

        # Mock Ollama client to return text response (no tool calls)
        mock_ollama = AsyncMock()
        mock_ollama.generate_chat_completion_with_tools = AsyncMock(
            return_value={
                "type": "text",
                "content": "Workflow loaded successfully"
            }
        )

        # Mock MCP registry
        mock_registry = AsyncMock()
        mock_registry.create_run_catalog = AsyncMock()
        mock_registry.get_available_tools = Mock(return_value=[])

        # Create config
        config = AgenticConfig(
            use_tool_catalog=False,  # Disable catalog to simplify test
            use_enhanced_catalog=False,
        )

        # Create service with workflow parameters
        service = AgenticService(
            ollama_client=mock_ollama,
            mcp_registry=mock_registry,
            config=config,
            session=db_session,
            tenant_id=tenant.id,
            workflow_name="test_workflow"
        )

        # Verify workflow_context is empty before execute
        assert service.workflow_context == {}

        # Mock WorkflowRuntimeService.log_workflow_execution to avoid logging issues
        with patch.object(
            WorkflowRuntimeService,
            'log_workflow_execution',
            return_value=None
        ):
            # Action: Call execute() with minimal messages
            result = await service.execute(
                messages=[{"role": "user", "content": "Test message"}],
                user=user,
                session_id=1,
                model="test-model"
            )

        # Assert: Verify workflow context was loaded during execute
        assert service.workflow_context != {}
        assert service.workflow_context["name"] == "test_workflow"
        assert service.workflow_context["version"] == 1
        assert service.workflow_context["approval_gates"] == ["manager", "admin"]
        assert service.workflow_context["tools_required"] == ["github", "jira"]
        assert service.workflow_context["max_retries"] == 5
        assert service.workflow_context["timeout_seconds"] == 600
        assert service.workflow_context["custom_rules"] == {"rule1": "value1"}

        # Verify execute completed successfully
        assert result.stopped_reason == "completed"
        assert result.final_response == "Workflow loaded successfully"
    finally:
        db_session.close()
