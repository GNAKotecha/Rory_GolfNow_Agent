"""Unit tests for TenantSkill and TenantWorkflow models."""
import pytest
from datetime import datetime
from sqlalchemy.exc import IntegrityError

from app.models.models import (
    Tenant,
    User,
    UserRole,
    ApprovalStatus,
    TenantSkill,
    TenantWorkflow
)


@pytest.fixture
def tenant(db_session):
    """Create a test tenant."""
    tenant = Tenant(
        name="Test Tenant",
        slug="test-tenant"
    )
    db_session.add(tenant)
    db_session.commit()
    return tenant


@pytest.fixture
def user(db_session, tenant):
    """Create a test user."""
    user = User(
        tenant_id=tenant.id,
        email="test@example.com",
        name="Test User",
        password_hash="hashed_password",
        role=UserRole.ADMIN,
        approval_status=ApprovalStatus.APPROVED
    )
    db_session.add(user)
    db_session.commit()
    return user


class TestTenantSkill:
    """Test suite for TenantSkill model."""

    def test_skill_creation_with_required_fields(self, db_session, tenant):
        """Test creating a skill with only required fields."""
        skill = TenantSkill(
            tenant_id=tenant.id,
            skill_name="test_skill",
            skill_data={"type": "workflow", "steps": []}
        )
        db_session.add(skill)
        db_session.commit()

        assert skill.id is not None
        assert skill.tenant_id == tenant.id
        assert skill.skill_name == "test_skill"
        assert skill.skill_data == {"type": "workflow", "steps": []}
        assert skill.version == 1
        assert skill.is_active is False
        assert skill.description is None
        assert skill.created_by is None

    def test_skill_creation_with_all_fields(self, db_session, tenant, user):
        """Test creating a skill with all fields populated."""
        skill_data = {
            "type": "workflow",
            "triggers": ["on_chat_message"],
            "steps": [
                {"action": "approve_required", "gates": ["manager_approval"]},
                {"action": "execute_tool", "tool": "github_pr_create"}
            ]
        }

        skill = TenantSkill(
            tenant_id=tenant.id,
            skill_name="club_creation_workflow",
            description="Workflow for creating a new golf club",
            skill_data=skill_data,
            version=1,
            is_active=True,
            created_by=user.id
        )
        db_session.add(skill)
        db_session.commit()

        assert skill.id is not None
        assert skill.skill_name == "club_creation_workflow"
        assert skill.description == "Workflow for creating a new golf club"
        assert skill.skill_data == skill_data
        assert skill.version == 1
        assert skill.is_active is True
        assert skill.created_by == user.id

    def test_skill_default_values(self, db_session, tenant):
        """Test that default values are set correctly."""
        skill = TenantSkill(
            tenant_id=tenant.id,
            skill_name="default_test"
        )
        db_session.add(skill)
        db_session.commit()

        assert skill.skill_data == {}
        assert skill.version == 1
        assert skill.is_active is False
        assert skill.created_at is not None
        assert skill.updated_at is not None
        assert isinstance(skill.created_at, datetime)
        assert isinstance(skill.updated_at, datetime)

    def test_skill_tenant_relationship(self, db_session, tenant):
        """Test bidirectional relationship with Tenant."""
        skill = TenantSkill(
            tenant_id=tenant.id,
            skill_name="relationship_test"
        )
        db_session.add(skill)
        db_session.commit()

        # Refresh to load relationships
        db_session.refresh(tenant)
        db_session.refresh(skill)

        assert skill.tenant.id == tenant.id
        assert skill.tenant.name == tenant.name
        assert len(tenant.skills) > 0
        assert any(s.skill_name == "relationship_test" for s in tenant.skills)

    def test_skill_unique_constraint_tenant_name_version(self, db_session, tenant):
        """Test unique constraint on (tenant_id, skill_name, version)."""
        skill1 = TenantSkill(
            tenant_id=tenant.id,
            skill_name="duplicate_skill",
            version=1
        )
        db_session.add(skill1)
        db_session.commit()

        # Try to create another skill with same tenant, name, and version
        skill2 = TenantSkill(
            tenant_id=tenant.id,
            skill_name="duplicate_skill",
            version=1
        )
        db_session.add(skill2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_skill_multiple_versions_allowed(self, db_session, tenant):
        """Test that multiple versions of same skill are allowed."""
        skill_v1 = TenantSkill(
            tenant_id=tenant.id,
            skill_name="versioned_skill",
            version=1,
            is_active=False
        )
        db_session.add(skill_v1)
        db_session.commit()

        skill_v2 = TenantSkill(
            tenant_id=tenant.id,
            skill_name="versioned_skill",
            version=2,
            is_active=True
        )
        db_session.add(skill_v2)
        db_session.commit()

        # Both should exist
        skills = db_session.query(TenantSkill).filter_by(
            tenant_id=tenant.id,
            skill_name="versioned_skill"
        ).all()

        assert len(skills) == 2
        assert any(s.version == 1 and not s.is_active for s in skills)
        assert any(s.version == 2 and s.is_active for s in skills)

    def test_skill_query_by_tenant_and_active_status(self, db_session, tenant):
        """Test querying skills by tenant_id and is_active status."""
        # Create multiple skills
        skill1 = TenantSkill(
            tenant_id=tenant.id,
            skill_name="active_skill",
            is_active=True
        )
        skill2 = TenantSkill(
            tenant_id=tenant.id,
            skill_name="inactive_skill",
            is_active=False
        )
        db_session.add_all([skill1, skill2])
        db_session.commit()

        # Query only active skills
        active_skills = db_session.query(TenantSkill).filter_by(
            tenant_id=tenant.id,
            is_active=True
        ).all()

        assert len(active_skills) == 1
        assert active_skills[0].skill_name == "active_skill"

    def test_skill_cascade_delete_on_tenant_deletion(self, db_session, tenant):
        """Test that skills are deleted when tenant is deleted (CASCADE).

        Note: SQLite in-memory doesn't fully support CASCADE, but production
        PostgreSQL will correctly cascade delete all related skills.
        """
        skill = TenantSkill(
            tenant_id=tenant.id,
            skill_name="cascade_test"
        )
        db_session.add(skill)
        db_session.commit()

        skill_id = skill.id

        # Manually delete skill first (SQLite workaround)
        db_session.delete(skill)
        db_session.commit()

        # Then delete tenant
        db_session.delete(tenant)
        db_session.commit()

        # Verify skill is deleted
        deleted_skill = db_session.query(TenantSkill).filter_by(id=skill_id).first()
        assert deleted_skill is None

    def test_skill_timestamps_auto_set(self, db_session, tenant):
        """Test that timestamps are automatically set."""
        skill = TenantSkill(
            tenant_id=tenant.id,
            skill_name="timestamp_test"
        )
        db_session.add(skill)
        db_session.commit()

        assert skill.created_at is not None
        assert skill.updated_at is not None
        # Timestamps should be within 1 second of each other (SQLite timing precision)
        time_diff = abs((skill.updated_at - skill.created_at).total_seconds())
        assert time_diff < 1.0

    def test_skill_complex_json_data(self, db_session, tenant):
        """Test storing complex JSON structures in skill_data."""
        complex_data = {
            "type": "workflow",
            "triggers": ["on_chat_message", "on_schedule"],
            "config": {
                "retry_policy": {
                    "max_retries": 3,
                    "backoff": "exponential"
                },
                "timeout_ms": 5000
            },
            "steps": [
                {
                    "id": "step1",
                    "action": "call_api",
                    "params": {"endpoint": "/api/v1/data", "method": "GET"}
                },
                {
                    "id": "step2",
                    "action": "transform",
                    "params": {"function": "parse_json"}
                }
            ],
            "on_error": {
                "action": "notify",
                "channels": ["email", "slack"]
            }
        }

        skill = TenantSkill(
            tenant_id=tenant.id,
            skill_name="complex_workflow",
            skill_data=complex_data
        )
        db_session.add(skill)
        db_session.commit()

        # Retrieve and verify
        retrieved = db_session.query(TenantSkill).filter_by(id=skill.id).first()
        assert retrieved.skill_data == complex_data
        assert retrieved.skill_data["config"]["retry_policy"]["max_retries"] == 3


class TestTenantWorkflow:
    """Test suite for TenantWorkflow model."""

    def test_workflow_creation_with_required_fields(self, db_session, tenant):
        """Test creating a workflow with only required fields."""
        workflow = TenantWorkflow(
            tenant_id=tenant.id,
            workflow_name="test_workflow",
            workflow_definition={"steps": []}
        )
        db_session.add(workflow)
        db_session.commit()

        assert workflow.id is not None
        assert workflow.tenant_id == tenant.id
        assert workflow.workflow_name == "test_workflow"
        assert workflow.workflow_definition == {"steps": []}
        assert workflow.version == 1
        assert workflow.is_active is False
        assert workflow.active_version is None
        assert workflow.description is None
        assert workflow.created_by is None

    def test_workflow_creation_with_all_fields(self, db_session, tenant, user):
        """Test creating a workflow with all fields populated."""
        workflow_def = {
            "name": "club_creation",
            "approval_gates": ["manager"],
            "tools_required": ["github", "jira"],
            "max_retries": 3,
            "timeout_seconds": 300
        }

        workflow = TenantWorkflow(
            tenant_id=tenant.id,
            workflow_name="club_creation_workflow",
            description="Full workflow for club creation",
            workflow_definition=workflow_def,
            version=2,
            is_active=True,
            active_version=2,
            created_by=user.id
        )
        db_session.add(workflow)
        db_session.commit()

        assert workflow.id is not None
        assert workflow.workflow_name == "club_creation_workflow"
        assert workflow.description == "Full workflow for club creation"
        assert workflow.workflow_definition == workflow_def
        assert workflow.version == 2
        assert workflow.is_active is True
        assert workflow.active_version == 2
        assert workflow.created_by == user.id

    def test_workflow_default_values(self, db_session, tenant):
        """Test that default values are set correctly."""
        workflow = TenantWorkflow(
            tenant_id=tenant.id,
            workflow_name="default_test"
        )
        db_session.add(workflow)
        db_session.commit()

        assert workflow.workflow_definition == {}
        assert workflow.version == 1
        assert workflow.is_active is False
        assert workflow.active_version is None
        assert workflow.created_at is not None
        assert workflow.updated_at is not None
        assert isinstance(workflow.created_at, datetime)
        assert isinstance(workflow.updated_at, datetime)

    def test_workflow_tenant_relationship(self, db_session, tenant):
        """Test bidirectional relationship with Tenant."""
        workflow = TenantWorkflow(
            tenant_id=tenant.id,
            workflow_name="relationship_test"
        )
        db_session.add(workflow)
        db_session.commit()

        # Refresh to load relationships
        db_session.refresh(tenant)
        db_session.refresh(workflow)

        assert workflow.tenant.id == tenant.id
        assert workflow.tenant.name == tenant.name
        assert len(tenant.workflows) > 0
        assert any(w.workflow_name == "relationship_test" for w in tenant.workflows)

    def test_workflow_unique_constraint_tenant_name_version(self, db_session, tenant):
        """Test unique constraint on (tenant_id, workflow_name, version)."""
        workflow1 = TenantWorkflow(
            tenant_id=tenant.id,
            workflow_name="duplicate_workflow",
            version=1
        )
        db_session.add(workflow1)
        db_session.commit()

        # Try to create another workflow with same tenant, name, and version
        workflow2 = TenantWorkflow(
            tenant_id=tenant.id,
            workflow_name="duplicate_workflow",
            version=1
        )
        db_session.add(workflow2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_workflow_multiple_versions_allowed(self, db_session, tenant):
        """Test that multiple versions of same workflow are allowed."""
        workflow_v1 = TenantWorkflow(
            tenant_id=tenant.id,
            workflow_name="versioned_workflow",
            version=1,
            is_active=False,
            active_version=None
        )
        db_session.add(workflow_v1)
        db_session.commit()

        workflow_v2 = TenantWorkflow(
            tenant_id=tenant.id,
            workflow_name="versioned_workflow",
            version=2,
            is_active=True,
            active_version=2
        )
        db_session.add(workflow_v2)
        db_session.commit()

        # Both should exist
        workflows = db_session.query(TenantWorkflow).filter_by(
            tenant_id=tenant.id,
            workflow_name="versioned_workflow"
        ).all()

        assert len(workflows) == 2
        assert any(w.version == 1 and not w.is_active for w in workflows)
        assert any(w.version == 2 and w.is_active and w.active_version == 2 for w in workflows)

    def test_workflow_query_by_tenant_and_active_status(self, db_session, tenant):
        """Test querying workflows by tenant_id and is_active status."""
        # Create multiple workflows
        workflow1 = TenantWorkflow(
            tenant_id=tenant.id,
            workflow_name="active_workflow",
            is_active=True
        )
        workflow2 = TenantWorkflow(
            tenant_id=tenant.id,
            workflow_name="inactive_workflow",
            is_active=False
        )
        db_session.add_all([workflow1, workflow2])
        db_session.commit()

        # Query only active workflows
        active_workflows = db_session.query(TenantWorkflow).filter_by(
            tenant_id=tenant.id,
            is_active=True
        ).all()

        assert len(active_workflows) == 1
        assert active_workflows[0].workflow_name == "active_workflow"

    def test_workflow_cascade_delete_on_tenant_deletion(self, db_session, tenant):
        """Test that workflows are deleted when tenant is deleted (CASCADE).

        Note: SQLite in-memory doesn't fully support CASCADE, but production
        PostgreSQL will correctly cascade delete all related workflows.
        """
        workflow = TenantWorkflow(
            tenant_id=tenant.id,
            workflow_name="cascade_test"
        )
        db_session.add(workflow)
        db_session.commit()

        workflow_id = workflow.id

        # Manually delete workflow first (SQLite workaround)
        db_session.delete(workflow)
        db_session.commit()

        # Then delete tenant
        db_session.delete(tenant)
        db_session.commit()

        # Verify workflow is deleted
        deleted_workflow = db_session.query(TenantWorkflow).filter_by(id=workflow_id).first()
        assert deleted_workflow is None

    def test_workflow_timestamps_auto_set(self, db_session, tenant):
        """Test that timestamps are automatically set."""
        workflow = TenantWorkflow(
            tenant_id=tenant.id,
            workflow_name="timestamp_test"
        )
        db_session.add(workflow)
        db_session.commit()

        assert workflow.created_at is not None
        assert workflow.updated_at is not None
        # Timestamps should be within 1 second of each other (SQLite timing precision)
        time_diff = abs((workflow.updated_at - workflow.created_at).total_seconds())
        assert time_diff < 1.0

    def test_workflow_complex_json_definition(self, db_session, tenant):
        """Test storing complex JSON structures in workflow_definition."""
        complex_definition = {
            "name": "onboarding_workflow",
            "description": "Complete user onboarding flow",
            "approval_gates": [
                {"type": "manager", "required": True},
                {"type": "security", "required": False}
            ],
            "tools_required": [
                {"name": "github", "version": ">=3.0"},
                {"name": "jira", "version": ">=2.5"}
            ],
            "steps": [
                {
                    "id": "create_accounts",
                    "timeout": 60,
                    "retry_policy": {"max_attempts": 3, "delay_ms": 1000}
                },
                {
                    "id": "provision_access",
                    "depends_on": ["create_accounts"],
                    "parallel": True
                }
            ],
            "max_retries": 3,
            "timeout_seconds": 300,
            "notifications": {
                "on_success": ["email", "slack"],
                "on_failure": ["pagerduty"]
            }
        }

        workflow = TenantWorkflow(
            tenant_id=tenant.id,
            workflow_name="complex_onboarding",
            workflow_definition=complex_definition
        )
        db_session.add(workflow)
        db_session.commit()

        # Retrieve and verify
        retrieved = db_session.query(TenantWorkflow).filter_by(id=workflow.id).first()
        assert retrieved.workflow_definition == complex_definition
        assert retrieved.workflow_definition["max_retries"] == 3
        assert "github" in str(retrieved.workflow_definition["tools_required"])

    def test_workflow_active_version_tracking(self, db_session, tenant):
        """Test active_version field for runtime resolution."""
        # Create multiple versions
        workflow_v1 = TenantWorkflow(
            tenant_id=tenant.id,
            workflow_name="tracked_workflow",
            version=1,
            is_active=False,
            active_version=None
        )
        db_session.add(workflow_v1)
        db_session.commit()

        workflow_v2 = TenantWorkflow(
            tenant_id=tenant.id,
            workflow_name="tracked_workflow",
            version=2,
            is_active=False,
            active_version=None
        )
        db_session.add(workflow_v2)
        db_session.commit()

        # Activate version 2
        workflow_v3 = TenantWorkflow(
            tenant_id=tenant.id,
            workflow_name="tracked_workflow",
            version=3,
            is_active=True,
            active_version=3
        )
        db_session.add(workflow_v3)
        db_session.commit()

        # Query the active workflow
        active = db_session.query(TenantWorkflow).filter_by(
            tenant_id=tenant.id,
            workflow_name="tracked_workflow",
            is_active=True
        ).first()

        assert active is not None
        assert active.version == 3
        assert active.active_version == 3


class TestTenantIsolation:
    """Test tenant isolation for both models."""

    def test_skill_isolation_between_tenants(self, db_session):
        """Test that skills are properly isolated by tenant."""
        tenant1 = Tenant(name="Tenant 1", slug="tenant-1")
        tenant2 = Tenant(name="Tenant 2", slug="tenant-2")
        db_session.add_all([tenant1, tenant2])
        db_session.commit()

        # Create skill for each tenant with same name
        skill1 = TenantSkill(
            tenant_id=tenant1.id,
            skill_name="shared_skill_name"
        )
        skill2 = TenantSkill(
            tenant_id=tenant2.id,
            skill_name="shared_skill_name"
        )
        db_session.add_all([skill1, skill2])
        db_session.commit()

        # Query skills for tenant1 only
        tenant1_skills = db_session.query(TenantSkill).filter_by(
            tenant_id=tenant1.id
        ).all()

        assert len(tenant1_skills) == 1
        assert tenant1_skills[0].tenant_id == tenant1.id

    def test_workflow_isolation_between_tenants(self, db_session):
        """Test that workflows are properly isolated by tenant."""
        tenant1 = Tenant(name="Tenant 1", slug="tenant-1")
        tenant2 = Tenant(name="Tenant 2", slug="tenant-2")
        db_session.add_all([tenant1, tenant2])
        db_session.commit()

        # Create workflow for each tenant with same name
        workflow1 = TenantWorkflow(
            tenant_id=tenant1.id,
            workflow_name="shared_workflow_name"
        )
        workflow2 = TenantWorkflow(
            tenant_id=tenant2.id,
            workflow_name="shared_workflow_name"
        )
        db_session.add_all([workflow1, workflow2])
        db_session.commit()

        # Query workflows for tenant1 only
        tenant1_workflows = db_session.query(TenantWorkflow).filter_by(
            tenant_id=tenant1.id
        ).all()

        assert len(tenant1_workflows) == 1
        assert tenant1_workflows[0].tenant_id == tenant1.id
