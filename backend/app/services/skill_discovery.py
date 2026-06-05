"""Service for discovering and matching skills based on user intent."""

import re
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.skill_model import Skill
from app.repositories.skill_repository import SkillRepository


class SkillDiscoveryService:
    """
    Service for discovering skills and matching them to user intent.

    This service provides semantic matching of user messages to skills
    using regex pattern matching against configured intent patterns.
    """

    def __init__(self, db: Session):
        """
        Initialize the skill discovery service.

        Args:
            db: Database session for querying skills
        """
        self.db = db

    def get_skills(self, tenant_id: int) -> List[Skill]:
        """
        Retrieve all active skills for a tenant.

        Args:
            tenant_id: ID of the tenant to retrieve skills for

        Returns:
            List of active Skill objects belonging to the tenant
        """
        return SkillRepository.get_active_skills(self.db, tenant_id)

    def match_skill_by_intent(
        self, user_message: str, tenant_id: int
    ) -> Optional[Skill]:
        """
        Match a user message to a skill using semantic intent patterns.

        Performs case-insensitive regex matching against each skill's
        intent_patterns. Returns the first skill that matches.

        Args:
            user_message: The user's message to match against skill patterns
            tenant_id: ID of the tenant to search skills for

        Returns:
            The first matching Skill object, or None if no match found

        Examples:
            >>> service = SkillDiscoveryService(db)
            >>> skill = service.match_skill_by_intent(
            ...     "I need to reinstate user 12345",
            ...     tenant_id=1
            ... )
            >>> print(skill.skill_name if skill else "No match")
        """
        # Handle edge case: empty user message
        if not user_message or not user_message.strip():
            return None

        # Get all active skills for the tenant
        skills = self.get_skills(tenant_id)

        # Try to match each skill's intent patterns
        for skill in skills:
            # Handle edge cases: no intent_patterns or empty list
            if not skill.intent_patterns:
                continue

            # Check each pattern for a match
            for pattern in skill.intent_patterns:
                if not pattern:  # Skip empty patterns
                    continue

                try:
                    # Perform case-insensitive regex search
                    if re.search(pattern, user_message, re.IGNORECASE):
                        return skill
                except re.error:
                    # Skip invalid regex patterns
                    continue

        # No match found
        return None
