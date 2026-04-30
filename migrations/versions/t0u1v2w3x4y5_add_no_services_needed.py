"""Add no_services_needed flag to techops_request_details

Adds a boolean to TechOpsRequestDetail capturing the "I have reviewed
all sections and my department needs no TechOps services for this event"
affirmation from the request form. When True, submit synthesizes a
TECHOPS_GEN-routed OTHER line so the affirmation goes through normal
review (admins verify the department actually considered their needs).

Defaults to False to preserve current row semantics — no existing rows
exist yet (TechOps inactive), but server_default protects future rows
inserted before the column is set explicitly.

Revision ID: t0u1v2w3x4y5
Revises: s9t0u1v2w3x4
Create Date: 2026-04-30 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 't0u1v2w3x4y5'
down_revision = 's9t0u1v2w3x4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('techops_request_details', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'no_services_needed', sa.Boolean(),
            nullable=False, server_default=sa.false(),
        ))


def downgrade():
    with op.batch_alter_table('techops_request_details', schema=None) as batch_op:
        batch_op.drop_column('no_services_needed')
