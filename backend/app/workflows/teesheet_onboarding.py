from typing import Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from app.models.workflow import WorkflowTemplate, WorkflowCategory


def create_teesheet_onboarding_template(db: Session) -> WorkflowTemplate:
    """Create teesheet onboarding workflow template.

    Workflow Steps:
    1. Init Database - Create club-specific database (./bin/teesheet init)
    2. Create Superuser - Setup admin account (./bin/teesheet update-superusers)
    3. Config Setup - Add club config to MongoDB (brs-config-api)
    4. Validate Config - Verify setup is correct

    Approval Gates:
    - After config setup (before validation) - human reviews generated config

    Args:
        db: Database session

    Returns:
        WorkflowTemplate for teesheet onboarding
    """

    # Define workflow steps
    workflow_definition = {
        "steps": [
            {
                "id": "init_database",
                "name": "Initialize Database",
                "type": "tool_call",
                "tool": "brs_teesheet_init",
                "description": "Initialize club database",
                "inputs": {
                    "club_name": "{{input.club_name}}",
                    "club_id": "{{input.club_id}}"
                },
                "next": ["create_superuser"],
                "timeout_seconds": 120
            },
            {
                "id": "create_superuser",
                "name": "Create Superuser",
                "type": "tool_call",
                "tool": "brs_create_superuser",
                "description": "Create admin account",
                "inputs": {
                    "club_name": "{{input.club_name}}",
                    "email": "{{input.contact_email}}",
                    "name": "{{input.contact_name}}"
                },
                "next": ["config_setup"],
                "timeout_seconds": 60,
                "depends_on": ["init_database"]
            },
            {
                "id": "config_setup",
                "name": "Configure Teesheet",
                "type": "llm_decision",
                "description": "Generate club configuration",
                "prompt_template": "teesheet_config_generation",
                "inputs": {
                    "club_name": "{{input.club_name}}",
                    "club_id": "{{input.club_id}}",
                    "facility_type": "{{input.facility_type}}",
                    "modules": "{{input.modules}}"
                },
                "next": ["approval_gate_config"],
                "depends_on": ["create_superuser"]
            },
            {
                "id": "approval_gate_config",
                "name": "Review Configuration",
                "type": "approval_gate",
                "description": "Review generated configuration",
                "approval_data_key": "config_setup.output",
                "next": ["validate_config"],
                "depends_on": ["config_setup"]
            },
            {
                "id": "validate_config",
                "name": "Validate Configuration",
                "type": "tool_call",
                "tool": "brs_config_validate",
                "description": "Validate configuration",
                "inputs": {
                    "club_id": "{{input.club_id}}"
                },
                "next": [],
                "depends_on": ["approval_gate_config"]
            }
        ],
        "input_schema": {
            "type": "object",
            "required": ["club_name", "club_id", "contact_email", "contact_name"],
            "properties": {
                "club_name": {"type": "string"},
                "club_id": {"type": "string"},
                "contact_email": {"type": "string", "format": "email"},
                "contact_name": {"type": "string"},
                "facility_type": {"type": "string", "enum": ["golf_course", "driving_range", "simulator"]},
                "modules": {"type": "array", "items": {"type": "string"}}
            }
        },
        "entry_point": "init_database"
    }

    # Create template
    template = WorkflowTemplate(
        name="Teesheet Onboarding",
        version="1.0.0",
        description="Complete teesheet onboarding workflow with database init, superuser creation, and config setup",
        definition=workflow_definition,
        workflow_category=WorkflowCategory.WORKFLOW,
        created_at=datetime.now(timezone.utc)
    )

    db.add(template)
    db.commit()
    db.refresh(template)

    return template


def validate_onboarding_input(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate onboarding workflow input data.

    Args:
        input_data: Input data to validate

    Returns:
        Input data if valid

    Raises:
        ValueError: If validation fails
    """
    from jsonschema import validate, ValidationError

    template_input_schema = {
        "type": "object",
        "required": ["club_name", "club_id", "contact_email", "contact_name"],
        "properties": {
            "club_name": {"type": "string"},
            "club_id": {"type": "string"},
            "contact_email": {"type": "string", "format": "email"},
            "contact_name": {"type": "string"},
            "facility_type": {"type": "string", "enum": ["golf_course", "driving_range", "simulator"]},
            "modules": {"type": "array", "items": {"type": "string"}}
        }
    }

    try:
        validate(instance=input_data, schema=template_input_schema)
        return input_data
    except ValidationError as e:
        raise ValueError(f"Input validation failed: {e.message}")