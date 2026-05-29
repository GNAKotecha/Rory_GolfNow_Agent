"""add session tool approvals

Revision ID: d4e5f6g7h8i9
Revises: 0942e34b4c43
Create Date: 2026-05-26 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6g7h8i9'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f607'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create session_tool_approvals table for session-scoped approval caching."""
    op.create_table(
        'session_tool_approvals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('tool_name', sa.String(length=255), nullable=False),
        sa.Column('approval_pattern', sa.JSON(), nullable=True),
        sa.Column('pattern_hash', sa.String(length=64), nullable=False),
        sa.Column('approved_at', sa.DateTime(), nullable=False),
        sa.Column('approved_by', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id']),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', 'tool_name', 'pattern_hash', name='uq_session_tool_approval')
    )
    op.create_index('ix_session_tool_approvals_id', 'session_tool_approvals', ['id'])
    op.create_index('ix_session_tool_approvals_session_id', 'session_tool_approvals', ['session_id'])
    op.create_index('ix_session_tool_approvals_tool_name', 'session_tool_approvals', ['tool_name'])


def downgrade() -> None:
    """Drop session_tool_approvals table."""
    op.drop_index('ix_session_tool_approvals_tool_name', table_name='session_tool_approvals')
    op.drop_index('ix_session_tool_approvals_session_id', table_name='session_tool_approvals')
    op.drop_index('ix_session_tool_approvals_id', table_name='session_tool_approvals')
    op.drop_table('session_tool_approvals')
