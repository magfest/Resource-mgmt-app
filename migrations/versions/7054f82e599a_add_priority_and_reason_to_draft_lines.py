"""Add priority and reason to draft_lines

Revision ID: 7054f82e599a
Revises: 7e94620bf16a
Create Date: 2026-01-21 14:27:51.683226

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7054f82e599a'
down_revision = '7e94620bf16a'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("draft_lines", schema=None) as batch_op:
        batch_op.add_column(sa.Column("priority", sa.String(length=32), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("reason", sa.Text(), nullable=False, server_default=""))

    # optional cleanup: remove defaults after migration
    with op.batch_alter_table("draft_lines", schema=None) as batch_op:
        batch_op.alter_column("priority", server_default=None)
        batch_op.alter_column("reason", server_default=None)


def downgrade():
    with op.batch_alter_table("draft_lines", schema=None) as batch_op:
        batch_op.drop_column("reason")
        batch_op.drop_column("priority")
