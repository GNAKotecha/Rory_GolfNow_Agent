"""add tenant isolation

Revision ID: e1f2g3h4i5j6
Revises: d4e5f6g7h8i9
Create Date: 2026-05-29 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1f2g3h4i5j6'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6g7h8i9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add tenant isolation to all core tables."""

    # Step 1: Create tenants table (skip if exists)
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'tenants' not in inspector.get_table_names():
        op.create_table(
            'tenants',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('slug', sa.String(length=255), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('name'),
            sa.UniqueConstraint('slug')
        )
        op.create_index('ix_tenants_slug', 'tenants', ['slug'])

    # Step 2: Add tenant_id columns (nullable initially, skip if exists)
    tables = [
        'users',
        'sessions',
        'external_credentials',
        'workflow_runs',
        'workflow_events',
        'tool_calls',
        'approvals',
        'session_tool_approvals',
        'workflow_classifications'
    ]

    for table in tables:
        if table in inspector.get_table_names():
            columns = [c['name'] for c in inspector.get_columns(table)]
            if 'tenant_id' not in columns:
                op.add_column(table, sa.Column('tenant_id', sa.Integer(), nullable=True))

    # Step 3: Seed default tenant (skip if exists)
    result = conn.execute(sa.text("SELECT COUNT(*) FROM tenants WHERE id = 1"))
    if result.scalar() == 0:
        op.execute("""
            INSERT INTO tenants (id, name, slug, created_at, updated_at)
            VALUES (1, 'Default Organization', 'default', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """)

    # Step 4: Assign existing records to default tenant
    for table in tables:
        op.execute(f"UPDATE {table} SET tenant_id = 1")

    # Step 5: Make tenant_id non-nullable
    for table in tables:
        op.alter_column(table, 'tenant_id', nullable=False)

    # Step 6: Add foreign key constraints
    for table in tables:
        op.create_foreign_key(
            f'fk_{table}_tenant_id',
            table,
            'tenants',
            ['tenant_id'],
            ['id']
        )

    # Step 7: Add indexes
    for table in tables:
        op.create_index(f'ix_{table}_tenant_id', table, ['tenant_id'])


def downgrade() -> None:
    """Remove tenant isolation."""

    tables = [
        'users',
        'sessions',
        'external_credentials',
        'workflow_runs',
        'workflow_events',
        'tool_calls',
        'approvals',
        'session_tool_approvals',
        'workflow_classifications'
    ]

    # Reverse Step 7: Drop indexes
    for table in tables:
        op.drop_index(f'ix_{table}_tenant_id', table_name=table)

    # Reverse Step 6: Drop foreign key constraints
    for table in tables:
        op.drop_constraint(f'fk_{table}_tenant_id', table, type_='foreignkey')

    # Reverse Step 5, 4, 2: Drop tenant_id columns
    for table in tables:
        op.drop_column(table, 'tenant_id')

    # Reverse Step 1: Drop tenants table
    op.drop_index('ix_tenants_slug', table_name='tenants')
    op.drop_table('tenants')
