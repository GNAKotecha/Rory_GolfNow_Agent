import pytest
import asyncio
from app.services.workflow_orchestrator import WorkflowOrchestrator
from app.models.workflow import WorkflowTemplate, WorkflowRun, WorkflowRunStatus, WorkflowStepExecution, StepStatus
from app.models.models import WorkflowCategory


def test_load_workflow_template(db_session, workflow_template_fixture):
    """Test loading workflow template by name."""
    orchestrator = WorkflowOrchestrator(db_session)

    template = orchestrator.load_template("test_template")

    assert template is not None
    assert template.name == "test_template"
    assert template.workflow_category == WorkflowCategory.WORKFLOW


def test_load_nonexistent_template(db_session):
    """Test loading non-existent template raises error."""
    orchestrator = WorkflowOrchestrator(db_session)

    with pytest.raises(ValueError, match="Template not found"):
        orchestrator.load_template("nonexistent")


def test_create_workflow_run(db_session, workflow_template_fixture):
    """Test creating a new workflow run."""
    orchestrator = WorkflowOrchestrator(db_session)

    # Create user and session for test
    from app.models.models import User, Session as DBSession
    user = User(email="test@example.com", name="Test User", password_hash="hashed_password")
    db_session.add(user)
    db_session.commit()

    session = DBSession(user_id=user.id)
    db_session.add(session)
    db_session.commit()

    # Create workflow run
    workflow_run = orchestrator.create_workflow_run(
        template_name="test_template",
        session_id=session.id,
        input_data={"club_name": "Test Club"}
    )

    assert workflow_run.id is not None
    assert workflow_run.template_id == workflow_template_fixture.id
    assert workflow_run.session_id == session.id
    assert workflow_run.status == WorkflowRunStatus.PENDING
    assert workflow_run.current_state == {"input_data": {"club_name": "Test Club"}}
    assert workflow_run.template.workflow_category == WorkflowCategory.WORKFLOW


def test_build_graph_from_simple_template(db_session):
    """Test building LangGraph from simple linear workflow."""
    template = WorkflowTemplate(
        name="simple_workflow",
        version="1.0.0",
        workflow_category=WorkflowCategory.WORKFLOW,
        definition={
            "entry_point": "step1",
            "steps": [
                {
                    "id": "step1",
                    "name": "First Step",
                    "type": "tool_call",
                    "config": {"tool": "test_tool"},
                    "next": ["step2"]
                },
                {
                    "id": "step2",
                    "name": "Second Step",
                    "type": "tool_call",
                    "config": {"tool": "test_tool2"},
                    "next": []
                }
            ]
        }
    )
    db_session.add(template)
    db_session.commit()

    orchestrator = WorkflowOrchestrator(db_session)
    graph = orchestrator.build_graph_from_template(template)

    # Verify graph is compiled
    assert graph is not None
    assert hasattr(graph, 'invoke')


def test_build_graph_with_dependencies(db_session):
    """Test building graph with step dependencies."""
    template = WorkflowTemplate(
        name="dependency_workflow",
        version="1.0.0",
        workflow_category=WorkflowCategory.WORKFLOW,
        definition={
            "entry_point": "step1",
            "steps": [
                {
                    "id": "step1",
                    "name": "Init",
                    "type": "tool_call",
                    "config": {},
                    "dependencies": [],
                    "next": ["step2", "step3"]
                },
                {
                    "id": "step2",
                    "name": "Branch A",
                    "type": "tool_call",
                    "config": {},
                    "dependencies": ["step1"],
                    "next": []
                },
                {
                    "id": "step3",
                    "name": "Branch B",
                    "type": "tool_call",
                    "config": {},
                    "dependencies": ["step1"],
                    "next": []
                }
            ]
        }
    )
    db_session.add(template)
    db_session.commit()

    orchestrator = WorkflowOrchestrator(db_session)
    graph = orchestrator.build_graph_from_template(template)

    assert graph is not None


@pytest.mark.asyncio
async def test_execute_simple_graph(db_session):
    """Test executing a simple workflow graph."""
    from app.services.workflow_orchestrator import WorkflowState

    template = WorkflowTemplate(
        name="executable_workflow",
        version="1.0.0",
        workflow_category=WorkflowCategory.WORKFLOW,
        definition={
            "entry_point": "step1",
            "steps": [
                {
                    "id": "step1",
                    "name": "Test Step",
                    "type": "tool_call",
                    "config": {},
                    "next": []
                }
            ]
        }
    )
    db_session.add(template)
    db_session.commit()

    orchestrator = WorkflowOrchestrator(db_session)
    graph = orchestrator.build_graph_from_template(template)

    # Execute graph with new state structure - now async
    initial_state = {"step_results": {}, "workflow_run_id": 1}
    result = await graph.ainvoke(initial_state)

    # Verify execution - results are in the step_results field
    assert result["step_results"]["step1_status"] == "completed"
    assert "step1_output" in result["step_results"]


def test_build_graph_validates_missing_steps(db_session):
    """Test validation catches missing steps field."""
    template = WorkflowTemplate(
        name="invalid_workflow",
        version="1.0.0",
        workflow_category=WorkflowCategory.WORKFLOW,
        definition={"entry_point": "step1"}  # Missing steps
    )
    db_session.add(template)
    db_session.commit()

    orchestrator = WorkflowOrchestrator(db_session)

    with pytest.raises(ValueError, match="must contain 'steps' field"):
        orchestrator.build_graph_from_template(template)


def test_build_graph_validates_duplicate_step_ids(db_session):
    """Test validation catches duplicate step IDs."""
    template = WorkflowTemplate(
        name="invalid_workflow",
        version="1.0.0",
        workflow_category=WorkflowCategory.WORKFLOW,
        definition={
            "steps": [
                {"id": "step1", "name": "Step 1", "type": "tool_call", "config": {}, "next": []},
                {"id": "step1", "name": "Duplicate", "type": "tool_call", "config": {}, "next": []}
            ]
        }
    )
    db_session.add(template)
    db_session.commit()

    orchestrator = WorkflowOrchestrator(db_session)

    with pytest.raises(ValueError, match="Step IDs must be unique"):
        orchestrator.build_graph_from_template(template)


def test_build_graph_validates_invalid_next_step(db_session):
    """Test validation catches invalid next step references."""
    template = WorkflowTemplate(
        name="invalid_workflow",
        version="1.0.0",
        workflow_category=WorkflowCategory.WORKFLOW,
        definition={
            "steps": [
                {"id": "step1", "name": "Step 1", "type": "tool_call", "config": {}, "next": ["nonexistent"]}
            ]
        }
    )
    db_session.add(template)
    db_session.commit()

    orchestrator = WorkflowOrchestrator(db_session)

    with pytest.raises(ValueError, match="references unknown next step"):
        orchestrator.build_graph_from_template(template)


def test_build_graph_validates_invalid_entry_point(db_session):
    """Test validation catches invalid entry point."""
    template = WorkflowTemplate(
        name="invalid_workflow",
        version="1.0.0",
        workflow_category=WorkflowCategory.WORKFLOW,
        definition={
            "entry_point": "nonexistent",
            "steps": [
                {"id": "step1", "name": "Step 1", "type": "tool_call", "config": {}, "next": []}
            ]
        }
    )
    db_session.add(template)
    db_session.commit()

    orchestrator = WorkflowOrchestrator(db_session)

    with pytest.raises(ValueError, match="Entry point .* is not a valid step ID"):
        orchestrator.build_graph_from_template(template)


@pytest.mark.asyncio
async def test_execute_workflow_with_metrics(db_session, workflow_run_fixture):
    """Test executing workflow and collecting metrics."""
    # Update fixture template with valid definition
    template = workflow_run_fixture.template
    template.definition = {
        "entry_point": "step1",
        "steps": [
            {
                "id": "step1",
                "name": "Test Step",
                "type": "tool_call",
                "config": {"tool": "mock_tool"},
                "next": []
            }
        ]
    }
    db_session.commit()

    orchestrator = WorkflowOrchestrator(db_session)

    # Execute workflow
    result = await orchestrator.execute_workflow(workflow_run_fixture.id)

    # Verify workflow run updated
    db_session.refresh(workflow_run_fixture)
    assert workflow_run_fixture.status == WorkflowRunStatus.COMPLETED

    # Verify step execution created
    steps = db_session.query(WorkflowStepExecution).filter_by(
        workflow_run_id=workflow_run_fixture.id
    ).all()
    assert len(steps) == 1
    assert steps[0].step_id == "step1"
    assert steps[0].status == StepStatus.COMPLETED

    # Verify metrics collected
    from app.models.metrics import StepMetrics
    metrics = db_session.query(StepMetrics).filter_by(
        workflow_run_id=workflow_run_fixture.id
    ).all()
    assert len(metrics) == 1
    assert metrics[0].status == StepStatus.COMPLETED
    assert metrics[0].started_at is not None
    assert metrics[0].completed_at is not None
