"""Tests for skill and workflow service layer."""
import pytest
from fastapi import HTTPException

from app.services.skill_workflow_service import SkillWorkflowService
from app.models.models import Tenant, User, UserRole, ApprovalStatus, TenantSkill, TenantWorkflow


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


class TestSkillService:
    """Tests for skill service methods."""

    def test_create_skill(self, db_session, tenant, user):
        """Test creating a new skill."""
        skill = SkillWorkflowService.create_skill(
            db=db_session,
            tenant_id=tenant.id,
            skill_name="test_skill",
            skill_data={"type": "workflow", "steps": []},
            description="Test skill",
            created_by=user.id
        )

        assert skill.id is not None
        assert skill.tenant_id == tenant.id
        assert skill.skill_name == "test_skill"
        assert skill.skill_data == {"type": "workflow", "steps": []}
        assert skill.description == "Test skill"
        assert skill.version == 1
        assert skill.is_active is False
        assert skill.created_by == user.id

    def test_create_skill_duplicate_name(self, db_session, tenant, user):
        """Test creating a skill with duplicate name raises 409."""
        SkillWorkflowService.create_skill(
            db=db_session,
            tenant_id=tenant.id,
            skill_name="duplicate_skill",
            skill_data={},
            created_by=user.id
        )

        with pytest.raises(HTTPException) as exc_info:
            SkillWorkflowService.create_skill(
                db=db_session,
                tenant_id=tenant.id,
                skill_name="duplicate_skill",
                skill_data={},
                created_by=user.id
            )

        assert exc_info.value.status_code == 409
        assert "already exists" in exc_info.value.detail

    def test_list_skills(self, db_session, tenant, user):
        """Test listing all skills for a tenant."""
        skill1 = SkillWorkflowService.create_skill(
            db=db_session,
            tenant_id=tenant.id,
            skill_name="skill_a",
            skill_data={},
            created_by=user.id
        )

        skill2 = SkillWorkflowService.create_skill(
            db=db_session,
            tenant_id=tenant.id,
            skill_name="skill_b",
            skill_data={},
            created_by=user.id
        )

        skills = SkillWorkflowService.list_skills(db=db_session, tenant_id=tenant.id)

        assert len(skills) == 2
        assert skills[0].skill_name in ["skill_a", "skill_b"]
        assert skills[1].skill_name in ["skill_a", "skill_b"]

    def test_list_skills_active_only(self, db_session, tenant, user):
        """Test listing only active skills."""
        skill1 = SkillWorkflowService.create_skill(
            db=db_session,
            tenant_id=tenant.id,
            skill_name="skill_active",
            skill_data={},
            created_by=user.id
        )

        skill2 = SkillWorkflowService.create_skill(
            db=db_session,
            tenant_id=tenant.id,
            skill_name="skill_inactive",
            skill_data={},
            created_by=user.id
        )

        # Activate skill1
        SkillWorkflowService.activate_skill_version(
            db=db_session,
            skill_id=skill1.id,
            tenant_id=tenant.id
        )

        skills = SkillWorkflowService.list_skills(
            db=db_session,
            tenant_id=tenant.id,
            active_only=True
        )

        assert len(skills) == 1
        assert skills[0].skill_name == "skill_active"
        assert skills[0].is_active is True

    def test_get_skill(self, db_session, tenant, user):
        """Test getting a specific skill."""
        created_skill = SkillWorkflowService.create_skill(
            db=db_session,
            tenant_id=tenant.id,
            skill_name="get_test",
            skill_data={"data": "value"},
            created_by=user.id
        )

        skill = SkillWorkflowService.get_skill(
            db=db_session,
            skill_id=created_skill.id,
            tenant_id=tenant.id
        )

        assert skill.id == created_skill.id
        assert skill.skill_name == "get_test"
        assert skill.skill_data == {"data": "value"}

    def test_get_skill_not_found(self, db_session, tenant):
        """Test getting non-existent skill raises 404."""
        with pytest.raises(HTTPException) as exc_info:
            SkillWorkflowService.get_skill(
                db=db_session,
                skill_id=99999,
                tenant_id=tenant.id
            )

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail

    def test_get_skill_wrong_tenant(self, db_session, user):
        """Test getting skill from different tenant raises 404."""
        # Create two tenants
        tenant1 = Tenant(name="Tenant 1", slug="tenant-1")
        tenant2 = Tenant(name="Tenant 2", slug="tenant-2")
        db_session.add(tenant1)
        db_session.add(tenant2)
        db_session.commit()

        # Create skill for tenant1
        skill = SkillWorkflowService.create_skill(
            db=db_session,
            tenant_id=tenant1.id,
            skill_name="tenant1_skill",
            skill_data={},
            created_by=user.id
        )

        # Try to get with tenant2
        with pytest.raises(HTTPException) as exc_info:
            SkillWorkflowService.get_skill(
                db=db_session,
                skill_id=skill.id,
                tenant_id=tenant2.id
            )

        assert exc_info.value.status_code == 404

    def test_update_skill(self, db_session, tenant, user):
        """Test updating a skill."""
        skill = SkillWorkflowService.create_skill(
            db=db_session,
            tenant_id=tenant.id,
            skill_name="update_test",
            skill_data={"old": "data"},
            description="Old description",
            created_by=user.id
        )

        updated_skill = SkillWorkflowService.update_skill(
            db=db_session,
            skill_id=skill.id,
            tenant_id=tenant.id,
            skill_data={"new": "data"},
            description="New description",
            is_active=True
        )

        assert updated_skill.id == skill.id
        assert updated_skill.skill_data == {"new": "data"}
        assert updated_skill.description == "New description"
        assert updated_skill.is_active is True

    def test_update_skill_partial(self, db_session, tenant, user):
        """Test updating only some fields."""
        skill = SkillWorkflowService.create_skill(
            db=db_session,
            tenant_id=tenant.id,
            skill_name="partial_update",
            skill_data={"original": "data"},
            description="Original description",
            created_by=user.id
        )

        updated_skill = SkillWorkflowService.update_skill(
            db=db_session,
            skill_id=skill.id,
            tenant_id=tenant.id,
            description="Updated description only"
        )

        assert updated_skill.description == "Updated description only"
        assert updated_skill.skill_data == {"original": "data"}  # Unchanged

    def test_delete_skill(self, db_session, tenant, user):
        """Test deleting all versions of a skill."""
        skill = SkillWorkflowService.create_skill(
            db=db_session,
            tenant_id=tenant.id,
            skill_name="delete_test",
            skill_data={},
            created_by=user.id
        )

        skill_id = skill.id

        SkillWorkflowService.delete_skill(
            db=db_session,
            skill_id=skill_id,
            tenant_id=tenant.id
        )

        # Verify deletion
        with pytest.raises(HTTPException) as exc_info:
            SkillWorkflowService.get_skill(
                db=db_session,
                skill_id=skill_id,
                tenant_id=tenant.id
            )

        assert exc_info.value.status_code == 404

    def test_activate_skill_version(self, db_session, tenant, user):
        """Test activating a skill version."""
        skill = SkillWorkflowService.create_skill(
            db=db_session,
            tenant_id=tenant.id,
            skill_name="activate_test",
            skill_data={},
            created_by=user.id
        )

        assert skill.is_active is False

        activated_skill = SkillWorkflowService.activate_skill_version(
            db=db_session,
            skill_id=skill.id,
            tenant_id=tenant.id
        )

        assert activated_skill.is_active is True


class TestWorkflowService:
    """Tests for workflow service methods."""

    def test_create_workflow(self, db_session, tenant, user):
        """Test creating a new workflow."""
        workflow = SkillWorkflowService.create_workflow(
            db=db_session,
            tenant_id=tenant.id,
            workflow_name="test_workflow",
            workflow_definition={"steps": [{"action": "approve"}]},
            description="Test workflow",
            created_by=user.id
        )

        assert workflow.id is not None
        assert workflow.tenant_id == tenant.id
        assert workflow.workflow_name == "test_workflow"
        assert workflow.workflow_definition == {"steps": [{"action": "approve"}]}
        assert workflow.description == "Test workflow"
        assert workflow.version == 1
        assert workflow.is_active is False
        assert workflow.active_version is None
        assert workflow.created_by == user.id

    def test_create_workflow_duplicate_name(self, db_session, tenant, user):
        """Test creating a workflow with duplicate name raises 409."""
        SkillWorkflowService.create_workflow(
            db=db_session,
            tenant_id=tenant.id,
            workflow_name="duplicate_workflow",
            workflow_definition={},
            created_by=user.id
        )

        with pytest.raises(HTTPException) as exc_info:
            SkillWorkflowService.create_workflow(
                db=db_session,
                tenant_id=tenant.id,
                workflow_name="duplicate_workflow",
                workflow_definition={},
                created_by=user.id
            )

        assert exc_info.value.status_code == 409
        assert "already exists" in exc_info.value.detail

    def test_list_workflows(self, db_session, tenant, user):
        """Test listing all workflows for a tenant."""
        workflow1 = SkillWorkflowService.create_workflow(
            db=db_session,
            tenant_id=tenant.id,
            workflow_name="workflow_a",
            workflow_definition={},
            created_by=user.id
        )

        workflow2 = SkillWorkflowService.create_workflow(
            db=db_session,
            tenant_id=tenant.id,
            workflow_name="workflow_b",
            workflow_definition={},
            created_by=user.id
        )

        workflows = SkillWorkflowService.list_workflows(db=db_session, tenant_id=tenant.id)

        assert len(workflows) == 2
        assert workflows[0].workflow_name in ["workflow_a", "workflow_b"]
        assert workflows[1].workflow_name in ["workflow_a", "workflow_b"]

    def test_list_workflows_active_only(self, db_session, tenant, user):
        """Test listing only active workflows."""
        workflow1 = SkillWorkflowService.create_workflow(
            db=db_session,
            tenant_id=tenant.id,
            workflow_name="workflow_active",
            workflow_definition={},
            created_by=user.id
        )

        workflow2 = SkillWorkflowService.create_workflow(
            db=db_session,
            tenant_id=tenant.id,
            workflow_name="workflow_inactive",
            workflow_definition={},
            created_by=user.id
        )

        # Activate workflow1
        SkillWorkflowService.activate_workflow_version(
            db=db_session,
            workflow_id=workflow1.id,
            tenant_id=tenant.id
        )

        workflows = SkillWorkflowService.list_workflows(
            db=db_session,
            tenant_id=tenant.id,
            active_only=True
        )

        assert len(workflows) == 1
        assert workflows[0].workflow_name == "workflow_active"
        assert workflows[0].is_active is True

    def test_get_workflow(self, db_session, tenant, user):
        """Test getting a specific workflow."""
        created_workflow = SkillWorkflowService.create_workflow(
            db=db_session,
            tenant_id=tenant.id,
            workflow_name="get_test",
            workflow_definition={"data": "value"},
            created_by=user.id
        )

        workflow = SkillWorkflowService.get_workflow(
            db=db_session,
            workflow_id=created_workflow.id,
            tenant_id=tenant.id
        )

        assert workflow.id == created_workflow.id
        assert workflow.workflow_name == "get_test"
        assert workflow.workflow_definition == {"data": "value"}

    def test_get_workflow_not_found(self, db_session, tenant):
        """Test getting non-existent workflow raises 404."""
        with pytest.raises(HTTPException) as exc_info:
            SkillWorkflowService.get_workflow(
                db=db_session,
                workflow_id=99999,
                tenant_id=tenant.id
            )

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail

    def test_get_workflow_wrong_tenant(self, db_session, user):
        """Test getting workflow from different tenant raises 404."""
        # Create two tenants
        tenant1 = Tenant(name="Tenant 1", slug="tenant-1")
        tenant2 = Tenant(name="Tenant 2", slug="tenant-2")
        db_session.add(tenant1)
        db_session.add(tenant2)
        db_session.commit()

        # Create workflow for tenant1
        workflow = SkillWorkflowService.create_workflow(
            db=db_session,
            tenant_id=tenant1.id,
            workflow_name="tenant1_workflow",
            workflow_definition={},
            created_by=user.id
        )

        # Try to get with tenant2
        with pytest.raises(HTTPException) as exc_info:
            SkillWorkflowService.get_workflow(
                db=db_session,
                workflow_id=workflow.id,
                tenant_id=tenant2.id
            )

        assert exc_info.value.status_code == 404

    def test_update_workflow(self, db_session, tenant, user):
        """Test updating a workflow."""
        workflow = SkillWorkflowService.create_workflow(
            db=db_session,
            tenant_id=tenant.id,
            workflow_name="update_test",
            workflow_definition={"old": "data"},
            description="Old description",
            created_by=user.id
        )

        updated_workflow = SkillWorkflowService.update_workflow(
            db=db_session,
            workflow_id=workflow.id,
            tenant_id=tenant.id,
            workflow_definition={"new": "data"},
            description="New description",
            is_active=True,
            active_version=workflow.id
        )

        assert updated_workflow.id == workflow.id
        assert updated_workflow.workflow_definition == {"new": "data"}
        assert updated_workflow.description == "New description"
        assert updated_workflow.is_active is True
        assert updated_workflow.active_version == workflow.id

    def test_update_workflow_partial(self, db_session, tenant, user):
        """Test updating only some fields."""
        workflow = SkillWorkflowService.create_workflow(
            db=db_session,
            tenant_id=tenant.id,
            workflow_name="partial_update",
            workflow_definition={"original": "data"},
            description="Original description",
            created_by=user.id
        )

        updated_workflow = SkillWorkflowService.update_workflow(
            db=db_session,
            workflow_id=workflow.id,
            tenant_id=tenant.id,
            description="Updated description only"
        )

        assert updated_workflow.description == "Updated description only"
        assert updated_workflow.workflow_definition == {"original": "data"}  # Unchanged

    def test_delete_workflow(self, db_session, tenant, user):
        """Test deleting all versions of a workflow."""
        workflow = SkillWorkflowService.create_workflow(
            db=db_session,
            tenant_id=tenant.id,
            workflow_name="delete_test",
            workflow_definition={},
            created_by=user.id
        )

        workflow_id = workflow.id

        SkillWorkflowService.delete_workflow(
            db=db_session,
            workflow_id=workflow_id,
            tenant_id=tenant.id
        )

        # Verify deletion
        with pytest.raises(HTTPException) as exc_info:
            SkillWorkflowService.get_workflow(
                db=db_session,
                workflow_id=workflow_id,
                tenant_id=tenant.id
            )

        assert exc_info.value.status_code == 404

    def test_activate_workflow_version(self, db_session, tenant, user):
        """Test activating a workflow version."""
        workflow = SkillWorkflowService.create_workflow(
            db=db_session,
            tenant_id=tenant.id,
            workflow_name="activate_test",
            workflow_definition={},
            created_by=user.id
        )

        assert workflow.is_active is False
        assert workflow.active_version is None

        activated_workflow = SkillWorkflowService.activate_workflow_version(
            db=db_session,
            workflow_id=workflow.id,
            tenant_id=tenant.id
        )

        assert activated_workflow.is_active is True
        assert activated_workflow.active_version == workflow.id
