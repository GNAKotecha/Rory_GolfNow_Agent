"""
Tenant isolation tests for Milestone 1.

Verifies that tenant_id filtering works correctly:
1. Sessions are scoped to tenants
2. Credentials are scoped to tenants
3. Cross-tenant access is denied
4. Default tenant seed migration worked
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime

from app.db.session import Base
from app.models.models import (
    Tenant,
    User,
    UserRole,
    ApprovalStatus,
    Session as SessionModel,
)
from app.models.external_credential import ExternalCredential, CredentialType


@pytest.fixture
def db() -> Session:
    """Create test database session with tables created."""
    # Use in-memory SQLite for tests
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    session.close()


@pytest.fixture
def test_tenants(db: Session):
    """Create 2 test tenants for isolation testing."""
    tenant1 = Tenant(
        name="Tenant One",
        slug="tenant-one",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    tenant2 = Tenant(
        name="Tenant Two",
        slug="tenant-two",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    db.add(tenant1)
    db.add(tenant2)
    db.commit()
    db.refresh(tenant1)
    db.refresh(tenant2)

    return {"tenant1": tenant1, "tenant2": tenant2}


def test_tenant_scoped_session_query(db: Session, test_tenants):
    """
    Test that sessions are properly isolated by tenant_id.

    Creates 2 tenants, 2 users (one per tenant), 2 sessions (one per tenant).
    Queries sessions with each tenant_id and verifies only that tenant's session is returned.
    """
    tenant1 = test_tenants["tenant1"]
    tenant2 = test_tenants["tenant2"]

    # Create users (one per tenant)
    user1 = User(
        tenant_id=tenant1.id,
        email="user1@tenant1.com",
        name="User One",
        password_hash="hash1",
        role=UserRole.USER,
        approval_status=ApprovalStatus.APPROVED,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    user2 = User(
        tenant_id=tenant2.id,
        email="user2@tenant2.com",
        name="User Two",
        password_hash="hash2",
        role=UserRole.USER,
        approval_status=ApprovalStatus.APPROVED,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    db.add(user1)
    db.add(user2)
    db.commit()
    db.refresh(user1)
    db.refresh(user2)

    # Create sessions (one per tenant)
    session1 = SessionModel(
        tenant_id=tenant1.id,
        user_id=user1.id,
        title="Session 1",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    session2 = SessionModel(
        tenant_id=tenant2.id,
        user_id=user2.id,
        title="Session 2",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    db.add(session1)
    db.add(session2)
    db.commit()
    db.refresh(session1)
    db.refresh(session2)

    # Query sessions for tenant 1
    tenant1_sessions = db.query(SessionModel).filter(
        SessionModel.tenant_id == tenant1.id
    ).all()

    assert len(tenant1_sessions) == 1
    assert tenant1_sessions[0].id == session1.id
    assert tenant1_sessions[0].title == "Session 1"
    assert tenant1_sessions[0].tenant_id == tenant1.id

    # Query sessions for tenant 2
    tenant2_sessions = db.query(SessionModel).filter(
        SessionModel.tenant_id == tenant2.id
    ).all()

    assert len(tenant2_sessions) == 1
    assert tenant2_sessions[0].id == session2.id
    assert tenant2_sessions[0].title == "Session 2"
    assert tenant2_sessions[0].tenant_id == tenant2.id

    # Verify no overlap
    assert session1.id not in [s.id for s in tenant2_sessions]
    assert session2.id not in [s.id for s in tenant1_sessions]


def test_tenant_scoped_credential_query(db: Session, test_tenants):
    """
    Test that external credentials are properly isolated by tenant_id.

    Creates 2 tenants, 2 users (one per tenant), 2 external credentials (one per tenant).
    Queries credentials with each tenant_id and verifies only that tenant's credential is returned.
    """
    tenant1 = test_tenants["tenant1"]
    tenant2 = test_tenants["tenant2"]

    # Create users (required for credentials foreign key)
    user1 = User(
        tenant_id=tenant1.id,
        email="user1@tenant1.com",
        name="User One",
        password_hash="hash1",
        role=UserRole.USER,
        approval_status=ApprovalStatus.APPROVED,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    user2 = User(
        tenant_id=tenant2.id,
        email="user2@tenant2.com",
        name="User Two",
        password_hash="hash2",
        role=UserRole.USER,
        approval_status=ApprovalStatus.APPROVED,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    db.add(user1)
    db.add(user2)
    db.commit()
    db.refresh(user1)
    db.refresh(user2)

    # Create external credentials (one per tenant)
    cred1 = ExternalCredential(
        tenant_id=tenant1.id,
        user_id=user1.id,
        provider="brs",
        credential_type=CredentialType.OAUTH,
        secret_enc=b"encrypted_key_1",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    cred2 = ExternalCredential(
        tenant_id=tenant2.id,
        user_id=user2.id,
        provider="brs",
        credential_type=CredentialType.OAUTH,
        secret_enc=b"encrypted_key_2",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    db.add(cred1)
    db.add(cred2)
    db.commit()
    db.refresh(cred1)
    db.refresh(cred2)

    # Query credentials for tenant 1
    tenant1_creds = db.query(ExternalCredential).filter(
        ExternalCredential.tenant_id == tenant1.id
    ).all()

    assert len(tenant1_creds) == 1
    assert tenant1_creds[0].id == cred1.id
    assert tenant1_creds[0].secret_enc == b"encrypted_key_1"
    assert tenant1_creds[0].tenant_id == tenant1.id

    # Query credentials for tenant 2
    tenant2_creds = db.query(ExternalCredential).filter(
        ExternalCredential.tenant_id == tenant2.id
    ).all()

    assert len(tenant2_creds) == 1
    assert tenant2_creds[0].id == cred2.id
    assert tenant2_creds[0].secret_enc == b"encrypted_key_2"
    assert tenant2_creds[0].tenant_id == tenant2.id

    # Verify no overlap
    assert cred1.id not in [c.id for c in tenant2_creds]
    assert cred2.id not in [c.id for c in tenant1_creds]


def test_cross_tenant_access_denial(db: Session, test_tenants):
    """
    Test that cross-tenant access is properly denied.

    Creates tenant 1 with a session, then tries to access that session
    using tenant 2's tenant_id. Verifies query returns None (not found).
    """
    tenant1 = test_tenants["tenant1"]
    tenant2 = test_tenants["tenant2"]

    # Create user and session for tenant 1
    user1 = User(
        tenant_id=tenant1.id,
        email="user1@tenant1.com",
        name="User One",
        password_hash="hash1",
        role=UserRole.USER,
        approval_status=ApprovalStatus.APPROVED,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(user1)
    db.commit()
    db.refresh(user1)

    session1 = SessionModel(
        tenant_id=tenant1.id,
        user_id=user1.id,
        title="Tenant 1 Session",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(session1)
    db.commit()
    db.refresh(session1)

    session1_id = session1.id

    # Try to access tenant 1's session using tenant 2's tenant_id
    cross_tenant_query = db.query(SessionModel).filter(
        SessionModel.id == session1_id,
        SessionModel.tenant_id == tenant2.id
    ).first()

    # Should return None (not found)
    assert cross_tenant_query is None

    # Verify the session still exists when queried with correct tenant_id
    correct_query = db.query(SessionModel).filter(
        SessionModel.id == session1_id,
        SessionModel.tenant_id == tenant1.id
    ).first()

    assert correct_query is not None
    assert correct_query.id == session1_id
    assert correct_query.tenant_id == tenant1.id

    # Verify no data leakage - tenant 2 cannot see any tenant 1 sessions
    all_tenant2_sessions = db.query(SessionModel).filter(
        SessionModel.tenant_id == tenant2.id
    ).all()

    assert len(all_tenant2_sessions) == 0
    assert session1_id not in [s.id for s in all_tenant2_sessions]


def test_default_tenant_seed_migration(db: Session):
    """
    Test that default tenant seed migration behavior works correctly.

    This simulates what the migration does:
    1. Create default tenant with id=1, slug='default'
    2. Create test users and assign to tenant_id=1
    3. Create test sessions and assign to tenant_id=1
    4. Verify all records properly reference tenant_id=1
    """
    # Simulate migration: Create default tenant
    default_tenant = Tenant(
        id=1,
        name="Default Organization",
        slug="default",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(default_tenant)
    db.commit()
    db.refresh(default_tenant)

    # Verify default tenant exists
    assert default_tenant is not None, "Default tenant not found"
    assert default_tenant.id == 1
    assert default_tenant.slug == "default"
    assert default_tenant.name == "Default Organization"

    # Simulate migration: Create user assigned to default tenant
    user = User(
        tenant_id=1,
        email="migrated_user@example.com",
        name="Migrated User",
        password_hash="hash",
        role=UserRole.USER,
        approval_status=ApprovalStatus.APPROVED,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Simulate migration: Create session assigned to default tenant
    session = SessionModel(
        tenant_id=1,
        user_id=user.id,
        title="Migrated Session",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # Verify all records have tenant_id=1
    assert user.tenant_id == 1, f"User has tenant_id={user.tenant_id}, expected 1"
    assert session.tenant_id == 1, f"Session has tenant_id={session.tenant_id}, expected 1"

    # Verify foreign key relationship works
    assert user.tenant.id == 1
    assert user.tenant.slug == "default"
    assert session.tenant.id == 1
    assert session.tenant.slug == "default"

    # Verify default tenant has proper timestamps
    assert default_tenant.created_at is not None
    assert default_tenant.updated_at is not None
    assert isinstance(default_tenant.created_at, datetime)
    assert isinstance(default_tenant.updated_at, datetime)
