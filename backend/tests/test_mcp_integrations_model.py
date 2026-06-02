"""Unit tests for TenantMCPIntegration model."""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError

from app.models.models import Tenant, TenantMCPIntegration
from app.db.session import get_db


@pytest.fixture
def test_tenant(db_session):
    """Create a test tenant."""
    tenant = Tenant(
        name="Test Tenant",
        slug="test-tenant"
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


@pytest.fixture
def second_tenant(db_session):
    """Create a second test tenant."""
    tenant = Tenant(
        name="Second Tenant",
        slug="second-tenant"
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


class TestModelCreation:
    """Test basic model creation."""

    def test_create_integration_with_required_fields(self, db_session, test_tenant):
        """Test creating integration with all required fields."""
        integration = TenantMCPIntegration(
            tenant_id=test_tenant.id,
            integration_name="github",
            auth_type="oauth",
            config={"api_version": "v3"}
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)

        assert integration.id is not None
        assert integration.tenant_id == test_tenant.id
        assert integration.integration_name == "github"
        assert integration.auth_type == "oauth"
        assert integration.config == {"api_version": "v3"}
        assert integration.is_enabled is True
        assert integration.created_at is not None
        assert integration.updated_at is not None

    def test_default_values(self, db_session, test_tenant):
        """Test default values for optional fields."""
        integration = TenantMCPIntegration(
            tenant_id=test_tenant.id,
            integration_name="jira",
            auth_type="api_key"
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)

        assert integration.is_enabled is True
        assert integration.config == {}

    def test_missing_required_fields_fails(self, db_session, test_tenant):
        """Test that missing required fields raises error."""
        # Missing integration_name
        integration = TenantMCPIntegration(
            tenant_id=test_tenant.id,
            auth_type="oauth"
        )
        db_session.add(integration)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

        # Missing auth_type
        integration = TenantMCPIntegration(
            tenant_id=test_tenant.id,
            integration_name="github"
        )
        db_session.add(integration)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

        # Missing tenant_id
        integration = TenantMCPIntegration(
            integration_name="github",
            auth_type="oauth"
        )
        db_session.add(integration)
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestUniqueConstraint:
    """Test unique constraint on (tenant_id, integration_name)."""

    def test_duplicate_integration_same_tenant_fails(self, db_session, test_tenant):
        """Test that duplicate integration_name for same tenant fails."""
        integration1 = TenantMCPIntegration(
            tenant_id=test_tenant.id,
            integration_name="github",
            auth_type="oauth"
        )
        db_session.add(integration1)
        db_session.commit()

        # Try to add duplicate
        integration2 = TenantMCPIntegration(
            tenant_id=test_tenant.id,
            integration_name="github",
            auth_type="pat"
        )
        db_session.add(integration2)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_same_integration_different_tenant_succeeds(self, db_session, test_tenant, second_tenant):
        """Test that same integration_name for different tenants succeeds."""
        integration1 = TenantMCPIntegration(
            tenant_id=test_tenant.id,
            integration_name="github",
            auth_type="oauth"
        )
        db_session.add(integration1)
        db_session.commit()

        # Same integration name, different tenant should succeed
        integration2 = TenantMCPIntegration(
            tenant_id=second_tenant.id,
            integration_name="github",
            auth_type="oauth"
        )
        db_session.add(integration2)
        db_session.commit()
        db_session.refresh(integration2)

        assert integration2.id is not None
        assert integration2.tenant_id == second_tenant.id


class TestTimestamps:
    """Test timestamp behavior."""

    def test_created_at_set_on_creation(self, db_session, test_tenant):
        """Test that created_at is set automatically."""
        before = datetime.utcnow()
        integration = TenantMCPIntegration(
            tenant_id=test_tenant.id,
            integration_name="github",
            auth_type="oauth"
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)
        after = datetime.utcnow()

        assert integration.created_at is not None
        assert before <= integration.created_at <= after

    def test_updated_at_changes_on_update(self, db_session, test_tenant):
        """Test that updated_at changes when record is updated."""
        integration = TenantMCPIntegration(
            tenant_id=test_tenant.id,
            integration_name="github",
            auth_type="oauth"
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)

        original_updated_at = integration.updated_at

        # Update the record
        integration.is_enabled = False
        db_session.commit()
        db_session.refresh(integration)

        assert integration.updated_at > original_updated_at


class TestRelationship:
    """Test relationship to Tenant model."""

    def test_relationship_to_tenant(self, db_session, test_tenant):
        """Test that integration has relationship to tenant."""
        integration = TenantMCPIntegration(
            tenant_id=test_tenant.id,
            integration_name="github",
            auth_type="oauth"
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)

        assert integration.tenant is not None
        assert integration.tenant.id == test_tenant.id
        assert integration.tenant.name == "Test Tenant"

    def test_tenant_back_populates(self, db_session, test_tenant):
        """Test that tenant has mcp_integrations relationship."""
        integration1 = TenantMCPIntegration(
            tenant_id=test_tenant.id,
            integration_name="github",
            auth_type="oauth"
        )
        integration2 = TenantMCPIntegration(
            tenant_id=test_tenant.id,
            integration_name="jira",
            auth_type="api_key"
        )
        db_session.add_all([integration1, integration2])
        db_session.commit()

        db_session.refresh(test_tenant)
        assert len(test_tenant.mcp_integrations) == 2
        assert {i.integration_name for i in test_tenant.mcp_integrations} == {"github", "jira"}


class TestSerialization:
    """Test serialization to dict."""

    def test_to_dict(self, db_session, test_tenant):
        """Test converting integration to dict."""
        integration = TenantMCPIntegration(
            tenant_id=test_tenant.id,
            integration_name="github",
            auth_type="oauth",
            config={"api_version": "v3"},
            is_enabled=True
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)

        result = {
            "id": integration.id,
            "tenant_id": integration.tenant_id,
            "integration_name": integration.integration_name,
            "auth_type": integration.auth_type,
            "config": integration.config,
            "is_enabled": integration.is_enabled,
            "created_at": integration.created_at.isoformat() if integration.created_at else None,
            "updated_at": integration.updated_at.isoformat() if integration.updated_at else None
        }

        assert result["id"] == integration.id
        assert result["tenant_id"] == test_tenant.id
        assert result["integration_name"] == "github"
        assert result["auth_type"] == "oauth"
        assert result["config"] == {"api_version": "v3"}
        assert result["is_enabled"] is True


class TestQuerying:
    """Test querying integrations."""

    def test_filter_by_tenant_id(self, db_session, test_tenant, second_tenant):
        """Test filtering integrations by tenant_id."""
        # Create integrations for both tenants
        integration1 = TenantMCPIntegration(
            tenant_id=test_tenant.id,
            integration_name="github",
            auth_type="oauth"
        )
        integration2 = TenantMCPIntegration(
            tenant_id=test_tenant.id,
            integration_name="jira",
            auth_type="api_key"
        )
        integration3 = TenantMCPIntegration(
            tenant_id=second_tenant.id,
            integration_name="github",
            auth_type="oauth"
        )
        db_session.add_all([integration1, integration2, integration3])
        db_session.commit()

        # Query integrations for test_tenant
        tenant1_integrations = db_session.query(TenantMCPIntegration).filter(
            TenantMCPIntegration.tenant_id == test_tenant.id
        ).all()

        assert len(tenant1_integrations) == 2
        assert {i.integration_name for i in tenant1_integrations} == {"github", "jira"}

        # Query integrations for second_tenant
        tenant2_integrations = db_session.query(TenantMCPIntegration).filter(
            TenantMCPIntegration.tenant_id == second_tenant.id
        ).all()

        assert len(tenant2_integrations) == 1
        assert tenant2_integrations[0].integration_name == "github"

    def test_filter_by_enabled_status(self, db_session, test_tenant):
        """Test filtering integrations by is_enabled status."""
        integration1 = TenantMCPIntegration(
            tenant_id=test_tenant.id,
            integration_name="github",
            auth_type="oauth",
            is_enabled=True
        )
        integration2 = TenantMCPIntegration(
            tenant_id=test_tenant.id,
            integration_name="jira",
            auth_type="api_key",
            is_enabled=False
        )
        db_session.add_all([integration1, integration2])
        db_session.commit()

        # Query only enabled integrations
        enabled = db_session.query(TenantMCPIntegration).filter(
            TenantMCPIntegration.tenant_id == test_tenant.id,
            TenantMCPIntegration.is_enabled == True
        ).all()

        assert len(enabled) == 1
        assert enabled[0].integration_name == "github"
