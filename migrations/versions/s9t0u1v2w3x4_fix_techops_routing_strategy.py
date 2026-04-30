"""Fix TECHOPS WorkTypeConfig.routing_strategy to category

The TECHOPS work type config was originally seeded with routing_strategy=
'direct', but TechOps actually uses category routing — each
TechOpsServiceType row carries a default_approval_group_id that gets
snapshotted onto TechOpsLineDetail.routed_approval_group_id at submit
time. The seed file was corrected in the same branch as this migration;
this UPDATE fixes existing rows in dev/staging/prod that were seeded
before the correction.

No-op for fresh DBs (the seed sets it correctly).

Revision ID: s9t0u1v2w3x4
Revises: r8s9t0u1v2w3
Create Date: 2026-04-29 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 's9t0u1v2w3x4'
down_revision = 'r8s9t0u1v2w3'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    bind.execute(sa.text("""
        UPDATE work_type_configs
           SET routing_strategy = 'category'
         WHERE routing_strategy = 'direct'
           AND work_type_id IN (
               SELECT id FROM work_types WHERE code = 'TECHOPS'
           )
    """))


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("""
        UPDATE work_type_configs
           SET routing_strategy = 'direct'
         WHERE routing_strategy = 'category'
           AND work_type_id IN (
               SELECT id FROM work_types WHERE code = 'TECHOPS'
           )
    """))
