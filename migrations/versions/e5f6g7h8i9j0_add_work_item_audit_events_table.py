"""Add work_item_audit_events table

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
Create Date: 2026-02-23 21:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f6g7h8i9j0'
down_revision = 'd4e5f6g7h8i9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('work_item_audit_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('work_item_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('old_value', sa.Text(), nullable=True),
        sa.Column('new_value', sa.Text(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by_user_id', sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(['work_item_id'], ['work_items.id'], name='fk_work_item_audit_work_item_id'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('work_item_audit_events', schema=None) as batch_op:
        batch_op.create_index('ix_work_item_audit_events_work_item_id', ['work_item_id'], unique=False)
        batch_op.create_index('ix_work_item_audit_events_event_type', ['event_type'], unique=False)
        batch_op.create_index('ix_work_item_audit_events_created_at', ['created_at'], unique=False)
        batch_op.create_index('ix_work_item_audit_events_created_by_user_id', ['created_by_user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('work_item_audit_events', schema=None) as batch_op:
        batch_op.drop_index('ix_work_item_audit_events_created_by_user_id')
        batch_op.drop_index('ix_work_item_audit_events_created_at')
        batch_op.drop_index('ix_work_item_audit_events_event_type')
        batch_op.drop_index('ix_work_item_audit_events_work_item_id')

    op.drop_table('work_item_audit_events')
