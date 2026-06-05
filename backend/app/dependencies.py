"""Dependency injection providers for FastAPI."""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.skill_discovery import SkillDiscoveryService


def get_skill_discovery_service(db: Session = Depends(get_db)) -> SkillDiscoveryService:
    """
    Dependency provider for SkillDiscoveryService.

    Args:
        db: Database session (injected by FastAPI)

    Returns:
        Initialized SkillDiscoveryService instance
    """
    return SkillDiscoveryService(db)
