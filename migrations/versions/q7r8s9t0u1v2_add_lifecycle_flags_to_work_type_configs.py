"""Add uses_dispatch and has_admin_final to work_type_configs

Per-worktype feature flags for the request lifecycle:
- uses_dispatch: whether AWAITING_DISPATCH is a real lifecycle stage and
  the dispatch routes are accessible for this worktype
- has_admin_final: whether the admin_final review/finalize stage applies

Existing active worktypes (BUDGET, CONTRACT, SUPPLY) are backfilled to
True/True to preserve current behavior. Inactive worktypes (TECHOPS, AV)
stay at the False/False default — they'll opt in explicitly when their
flows are built.

Revision ID: q7r8s9t0u1v2
Revises: p6q7r8s9t0u1
Create Date: 2026-04-29 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'q7r8s9t0u1v2'
down_revision = 'p6q7r8s9t0u1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('work_type_configs', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'uses_dispatch', sa.Boolean(),
            nullable=False, server_default=sa.false(),
        ))
        batch_op.add_column(sa.Column(
            'has_admin_final', sa.Boolean(),
            nullable=False, server_default=sa.false(),
        ))

    # Preserve current behavior: BUDGET, CONTRACT, SUPPLY all use the full
    # dispatch + admin_final lifecycle today. Backfill them by joining on
    # work_types.code so this works whether or not the seed has run yet.
    bind = op.get_bind()
    bind.execute(sa.text("""
        UPDATE work_type_configs
           SET uses_dispatch = :true_val,
               has_admin_final = :true_val
         WHERE work_type_id IN (
            SELECT id FROM work_types WHERE code IN ('BUDGET', 'CONTRACT', 'SUPPLY')
         )
    """), {"true_val": True})


def downgrade():
    with op.batch_alter_table('work_type_configs', schema=None) as batch_op:
        batch_op.drop_column('has_admin_final')
        batch_op.drop_column('uses_dispatch')
