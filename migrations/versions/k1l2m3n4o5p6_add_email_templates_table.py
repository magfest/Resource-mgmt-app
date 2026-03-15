"""Add email_templates table.

Store email templates in database for admin editing.
Seeds with existing templates from filesystem.

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-03-14

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'k1l2m3n4o5p6'
down_revision = 'j0k1l2m3n4o5'
branch_labels = None
depends_on = None


# Template seed data extracted from existing .txt files and notifications.py
TEMPLATE_SEEDS = [
    {
        'template_key': 'submitted',
        'name': 'Budget Submitted',
        'description': 'Sent to budget admins when a new budget request is submitted and awaiting dispatch.',
        'subject': '[MAGFest Budget] New Submission - {{ work_item.public_id }}',
        'body_text': '''A new budget request has been submitted and is ready for dispatch.

Request: {{ work_item.public_id }}
Department: {{ work_item.portfolio.department.name }}
Event: {{ work_item.portfolio.event_cycle.name }}

Log in to dispatch:
{{ base_url }}/dispatch/
''',
    },
    {
        'template_key': 'dispatched',
        'name': 'Budget Dispatched for Review',
        'description': 'Sent to approval group members when a budget is assigned to their group for review.',
        'subject': '[MAGFest Budget] Ready for Review - {{ work_item.public_id }}',
        'body_text': '''A budget request has been assigned to your reviewer group for review.

Request: {{ work_item.public_id }}
Department: {{ work_item.portfolio.department.name }}
Event: {{ work_item.portfolio.event_cycle.name }}

Log in to review:
{{ base_url }}/approvals/
''',
    },
    {
        'template_key': 'needs_attention',
        'name': 'Budget Needs Attention',
        'description': 'Sent to department members when a reviewer marks lines as NEEDS_INFO or NEEDS_ADJUSTMENT.',
        'subject': '[MAGFest Budget] Action Required - {{ work_item.public_id }}',
        'body_text': '''One or more lines in your budget request need attention.

Request: {{ work_item.public_id }}
Department: {{ work_item.portfolio.department.name }}

Please log in to review and respond:
{{ base_url }}/work/{{ work_item.portfolio.event_cycle.code }}/{{ work_item.portfolio.department.code }}/budget/item/{{ work_item.public_id }}
''',
    },
    {
        'template_key': 'response_received',
        'name': 'Requester Response Received',
        'description': 'Sent to the reviewer when a requester responds to their NEEDS_INFO or NEEDS_ADJUSTMENT feedback.',
        'subject': '[MAGFest Budget] Response Received - {{ work_item.public_id }}',
        'body_text': '''A requester has responded to your feedback on a budget line.

Request: {{ work_item.public_id }}
Department: {{ work_item.portfolio.department.name }}

Log in to continue review:
{{ base_url }}/approvals/
''',
    },
    {
        'template_key': 'finalized',
        'name': 'Budget Finalized',
        'description': 'Sent to department members when their budget request has been finalized.',
        'subject': '[MAGFest Budget] Finalized - {{ work_item.public_id }}',
        'body_text': '''Your budget request has been finalized.

Request: {{ work_item.public_id }}
Department: {{ work_item.portfolio.department.name }}
Event: {{ work_item.portfolio.event_cycle.name }}

Log in to view details:
{{ base_url }}/work/{{ work_item.portfolio.event_cycle.code }}/{{ work_item.portfolio.department.code }}/budget/item/{{ work_item.public_id }}
''',
    },
]


def upgrade():
    # Create email_templates table
    op.create_table(
        'email_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('template_key', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('subject', sa.String(length=256), nullable=False),
        sa.Column('body_text', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_by_user_id', sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_email_templates_template_key', 'email_templates', ['template_key'], unique=True)

    # Seed with existing templates
    email_templates = sa.table(
        'email_templates',
        sa.column('template_key', sa.String),
        sa.column('name', sa.String),
        sa.column('description', sa.Text),
        sa.column('subject', sa.String),
        sa.column('body_text', sa.Text),
        sa.column('is_active', sa.Boolean),
        sa.column('version', sa.Integer),
    )

    op.bulk_insert(email_templates, TEMPLATE_SEEDS)


def downgrade():
    op.drop_index('ix_email_templates_template_key', table_name='email_templates')
    op.drop_table('email_templates')
