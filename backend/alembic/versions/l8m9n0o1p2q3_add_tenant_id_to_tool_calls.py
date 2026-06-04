"""Add tenant_id to tool_calls table for multi-tenant isolation.

Revision ID: l8m9n0o1p2q3
Revises: k7l8m9n0o1p2
Create Date: 2026-06-04 14:59:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'l8m9n0o1p2q3'
down_revision = 'k7l8m9n0o1p2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add tenant_id column to tool_calls table
    op.add_column('tool_calls', sa.Column('tenant_id', sa.Integer(), nullable=True))

    # Populate existing rows with tenant_id from session
    op.execute("""
        UPDATE tool_calls tc
        SET tenant_id = s.tenant_id
        FROM sessions s
        WHERE tc.session_id = s.id AND tc.tenant_id IS NULL
    """)

    # Make tenant_id NOT NULL
    op.alter_column('tool_calls', 'tenant_id', nullable=False)

    # Add foreign key constraint
    op.create_foreign_key(
        'fk_tool_calls_tenant_id',
        'tool_calls',
        'tenants',
        ['tenant_id'],
        ['id']
    )

    # Create index for performance
    op.create_index('idx_tool_calls_tenant_id', 'tool_calls', ['tenant_id'])


def downgrade() -> None:
    # Drop index
    op.drop_index('idx_tool_calls_tenant_id', table_name='tool_calls')

    # Drop foreign key
    op.drop_constraint('fk_tool_calls_tenant_id', 'tool_calls', type_='foreignkey')

    # Drop column
    op.drop_column('tool_calls', 'tenant_id')
