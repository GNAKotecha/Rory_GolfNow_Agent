"""Add agent memory support (session_working_memory and session_memory_summaries).

Revision ID: i5j6k7l8m9n0
Revises: h4i5j6k7l8m9
Create Date: 2026-06-03 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'i5j6k7l8m9n0'
down_revision = 'h4i5j6k7l8m9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add working memory field and historical summaries table."""
    inspector = sa.inspect(op.get_bind())

    # Add session_working_memory column to sessions table
    if 'session_working_memory' not in [c['name'] for c in inspector.get_columns('sessions')]:
        op.add_column('sessions', sa.Column('session_working_memory', sa.JSON(), nullable=True, server_default='{}'))

    # Create session_memory_summaries table
    if not inspector.has_table('session_memory_summaries'):
        op.create_table(
            'session_memory_summaries',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('tenant_id', sa.Integer(), nullable=False),
            sa.Column('session_id', sa.Integer(), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
            sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ),
            sa.PrimaryKeyConstraint('id')
        )

        # Create indexes
        op.create_index('ix_session_memory_summaries_id', 'session_memory_summaries', ['id'], unique=False)
        op.create_index('ix_session_memory_summaries_tenant_id', 'session_memory_summaries', ['tenant_id'], unique=False)
        op.create_index('ix_session_memory_summaries_created_at', 'session_memory_summaries', ['created_at'], unique=False)


def downgrade() -> None:
    """Revert agent memory changes."""
    inspector = sa.inspect(op.get_bind())

    # Drop session_memory_summaries table
    if inspector.has_table('session_memory_summaries'):
        op.drop_index('ix_session_memory_summaries_created_at', table_name='session_memory_summaries')
        op.drop_index('ix_session_memory_summaries_tenant_id', table_name='session_memory_summaries')
        op.drop_index('ix_session_memory_summaries_id', table_name='session_memory_summaries')
        op.drop_table('session_memory_summaries')

    # Remove session_working_memory column
    if inspector.has_column('sessions', 'session_working_memory'):
        op.drop_column('sessions', 'session_working_memory')
