"""Tests for WorkflowRuntimeService."""
import pytest
from sqlalchemy.orm import Session
from datetime import datetime

from app.services.workflow_runtime_service import WorkflowRuntimeService
from app.models.models import Tenant, TenantSkill, TenantWorkflow, User, UserRole


class TestLoadActiveWorkflow:
    """Tests for load_active_workflow method."""

    def test_load_active_workflow_found(self, db_session: Session):
        """Test loading an active workflow successfully."""
        # Create tenant
        tenant = Tenant(name="Test Tenant", slug="test-tenant")
        db_session.add(tenant)
        db_session.commit()

        # Create active workflow
        workflow = TenantWorkflow(
            tenant_id=tenant.id,
            workflow_name="club_creation",
            description="Golf club creation workflow",
            workflow_definition={
                "approval_gates": ["manager"],
                "tools_required": ["github", "jira"],
                "max_retries": 3,
                "timeout_seconds": 300
            },
            version=1,
            is_active=True
        )
        db_session.add(workflow)
        db_session.commit()

        # Load workflow
        result = WorkflowRuntimeService.load_active_workflow(
            db_session, tenant.id, "club_creation"
        )

        assert result is not None
        assert result.workflow_name == "club_creation"
        assert result.version == 1
        assert result.is_active is True
        assert result.tenant_id == tenant.id

    def test_load_active_workflow_not_found(self, db_session: Session):
        """Test loading non-existent workflow returns None."""
        # Create tenant
        tenant = Tenant(name="Test Tenant", slug="test-tenant")
        db_session.add(tenant)
        db_session.commit()

        # Try to load non-existent workflow
        result = WorkflowRuntimeService.load_active_workflow(
            db_session, tenant.id, "nonexistent_workflow"
        )

        assert result is None

    def test_load_active_workflow_inactive(self, db_session: Session):
        """Test loading inactive workflow returns None."""
        # Create tenant
        tenant = Tenant(name="Test Tenant", slug="test-tenant")
        db_session.add(tenant)
        db_session.commit()

        # Create inactive workflow
        workflow = TenantWorkflow(
            tenant_id=tenant.id,
            workflow_name="inactive_workflow",
            description="Inactive workflow",
            workflow_definition={},
            version=1,
            is_active=False
        )
        db_session.add(workflow)
        db_session.commit()

        # Try to load inactive workflow
        result = WorkflowRuntimeService.load_active_workflow(
            db_session, tenant.id, "inactive_workflow"
        )

        assert result is None

    def test_load_active_workflow_wrong_tenant(self, db_session: Session):
        """Test tenant isolation - wrong tenant returns None."""
        # Create two tenants
        tenant1 = Tenant(name="Tenant 1", slug="tenant-1")
        tenant2 = Tenant(name="Tenant 2", slug="tenant-2")
        db_session.add_all([tenant1, tenant2])
        db_session.commit()

        # Create workflow for tenant1
        workflow = TenantWorkflow(
            tenant_id=tenant1.id,
            workflow_name="tenant1_workflow",
            description="Tenant 1 workflow",
            workflow_definition={},
            version=1,
            is_active=True
        )
        db_session.add(workflow)
        db_session.commit()

        # Try to load tenant1's workflow using tenant2's ID
        result = WorkflowRuntimeService.load_active_workflow(
            db_session, tenant2.id, "tenant1_workflow"
        )

        assert result is None


class TestLoadActiveSkills:
    """Tests for load_active_skills method."""

    def test_load_active_skills_returns_active_only(self, db_session: Session):
        """Test returns only active skills."""
        # Create tenant
        tenant = Tenant(name="Test Tenant", slug="test-tenant")
        db_session.add(tenant)
        db_session.commit()

        # Create active and inactive skills
        active_skill1 = TenantSkill(
            tenant_id=tenant.id,
            skill_name="active_skill_1",
            description="Active skill 1",
            skill_data={"type": "workflow"},
            version=1,
            is_active=True
        )
        active_skill2 = TenantSkill(
            tenant_id=tenant.id,
            skill_name="active_skill_2",
            description="Active skill 2",
            skill_data={"type": "tool"},
            version=1,
            is_active=True
        )
        inactive_skill = TenantSkill(
            tenant_id=tenant.id,
            skill_name="inactive_skill",
            description="Inactive skill",
            skill_data={},
            version=1,
            is_active=False
        )
        db_session.add_all([active_skill1, active_skill2, inactive_skill])
        db_session.commit()

        # Load active skills
        result = WorkflowRuntimeService.load_active_skills(db_session, tenant.id)

        assert len(result) == 2
        skill_names = [skill.skill_name for skill in result]
        assert "active_skill_1" in skill_names
        assert "active_skill_2" in skill_names
        assert "inactive_skill" not in skill_names

    def test_load_active_skills_empty_list(self, db_session: Session):
        """Test returns empty list for tenant with no skills."""
        # Create tenant
        tenant = Tenant(name="Test Tenant", slug="test-tenant")
        db_session.add(tenant)
        db_session.commit()

        # Load skills (should be empty)
        result = WorkflowRuntimeService.load_active_skills(db_session, tenant.id)

        assert result == []

    def test_load_active_skills_tenant_isolation(self, db_session: Session):
        """Test tenant isolation for skills."""
        # Create two tenants
        tenant1 = Tenant(name="Tenant 1", slug="tenant-1")
        tenant2 = Tenant(name="Tenant 2", slug="tenant-2")
        db_session.add_all([tenant1, tenant2])
        db_session.commit()

        # Create skills for each tenant
        skill1 = TenantSkill(
            tenant_id=tenant1.id,
            skill_name="tenant1_skill",
            description="Tenant 1 skill",
            skill_data={},
            version=1,
            is_active=True
        )
        skill2 = TenantSkill(
            tenant_id=tenant2.id,
            skill_name="tenant2_skill",
            description="Tenant 2 skill",
            skill_data={},
            version=1,
            is_active=True
        )
        db_session.add_all([skill1, skill2])
        db_session.commit()

        # Load skills for tenant1
        result = WorkflowRuntimeService.load_active_skills(db_session, tenant1.id)

        assert len(result) == 1
        assert result[0].skill_name == "tenant1_skill"
        assert result[0].tenant_id == tenant1.id


class TestGetWorkflowContext:
    """Tests for get_workflow_context method."""

    def test_get_workflow_context_extracts_all_fields(self):
        """Test extracts all fields from workflow_definition."""
        # Create workflow with full definition
        workflow = TenantWorkflow(
            id=1,
            tenant_id=1,
            workflow_name="test_workflow",
            description="Test workflow",
            workflow_definition={
                "approval_gates": ["manager", "admin"],
                "tools_required": ["github", "jira", "slack"],
                "max_retries": 5,
                "timeout_seconds": 600,
                "custom_rules": {"priority": "high", "notify": True}
            },
            version=2,
            is_active=True
        )

        result = WorkflowRuntimeService.get_workflow_context(workflow)

        assert result["name"] == "test_workflow"
        assert result["version"] == 2
        assert result["approval_gates"] == ["manager", "admin"]
        assert result["tools_required"] == ["github", "jira", "slack"]
        assert result["max_retries"] == 5
        assert result["timeout_seconds"] == 600
        assert result["custom_rules"] == {"priority": "high", "notify": True}

    def test_get_workflow_context_with_defaults(self):
        """Test provides defaults for missing fields."""
        # Create workflow with minimal definition
        workflow = TenantWorkflow(
            id=1,
            tenant_id=1,
            workflow_name="minimal_workflow",
            description="Minimal workflow",
            workflow_definition={},  # Empty definition
            version=1,
            is_active=True
        )

        result = WorkflowRuntimeService.get_workflow_context(workflow)

        assert result["name"] == "minimal_workflow"
        assert result["version"] == 1
        assert result["approval_gates"] == []
        assert result["tools_required"] == []
        assert result["max_retries"] == 3  # Default
        assert result["timeout_seconds"] == 300  # Default
        assert result["custom_rules"] == {}  # Default

    def test_get_workflow_context_with_none_definition(self):
        """Test handles None workflow_definition."""
        # Create workflow with None definition
        workflow = TenantWorkflow(
            id=1,
            tenant_id=1,
            workflow_name="none_workflow",
            description="Workflow with None definition",
            workflow_definition=None,
            version=1,
            is_active=True
        )

        result = WorkflowRuntimeService.get_workflow_context(workflow)

        assert result["name"] == "none_workflow"
        assert result["version"] == 1
        assert result["approval_gates"] == []
        assert result["tools_required"] == []
        assert result["max_retries"] == 3
        assert result["timeout_seconds"] == 300
        assert result["custom_rules"] == {}


class TestGetSkillsContext:
    """Tests for get_skills_context method."""

    def test_get_skills_context_combines_all_skills(self):
        """Test combines all skills into context dict."""
        # Create skills
        skill1 = TenantSkill(
            id=1,
            tenant_id=1,
            skill_name="skill_1",
            description="Skill 1",
            skill_data={"type": "workflow", "steps": ["a", "b"]},
            version=1,
            is_active=True
        )
        skill2 = TenantSkill(
            id=2,
            tenant_id=1,
            skill_name="skill_2",
            description="Skill 2",
            skill_data={"type": "tool", "config": {"key": "value"}},
            version=1,
            is_active=True
        )

        skills = [skill1, skill2]
        result = WorkflowRuntimeService.get_skills_context(skills)

        assert "skill_names" in result
        assert "skill_data" in result
        assert result["skill_names"] == ["skill_1", "skill_2"]
        assert result["skill_data"]["skill_1"] == {"type": "workflow", "steps": ["a", "b"]}
        assert result["skill_data"]["skill_2"] == {"type": "tool", "config": {"key": "value"}}

    def test_get_skills_context_empty_list(self):
        """Test handles empty skills list."""
        result = WorkflowRuntimeService.get_skills_context([])

        assert result["skill_names"] == []
        assert result["skill_data"] == {}

    def test_get_skills_context_with_none_skill_data(self):
        """Test handles skills with None skill_data."""
        skill = TenantSkill(
            id=1,
            tenant_id=1,
            skill_name="skill_none",
            description="Skill with None data",
            skill_data=None,
            version=1,
            is_active=True
        )

        result = WorkflowRuntimeService.get_skills_context([skill])

        assert result["skill_names"] == ["skill_none"]
        assert result["skill_data"]["skill_none"] == {}


class TestLogWorkflowExecution:
    """Tests for log_workflow_execution method."""

    def test_log_workflow_execution_creates_log_entry(self, caplog):
        """Test creates log entry with correct format."""
        import logging
        caplog.set_level(logging.INFO)

        WorkflowRuntimeService.log_workflow_execution(
            run_id="test-run-123",
            tenant_id=1,
            workflow_name="test_workflow",
            workflow_version=2,
            action="started"
        )

        assert len(caplog.records) == 1
        log_message = caplog.records[0].message
        assert "[test-run-123]" in log_message
        assert "tenant=1" in log_message
        assert "workflow=test_workflow" in log_message
        assert "v2" in log_message
        assert "action=started" in log_message

    def test_log_workflow_execution_different_actions(self, caplog):
        """Test logs different action types."""
        import logging
        caplog.set_level(logging.INFO)

        actions = ["started", "step_completed", "error", "finished"]
        for action in actions:
            WorkflowRuntimeService.log_workflow_execution(
                run_id=f"run-{action}",
                tenant_id=1,
                workflow_name="test",
                workflow_version=1,
                action=action
            )

        assert len(caplog.records) == 4
        for idx, action in enumerate(actions):
            assert f"action={action}" in caplog.records[idx].message
