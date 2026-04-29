"""Add work_type_id to approval_groups

Each approval group now belongs to one work type so different work types can
own their own queues (e.g. BUDGET / TECH vs TECHOPS / TECHOPS_NET). The
`code` uniqueness becomes scoped to (work_type_id, code) so different work
types can reuse codes like GEN.

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2026-04-29 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'p6q7r8s9t0u1'
down_revision = 'o5p6q7r8s9t0'
branch_labels = None
depends_on = None


def upgrade():
    # Step 1: add nullable column so existing rows survive insertion
    with op.batch_alter_table('approval_groups', schema=None) as batch_op:
        batch_op.add_column(sa.Column('work_type_id', sa.Integer(), nullable=True))

    # Step 2: backfill existing rows with the BUDGET work type id. Existing
    # approval groups (LOGISTICS, OFFICE, GEN, GUEST, TECH, HOTEL, etc.) all
    # belong to BUDGET — that's the only work type that has groups today.
    bind = op.get_bind()
    budget_id = bind.execute(
        sa.text("SELECT id FROM work_types WHERE code = 'BUDGET'")
    ).scalar()

    if budget_id is None:
        # Fresh database with no seeded work types yet — nothing to backfill.
        # The seed will create groups with work_type_id populated directly.
        pass
    else:
        bind.execute(
            sa.text(
                "UPDATE approval_groups SET work_type_id = :wt WHERE work_type_id IS NULL"
            ),
            {"wt": budget_id},
        )

    # Step 3: tighten the column, swap unique-on-code for composite unique,
    # and add the FK + supporting index.
    with op.batch_alter_table('approval_groups', schema=None) as batch_op:
        batch_op.alter_column('work_type_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            'fk_approval_groups_work_type_id',
            'work_types',
            ['work_type_id'], ['id'],
        )
        batch_op.create_index(
            batch_op.f('ix_approval_groups_work_type_id'),
            ['work_type_id'],
            unique=False,
        )
        # Drop the global unique on code, recreate as a plain index.
        batch_op.drop_index(batch_op.f('ix_approval_groups_code'))
        batch_op.create_index(
            batch_op.f('ix_approval_groups_code'),
            ['code'],
            unique=False,
        )
        batch_op.create_unique_constraint(
            'uq_approval_groups_work_type_code',
            ['work_type_id', 'code'],
        )


def downgrade():
    with op.batch_alter_table('approval_groups', schema=None) as batch_op:
        batch_op.drop_constraint('uq_approval_groups_work_type_code', type_='unique')
        batch_op.drop_index(batch_op.f('ix_approval_groups_code'))
        batch_op.create_index(
            batch_op.f('ix_approval_groups_code'),
            ['code'],
            unique=True,
        )
        batch_op.drop_index(batch_op.f('ix_approval_groups_work_type_id'))
        batch_op.drop_constraint('fk_approval_groups_work_type_id', type_='foreignkey')
        batch_op.drop_column('work_type_id')
