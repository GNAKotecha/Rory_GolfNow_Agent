"""add approval fields to workflow runs

Revision ID: a1b2c3d4e5f6
Revises: c57565c485d3
Create Date: 2026-05-06 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'c57565c485d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add approval fields to workflow_runs."""
    conn = op.get_bind()

    # For Postgres, add new value to existing enum before adding columns
    # SQLite doesn't enforce enum types so this is a no-op there.
    if conn.dialect.name == 'postgresql':
        # ALTER TYPE ... ADD VALUE cannot run inside a transaction block in older
        # Postgres, but in PG 12+ it works. Wrap with autocommit for safety.
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE workflowrunstatus ADD VALUE IF NOT EXISTS 'waiting_approval'")

    # Add approval-related columns
    op.add_column('workflow_runs', sa.Column('approval_data', sa.JSON(), nullable=True))
    op.add_column('workflow_runs', sa.Column('approval_prompt', sa.Text(), nullable=True))
    op.add_column('workflow_runs', sa.Column('approved_by', sa.Integer(), nullable=True))
    op.add_column('workflow_runs', sa.Column('approved_at', sa.DateTime(), nullable=True))
    op.add_column('workflow_runs', sa.Column('approval_notes', sa.Text(), nullable=True))

    # Foreign key to users.id
    op.create_foreign_key(
        'fk_workflow_runs_approved_by_users',
        'workflow_runs',
        'users',
        ['approved_by'],
        ['id'],
    )


def downgrade() -> None:
    """Downgrade schema - remove approval fields from workflow_runs.

    NOTE: Postgres does not support DROP VALUE on an enum type.
    The 'waiting_approval' value will remain in the workflowrunstatus enum
    after downgrade. Removing it would require recreating the enum type,
    which is intentionally not done here to avoid data loss risk.
    """
    conn = op.get_bind()

    # Drop foreign key first (naming may differ on SQLite which doesn't
    # support dropping FKs, so guard it).
    if conn.dialect.name != 'sqlite':
        op.drop_constraint(
            'fk_workflow_runs_approved_by_users',
            'workflow_runs',
            type_='foreignkey',
        )

    op.drop_column('workflow_runs', 'approval_notes')
    op.drop_column('workflow_runs', 'approved_at')
    op.drop_column('workflow_runs', 'approved_by')
    op.drop_column('workflow_runs', 'approval_prompt')
    op.drop_column('workflow_runs', 'approval_data')

    # Enum value 'waiting_approval' cannot be removed from Postgres enum type
    # without recreating the type. See docstring above.
