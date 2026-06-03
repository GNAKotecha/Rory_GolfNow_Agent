"""add tenant workflows

Revision ID: h4i5j6k7l8m9
Revises: g3h4i5j6k7l8
Create Date: 2026-06-03 10:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'h4i5j6k7l8m9'
down_revision: Union[str, Sequence[str], None] = 'g3h4i5j6k7l8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add tenant_workflows table for tenant-scoped workflow definitions."""

    # Check if table already exists (idempotent migration)
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'tenant_workflows' not in inspector.get_table_names():
        op.create_table(
            'tenant_workflows',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('tenant_id', sa.Integer(), nullable=False),
            sa.Column('workflow_name', sa.String(length=255), nullable=False),
            sa.Column('description', sa.String(length=500), nullable=True),
            sa.Column('workflow_definition', sa.JSON(), nullable=False, server_default='{}'),
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('active_version', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE', name='fk_tenant_workflows_tenant_id'),
            sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_tenant_workflows_created_by'),
            sa.UniqueConstraint('tenant_id', 'workflow_name', 'version', name='uq_tenant_workflow_name_version')
        )

        # Add indexes
        op.create_index('ix_tenant_workflows_id', 'tenant_workflows', ['id'])
        op.create_index('ix_tenant_workflows_tenant_id', 'tenant_workflows', ['tenant_id'])
        op.create_index('ix_tenant_workflows_tenant_id_workflow_name', 'tenant_workflows', ['tenant_id', 'workflow_name'])
        op.create_index('ix_tenant_workflows_is_active', 'tenant_workflows', ['is_active'])


def downgrade() -> None:
    """Remove tenant_workflows table."""

    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'tenant_workflows' in inspector.get_table_names():
        # Drop indexes
        op.drop_index('ix_tenant_workflows_is_active', table_name='tenant_workflows')
        op.drop_index('ix_tenant_workflows_tenant_id_workflow_name', table_name='tenant_workflows')
        op.drop_index('ix_tenant_workflows_tenant_id', table_name='tenant_workflows')
        op.drop_index('ix_tenant_workflows_id', table_name='tenant_workflows')

        # Drop table (foreign key constraints will be dropped automatically with table)
        op.drop_table('tenant_workflows')
