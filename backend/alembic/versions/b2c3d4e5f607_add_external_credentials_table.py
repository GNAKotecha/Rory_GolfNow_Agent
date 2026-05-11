"""add external_credentials table

Revision ID: b2c3d4e5f607
Revises: 0942e34b4c43
Create Date: 2026-05-10 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f607'
down_revision: Union[str, Sequence[str], None] = '0942e34b4c43'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add external_credentials table."""
    conn = op.get_bind()

    # Create credential_type enum
    if conn.dialect.name == 'postgresql':
        credential_type_enum = postgresql.ENUM(
            'oauth', 'pat',
            name='credentialtype',
            create_type=False,
        )
        credential_type_enum.create(conn, checkfirst=True)

    # Create external_credentials table
    op.create_table(
        'external_credentials',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column(
            'credential_type',
            postgresql.ENUM('oauth', 'pat', name='credentialtype', create_type=False)
            if conn.dialect.name == 'postgresql'
            else sa.String(length=10),
            nullable=False,
        ),
        sa.Column('secret_enc', sa.LargeBinary(), nullable=False),
        sa.Column('refresh_token_enc', sa.LargeBinary(), nullable=True),
        sa.Column('scope', sa.String(length=1000), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('provider_metadata', postgresql.JSONB() if conn.dialect.name == 'postgresql' else sa.JSON(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create indexes
    op.create_index('ix_external_credentials_id', 'external_credentials', ['id'])
    op.create_index('ix_external_credentials_user_id', 'external_credentials', ['user_id'])

    # Composite unique index on (user_id, provider) - one credential per provider per user
    op.create_index(
        'ix_external_credentials_user_provider',
        'external_credentials',
        ['user_id', 'provider'],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema - remove external_credentials table."""
    conn = op.get_bind()

    op.drop_index('ix_external_credentials_user_provider', table_name='external_credentials')
    op.drop_index('ix_external_credentials_user_id', table_name='external_credentials')
    op.drop_index('ix_external_credentials_id', table_name='external_credentials')
    op.drop_table('external_credentials')

    # Drop credential_type enum
    if conn.dialect.name == 'postgresql':
        op.execute('DROP TYPE IF EXISTS credentialtype')
