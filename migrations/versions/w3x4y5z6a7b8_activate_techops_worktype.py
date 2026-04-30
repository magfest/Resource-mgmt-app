"""Activate TechOps WorkType

Flips work_types.is_active to True for the TECHOPS row so the worktype
appears in user-facing pickers (admin user-role editor, division/
department config, request creation pickers). The seed already lists
TECHOPS as active=True, but seed_work_types only updates existing rows
when re-seeded — environments that ran an earlier seed (where TECHOPS
was active=False) need this migration to flip the row in place.

The named TechOps admins (Heather Selbe + Mark Murnane) are NOT added
here — user-role data is environment-specific (different identifiers
in dev / staging / prod), so role assignments belong in the admin UI
after this migration runs. See T6 in project memory for the activation
checklist.

Revision ID: w3x4y5z6a7b8
Revises: v2w3x4y5z6a7
Create Date: 2026-04-30 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'w3x4y5z6a7b8'
down_revision = 'v2w3x4y5z6a7'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    bind.execute(
        sa.text("UPDATE work_types SET is_active = :active WHERE code = :code"),
        {"active": True, "code": "TECHOPS"},
    )


def downgrade():
    bind = op.get_bind()
    bind.execute(
        sa.text("UPDATE work_types SET is_active = :active WHERE code = :code"),
        {"active": False, "code": "TECHOPS"},
    )
