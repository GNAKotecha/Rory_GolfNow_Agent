import pytest
from datetime import datetime
from app.models.workflow import (
    WorkflowTemplate,
    WorkflowRun,
    WorkflowStepExecution,
    WorkflowRunStatus,
    StepStatus
)
from app.models.models import WorkflowCategory


def test_workflow_template_creation(db_session):
    """Test creating a workflow template."""
    template = WorkflowTemplate(
        name="test_onboarding",
        description="Test onboarding workflow",
        version="1.0.0",
        workflow_category=WorkflowCategory.WORKFLOW,
        definition={
            "steps": [
                {
                    "id": "step1",
                    "name": "Initialize",
                    "type": "tool_call",
                    "config": {"tool": "init_db"}
                }
            ],
            "entry_point": "step1"
        }
    )

    db_session.add(template)
    db_session.commit()

    assert template.id is not None
    assert template.name == "test_onboarding"
    assert template.workflow_category == WorkflowCategory.WORKFLOW
    assert "steps" in template.definition


def test_workflow_template_unique_name(db_session):
    """Test workflow template name uniqueness constraint."""
    template1 = WorkflowTemplate(
        name="duplicate_name",
        version="1.0.0",
        workflow_category=WorkflowCategory.WORKFLOW,
        definition={"steps": []}
    )
    db_session.add(template1)
    db_session.commit()

    template2 = WorkflowTemplate(
        name="duplicate_name",
        version="2.0.0",
        workflow_category=WorkflowCategory.WORKFLOW,
        definition={"steps": []}
    )
    db_session.add(template2)

    with pytest.raises(Exception):  # IntegrityError
        db_session.commit()
