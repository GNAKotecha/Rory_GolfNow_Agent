"""add tenant skills

Revision ID: g3h4i5j6k7l8
Revises: f0e912a4580d
Create Date: 2026-06-03 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'g3h4i5j6k7l8'
down_revision: Union[str, Sequence[str], None] = 'f0e912a4580d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add tenant_skills table for tenant-scoped custom skills."""

    # Check if table already exists (idempotent migration)
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'tenant_skills' not in inspector.get_table_names():
        op.create_table(
            'tenant_skills',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('tenant_id', sa.Integer(), nullable=False),
            sa.Column('skill_name', sa.String(length=255), nullable=False),
            sa.Column('description', sa.String(length=500), nullable=True),
            sa.Column('skill_data', sa.JSON(), nullable=False, server_default='{}'),
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE', name='fk_tenant_skills_tenant_id'),
            sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_tenant_skills_created_by'),
            sa.UniqueConstraint('tenant_id', 'skill_name', 'version', name='uq_tenant_skill_name_version')
        )

        # Add indexes
        op.create_index('ix_tenant_skills_id', 'tenant_skills', ['id'])
        op.create_index('ix_tenant_skills_tenant_id', 'tenant_skills', ['tenant_id'])
        op.create_index('ix_tenant_skills_tenant_id_skill_name', 'tenant_skills', ['tenant_id', 'skill_name'])
        op.create_index('ix_tenant_skills_is_active', 'tenant_skills', ['is_active'])


def downgrade() -> None:
    """Remove tenant_skills table."""

    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'tenant_skills' in inspector.get_table_names():
        # Drop indexes
        op.drop_index('ix_tenant_skills_is_active', table_name='tenant_skills')
        op.drop_index('ix_tenant_skills_tenant_id_skill_name', table_name='tenant_skills')
        op.drop_index('ix_tenant_skills_tenant_id', table_name='tenant_skills')
        op.drop_index('ix_tenant_skills_id', table_name='tenant_skills')

        # Drop table (foreign key constraints will be dropped automatically with table)
        op.drop_table('tenant_skills')
