"""Simplify site_content schema

Replace description + info_text with single content field and display_style.

Revision ID: l2m3n4o5p6q7
Revises: cb686990cd0c
Create Date: 2026-03-22 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'l2m3n4o5p6q7'
down_revision = 'cb686990cd0c'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('site_content', schema=None) as batch_op:
        # Add new columns
        batch_op.add_column(sa.Column('content', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('display_style', sa.String(length=16), nullable=False, server_default='PLAIN'))

        # Drop old columns
        batch_op.drop_column('description')
        batch_op.drop_column('info_text')


def downgrade():
    with op.batch_alter_table('site_content', schema=None) as batch_op:
        # Add back old columns
        batch_op.add_column(sa.Column('description', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('info_text', sa.Text(), nullable=True))

        # Drop new columns
        batch_op.drop_column('display_style')
        batch_op.drop_column('content')
