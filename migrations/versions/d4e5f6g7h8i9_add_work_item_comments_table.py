"""Add work_item_comments table

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-02-23 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e5f6g7h8i9'
down_revision = 'c3d4e5f6g7h8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('work_item_comments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('work_item_id', sa.Integer(), nullable=False),
        sa.Column('visibility', sa.String(length=16), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by_user_id', sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(['work_item_id'], ['work_items.id'], name='fk_work_item_comments_work_item_id'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('work_item_comments', schema=None) as batch_op:
        batch_op.create_index('ix_work_item_comments_work_item_id', ['work_item_id'], unique=False)
        batch_op.create_index('ix_work_item_comments_visibility', ['visibility'], unique=False)
        batch_op.create_index('ix_work_item_comments_created_at', ['created_at'], unique=False)
        batch_op.create_index('ix_work_item_comments_created_by_user_id', ['created_by_user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('work_item_comments', schema=None) as batch_op:
        batch_op.drop_index('ix_work_item_comments_created_by_user_id')
        batch_op.drop_index('ix_work_item_comments_created_at')
        batch_op.drop_index('ix_work_item_comments_visibility')
        batch_op.drop_index('ix_work_item_comments_work_item_id')

    op.drop_table('work_item_comments')
