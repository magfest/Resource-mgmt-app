"""Add qb_class to org models and dates_are_public to event_cycles

Revision ID: 3ef69c594552
Revises: cb2f128f158d
Create Date: 2026-03-28 10:01:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3ef69c594552'
down_revision = 'cb2f128f158d'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('event_cycles') as batch_op:
        batch_op.add_column(sa.Column('qb_class', sa.String(128), nullable=True))
        batch_op.add_column(sa.Column('dates_are_public', sa.Boolean(), nullable=False, server_default='0'))

    with op.batch_alter_table('divisions') as batch_op:
        batch_op.add_column(sa.Column('qb_class', sa.String(128), nullable=True))

    with op.batch_alter_table('departments') as batch_op:
        batch_op.add_column(sa.Column('qb_class', sa.String(128), nullable=True))


def downgrade():
    with op.batch_alter_table('departments') as batch_op:
        batch_op.drop_column('qb_class')

    with op.batch_alter_table('divisions') as batch_op:
        batch_op.drop_column('qb_class')

    with op.batch_alter_table('event_cycles') as batch_op:
        batch_op.drop_column('dates_are_public')
        batch_op.drop_column('qb_class')
