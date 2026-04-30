"""Add techops_service_types, techops_line_details, techops_request_details

Creates the three TechOps detail tables that back the TechOps Services
work type. TechOps stays is_active=False until T6 activation; these
tables sit dormant in the schema until then.

- techops_service_types: catalog of 6 service types (WiFi, Ethernet,
  Bandwidth, Phone, Radio Channel, Other), each carrying a default
  approval group used by category routing at submit time.
- techops_line_details: one row per WorkLine in a TechOps request.
  Mirrors the BUDGET/Contract/Supply line-detail pattern with a
  routing snapshot column and a JSON config for service-specific
  extras.
- techops_request_details: one row per WorkItem with the
  per-request primary contact and additional notes catch-all.

Revision ID: r8s9t0u1v2w3
Revises: q7r8s9t0u1v2
Create Date: 2026-04-29 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'r8s9t0u1v2w3'
down_revision = 'q7r8s9t0u1v2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'techops_service_types',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('default_approval_group_id', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by_user_id', sa.String(length=64), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('updated_by_user_id', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ['default_approval_group_id'], ['approval_groups.id'],
            name='fk_techops_service_types_default_approval_group_id',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.create_index(
        'ix_techops_service_types_code',
        'techops_service_types', ['code'], unique=False,
    )
    op.create_index(
        'ix_techops_service_types_default_approval_group_id',
        'techops_service_types', ['default_approval_group_id'], unique=False,
    )

    op.create_table(
        'techops_line_details',
        sa.Column('work_line_id', sa.Integer(), nullable=False),
        sa.Column('service_type_id', sa.Integer(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=True),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('routed_approval_group_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ['routed_approval_group_id'], ['approval_groups.id'],
            name='fk_techops_line_details_routed_approval_group_id',
        ),
        sa.ForeignKeyConstraint(
            ['service_type_id'], ['techops_service_types.id'],
            name='fk_techops_line_details_service_type_id',
        ),
        sa.ForeignKeyConstraint(
            ['work_line_id'], ['work_lines.id'],
            name='fk_techops_line_details_work_line_id',
        ),
        sa.PrimaryKeyConstraint('work_line_id'),
    )
    op.create_index(
        'ix_techops_line_details_service_type_id',
        'techops_line_details', ['service_type_id'], unique=False,
    )
    op.create_index(
        'ix_techops_line_details_routed_approval_group_id',
        'techops_line_details', ['routed_approval_group_id'], unique=False,
    )
    op.create_index(
        'ix_techops_line_details_approval_routing',
        'techops_line_details', ['routed_approval_group_id', 'service_type_id'],
        unique=False,
    )

    op.create_table(
        'techops_request_details',
        sa.Column('work_item_id', sa.Integer(), nullable=False),
        sa.Column('primary_contact_name', sa.String(length=256), nullable=False),
        sa.Column('primary_contact_email', sa.String(length=256), nullable=False),
        sa.Column('additional_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by_user_id', sa.String(length=64), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('updated_by_user_id', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ['work_item_id'], ['work_items.id'],
            name='fk_techops_request_details_work_item_id',
        ),
        sa.PrimaryKeyConstraint('work_item_id'),
    )


def downgrade():
    op.drop_table('techops_request_details')

    op.drop_index('ix_techops_line_details_approval_routing', table_name='techops_line_details')
    op.drop_index('ix_techops_line_details_routed_approval_group_id', table_name='techops_line_details')
    op.drop_index('ix_techops_line_details_service_type_id', table_name='techops_line_details')
    op.drop_table('techops_line_details')

    op.drop_index('ix_techops_service_types_default_approval_group_id', table_name='techops_service_types')
    op.drop_index('ix_techops_service_types_code', table_name='techops_service_types')
    op.drop_table('techops_service_types')
