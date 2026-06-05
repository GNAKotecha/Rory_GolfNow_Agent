"""Tests for SkillRepository database operations."""

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.db.session import Base
from app.models.models import Tenant, User
from app.models.skill_model import Skill
from app.repositories.skill_repository import SkillRepository


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test."""
    # Use in-memory SQLite for fast tests
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    session.close()


@pytest.fixture
def tenant1(db_session: Session):
    """Create test tenant 1."""
    tenant = Tenant(name="Test Tenant 1", slug="test-tenant-1")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


@pytest.fixture
def tenant2(db_session: Session):
    """Create test tenant 2."""
    tenant = Tenant(name="Test Tenant 2", slug="test-tenant-2")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


@pytest.fixture
def user1(db_session: Session, tenant1: Tenant):
    """Create test user 1."""
    user = User(
        name="User 1",
        email="user1@test.com",
        password_hash="fake_hash",
        tenant_id=tenant1.id,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def user2(db_session: Session, tenant2: Tenant):
    """Create test user 2."""
    user = User(
        name="User 2",
        email="user2@test.com",
        password_hash="fake_hash",
        tenant_id=tenant2.id,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


# ==============================================================================
# Create Skill Tests
# ==============================================================================

def test_create_skill_minimal(db_session: Session, tenant1: Tenant, user1: User):
    """Test creating a skill with minimal required fields."""
    skill_data = {"skill_name": "test_skill"}

    skill = SkillRepository.create_skill(
        db_session, skill_data, tenant1.id, user1.id
    )

    assert skill.id is not None
    assert skill.skill_name == "test_skill"
    assert skill.tenant_id == tenant1.id
    assert skill.created_by == user1.id
    assert skill.version == 1
    assert skill.is_active is False
    assert skill.skill_data == {}
    assert skill.intent_patterns == []
    assert skill.description is None


def test_create_skill_full(db_session: Session, tenant1: Tenant, user1: User):
    """Test creating a skill with all fields."""
    skill_data = {
        "skill_name": "advanced_skill",
        "description": "An advanced test skill",
        "skill_data": {"type": "workflow", "steps": ["step1", "step2"]},
        "version": 2,
        "is_active": True,
        "intent_patterns": ["create club", "setup golf club"],
    }

    skill = SkillRepository.create_skill(
        db_session, skill_data, tenant1.id, user1.id
    )

    assert skill.skill_name == "advanced_skill"
    assert skill.description == "An advanced test skill"
    assert skill.skill_data == {"type": "workflow", "steps": ["step1", "step2"]}
    assert skill.version == 2
    assert skill.is_active is True
    assert skill.intent_patterns == ["create club", "setup golf club"]


def test_create_skill_missing_name(db_session: Session, tenant1: Tenant, user1: User):
    """Test creating a skill without required skill_name raises ValueError."""
    skill_data = {"description": "Missing name"}

    with pytest.raises(ValueError, match="skill_name is required"):
        SkillRepository.create_skill(db_session, skill_data, tenant1.id, user1.id)


# ==============================================================================
# Get Skill Tests
# ==============================================================================

def test_get_by_id_success(db_session: Session, tenant1: Tenant, user1: User):
    """Test retrieving a skill by ID."""
    skill_data = {"skill_name": "test_skill"}
    created_skill = SkillRepository.create_skill(
        db_session, skill_data, tenant1.id, user1.id
    )

    retrieved_skill = SkillRepository.get_by_id(db_session, created_skill.id, tenant1.id)

    assert retrieved_skill is not None
    assert retrieved_skill.id == created_skill.id
    assert retrieved_skill.skill_name == "test_skill"


def test_get_by_id_wrong_tenant(
    db_session: Session, tenant1: Tenant, tenant2: Tenant, user1: User
):
    """Test retrieving a skill from another tenant returns None."""
    skill_data = {"skill_name": "tenant1_skill"}
    created_skill = SkillRepository.create_skill(
        db_session, skill_data, tenant1.id, user1.id
    )

    # Try to retrieve from tenant2
    retrieved_skill = SkillRepository.get_by_id(db_session, created_skill.id, tenant2.id)

    assert retrieved_skill is None


def test_get_by_id_not_found(db_session: Session, tenant1: Tenant):
    """Test retrieving non-existent skill returns None."""
    retrieved_skill = SkillRepository.get_by_id(db_session, 99999, tenant1.id)

    assert retrieved_skill is None


# ==============================================================================
# Get By Tenant Tests
# ==============================================================================

def test_get_by_tenant_all(db_session: Session, tenant1: Tenant, user1: User):
    """Test retrieving all skills for a tenant."""
    # Create multiple skills
    SkillRepository.create_skill(
        db_session, {"skill_name": "skill1", "is_active": True}, tenant1.id, user1.id
    )
    SkillRepository.create_skill(
        db_session, {"skill_name": "skill2", "is_active": False}, tenant1.id, user1.id
    )
    SkillRepository.create_skill(
        db_session, {"skill_name": "skill3", "is_active": True}, tenant1.id, user1.id
    )

    skills = SkillRepository.get_by_tenant(db_session, tenant1.id)

    assert len(skills) == 3
    skill_names = {skill.skill_name for skill in skills}
    assert skill_names == {"skill1", "skill2", "skill3"}


def test_get_by_tenant_active_only(db_session: Session, tenant1: Tenant, user1: User):
    """Test retrieving only active skills for a tenant."""
    SkillRepository.create_skill(
        db_session, {"skill_name": "active1", "is_active": True}, tenant1.id, user1.id
    )
    SkillRepository.create_skill(
        db_session, {"skill_name": "inactive1", "is_active": False}, tenant1.id, user1.id
    )
    SkillRepository.create_skill(
        db_session, {"skill_name": "active2", "is_active": True}, tenant1.id, user1.id
    )

    skills = SkillRepository.get_by_tenant(db_session, tenant1.id, is_active=True)

    assert len(skills) == 2
    skill_names = {skill.skill_name for skill in skills}
    assert skill_names == {"active1", "active2"}


def test_get_by_tenant_inactive_only(db_session: Session, tenant1: Tenant, user1: User):
    """Test retrieving only inactive skills for a tenant."""
    SkillRepository.create_skill(
        db_session, {"skill_name": "active1", "is_active": True}, tenant1.id, user1.id
    )
    SkillRepository.create_skill(
        db_session, {"skill_name": "inactive1", "is_active": False}, tenant1.id, user1.id
    )
    SkillRepository.create_skill(
        db_session, {"skill_name": "inactive2", "is_active": False}, tenant1.id, user1.id
    )

    skills = SkillRepository.get_by_tenant(db_session, tenant1.id, is_active=False)

    assert len(skills) == 2
    skill_names = {skill.skill_name for skill in skills}
    assert skill_names == {"inactive1", "inactive2"}


def test_get_by_tenant_empty(db_session: Session, tenant1: Tenant):
    """Test retrieving skills for tenant with no skills."""
    skills = SkillRepository.get_by_tenant(db_session, tenant1.id)

    assert len(skills) == 0


def test_get_by_tenant_isolation(
    db_session: Session, tenant1: Tenant, tenant2: Tenant, user1: User, user2: User
):
    """Test tenant isolation: tenants only see their own skills."""
    # Create skills for tenant1
    SkillRepository.create_skill(
        db_session, {"skill_name": "tenant1_skill"}, tenant1.id, user1.id
    )

    # Create skills for tenant2
    SkillRepository.create_skill(
        db_session, {"skill_name": "tenant2_skill"}, tenant2.id, user2.id
    )

    # Verify tenant1 only sees their skill
    tenant1_skills = SkillRepository.get_by_tenant(db_session, tenant1.id)
    assert len(tenant1_skills) == 1
    assert tenant1_skills[0].skill_name == "tenant1_skill"

    # Verify tenant2 only sees their skill
    tenant2_skills = SkillRepository.get_by_tenant(db_session, tenant2.id)
    assert len(tenant2_skills) == 1
    assert tenant2_skills[0].skill_name == "tenant2_skill"


# ==============================================================================
# Get Active Skills Tests
# ==============================================================================

def test_get_active_skills(db_session: Session, tenant1: Tenant, user1: User):
    """Test retrieving only active skills."""
    SkillRepository.create_skill(
        db_session, {"skill_name": "active1", "is_active": True}, tenant1.id, user1.id
    )
    SkillRepository.create_skill(
        db_session, {"skill_name": "inactive1", "is_active": False}, tenant1.id, user1.id
    )

    active_skills = SkillRepository.get_active_skills(db_session, tenant1.id)

    assert len(active_skills) == 1
    assert active_skills[0].skill_name == "active1"
    assert active_skills[0].is_active is True


# ==============================================================================
# Update Skill Tests
# ==============================================================================

def test_update_skill_name(db_session: Session, tenant1: Tenant, user1: User):
    """Test updating skill name."""
    skill = SkillRepository.create_skill(
        db_session, {"skill_name": "old_name"}, tenant1.id, user1.id
    )

    updated_skill = SkillRepository.update_skill(
        db_session, skill.id, tenant1.id, {"skill_name": "new_name"}
    )

    assert updated_skill is not None
    assert updated_skill.skill_name == "new_name"


def test_update_skill_multiple_fields(db_session: Session, tenant1: Tenant, user1: User):
    """Test updating multiple skill fields."""
    skill = SkillRepository.create_skill(
        db_session,
        {"skill_name": "test_skill", "is_active": False, "version": 1},
        tenant1.id,
        user1.id,
    )

    updated_skill = SkillRepository.update_skill(
        db_session,
        skill.id,
        tenant1.id,
        {
            "description": "Updated description",
            "is_active": True,
            "version": 2,
            "intent_patterns": ["new pattern"],
        },
    )

    assert updated_skill is not None
    assert updated_skill.description == "Updated description"
    assert updated_skill.is_active is True
    assert updated_skill.version == 2
    assert updated_skill.intent_patterns == ["new pattern"]


def test_update_skill_wrong_tenant(
    db_session: Session, tenant1: Tenant, tenant2: Tenant, user1: User
):
    """Test updating skill from wrong tenant returns None."""
    skill = SkillRepository.create_skill(
        db_session, {"skill_name": "test_skill"}, tenant1.id, user1.id
    )

    # Try to update from tenant2
    updated_skill = SkillRepository.update_skill(
        db_session, skill.id, tenant2.id, {"skill_name": "hacked_name"}
    )

    assert updated_skill is None

    # Verify original skill unchanged
    original_skill = SkillRepository.get_by_id(db_session, skill.id, tenant1.id)
    assert original_skill.skill_name == "test_skill"


def test_update_skill_not_found(db_session: Session, tenant1: Tenant):
    """Test updating non-existent skill returns None."""
    updated_skill = SkillRepository.update_skill(
        db_session, 99999, tenant1.id, {"skill_name": "new_name"}
    )

    assert updated_skill is None


# ==============================================================================
# Delete Skill Tests
# ==============================================================================

def test_delete_skill_success(db_session: Session, tenant1: Tenant, user1: User):
    """Test deleting a skill."""
    skill = SkillRepository.create_skill(
        db_session, {"skill_name": "test_skill"}, tenant1.id, user1.id
    )

    result = SkillRepository.delete_skill(db_session, skill.id, tenant1.id)

    assert result is True

    # Verify skill is deleted
    deleted_skill = SkillRepository.get_by_id(db_session, skill.id, tenant1.id)
    assert deleted_skill is None


def test_delete_skill_wrong_tenant(
    db_session: Session, tenant1: Tenant, tenant2: Tenant, user1: User
):
    """Test deleting skill from wrong tenant returns False."""
    skill = SkillRepository.create_skill(
        db_session, {"skill_name": "test_skill"}, tenant1.id, user1.id
    )

    # Try to delete from tenant2
    result = SkillRepository.delete_skill(db_session, skill.id, tenant2.id)

    assert result is False

    # Verify skill still exists
    existing_skill = SkillRepository.get_by_id(db_session, skill.id, tenant1.id)
    assert existing_skill is not None


def test_delete_skill_not_found(db_session: Session, tenant1: Tenant):
    """Test deleting non-existent skill returns False."""
    result = SkillRepository.delete_skill(db_session, 99999, tenant1.id)

    assert result is False


# ==============================================================================
# Version Handling Tests
# ==============================================================================

def test_multiple_versions_same_skill(db_session: Session, tenant1: Tenant, user1: User):
    """Test creating multiple versions of the same skill."""
    # Create version 1
    v1 = SkillRepository.create_skill(
        db_session,
        {"skill_name": "test_skill", "version": 1, "is_active": True},
        tenant1.id,
        user1.id,
    )

    # Create version 2
    v2 = SkillRepository.create_skill(
        db_session,
        {"skill_name": "test_skill", "version": 2, "is_active": False},
        tenant1.id,
        user1.id,
    )

    # Both versions should exist
    skills = SkillRepository.get_by_tenant(db_session, tenant1.id)
    assert len(skills) == 2

    versions = {skill.version for skill in skills}
    assert versions == {1, 2}


def test_get_active_skills_respects_version(
    db_session: Session, tenant1: Tenant, user1: User
):
    """Test that get_active_skills returns correct versions."""
    # Create version 1 (inactive)
    SkillRepository.create_skill(
        db_session,
        {"skill_name": "test_skill", "version": 1, "is_active": False},
        tenant1.id,
        user1.id,
    )

    # Create version 2 (active)
    v2 = SkillRepository.create_skill(
        db_session,
        {"skill_name": "test_skill", "version": 2, "is_active": True},
        tenant1.id,
        user1.id,
    )

    # Only version 2 should be active
    active_skills = SkillRepository.get_active_skills(db_session, tenant1.id)
    assert len(active_skills) == 1
    assert active_skills[0].version == 2


# ==============================================================================
# Intent Patterns Tests
# ==============================================================================

def test_intent_patterns_storage(db_session: Session, tenant1: Tenant, user1: User):
    """Test storing and retrieving intent patterns."""
    patterns = [
        "create new club",
        "setup golf club",
        "initialize club configuration",
    ]

    skill = SkillRepository.create_skill(
        db_session,
        {"skill_name": "club_creation", "intent_patterns": patterns},
        tenant1.id,
        user1.id,
    )

    assert skill.intent_patterns == patterns

    # Verify persistence
    retrieved = SkillRepository.get_by_id(db_session, skill.id, tenant1.id)
    assert retrieved.intent_patterns == patterns


def test_intent_patterns_empty_list(db_session: Session, tenant1: Tenant, user1: User):
    """Test skill with empty intent patterns."""
    skill = SkillRepository.create_skill(
        db_session,
        {"skill_name": "no_patterns", "intent_patterns": []},
        tenant1.id,
        user1.id,
    )

    assert skill.intent_patterns == []


def test_intent_patterns_update(db_session: Session, tenant1: Tenant, user1: User):
    """Test updating intent patterns."""
    skill = SkillRepository.create_skill(
        db_session,
        {"skill_name": "test_skill", "intent_patterns": ["old pattern"]},
        tenant1.id,
        user1.id,
    )

    updated = SkillRepository.update_skill(
        db_session,
        skill.id,
        tenant1.id,
        {"intent_patterns": ["new pattern 1", "new pattern 2"]},
    )

    assert updated.intent_patterns == ["new pattern 1", "new pattern 2"]
