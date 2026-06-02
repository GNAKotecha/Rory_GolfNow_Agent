"""add mcp integrations

Revision ID: f2g3h4i5j6k7
Revises: e1f2g3h4i5j6
Create Date: 2026-06-02 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f2g3h4i5j6k7'
down_revision: Union[str, Sequence[str], None] = 'e1f2g3h4i5j6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add tenant-scoped MCP integrations table."""

    # Check if table already exists (idempotent migration)
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'mcp_integrations' not in inspector.get_table_names():
        op.create_table(
            'mcp_integrations',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('tenant_id', sa.Integer(), nullable=False),
            sa.Column('integration_name', sa.String(length=100), nullable=False),
            sa.Column('auth_type', sa.String(length=50), nullable=False),
            sa.Column('config', sa.JSON(), nullable=False, server_default='{}'),
            sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE', name='fk_mcp_integrations_tenant_id'),
            sa.UniqueConstraint('tenant_id', 'integration_name', name='uq_tenant_integration_name')
        )

        # Add indexes
        op.create_index('ix_mcp_integrations_id', 'mcp_integrations', ['id'])
        op.create_index('ix_mcp_integrations_tenant_id', 'mcp_integrations', ['tenant_id'])
        op.create_index('ix_mcp_integrations_tenant_id_integration_name', 'mcp_integrations', ['tenant_id', 'integration_name'])


def downgrade() -> None:
    """Remove mcp_integrations table."""

    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'mcp_integrations' in inspector.get_table_names():
        # Drop indexes
        op.drop_index('ix_mcp_integrations_tenant_id_integration_name', table_name='mcp_integrations')
        op.drop_index('ix_mcp_integrations_tenant_id', table_name='mcp_integrations')
        op.drop_index('ix_mcp_integrations_id', table_name='mcp_integrations')

        # Drop table (foreign key constraint will be dropped automatically with table)
        op.drop_table('mcp_integrations')
