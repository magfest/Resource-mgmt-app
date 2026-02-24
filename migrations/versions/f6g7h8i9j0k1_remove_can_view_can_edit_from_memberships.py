"""Remove can_view and can_edit from membership models

These fields are redundant because actual permission checks use work type-specific
access only (via DepartmentMembershipWorkTypeAccess and DivisionMembershipWorkTypeAccess).

Revision ID: f6g7h8i9j0k1
Revises: e5f6g7h8i9j0
Create Date: 2026-02-23 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6g7h8i9j0k1'
down_revision = 'e5f6g7h8i9j0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('department_memberships', schema=None) as batch_op:
        batch_op.drop_column('can_view')
        batch_op.drop_column('can_edit')

    with op.batch_alter_table('division_memberships', schema=None) as batch_op:
        batch_op.drop_column('can_view')
        batch_op.drop_column('can_edit')


def downgrade():
    with op.batch_alter_table('division_memberships', schema=None) as batch_op:
        batch_op.add_column(sa.Column('can_edit', sa.BOOLEAN(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('can_view', sa.BOOLEAN(), nullable=False, server_default='1'))

    with op.batch_alter_table('department_memberships', schema=None) as batch_op:
        batch_op.add_column(sa.Column('can_edit', sa.BOOLEAN(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('can_view', sa.BOOLEAN(), nullable=False, server_default='1'))
