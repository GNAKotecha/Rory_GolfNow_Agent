"""add user_mcp_credentials table

Revision ID: m9n0o1p2q3r4
Revises: eac10a7850ae
Create Date: 2026-06-09 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'm9n0o1p2q3r4'
down_revision: Union[str, Sequence[str], None] = 'eac10a7850ae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add user_mcp_credentials table."""
    conn = op.get_bind()

    # Create user_mcp_credentials table
    op.create_table(
        'user_mcp_credentials',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('auth_method', sa.String(length=20), nullable=False),
        sa.Column('access_token', sa.Text(), nullable=False),
        sa.Column('refresh_token', sa.Text(), nullable=True),
        sa.Column('token_type', sa.String(length=20), nullable=True, server_default='Bearer'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'scopes',
            postgresql.ARRAY(sa.Text()) if conn.dialect.name == 'postgresql' else sa.JSON(),
            nullable=True,
        ),
        sa.Column(
            'provider_metadata',
            postgresql.JSONB() if conn.dialect.name == 'postgresql' else sa.JSON(),
            nullable=True,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create indexes
    op.create_index('idx_user_mcp_creds_id', 'user_mcp_credentials', ['id'])
    op.create_index('idx_user_mcp_creds_user_id', 'user_mcp_credentials', ['user_id'])
    op.create_index('idx_user_mcp_creds_provider', 'user_mcp_credentials', ['provider'])
    op.create_index('idx_user_mcp_creds_expires_at', 'user_mcp_credentials', ['expires_at'])

    # Composite unique index on (user_id, provider) - one credential per provider per user
    op.create_index(
        'idx_user_mcp_creds_user_provider',
        'user_mcp_credentials',
        ['user_id', 'provider'],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema - remove user_mcp_credentials table."""
    op.drop_index('idx_user_mcp_creds_user_provider', table_name='user_mcp_credentials')
    op.drop_index('idx_user_mcp_creds_expires_at', table_name='user_mcp_credentials')
    op.drop_index('idx_user_mcp_creds_provider', table_name='user_mcp_credentials')
    op.drop_index('idx_user_mcp_creds_user_id', table_name='user_mcp_credentials')
    op.drop_index('idx_user_mcp_creds_id', table_name='user_mcp_credentials')
    op.drop_table('user_mcp_credentials')
