"""Add quantity_label to techops_service_types

Per-service caption for the New Request form's quantity input. When set,
the form renders a labeled quantity field under the service section (e.g.
"Number of drops" for ETHERNET, "Number of channels" for RADIO_CHANNEL).
When NULL the quantity field is hidden — appropriate for services where
quantity has no requester-side semantics (WiFi coverage area, bandwidth,
generic consultation).

Initial values are populated by the seed (seed_techops_service_types);
existing rows in dev/staging environments will get NULL until re-seeded.

Revision ID: u1v2w3x4y5z6
Revises: t0u1v2w3x4y5
Create Date: 2026-04-30 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'u1v2w3x4y5z6'
down_revision = 't0u1v2w3x4y5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('techops_service_types', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'quantity_label', sa.String(length=64), nullable=True,
        ))

    # Backfill existing rows with the right label per code so the column
    # is populated without needing a re-seed in dev/staging.
    bind = op.get_bind()
    for code, label in (
        ("ETHERNET", "Number of drops"),
        ("PHONE", "Number of phone lines"),
        ("RADIO_CHANNEL", "Number of channels"),
    ):
        bind.execute(
            sa.text(
                "UPDATE techops_service_types "
                "SET quantity_label = :label "
                "WHERE code = :code"
            ),
            {"label": label, "code": code},
        )


def downgrade():
    with op.batch_alter_table('techops_service_types', schema=None) as batch_op:
        batch_op.drop_column('quantity_label')
