"""Tests for User model RBAC authentication fields (Phase 6 Task 2)."""
import pytest
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.models import User, UserRole, ApprovalStatus, Tenant
from app.core.rbac.models import AuthSource


class TestUserRBACFields:
    """Test User model RBAC fields for three-way authentication."""

    @pytest.fixture
    def tenant(self, db_session: Session):
        """Create test tenant."""
        tenant = Tenant(name="Test Tenant", slug="test-tenant")
        db_session.add(tenant)
        db_session.commit()
        db_session.refresh(tenant)
        return tenant

    def test_user_has_auth_source_field(self, db_session: Session, tenant: Tenant):
        """User model should have auth_source field."""
        user = User(
            tenant_id=tenant.id,
            email="test@example.com",
            name="Test User",
            password_hash="hashed",
            auth_source=AuthSource.LOCAL
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert hasattr(user, 'auth_source')
        assert user.auth_source == AuthSource.LOCAL

    def test_user_auth_source_defaults_to_local(self, db_session: Session, tenant: Tenant):
        """auth_source should default to LOCAL for backward compatibility."""
        user = User(
            tenant_id=tenant.id,
            email="local@example.com",
            name="Local User",
            password_hash="hashed"
            # No auth_source specified
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.auth_source == AuthSource.LOCAL

    def test_user_has_external_id_field(self, db_session: Session, tenant: Tenant):
        """User model should have external_id field for SSO/embed users."""
        user = User(
            tenant_id=tenant.id,
            email="sso@example.com",
            name="SSO User",
            password_hash="",
            auth_source=AuthSource.SSO,
            external_id="sso_12345"
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert hasattr(user, 'external_id')
        assert user.external_id == "sso_12345"

    def test_user_external_id_nullable(self, db_session: Session, tenant: Tenant):
        """external_id should be nullable for local users."""
        user = User(
            tenant_id=tenant.id,
            email="local@example.com",
            name="Local User",
            password_hash="hashed",
            auth_source=AuthSource.LOCAL,
            external_id=None
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.external_id is None

    def test_user_has_sso_claims_field(self, db_session: Session, tenant: Tenant):
        """User model should have sso_claims JSON field."""
        sso_claims = {
            "Job_Role": "support",
            "email": "support@golfnow.com",
            "sub": "sso_12345"
        }
        user = User(
            tenant_id=tenant.id,
            email="support@golfnow.com",
            name="Support User",
            password_hash="",
            auth_source=AuthSource.SSO,
            external_id="sso_12345",
            sso_claims=sso_claims
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert hasattr(user, 'sso_claims')
        assert user.sso_claims == sso_claims
        assert user.sso_claims["Job_Role"] == "support"

    def test_user_sso_claims_nullable(self, db_session: Session, tenant: Tenant):
        """sso_claims should be nullable for non-SSO users."""
        user = User(
            tenant_id=tenant.id,
            email="local@example.com",
            name="Local User",
            password_hash="hashed",
            auth_source=AuthSource.LOCAL,
            sso_claims=None
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.sso_claims is None

    def test_user_has_club_context_field(self, db_session: Session, tenant: Tenant):
        """User model should have club_context JSON field for teesheet users."""
        club_context = {
            "club_id": 123,
            "role": "admin",
            "scope": "club"
        }
        user = User(
            tenant_id=tenant.id,
            email="admin@testclub.com",
            name="Club Admin",
            password_hash="",
            auth_source=AuthSource.TEESHEET_EMBED,
            external_id="teesheet_456",
            club_context=club_context
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert hasattr(user, 'club_context')
        assert user.club_context == club_context
        assert user.club_context["club_id"] == 123

    def test_user_club_context_nullable(self, db_session: Session, tenant: Tenant):
        """club_context should be nullable for non-teesheet users."""
        user = User(
            tenant_id=tenant.id,
            email="local@example.com",
            name="Local User",
            password_hash="hashed",
            auth_source=AuthSource.LOCAL,
            club_context=None
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.club_context is None

    def test_user_has_last_login_field(self, db_session: Session, tenant: Tenant):
        """User model should have last_login DateTime field."""
        now = datetime.utcnow()
        user = User(
            tenant_id=tenant.id,
            email="test@example.com",
            name="Test User",
            password_hash="hashed",
            auth_source=AuthSource.LOCAL,
            last_login=now
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert hasattr(user, 'last_login')
        assert user.last_login is not None
        assert isinstance(user.last_login, datetime)

    def test_user_last_login_nullable(self, db_session: Session, tenant: Tenant):
        """last_login should be nullable for users who haven't logged in."""
        user = User(
            tenant_id=tenant.id,
            email="new@example.com",
            name="New User",
            password_hash="hashed",
            auth_source=AuthSource.LOCAL,
            last_login=None
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.last_login is None

    def test_user_all_auth_sources(self, db_session: Session, tenant: Tenant):
        """Test creating users with all three auth sources."""
        # Local user
        local_user = User(
            tenant_id=tenant.id,
            email="local@example.com",
            name="Local User",
            password_hash="hashed",
            auth_source=AuthSource.LOCAL
        )
        db_session.add(local_user)

        # SSO user
        sso_user = User(
            tenant_id=tenant.id,
            email="sso@example.com",
            name="SSO User",
            password_hash="",
            auth_source=AuthSource.SSO,
            external_id="sso_123",
            sso_claims={"Job_Role": "support"}
        )
        db_session.add(sso_user)

        # Teesheet embed user
        teesheet_user = User(
            tenant_id=tenant.id,
            email="teesheet@example.com",
            name="Teesheet User",
            password_hash="",
            auth_source=AuthSource.TEESHEET_EMBED,
            external_id="teesheet_456",
            club_context={"club_id": 123, "role": "admin"}
        )
        db_session.add(teesheet_user)

        db_session.commit()

        # Verify all created successfully
        assert local_user.id is not None
        assert sso_user.id is not None
        assert teesheet_user.id is not None

    def test_user_external_id_indexed(self, db_session: Session):
        """external_id should be indexed for fast lookups."""
        # This test verifies the index exists in the schema
        from sqlalchemy import inspect

        inspector = inspect(db_session.bind)
        indexes = inspector.get_indexes('users')

        # Check if external_id is in any index
        external_id_indexed = any(
            'external_id' in idx['column_names']
            for idx in indexes
        )

        assert external_id_indexed, "external_id should be indexed"
