import pytest
from app.services.workflow_orchestrator import WorkflowOrchestrator
from app.models.workflow import WorkflowTemplate, WorkflowRun, WorkflowRunStatus
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
