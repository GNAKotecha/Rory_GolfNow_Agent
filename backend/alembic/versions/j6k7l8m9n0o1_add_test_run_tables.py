"""add_test_run_tables

Revision ID: j6k7l8m9n0o1
Revises: f0e912a4580d
Create Date: 2026-06-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'j6k7l8m9n0o1'
down_revision: Union[str, Sequence[str], None] = 'f0e912a4580d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create test_runs and test_scenario_results tables."""
    # Create test_runs table
    op.create_table(
        'test_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.String(36), nullable=False, unique=True),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('environment', sa.String(50), nullable=False),
        sa.Column('total_scenarios', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('passed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('duration_seconds', sa.Float(), nullable=False),
        sa.Column('tags', sa.JSON(), nullable=True, server_default='[]'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Indexes are created through Column(index=True) definitions in ORM

    # Create test_scenario_results table
    op.create_table(
        'test_scenario_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('test_run_id', sa.Integer(), nullable=False),
        sa.Column('scenario_name', sa.String(255), nullable=False),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('turn_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tool_calls_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.String(1000), nullable=True),
        sa.Column('turn_results', sa.JSON(), nullable=True, server_default='[]'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['test_run_id'], ['test_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Indexes are created through Column(index=True) definitions in ORM


def downgrade() -> None:
    """Drop test_runs and test_scenario_results tables."""
    # Drop tables (indexes are dropped automatically)
    op.drop_table('test_scenario_results')
    op.drop_table('test_runs')
