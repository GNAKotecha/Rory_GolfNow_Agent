"""add prompt templates and versions

Revision ID: 0942e34b4c43
Revises: a1b2c3d4e5f6
Create Date: 2026-05-07 18:13:20.471314

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0942e34b4c43'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'prompt_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('current_version_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_prompt_templates_id', 'prompt_templates', ['id'])
    op.create_index('ix_prompt_templates_name', 'prompt_templates', ['name'], unique=True)

    op.create_table(
        'prompt_template_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('prompt_text', sa.Text(), nullable=False),
        sa.Column('variables', sa.JSON(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('usage_count', sa.Integer(), nullable=False),
        sa.Column('success_count', sa.Integer(), nullable=False),
        sa.Column('avg_latency_ms', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['template_id'], ['prompt_templates.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_prompt_template_versions_id', 'prompt_template_versions', ['id'])

    op.create_foreign_key(
        'fk_prompt_templates_current_version',
        'prompt_templates', 'prompt_template_versions',
        ['current_version_id'], ['id']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_prompt_templates_current_version', 'prompt_templates', type_='foreignkey')
    op.drop_index('ix_prompt_template_versions_id', table_name='prompt_template_versions')
    op.drop_table('prompt_template_versions')
    op.drop_index('ix_prompt_templates_name', table_name='prompt_templates')
    op.drop_index('ix_prompt_templates_id', table_name='prompt_templates')
    op.drop_table('prompt_templates')
