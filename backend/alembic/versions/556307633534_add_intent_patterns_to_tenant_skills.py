"""add_intent_patterns_to_tenant_skills

Revision ID: 556307633534
Revises: 7b83402df8d1
Create Date: 2026-06-05 20:34:38.518732

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '556307633534'
down_revision: Union[str, Sequence[str], None] = '7b83402df8d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add intent_patterns column to tenant_skills table
    op.add_column(
        'tenant_skills',
        sa.Column('intent_patterns', sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove intent_patterns column from tenant_skills table
    op.drop_column('tenant_skills', 'intent_patterns')
