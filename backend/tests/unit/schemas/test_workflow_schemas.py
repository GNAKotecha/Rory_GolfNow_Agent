import pytest
from datetime import datetime
from pydantic import ValidationError
from app.schemas.workflow import (
    WorkflowTemplateCreate,
    WorkflowTemplateResponse,
    WorkflowRunCreate,
    WorkflowRunResponse,
    WorkflowStepExecutionResponse
)
from app.models.models import WorkflowCategory


def test_workflow_template_create_schema():
    """Test creating workflow template schema."""
    data = {
        "name": "test_workflow",
        "description": "Test workflow",
        "version": "1.0.0",
        "workflow_category": WorkflowCategory.WORKFLOW,
        "definition": {
            "entry_point": "step1",
            "steps": [
                {"id": "step1", "name": "Test", "type": "tool_call", "config": {}, "next": []}
            ]
        }
    }

    schema = WorkflowTemplateCreate(**data)
    assert schema.name == "test_workflow"
    assert schema.workflow_category == WorkflowCategory.WORKFLOW
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


# Negative-path validation tests
def test_workflow_template_create_invalid_version():
    """Test that invalid version format is rejected."""
    data = {
        "name": "test_workflow",
        "version": "1.0",  # Invalid: should be X.Y.Z
        "workflow_category": WorkflowCategory.WORKFLOW,
        "definition": {"entry_point": "step1", "steps": []}
    }

    with pytest.raises(ValidationError) as exc_info:
        WorkflowTemplateCreate(**data)
    assert "version" in str(exc_info.value)


def test_workflow_template_create_invalid_category():
    """Test that invalid workflow category is rejected."""
    data = {
        "name": "test_workflow",
        "version": "1.0.0",
        "workflow_category": "INVALID_CATEGORY",
        "definition": {"entry_point": "step1", "steps": []}
    }

    with pytest.raises(ValidationError) as exc_info:
        WorkflowTemplateCreate(**data)
    assert "workflow_category" in str(exc_info.value)


def test_workflow_template_create_empty_name():
    """Test that empty name is rejected."""
    data = {
        "name": "",
        "version": "1.0.0",
        "workflow_category": WorkflowCategory.WORKFLOW,
        "definition": {"entry_point": "step1", "steps": []}
    }

    with pytest.raises(ValidationError) as exc_info:
        WorkflowTemplateCreate(**data)
    assert "name" in str(exc_info.value)


def test_workflow_template_create_name_too_long():
    """Test that name exceeding 255 characters is rejected."""
    data = {
        "name": "a" * 256,
        "version": "1.0.0",
        "workflow_category": WorkflowCategory.WORKFLOW,
        "definition": {"entry_point": "step1", "steps": []}
    }

    with pytest.raises(ValidationError) as exc_info:
        WorkflowTemplateCreate(**data)
    assert "name" in str(exc_info.value)


def test_workflow_run_create_invalid_session_id():
    """Test that session_id <= 0 is rejected."""
    data = {
        "template_name": "test_workflow",
        "session_id": 0,
        "input_data": {}
    }

    with pytest.raises(ValidationError) as exc_info:
        WorkflowRunCreate(**data)
    assert "session_id" in str(exc_info.value)


# Response schema from_attributes tests
def test_workflow_template_response_from_dict():
    """Test WorkflowTemplateResponse can be created from dict (mimics ORM)."""
    data = {
        "id": 1,
        "name": "test_workflow",
        "description": "Test description",
        "version": "1.0.0",
        "workflow_category": WorkflowCategory.WORKFLOW,
        "definition": {"entry_point": "step1", "steps": []},
        "created_at": datetime(2026, 1, 1, 12, 0, 0),
        "updated_at": datetime(2026, 1, 1, 12, 0, 0)
    }

    response = WorkflowTemplateResponse(**data)
    assert response.id == 1
    assert response.name == "test_workflow"
    assert response.workflow_category == WorkflowCategory.WORKFLOW


def test_workflow_run_response_from_dict():
    """Test WorkflowRunResponse can be created from dict (mimics ORM)."""
    data = {
        "id": 1,
        "template_id": 1,
        "session_id": 1,
        "status": "running",
        "workflow_category": WorkflowCategory.WORKFLOW,
        "input_data": {"key": "value"},
        "state": {"current_step": "step1"},
        "output_data": None,
        "started_at": datetime(2026, 1, 1, 12, 0, 0),
        "completed_at": None
    }

    response = WorkflowRunResponse(**data)
    assert response.id == 1
    assert response.status == "running"
    assert response.workflow_category == WorkflowCategory.WORKFLOW


def test_workflow_step_execution_response_from_dict():
    """Test WorkflowStepExecutionResponse can be created from dict (mimics ORM)."""
    data = {
        "id": 1,
        "workflow_run_id": 1,
        "step_id": "step1",
        "step_name": "Test Step",
        "step_type": "tool_call",
        "status": "completed",
        "inputs": {"param": "value"},
        "outputs": {"result": "success"},
        "error": None,
        "started_at": datetime(2026, 1, 1, 12, 0, 0),
        "completed_at": datetime(2026, 1, 1, 12, 1, 0)
    }

    response = WorkflowStepExecutionResponse(**data)
    assert response.id == 1
    assert response.step_id == "step1"
    assert response.status == "completed"

