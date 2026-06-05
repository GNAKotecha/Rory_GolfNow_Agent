"""Tests for SkillDiscoveryService."""

import pytest
from sqlalchemy.orm import Session

from app.services.skill_discovery import SkillDiscoveryService
from app.repositories.skill_repository import SkillRepository
from app.models.skill_model import Skill


@pytest.fixture
def skill_discovery_service(db_session: Session) -> SkillDiscoveryService:
    """Create a SkillDiscoveryService instance for testing."""
    return SkillDiscoveryService(db_session)


@pytest.fixture
def test_skills(db_session: Session) -> dict:
    """
    Create test skills with various intent patterns.

    Returns:
        Dictionary with skill names as keys and Skill objects as values
    """
    # Skill 1: User reinstatement with multiple patterns
    reinstate_skill = SkillRepository.create_skill(
        db=db_session,
        skill_data={
            "skill_name": "REINSTATE_USER",
            "description": "Reinstate a suspended or deleted user",
            "skill_data": {"workflow": "user_management"},
            "is_active": True,
            "intent_patterns": [
                r"reinstate.*user",
                r"restore.*account",
                r"reactivate.*member",
            ],
        },
        tenant_id=1,
        created_by=1,
    )

    # Skill 2: Booking management
    booking_skill = SkillRepository.create_skill(
        db=db_session,
        skill_data={
            "skill_name": "MANAGE_BOOKING",
            "description": "Create or modify golf bookings",
            "skill_data": {"workflow": "booking"},
            "is_active": True,
            "intent_patterns": [
                r"create.*booking",
                r"book.*tee time",
                r"reserve.*slot",
            ],
        },
        tenant_id=1,
        created_by=1,
    )

    # Skill 3: Inactive skill (should not be matched)
    inactive_skill = SkillRepository.create_skill(
        db=db_session,
        skill_data={
            "skill_name": "INACTIVE_SKILL",
            "description": "An inactive skill",
            "skill_data": {},
            "is_active": False,
            "intent_patterns": [r"test.*pattern"],
        },
        tenant_id=1,
        created_by=1,
    )

    # Skill 4: Skill with empty intent patterns
    empty_patterns_skill = SkillRepository.create_skill(
        db=db_session,
        skill_data={
            "skill_name": "EMPTY_PATTERNS",
            "description": "Skill with no patterns",
            "skill_data": {},
            "is_active": True,
            "intent_patterns": [],
        },
        tenant_id=1,
        created_by=1,
    )

    # Skill 5: Skill for tenant 2 (different tenant)
    other_tenant_skill = SkillRepository.create_skill(
        db=db_session,
        skill_data={
            "skill_name": "OTHER_TENANT_SKILL",
            "description": "Skill for different tenant",
            "skill_data": {},
            "is_active": True,
            "intent_patterns": [r"other.*tenant"],
        },
        tenant_id=2,
        created_by=1,
    )

    return {
        "reinstate": reinstate_skill,
        "booking": booking_skill,
        "inactive": inactive_skill,
        "empty_patterns": empty_patterns_skill,
        "other_tenant": other_tenant_skill,
    }


class TestGetSkills:
    """Tests for get_skills method."""

    def test_get_skills_returns_active_skills_only(
        self, skill_discovery_service: SkillDiscoveryService, test_skills: dict
    ):
        """Test that get_skills returns only active skills."""
        skills = skill_discovery_service.get_skills(tenant_id=1)

        # Should return 3 active skills (reinstate, booking, empty_patterns)
        # but not the inactive one
        assert len(skills) == 3

        skill_names = {skill.skill_name for skill in skills}
        assert "REINSTATE_USER" in skill_names
        assert "MANAGE_BOOKING" in skill_names
        assert "EMPTY_PATTERNS" in skill_names
        assert "INACTIVE_SKILL" not in skill_names

    def test_get_skills_filters_by_tenant(
        self, skill_discovery_service: SkillDiscoveryService, test_skills: dict
    ):
        """Test that get_skills filters skills by tenant."""
        # Get skills for tenant 1
        tenant1_skills = skill_discovery_service.get_skills(tenant_id=1)
        tenant1_names = {skill.skill_name for skill in tenant1_skills}

        # Should not include tenant 2's skill
        assert "OTHER_TENANT_SKILL" not in tenant1_names

        # Get skills for tenant 2
        tenant2_skills = skill_discovery_service.get_skills(tenant_id=2)
        tenant2_names = {skill.skill_name for skill in tenant2_skills}

        # Should include tenant 2's skill
        assert "OTHER_TENANT_SKILL" in tenant2_names
        # Should not include tenant 1's skills
        assert "REINSTATE_USER" not in tenant2_names
        assert "MANAGE_BOOKING" not in tenant2_names

    def test_get_skills_returns_empty_list_for_nonexistent_tenant(
        self, skill_discovery_service: SkillDiscoveryService
    ):
        """Test that get_skills returns empty list for tenant with no skills."""
        skills = skill_discovery_service.get_skills(tenant_id=999)
        assert skills == []


class TestMatchSkillByIntent:
    """Tests for match_skill_by_intent method."""

    def test_match_exact_pattern(
        self, skill_discovery_service: SkillDiscoveryService, test_skills: dict
    ):
        """Test matching with exact pattern match."""
        match = skill_discovery_service.match_skill_by_intent(
            "reinstate user 12345", tenant_id=1
        )

        assert match is not None
        assert match.skill_name == "REINSTATE_USER"

    def test_match_partial_pattern(
        self, skill_discovery_service: SkillDiscoveryService, test_skills: dict
    ):
        """Test matching with partial pattern match."""
        match = skill_discovery_service.match_skill_by_intent(
            "I need to reinstate the user account", tenant_id=1
        )

        assert match is not None
        assert match.skill_name == "REINSTATE_USER"

    def test_case_insensitive_matching(
        self, skill_discovery_service: SkillDiscoveryService, test_skills: dict
    ):
        """Test that matching is case-insensitive."""
        # Test uppercase
        match_upper = skill_discovery_service.match_skill_by_intent(
            "REINSTATE USER", tenant_id=1
        )
        assert match_upper is not None
        assert match_upper.skill_name == "REINSTATE_USER"

        # Test mixed case
        match_mixed = skill_discovery_service.match_skill_by_intent(
            "ReInStAtE uSeR", tenant_id=1
        )
        assert match_mixed is not None
        assert match_mixed.skill_name == "REINSTATE_USER"

        # Test lowercase
        match_lower = skill_discovery_service.match_skill_by_intent(
            "reinstate user", tenant_id=1
        )
        assert match_lower is not None
        assert match_lower.skill_name == "REINSTATE_USER"

    def test_multiple_patterns_per_skill(
        self, skill_discovery_service: SkillDiscoveryService, test_skills: dict
    ):
        """Test that skills with multiple patterns match any of them."""
        # Test first pattern
        match1 = skill_discovery_service.match_skill_by_intent(
            "reinstate user", tenant_id=1
        )
        assert match1 is not None
        assert match1.skill_name == "REINSTATE_USER"

        # Test second pattern
        match2 = skill_discovery_service.match_skill_by_intent(
            "restore account", tenant_id=1
        )
        assert match2 is not None
        assert match2.skill_name == "REINSTATE_USER"

        # Test third pattern
        match3 = skill_discovery_service.match_skill_by_intent(
            "reactivate member", tenant_id=1
        )
        assert match3 is not None
        assert match3.skill_name == "REINSTATE_USER"

    def test_first_match_wins(
        self,
        skill_discovery_service: SkillDiscoveryService,
        test_skills: dict,
        db_session: Session,
    ):
        """Test that the first matching skill is returned."""
        # Create a second skill with overlapping pattern
        second_skill = SkillRepository.create_skill(
            db=db_session,
            skill_data={
                "skill_name": "SECOND_MATCH",
                "description": "Second skill with overlapping pattern",
                "skill_data": {},
                "is_active": True,
                "intent_patterns": [r"reinstate.*user"],
            },
            tenant_id=1,
            created_by=1,
        )

        # Match should return one of them (depends on query order)
        match = skill_discovery_service.match_skill_by_intent(
            "reinstate user", tenant_id=1
        )

        assert match is not None
        # Should be one of the two skills with matching pattern
        assert match.skill_name in ["REINSTATE_USER", "SECOND_MATCH"]

    def test_no_match_returns_none(
        self, skill_discovery_service: SkillDiscoveryService, test_skills: dict
    ):
        """Test that non-matching message returns None."""
        match = skill_discovery_service.match_skill_by_intent(
            "this does not match any pattern", tenant_id=1
        )

        assert match is None

    def test_empty_user_message_returns_none(
        self, skill_discovery_service: SkillDiscoveryService, test_skills: dict
    ):
        """Test that empty user message returns None."""
        # Empty string
        match_empty = skill_discovery_service.match_skill_by_intent("", tenant_id=1)
        assert match_empty is None

        # Whitespace only
        match_whitespace = skill_discovery_service.match_skill_by_intent(
            "   ", tenant_id=1
        )
        assert match_whitespace is None

    def test_empty_intent_patterns_returns_none(
        self, skill_discovery_service: SkillDiscoveryService, test_skills: dict
    ):
        """Test that skill with empty intent_patterns is not matched."""
        match = skill_discovery_service.match_skill_by_intent(
            "any message at all", tenant_id=1
        )

        # Should not match EMPTY_PATTERNS skill
        if match is not None:
            assert match.skill_name != "EMPTY_PATTERNS"

    def test_null_intent_patterns_returns_none(
        self,
        skill_discovery_service: SkillDiscoveryService,
        db_session: Session,
    ):
        """Test that skill with null intent_patterns is not matched."""
        # Create skill with None intent_patterns
        null_skill = SkillRepository.create_skill(
            db=db_session,
            skill_data={
                "skill_name": "NULL_PATTERNS",
                "description": "Skill with null patterns",
                "skill_data": {},
                "is_active": True,
                # Don't set intent_patterns at all
            },
            tenant_id=1,
            created_by=1,
        )

        match = skill_discovery_service.match_skill_by_intent(
            "any message", tenant_id=1
        )

        # Should not match NULL_PATTERNS skill
        if match is not None:
            assert match.skill_name != "NULL_PATTERNS"

    def test_tenant_isolation_in_matching(
        self, skill_discovery_service: SkillDiscoveryService, test_skills: dict
    ):
        """Test that matching respects tenant isolation."""
        # Try to match tenant 2's pattern while querying tenant 1
        match = skill_discovery_service.match_skill_by_intent(
            "other tenant skill", tenant_id=1
        )

        # Should not match tenant 2's skill
        assert match is None

        # Now try with correct tenant
        match_correct_tenant = skill_discovery_service.match_skill_by_intent(
            "other tenant skill", tenant_id=2
        )

        assert match_correct_tenant is not None
        assert match_correct_tenant.skill_name == "OTHER_TENANT_SKILL"

    def test_inactive_skill_not_matched(
        self, skill_discovery_service: SkillDiscoveryService, test_skills: dict
    ):
        """Test that inactive skills are not matched."""
        match = skill_discovery_service.match_skill_by_intent(
            "test pattern", tenant_id=1
        )

        # Should not match INACTIVE_SKILL
        assert match is None

    def test_invalid_regex_pattern_skipped(
        self,
        skill_discovery_service: SkillDiscoveryService,
        db_session: Session,
    ):
        """Test that invalid regex patterns are gracefully skipped."""
        # Create skill with invalid regex pattern
        invalid_skill = SkillRepository.create_skill(
            db=db_session,
            skill_data={
                "skill_name": "INVALID_REGEX",
                "description": "Skill with invalid regex",
                "skill_data": {},
                "is_active": True,
                "intent_patterns": [
                    r"[invalid(regex",  # Invalid regex
                    r"valid.*pattern",  # Valid pattern after invalid one
                ],
            },
            tenant_id=1,
            created_by=1,
        )

        # Should skip invalid pattern and try the valid one
        match = skill_discovery_service.match_skill_by_intent(
            "valid pattern match", tenant_id=1
        )

        assert match is not None
        assert match.skill_name == "INVALID_REGEX"

        # Invalid pattern should be skipped without error
        no_match = skill_discovery_service.match_skill_by_intent(
            "something else", tenant_id=1
        )
        # Just checking it doesn't crash
