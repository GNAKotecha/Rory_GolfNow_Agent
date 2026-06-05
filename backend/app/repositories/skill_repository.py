"""Repository for Skill database operations with tenant isolation."""

from typing import List, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from app.models.skill_model import Skill


class SkillRepository:
    """Repository for managing tenant-scoped skills with CRUD operations."""

    @staticmethod
    def get_by_id(db: Session, skill_id: int, tenant_id: int) -> Optional[Skill]:
        """
        Get a skill by ID with tenant isolation.

        Args:
            db: Database session
            skill_id: Skill ID to retrieve
            tenant_id: Tenant ID for isolation

        Returns:
            Skill if found and belongs to tenant, None otherwise
        """
        return (
            db.query(Skill)
            .filter(Skill.id == skill_id, Skill.tenant_id == tenant_id)
            .first()
        )

    @staticmethod
    def get_by_tenant(
        db: Session, tenant_id: int, is_active: Optional[bool] = None
    ) -> List[Skill]:
        """
        Get all skills for a tenant, optionally filtered by active status.

        Args:
            db: Database session
            tenant_id: Tenant ID to retrieve skills for
            is_active: Optional filter for active (True), inactive (False), or all (None)

        Returns:
            List of skills belonging to the tenant
        """
        query = db.query(Skill).filter(Skill.tenant_id == tenant_id)

        if is_active is not None:
            query = query.filter(Skill.is_active == is_active)

        return query.order_by(Skill.created_at.desc()).all()

    @staticmethod
    def get_active_skills(db: Session, tenant_id: int) -> List[Skill]:
        """
        Get all active skills for a tenant.

        Args:
            db: Database session
            tenant_id: Tenant ID to retrieve skills for

        Returns:
            List of active skills belonging to the tenant
        """
        return SkillRepository.get_by_tenant(db, tenant_id, is_active=True)

    @staticmethod
    def create_skill(
        db: Session, skill_data: dict, tenant_id: int, created_by: int
    ) -> Skill:
        """
        Create a new skill for a tenant.

        Args:
            db: Database session
            skill_data: Dictionary containing skill fields:
                - skill_name (required): Name of the skill
                - description (optional): Skill documentation
                - skill_data (optional): Skill definition/config
                - version (optional): Version number, defaults to 1
                - is_active (optional): Whether skill is active, defaults to False
                - intent_patterns (optional): Semantic matching patterns
            tenant_id: Tenant ID that owns this skill
            created_by: User ID who created the skill

        Returns:
            Newly created Skill instance

        Raises:
            ValueError: If required fields are missing
        """
        if "skill_name" not in skill_data:
            raise ValueError("skill_name is required")

        skill = Skill(
            tenant_id=tenant_id,
            skill_name=skill_data["skill_name"],
            description=skill_data.get("description"),
            skill_data=skill_data.get("skill_data", {}),
            version=skill_data.get("version", 1),
            is_active=skill_data.get("is_active", False),
            intent_patterns=skill_data.get("intent_patterns", []),
            created_by=created_by,
        )

        db.add(skill)
        db.commit()
        db.refresh(skill)

        return skill

    @staticmethod
    def update_skill(
        db: Session, skill_id: int, tenant_id: int, skill_data: dict
    ) -> Optional[Skill]:
        """
        Update an existing skill with tenant isolation.

        Args:
            db: Database session
            skill_id: Skill ID to update
            tenant_id: Tenant ID for isolation
            skill_data: Dictionary containing fields to update:
                - skill_name (optional): New skill name
                - description (optional): New description
                - skill_data (optional): New skill definition
                - version (optional): New version number
                - is_active (optional): New active status
                - intent_patterns (optional): New intent patterns

        Returns:
            Updated Skill if found and belongs to tenant, None otherwise
        """
        skill = SkillRepository.get_by_id(db, skill_id, tenant_id)

        if not skill:
            return None

        # Update provided fields
        if "skill_name" in skill_data:
            skill.skill_name = skill_data["skill_name"]
        if "description" in skill_data:
            skill.description = skill_data["description"]
        if "skill_data" in skill_data:
            skill.skill_data = skill_data["skill_data"]
        if "version" in skill_data:
            skill.version = skill_data["version"]
        if "is_active" in skill_data:
            skill.is_active = skill_data["is_active"]
        if "intent_patterns" in skill_data:
            skill.intent_patterns = skill_data["intent_patterns"]

        skill.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(skill)

        return skill

    @staticmethod
    def delete_skill(db: Session, skill_id: int, tenant_id: int) -> bool:
        """
        Delete a skill with tenant isolation.

        Args:
            db: Database session
            skill_id: Skill ID to delete
            tenant_id: Tenant ID for isolation

        Returns:
            True if skill was deleted, False if not found or doesn't belong to tenant
        """
        skill = SkillRepository.get_by_id(db, skill_id, tenant_id)

        if not skill:
            return False

        db.delete(skill)
        db.commit()

        return True
