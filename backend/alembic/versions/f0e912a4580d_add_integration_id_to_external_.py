"""add_integration_id_to_external_credentials

Revision ID: f0e912a4580d
Revises: f2g3h4i5j6k7
Create Date: 2026-06-02 15:50:04.426587

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f0e912a4580d'
down_revision: Union[str, Sequence[str], None] = 'f2g3h4i5j6k7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add integration_id foreign key to external_credentials table."""
    # Add integration_id column
    op.add_column(
        'external_credentials',
        sa.Column('integration_id', sa.Integer(), nullable=True)
    )

    # Create foreign key to mcp_integrations
    op.create_foreign_key(
        'fk_external_credentials_integration_id',
        'external_credentials',
        'mcp_integrations',
        ['integration_id'],
        ['id']
    )

    # Create index on integration_id
    op.create_index(
        'ix_external_credentials_integration_id',
        'external_credentials',
        ['integration_id']
    )


def downgrade() -> None:
    """Remove integration_id foreign key from external_credentials table."""
    # Drop index
    op.drop_index('ix_external_credentials_integration_id', table_name='external_credentials')

    # Drop foreign key
    op.drop_constraint('fk_external_credentials_integration_id', 'external_credentials', type_='foreignkey')

    # Drop column
    op.drop_column('external_credentials', 'integration_id')
