"""Service layer for tenant skills and workflows management."""
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.models import TenantSkill, TenantWorkflow


class SkillWorkflowService:
    """Service class for managing tenant skills and workflows."""

    @staticmethod
    def create_skill(
        db: Session,
        tenant_id: int,
        skill_name: str,
        skill_data: dict,
        description: Optional[str] = None,
        created_by: Optional[int] = None,
    ) -> TenantSkill:
        """
        Create a new skill for a tenant.

        Args:
            db: Database session
            tenant_id: ID of the tenant
            skill_name: Name of the skill
            skill_data: Skill definition (JSON)
            description: Optional skill description
            created_by: Optional user ID who created the skill

        Returns:
            Created TenantSkill instance

        Raises:
            HTTPException 409: If skill with same name already exists for tenant
        """
        # Check for duplicate skill name in tenant
        existing = db.query(TenantSkill).filter(
            TenantSkill.tenant_id == tenant_id,
            TenantSkill.skill_name == skill_name
        ).first()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Skill '{skill_name}' already exists for this tenant"
            )

        # Create new skill (version 1, inactive by default)
        skill = TenantSkill(
            tenant_id=tenant_id,
            skill_name=skill_name,
            skill_data=skill_data,
            description=description,
            version=1,
            is_active=False,
            created_by=created_by
        )

        db.add(skill)
        db.commit()
        db.refresh(skill)

        return skill

    @staticmethod
    def list_skills(
        db: Session,
        tenant_id: int,
        active_only: bool = False
    ) -> List[TenantSkill]:
        """
        List all skills for a tenant.

        Args:
            db: Database session
            tenant_id: ID of the tenant
            active_only: If True, only return active skills

        Returns:
            List of TenantSkill instances
        """
        query = db.query(TenantSkill).filter(
            TenantSkill.tenant_id == tenant_id
        )

        if active_only:
            query = query.filter(TenantSkill.is_active == True)

        # Order by skill_name, then version (descending)
        query = query.order_by(
            TenantSkill.skill_name,
            TenantSkill.version.desc()
        )

        return query.all()

    @staticmethod
    def get_skill(
        db: Session,
        skill_id: int,
        tenant_id: int
    ) -> TenantSkill:
        """
        Get a specific skill by ID.

        Args:
            db: Database session
            skill_id: ID of the skill
            tenant_id: ID of the tenant

        Returns:
            TenantSkill instance

        Raises:
            HTTPException 404: If skill not found or belongs to different tenant
        """
        skill = db.query(TenantSkill).filter(
            TenantSkill.id == skill_id,
            TenantSkill.tenant_id == tenant_id
        ).first()

        if not skill:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Skill with ID {skill_id} not found"
            )

        return skill

    @staticmethod
    def update_skill(
        db: Session,
        skill_id: int,
        tenant_id: int,
        description: Optional[str] = None,
        skill_data: Optional[dict] = None,
        is_active: Optional[bool] = None
    ) -> TenantSkill:
        """
        Update a skill.

        Args:
            db: Database session
            skill_id: ID of the skill
            tenant_id: ID of the tenant
            description: New description (if provided)
            skill_data: New skill data (if provided)
            is_active: New active status (if provided)

        Returns:
            Updated TenantSkill instance

        Raises:
            HTTPException 404: If skill not found or belongs to different tenant
        """
        skill = SkillWorkflowService.get_skill(db, skill_id, tenant_id)

        # Update only provided fields
        if description is not None:
            skill.description = description
        if skill_data is not None:
            skill.skill_data = skill_data
        if is_active is not None:
            skill.is_active = is_active

        db.commit()
        db.refresh(skill)

        return skill

    @staticmethod
    def delete_skill(
        db: Session,
        skill_id: int,
        tenant_id: int
    ) -> None:
        """
        Delete all versions of a skill.

        Args:
            db: Database session
            skill_id: ID of the skill
            tenant_id: ID of the tenant

        Raises:
            HTTPException 404: If skill not found or belongs to different tenant
        """
        # Get the skill to find its name
        skill = SkillWorkflowService.get_skill(db, skill_id, tenant_id)
        skill_name = skill.skill_name

        # Delete all versions of this skill for the tenant
        db.query(TenantSkill).filter(
            TenantSkill.tenant_id == tenant_id,
            TenantSkill.skill_name == skill_name
        ).delete()

        db.commit()

    @staticmethod
    def activate_skill_version(
        db: Session,
        skill_id: int,
        tenant_id: int
    ) -> TenantSkill:
        """
        Activate a specific skill version.

        This sets is_active=True for the target skill and is_active=False
        for all other versions of the same skill_name.

        Args:
            db: Database session
            skill_id: ID of the skill version to activate
            tenant_id: ID of the tenant

        Returns:
            Activated TenantSkill instance

        Raises:
            HTTPException 404: If skill not found or belongs to different tenant
        """
        # Get the target skill
        skill = SkillWorkflowService.get_skill(db, skill_id, tenant_id)
        skill_name = skill.skill_name

        # Deactivate all versions of this skill
        db.query(TenantSkill).filter(
            TenantSkill.tenant_id == tenant_id,
            TenantSkill.skill_name == skill_name
        ).update({"is_active": False})

        # Activate the target version
        skill.is_active = True

        db.commit()
        db.refresh(skill)

        return skill

    @staticmethod
    def create_workflow(
        db: Session,
        tenant_id: int,
        workflow_name: str,
        workflow_definition: dict,
        description: Optional[str] = None,
        created_by: Optional[int] = None,
    ) -> TenantWorkflow:
        """
        Create a new workflow for a tenant.

        Args:
            db: Database session
            tenant_id: ID of the tenant
            workflow_name: Name of the workflow
            workflow_definition: Workflow definition (JSON)
            description: Optional workflow description
            created_by: Optional user ID who created the workflow

        Returns:
            Created TenantWorkflow instance

        Raises:
            HTTPException 409: If workflow with same name already exists for tenant
        """
        # Check for duplicate workflow name in tenant
        existing = db.query(TenantWorkflow).filter(
            TenantWorkflow.tenant_id == tenant_id,
            TenantWorkflow.workflow_name == workflow_name
        ).first()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Workflow '{workflow_name}' already exists for this tenant"
            )

        # Create new workflow (version 1, inactive by default)
        workflow = TenantWorkflow(
            tenant_id=tenant_id,
            workflow_name=workflow_name,
            workflow_definition=workflow_definition,
            description=description,
            version=1,
            is_active=False,
            active_version=None,
            created_by=created_by
        )

        db.add(workflow)
        db.commit()
        db.refresh(workflow)

        return workflow

    @staticmethod
    def list_workflows(
        db: Session,
        tenant_id: int,
        active_only: bool = False
    ) -> List[TenantWorkflow]:
        """
        List all workflows for a tenant.

        Args:
            db: Database session
            tenant_id: ID of the tenant
            active_only: If True, only return active workflows

        Returns:
            List of TenantWorkflow instances
        """
        query = db.query(TenantWorkflow).filter(
            TenantWorkflow.tenant_id == tenant_id
        )

        if active_only:
            query = query.filter(TenantWorkflow.is_active == True)

        # Order by workflow_name, then version (descending)
        query = query.order_by(
            TenantWorkflow.workflow_name,
            TenantWorkflow.version.desc()
        )

        return query.all()

    @staticmethod
    def get_workflow(
        db: Session,
        workflow_id: int,
        tenant_id: int
    ) -> TenantWorkflow:
        """
        Get a specific workflow by ID.

        Args:
            db: Database session
            workflow_id: ID of the workflow
            tenant_id: ID of the tenant

        Returns:
            TenantWorkflow instance

        Raises:
            HTTPException 404: If workflow not found or belongs to different tenant
        """
        workflow = db.query(TenantWorkflow).filter(
            TenantWorkflow.id == workflow_id,
            TenantWorkflow.tenant_id == tenant_id
        ).first()

        if not workflow:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow with ID {workflow_id} not found"
            )

        return workflow

    @staticmethod
    def update_workflow(
        db: Session,
        workflow_id: int,
        tenant_id: int,
        description: Optional[str] = None,
        workflow_definition: Optional[dict] = None,
        is_active: Optional[bool] = None,
        active_version: Optional[int] = None
    ) -> TenantWorkflow:
        """
        Update a workflow.

        Args:
            db: Database session
            workflow_id: ID of the workflow
            tenant_id: ID of the tenant
            description: New description (if provided)
            workflow_definition: New workflow definition (if provided)
            is_active: New active status (if provided)
            active_version: New active version pointer (if provided)

        Returns:
            Updated TenantWorkflow instance

        Raises:
            HTTPException 404: If workflow not found or belongs to different tenant
        """
        workflow = SkillWorkflowService.get_workflow(db, workflow_id, tenant_id)

        # Update only provided fields
        if description is not None:
            workflow.description = description
        if workflow_definition is not None:
            workflow.workflow_definition = workflow_definition
        if is_active is not None:
            workflow.is_active = is_active
        if active_version is not None:
            workflow.active_version = active_version

        db.commit()
        db.refresh(workflow)

        return workflow

    @staticmethod
    def delete_workflow(
        db: Session,
        workflow_id: int,
        tenant_id: int
    ) -> None:
        """
        Delete all versions of a workflow.

        Args:
            db: Database session
            workflow_id: ID of the workflow
            tenant_id: ID of the tenant

        Raises:
            HTTPException 404: If workflow not found or belongs to different tenant
        """
        # Get the workflow to find its name
        workflow = SkillWorkflowService.get_workflow(db, workflow_id, tenant_id)
        workflow_name = workflow.workflow_name

        # Delete all versions of this workflow for the tenant
        db.query(TenantWorkflow).filter(
            TenantWorkflow.tenant_id == tenant_id,
            TenantWorkflow.workflow_name == workflow_name
        ).delete()

        db.commit()

    @staticmethod
    def activate_workflow_version(
        db: Session,
        workflow_id: int,
        tenant_id: int
    ) -> TenantWorkflow:
        """
        Activate a specific workflow version.

        This sets is_active=True for the target workflow, is_active=False for all
        other versions, and sets active_version to the target workflow's ID for all versions.

        Args:
            db: Session database session
            workflow_id: ID of the workflow version to activate
            tenant_id: ID of the tenant

        Returns:
            Activated TenantWorkflow instance

        Raises:
            HTTPException 404: If workflow not found or belongs to different tenant
        """
        # Get the target workflow
        workflow = SkillWorkflowService.get_workflow(db, workflow_id, tenant_id)
        workflow_name = workflow.workflow_name

        # Update all versions: set is_active=False and active_version to target ID
        db.query(TenantWorkflow).filter(
            TenantWorkflow.tenant_id == tenant_id,
            TenantWorkflow.workflow_name == workflow_name
        ).update({
            "is_active": False,
            "active_version": workflow_id
        })

        # Activate the target version
        workflow.is_active = True
        workflow.active_version = workflow_id

        db.commit()
        db.refresh(workflow)

        return workflow
