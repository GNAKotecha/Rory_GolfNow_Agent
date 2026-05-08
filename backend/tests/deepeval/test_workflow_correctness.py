import pytest
from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

from app.workflows.teesheet_onboarding import create_teesheet_onboarding_template
from app.services.workflow_orchestrator import WorkflowOrchestrator

CONFIG_STEP_NAME = "Configure Teesheet"


@pytest.mark.deepeval
@pytest.mark.asyncio
async def test_onboarding_workflow_generates_correct_config(
    db_session,
    session,
    skip_if_no_deepeval_key
):
    """Test that onboarding workflow generates correct club configuration."""
    # Setup workflow
    template = create_teesheet_onboarding_template(db_session)
    orchestrator = WorkflowOrchestrator(db_session)

    # Create workflow run
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
        },
    )

    # Execute workflow
    await orchestrator.execute_workflow(workflow_run.id)

    # Get config generation step output
    config_step = next(
        (step for step in workflow_run.step_executions
         if step.step_name == CONFIG_STEP_NAME),
        None,
    )
    assert config_step is not None, (
        f"{CONFIG_STEP_NAME!r} step not found in workflow {workflow_run.id}; "
        f"steps present: {[s.step_name for s in workflow_run.step_executions]}"
    )
    generated_config = config_step.output_data

    # Define correctness criteria
    correctness_metric = GEval(
        name="Config Correctness",
        criteria="The generated configuration should correctly include the club name, ID, facility type, and requested modules (member and SMS). It should not include unrequested modules.",
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT
        ],
        threshold=0.7
    )

    # Create test case
    test_case = LLMTestCase(
        input=f"Generate configuration for {workflow_run.input_data}",
        actual_output=str(generated_config),
        context=[
            "Club: Pebble Beach Golf Links (PB001)",
            "Facility: golf_course",
            "Modules: member, sms"
        ]
    )

    # Assert correctness
    assert_test(test_case, [correctness_metric])


@pytest.mark.deepeval
@pytest.mark.asyncio
async def test_onboarding_workflow_validates_required_fields(
    db_session,
    session,
    skip_if_no_deepeval_key
):
    """Test that workflow properly validates required fields."""
    # Setup
    template = create_teesheet_onboarding_template(db_session)
    orchestrator = WorkflowOrchestrator(db_session)

    # Create workflow with incomplete data
    workflow_run = orchestrator.create_workflow_run(
        template_name=template.name,
        session_id=session.id,
        input_data={
            "club_name": "Test Club",
            # Missing: club_id, contact_email, contact_name
        },
    )

    # Execute workflow (should fail validation)
    try:
        result = await orchestrator.execute_workflow(workflow_run.id)
        validation_passed = False
    except ValueError as e:
        validation_passed = True
        error_message = str(e)

    # Verify validation failed appropriately
    assert validation_passed, "Workflow should reject incomplete input"
    assert "required" in error_message.lower() or "missing" in error_message.lower()
