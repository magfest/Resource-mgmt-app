"""TechOps per-instance line refactor

Restructures TechOps services so each instance (ethernet drop, phone,
radio channel) is its own WorkLine instead of being collapsed into one
line with quantity > 1. Reasoning: per-drop location + use case is core
data the load-in crew and reviewers need; bundling drops via quantity
hides that detail in one free-text blob.

Schema changes:
- techops_service_types.instance_noun (varchar(32), nullable). When set,
  the service is per-instance and the form renders a repeating group;
  when NULL the service is single-line.
- techops_line_details.location (Text, nullable). Per-instance services
  fill this with physical location (ETHERNET, PHONE) or channel name
  (RADIO_CHANNEL).
- techops_line_details.usage (Text, nullable). Per-instance services
  fill this with the use case for the specific instance.

Data updates (idempotent):
- ETHERNET → instance_noun = "drop"
- PHONE → instance_noun = "phone line"
- RADIO_CHANNEL → instance_noun = "channel"
- BANDWIDTH → is_active = False (concerns merged into WIFI/ETHERNET
  descriptions; row preserved for rollback)
- WIFI/ETHERNET descriptions updated to mention bandwidth needs

The existing description and quantity columns are kept. Single-line
services (WIFI, OTHER) still use description; per-instance services
will use location + usage on new rows. quantity_label and quantity
become unused for per-instance services but stay on the schema; a
later cleanup can drop them once we're confident no legacy rows
reference them.

Revision ID: v2w3x4y5z6a7
Revises: u1v2w3x4y5z6
Create Date: 2026-04-30 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v2w3x4y5z6a7'
down_revision = 'u1v2w3x4y5z6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('techops_service_types', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'instance_noun', sa.String(length=32), nullable=True,
        ))

    with op.batch_alter_table('techops_line_details', schema=None) as batch_op:
        batch_op.add_column(sa.Column('location', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('usage', sa.Text(), nullable=True))

    bind = op.get_bind()

    # Set per-instance noun for the three services that decompose into
    # individual instances.
    for code, noun in (
        ("ETHERNET", "drop"),
        ("PHONE", "phone line"),
        ("RADIO_CHANNEL", "channel"),
    ):
        bind.execute(
            sa.text(
                "UPDATE techops_service_types "
                "SET instance_noun = :noun "
                "WHERE code = :code"
            ),
            {"noun": noun, "code": code},
        )

    # Deactivate BANDWIDTH — bandwidth concerns roll into WIFI/ETHERNET
    # descriptions instead of being a separate service.
    bind.execute(
        sa.text(
            "UPDATE techops_service_types "
            "SET is_active = :inactive "
            "WHERE code = :code"
        ),
        {"inactive": False, "code": "BANDWIDTH"},
    )

    # Refresh WIFI / ETHERNET descriptions so the bandwidth prompt is
    # surfaced where the requester is actually picking a connection type.
    bind.execute(
        sa.text(
            "UPDATE techops_service_types "
            "SET description = :desc "
            "WHERE code = :code"
        ),
        {
            "desc": (
                "WiFi coverage for staff or attendees in a specific area "
                "or for a use case. Call out heavy bandwidth needs "
                "(streaming, large transfers, attendees on network) in "
                "the description."
            ),
            "code": "WIFI",
        },
    )
    bind.execute(
        sa.text(
            "UPDATE techops_service_types "
            "SET description = :desc "
            "WHERE code = :code"
        ),
        {
            "desc": (
                "Wired network drop at a specific location for a specific "
                "use. Call out heavy bandwidth needs (streaming, large "
                "transfers) in the per-drop usage notes."
            ),
            "code": "ETHERNET",
        },
    )


def downgrade():
    bind = op.get_bind()

    # Reverse the data updates so a re-upgrade behaves consistently.
    bind.execute(
        sa.text(
            "UPDATE techops_service_types "
            "SET is_active = :active "
            "WHERE code = :code"
        ),
        {"active": True, "code": "BANDWIDTH"},
    )

    # Restore prior descriptions (matches u1v2w3x4y5z6 era).
    bind.execute(
        sa.text(
            "UPDATE techops_service_types "
            "SET description = :desc "
            "WHERE code = :code"
        ),
        {
            "desc": "WiFi for staff or attendees in a specific area or for a use case",
            "code": "WIFI",
        },
    )
    bind.execute(
        sa.text(
            "UPDATE techops_service_types "
            "SET description = :desc "
            "WHERE code = :code"
        ),
        {
            "desc": "Wired network drop at a specific location for a specific use",
            "code": "ETHERNET",
        },
    )

    with op.batch_alter_table('techops_line_details', schema=None) as batch_op:
        batch_op.drop_column('usage')
        batch_op.drop_column('location')

    with op.batch_alter_table('techops_service_types', schema=None) as batch_op:
        batch_op.drop_column('instance_noun')
