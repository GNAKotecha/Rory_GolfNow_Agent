"""Fixtures for workflow testing."""
from datetime import datetime, timezone

import pytest

from app.models.models import User, Session, UserRole
from app.models.workflow import WorkflowTemplate, WorkflowRun, WorkflowRunStatus


@pytest.fixture
def workflow_template_fixture(db_session):
    """Create a test workflow template."""
    template = WorkflowTemplate(
        name="test_workflow",
        description="Test workflow for fixtures",
        definition={
            "steps": [
                {"name": "research", "type": "research"},
                {"name": "analysis", "type": "analysis"},
            ]
        },
        version="1.0.0",
        is_active=True,
    )
    db_session.add(template)
    db_session.commit()
    db_session.refresh(template)
    return template


@pytest.fixture
def workflow_run_fixture(db_session, workflow_template_fixture):
    """Create a test workflow run with user and session."""
    # Create user
    user = User(
        username="test_user",
        email="test@example.com",
        hashed_password="hashed_password_123",
        role=UserRole.USER,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    # Create session
    session = Session(
        user_id=user.id,
        title="Test Session",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    # Create workflow run
    workflow_run = WorkflowRun(
        workflow_template_id=workflow_template_fixture.id,
        session_id=session.id,
        status=WorkflowRunStatus.RUNNING,
        input_data={"query": "test query"},
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(workflow_run)
    db_session.commit()
    db_session.refresh(workflow_run)

    return workflow_run
