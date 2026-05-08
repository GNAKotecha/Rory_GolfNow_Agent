import pytest
from deepeval import assert_test
from deepeval.metrics import HallucinationMetric
from deepeval.test_case import LLMTestCase

from app.workflows.teesheet_onboarding import create_teesheet_onboarding_template
from app.services.workflow_orchestrator import WorkflowOrchestrator

CONFIG_STEP_NAME = "Configure Teesheet"
SUPERUSER_STEP_NAME = "Create Superuser"


@pytest.mark.deepeval
@pytest.mark.asyncio
async def test_config_generation_does_not_hallucinate(
    db_session,
    session,
    skip_if_no_deepeval_key
):
    """Test that config generation doesn't hallucinate modules or settings not requested."""
    # Setup workflow
    template = create_teesheet_onboarding_template(db_session)
    orchestrator = WorkflowOrchestrator(db_session)

    # Create workflow with specific module requests
    workflow_run = orchestrator.create_workflow_run(
        template_name=template.name,
        session_id=session.id,
        input_data={
            "club_name": "Simple Golf Club",
            "club_id": "SGC001",
            "contact_email": "admin@simplegolf.com",
            "contact_name": "Jane Doe",
            "facility_type": "golf_course",
            "modules": ["sms"]  # ONLY SMS module requested
        },
    )

    # Execute workflow
    await orchestrator.execute_workflow(workflow_run.id)

    # Get config generation output
    config_step = next(
        (step for step in workflow_run.step_executions
         if step.step_name == CONFIG_STEP_NAME),
        None,
    )
    assert config_step is not None, (
        f"config_setup step not found in workflow {workflow_run.id}; "
        f"steps present: {[s.step_name for s in workflow_run.step_executions]}"
    )
    generated_config = config_step.output_data

    # Define context (what was actually requested)
    context = [
        "Club name: Simple Golf Club",
        "Club ID: SGC001",
        "Facility type: golf_course",
        "Modules requested: SMS only",
        "Modules NOT requested: member, visitor, clubhouse_pc, green_fee_printer"
    ]

    # Check for hallucination
    hallucination_metric = HallucinationMetric(threshold=0.7)

    test_case = LLMTestCase(
        input="Generate configuration for Simple Golf Club with SMS module only",
        actual_output=str(generated_config),
        context=context
    )

    # Assert no hallucination
    assert_test(test_case, [hallucination_metric])


@pytest.mark.deepeval
@pytest.mark.asyncio
async def test_superuser_creation_uses_provided_email(
    db_session,
    session,
    skip_if_no_deepeval_key
):
    """Test that superuser creation uses provided email, not hallucinated one."""
    # Setup
    template = create_teesheet_onboarding_template(db_session)
    orchestrator = WorkflowOrchestrator(db_session)

    # Create workflow with specific contact email
    workflow_run = orchestrator.create_workflow_run(
        template_name=template.name,
        session_id=session.id,
        input_data={
            "club_name": "Test Club",
            "club_id": "TC001",
            "contact_email": "specific@testclub.com",  # This EXACT email should be used
            "contact_name": "Test Admin",
            "facility_type": "golf_course",
            "modules": []
        },
    )

    # Execute
    await orchestrator.execute_workflow(workflow_run.id)

    # Get superuser creation step
    superuser_step = next(
        (step for step in workflow_run.step_executions
         if step.step_name == SUPERUSER_STEP_NAME),
        None,
    )
    assert superuser_step is not None, (
        f"create_superuser step not found in workflow {workflow_run.id}; "
        f"steps present: {[s.step_name for s in workflow_run.step_executions]}"
    )

    # Verify no email hallucination
    context = ["Contact email provided: specific@testclub.com"]

    hallucination_metric = HallucinationMetric(threshold=0.9)

    test_case = LLMTestCase(
        input="Create superuser with email specific@testclub.com",
        actual_output=str(superuser_step.output_data),
        context=context
    )

    assert_test(test_case, [hallucination_metric])
