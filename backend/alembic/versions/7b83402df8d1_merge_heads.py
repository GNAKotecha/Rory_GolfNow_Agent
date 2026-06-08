"""merge_heads

Revision ID: 7b83402df8d1
Revises: i5j6k7l8m9n0, l8m9n0o1p2q3
Create Date: 2026-06-05 20:34:34.856461

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7b83402df8d1'
down_revision: Union[str, Sequence[str], None] = ('i5j6k7l8m9n0', 'l8m9n0o1p2q3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
