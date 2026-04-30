import pytest
from datetime import datetime
from app.schemas.workflow import (
    WorkflowTemplateCreate,
    WorkflowTemplateResponse,
    WorkflowRunCreate,
    WorkflowRunResponse
)
from app.models.models import WorkflowCategory


def test_workflow_template_create_schema():
    """Test creating workflow template schema."""
    data = {
        "name": "test_workflow",
        "description": "Test workflow",
        "version": "1.0.0",
        "workflow_category": "WORKFLOW",
        "definition": {
            "entry_point": "step1",
            "steps": [
                {"id": "step1", "name": "Test", "type": "tool_call", "config": {}, "next": []}
            ]
        }
    }

    schema = WorkflowTemplateCreate(**data)
    assert schema.name == "test_workflow"
    assert schema.workflow_category == "WORKFLOW"
    assert "steps" in schema.definition


def test_workflow_run_create_schema():
    """Test creating workflow run schema."""
    data = {
        "template_name": "test_workflow",
        "session_id": 1,
        "input_data": {"club_name": "Test Club"}
    }

    schema = WorkflowRunCreate(**data)
    assert schema.template_name == "test_workflow"
    assert schema.input_data["club_name"] == "Test Club"
