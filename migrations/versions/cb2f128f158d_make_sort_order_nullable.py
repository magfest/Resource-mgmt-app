"""Make sort_order nullable with NULL default for alphabetical fallback

Revision ID: cb2f128f158d
Revises: 66a9f637a173
Create Date: 2026-03-28 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cb2f128f158d'
down_revision = '66a9f637a173'
branch_labels = None
depends_on = None


# All tables that have a sort_order column
TABLES = [
    'event_cycles',
    'divisions',
    'departments',
    'approval_groups',
    'work_types',
    'spend_types',
    'frequency_options',
    'confidence_levels',
    'priority_levels',
    'expense_accounts',
    'contract_types',
    'supply_categories',
    'supply_items',
]


def upgrade():
    for table in TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(
                'sort_order',
                existing_type=sa.Integer(),
                nullable=True,
            )
        # Convert default 0 values to NULL (these were never intentionally set)
        op.execute(f"UPDATE {table} SET sort_order = NULL WHERE sort_order = 0")


def downgrade():
    for table in TABLES:
        # Convert NULLs back to 0
        op.execute(f"UPDATE {table} SET sort_order = 0 WHERE sort_order IS NULL")
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(
                'sort_order',
                existing_type=sa.Integer(),
                nullable=False,
                server_default='0',
            )
