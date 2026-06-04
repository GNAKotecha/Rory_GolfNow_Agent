"""Add workflow_outcomes table for tracking workflow execution results.

Revision ID: k7l8m9n0o1p2
Revises: j6k7l8m9n0o1
Create Date: 2026-06-04 14:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'k7l8m9n0o1p2'
down_revision = 'j6k7l8m9n0o1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create workflow_outcomes table
    op.create_table(
        'workflow_outcomes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('workflow_type', sa.String(100), nullable=False),
        sa.Column('outcome', sa.String(50), nullable=False),
        sa.Column('context', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for better query performance
    op.create_index('idx_workflow_outcomes_user_id', 'workflow_outcomes', ['user_id'])
    op.create_index('idx_workflow_outcomes_workflow_type', 'workflow_outcomes', ['workflow_type'])
    op.create_index('idx_workflow_outcomes_created_at', 'workflow_outcomes', ['created_at'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_workflow_outcomes_created_at', table_name='workflow_outcomes')
    op.drop_index('idx_workflow_outcomes_workflow_type', table_name='workflow_outcomes')
    op.drop_index('idx_workflow_outcomes_user_id', table_name='workflow_outcomes')

    # Drop table
    op.drop_table('workflow_outcomes')
