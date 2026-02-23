"""Change config_audit_events.entity_id to String

Revision ID: 62af099c1fd5
Revises: b2c3d4e5f6g7
Create Date: 2026-02-22 20:07:15.712951

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '62af099c1fd5'
down_revision = 'b2c3d4e5f6g7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('config_audit_events', schema=None) as batch_op:
        batch_op.alter_column('entity_id',
               existing_type=sa.INTEGER(),
               type_=sa.String(length=64),
               existing_nullable=False)


def downgrade():
    with op.batch_alter_table('config_audit_events', schema=None) as batch_op:
        batch_op.alter_column('entity_id',
               existing_type=sa.String(length=64),
               type_=sa.INTEGER(),
               existing_nullable=False)