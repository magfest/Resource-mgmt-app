"""Add event_end_date to event_cycles

Revision ID: c3d4e5f6g7h8
Revises: 62af099c1fd5
Create Date: 2026-02-23 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6g7h8'
down_revision = '62af099c1fd5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('event_cycles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('event_end_date', sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table('event_cycles', schema=None) as batch_op:
        batch_op.drop_column('event_end_date')
