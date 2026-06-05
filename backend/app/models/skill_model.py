"""Skill model for tenant-scoped custom skills.

This module provides the Skill model which is an alias for TenantSkill,
providing a clean interface for the skill invocation system.
"""

# Import TenantSkill and expose it as Skill for the skill invocation system
from app.models.models import TenantSkill as Skill

__all__ = ["Skill"]
