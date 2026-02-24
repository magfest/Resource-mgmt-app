"""Add security_audit_logs table

Security audit log for authentication and sensitive operations.
Designed for PII compliance with 6-month retention.

Revision ID: g7h8i9j0k1l2
Revises: f6g7h8i9j0k1
Create Date: 2026-02-24 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'g7h8i9j0k1l2'
down_revision = 'f6g7h8i9j0k1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('security_audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=512), nullable=True),
        sa.Column('event_type', sa.String(length=32), nullable=False),
        sa.Column('event_category', sa.String(length=32), nullable=False),
        sa.Column('severity', sa.String(length=16), nullable=False),
        sa.Column('details', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('security_audit_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_security_audit_logs_timestamp'), ['timestamp'], unique=False)
        batch_op.create_index(batch_op.f('ix_security_audit_logs_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_security_audit_logs_event_type'), ['event_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_security_audit_logs_event_category'), ['event_category'], unique=False)
        batch_op.create_index('ix_security_audit_timestamp_category', ['timestamp', 'event_category'], unique=False)
        batch_op.create_index('ix_security_audit_user_timestamp', ['user_id', 'timestamp'], unique=False)


def downgrade():
    with op.batch_alter_table('security_audit_logs', schema=None) as batch_op:
        batch_op.drop_index('ix_security_audit_user_timestamp')
        batch_op.drop_index('ix_security_audit_timestamp_category')
        batch_op.drop_index(batch_op.f('ix_security_audit_logs_event_category'))
        batch_op.drop_index(batch_op.f('ix_security_audit_logs_event_type'))
        batch_op.drop_index(batch_op.f('ix_security_audit_logs_user_id'))
        batch_op.drop_index(batch_op.f('ix_security_audit_logs_timestamp'))

    op.drop_table('security_audit_logs')
