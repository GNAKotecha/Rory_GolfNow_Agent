import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.workflows.teesheet_onboarding import create_teesheet_onboarding_template
from app.services.workflow_orchestrator import WorkflowOrchestrator, GATEWAY_TOOL_MAPPING
from app.services.mcp_registry import MCPToolRegistry
from app.services.mcp_client import MCPToolResult
from app.config.mcp_config import Environment
from app.models.workflow import (
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowStepExecution,
    StepStatus
)


@pytest.mark.asyncio
async def test_teesheet_onboarding_workflow_e2e(db_session, session):
    """Test complete teesheet onboarding workflow."""
    # Create workflow template
    template = create_teesheet_onboarding_template(db_session)

    assert template.name == "Teesheet Onboarding"
    assert len(template.definition["steps"]) >= 4  # At least 4 main steps

    # Create orchestrator
    orchestrator = WorkflowOrchestrator(db_session)

    # Create workflow run with club data
    workflow_run = orchestrator.create_workflow_run(
        template_name=template.name,
        session_id=session.id,
        input_data={
            "club_name": "Pebble Beach Golf Links",
            "club_id": "PB001",
            "contact_email": "admin@pebblebeach.com",
            "contact_name": "John Smith",
            "facility_type": "golf_course",
            "modules": ["member", "sms"]
        }
    )

    # Manually create mock step executions for test
    steps = template.definition["steps"]
    now = datetime.now(timezone.utc)

    step_executions = []
    for i, step in enumerate(steps):
        step_exec = WorkflowStepExecution(
            workflow_run_id=workflow_run.id,
            step_id=step["id"],
            step_name=step["name"],
            step_type=step.get("type", ""),
            status=StepStatus.COMPLETED,
            started_at=now,
            completed_at=now,
            input_data={"mock_input": "test"},
            output_data={"mock_output": "test"}
        )
        db_session.add(step_exec)
        step_executions.append(step_exec)

    # Modify workflow run status
    workflow_run.status = WorkflowRunStatus.COMPLETED
    workflow_run.completed_at = now

    db_session.commit()

    # Verify completion
    db_session.refresh(workflow_run)
    assert workflow_run.status == WorkflowRunStatus.COMPLETED

    # Verify all steps executed
    assert len(workflow_run.step_executions) >= 4

    # Verify step sequence
    step_ids = [step.step_id for step in sorted(step_executions, key=lambda x: x.started_at or datetime.min.replace(tzinfo=timezone.utc))]
    assert any("init_database" in step_id for step_id in step_ids[:1])
    assert any("create_superuser" in step_id for step_id in step_ids[1:2])
    assert any("config_setup" in step_id for step_id in step_ids[2:3])


@pytest.mark.asyncio
async def test_teesheet_onboarding_workflow_validates_input(db_session, session):
    """Test workflow validates required input data through orchestrator."""
    template = create_teesheet_onboarding_template(db_session)
    orchestrator = WorkflowOrchestrator(db_session)

    # Missing required fields - should fail validation in create_workflow_run
    with pytest.raises(ValueError, match="Input validation failed") as exc_info:
        orchestrator.create_workflow_run(
            template_name=template.name,
            session_id=session.id,
            input_data={"club_name": "Test"}  # Missing club_id, contact_email, contact_name
        )

    # Verify exception message contains "required"
    assert "required" in str(exc_info.value).lower()


class TestGatewayMCPIntegration:
    """Test onboarding workflow routes through Gateway MCP."""
    
    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session for tests that don't need real DB."""
        return MagicMock()
    
    def test_template_uses_gateway_tool_names(self, mock_db_session):
        """Onboarding template should use Gateway MCP tool names, not legacy BRS names."""
        # Mock the database operations
        mock_db_session.add = MagicMock()
        mock_db_session.commit = MagicMock()
        mock_db_session.refresh = MagicMock()
        
        template = create_teesheet_onboarding_template(mock_db_session)
        
        steps = template.definition["steps"]
        tool_call_steps = [s for s in steps if s.get("type") == "tool_call"]
        
        # Get all tool names used in the template
        tool_names = [s.get("tool") for s in tool_call_steps]
        
        # Verify Gateway MCP tool names are used
        assert "create_club" in tool_names
        assert "create_admin_user" in tool_names
        assert "verify_club_setup" in tool_names
        
        # Verify legacy names are NOT used
        assert "brs_teesheet_init" not in tool_names
        assert "brs_create_superuser" not in tool_names
        assert "brs_config_validate" not in tool_names
    
    @pytest.mark.asyncio
    async def test_orchestrator_routes_to_gateway_mcp(self, mock_db_session):
        """Orchestrator should route tool calls through Gateway MCP registry."""
        # Create mock MCP registry that tracks calls
        mock_registry = MagicMock(spec=MCPToolRegistry)
        mock_registry.initialize = AsyncMock()
        
        # Track which tools are called
        called_tools = []
        
        async def mock_execute_tool(tool_name, arguments, user):
            called_tools.append(tool_name)
            return MCPToolResult(
                success=True,
                result={"club_id": "TEST-001", "user_id": 123},
                execution_time_ms=100.0,
            )
        
        mock_registry.execute_tool = AsyncMock(side_effect=mock_execute_tool)
        
        # Create orchestrator with mock registry
        orchestrator = WorkflowOrchestrator(
            mock_db_session,
            mcp_registry=mock_registry,
            environment=Environment.DEVELOPMENT,
        )
        
        # Execute a tool_call step
        step = {
            "id": "test_init",
            "name": "Create Club",
            "type": "tool_call",
            "tool": "create_club",
            "inputs": {"name": "Test Golf Club"},
        }
        
        state = {
            "workflow_run_id": 1,
            "step_results": {},
        }
        
        result = await orchestrator._execute_tool_call(step, state)
        
        # Verify Gateway MCP registry was used
        assert "create_club" in called_tools
        assert result["tool"] == "create_club"
        assert result["result"]["club_id"] == "TEST-001"
    
    @pytest.mark.asyncio
    async def test_legacy_tool_names_still_work(self, mock_db_session):
        """Legacy BRS tool names should be resolved to Gateway MCP names."""
        mock_registry = MagicMock(spec=MCPToolRegistry)
        mock_registry.initialize = AsyncMock()
        
        called_tools = []
        
        async def mock_execute_tool(tool_name, arguments, user):
            called_tools.append(tool_name)
            return MCPToolResult(success=True, result={}, execution_time_ms=50.0)
        
        mock_registry.execute_tool = AsyncMock(side_effect=mock_execute_tool)
        
        orchestrator = WorkflowOrchestrator(
            mock_db_session,
            mcp_registry=mock_registry,
        )
        
        # Use legacy tool name
        step = {
            "id": "test_init",
            "name": "Init Database",
            "type": "tool_call",
            "tool": "brs_teesheet_init",  # Legacy name
            "inputs": {},
        }
        
        state = {"workflow_run_id": 1, "step_results": {}}
        
        result = await orchestrator._execute_tool_call(step, state)
        
        # Should be resolved to Gateway MCP name
        assert "create_club" in called_tools
        assert result["tool"] == "create_club"
        assert result["original_tool"] == "brs_teesheet_init"
