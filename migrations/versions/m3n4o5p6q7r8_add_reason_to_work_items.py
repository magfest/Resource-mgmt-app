"""Add reason field to work_items

Optional reason/description for work items, primarily used for supplementals.

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-03-23 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'm3n4o5p6q7r8'
down_revision = 'l2m3n4o5p6q7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('work_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reason', sa.String(length=256), nullable=True))


def downgrade():
    with op.batch_alter_table('work_items', schema=None) as batch_op:
        batch_op.drop_column('reason')
