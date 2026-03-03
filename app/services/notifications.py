"""
High-level notification functions for budget workflow events.

Each function:
- Gets recipient emails via helper functions
- Renders email template
- Sends via send_email() which handles rate limits, debounce, and logging
- Logs warnings for edge cases (no recipients, user not found, etc.)
"""
from __future__ import annotations

import logging
from flask import render_template, current_app
from typing import List, Set

from app import db
from app.models import (
    WorkItem,
    User,
    UserRole,
    DepartmentMembership,
    DivisionMembership,
    WorkLineReview,
    ROLE_WORKTYPE_ADMIN,
    ROLE_SUPER_ADMIN,
    ROLE_APPROVER,
)
from .email import send_email

logger = logging.getLogger(__name__)


def get_base_url() -> str:
    """Get base URL for email links."""
    return current_app.config.get('BASE_URL', 'https://budget.magfest.org')


def notify_budget_submitted(work_item: WorkItem) -> int:
    """
    Notify budget admins that a new budget was submitted and is awaiting dispatch.

    Called after: work_item.status set to AWAITING_DISPATCH
    Returns: Number of emails sent
    """
    recipients = _get_budget_admin_emails()

    if not recipients:
        logger.warning(f"No budget admin recipients found for submission notification: {work_item.public_id}")
        return 0

    subject = f'[MAGFest Budget] New Submission - {work_item.public_id}'
    body = render_template(
        'email/submitted.txt',
        work_item=work_item,
        base_url=get_base_url(),
    )

    sent_count = 0
    for email in recipients:
        if send_email(
            to=email,
            subject=subject,
            body_text=body,
            template_key='submitted',
            work_item_id=work_item.id,
        ):
            sent_count += 1

    logger.info(f"Sent {sent_count}/{len(recipients)} submission notifications for {work_item.public_id}")
    return sent_count


def notify_budget_dispatched(work_item: WorkItem, approval_group_ids: List[int]) -> int:
    """
    Notify approval group members that a budget is ready for their review.

    Called after: work_item dispatched to approval groups
    Returns: Number of emails sent
    """
    if not approval_group_ids:
        logger.warning(f"No approval groups provided for dispatch notification: {work_item.public_id}")
        return 0

    recipients = _get_approval_group_emails(approval_group_ids)

    if not recipients:
        logger.warning(f"No approver recipients found for groups {approval_group_ids}: {work_item.public_id}")
        return 0

    subject = f'[MAGFest Budget] Ready for Review - {work_item.public_id}'
    body = render_template(
        'email/dispatched.txt',
        work_item=work_item,
        base_url=get_base_url(),
    )

    sent_count = 0
    for email in recipients:
        if send_email(
            to=email,
            subject=subject,
            body_text=body,
            template_key='dispatched',
            work_item_id=work_item.id,
        ):
            sent_count += 1

    logger.info(f"Sent {sent_count}/{len(recipients)} dispatch notifications for {work_item.public_id}")
    return sent_count


def notify_needs_attention(work_item: WorkItem) -> int:
    """
    Notify department members that their budget request needs attention.

    Called after: reviewer marks a line as NEEDS_INFO or NEEDS_ADJUSTMENT
    Returns: Number of emails sent
    """
    recipients = _get_department_member_emails(
        department_id=work_item.portfolio.department_id,
        event_cycle_id=work_item.portfolio.event_cycle_id,
    )

    if not recipients:
        logger.warning(f"No department member recipients found for needs_attention: {work_item.public_id}")
        return 0

    subject = f'[MAGFest Budget] Action Required - {work_item.public_id}'
    body = render_template(
        'email/needs_attention.txt',
        work_item=work_item,
        base_url=get_base_url(),
    )

    sent_count = 0
    for email in recipients:
        if send_email(
            to=email,
            subject=subject,
            body_text=body,
            template_key='needs_attention',
            work_item_id=work_item.id,
        ):
            sent_count += 1

    logger.info(f"Sent {sent_count}/{len(recipients)} needs_attention notifications for {work_item.public_id}")
    return sent_count


def notify_response_received(work_item: WorkItem, reviewer_user_id: str) -> bool:
    """
    Notify the reviewer that the requester has responded to their feedback.

    Called after: requester responds to NEEDS_INFO or NEEDS_ADJUSTMENT
    Returns: True if email sent, False otherwise
    """
    user = db.session.query(User).filter_by(id=reviewer_user_id).first()
    if not user:
        logger.warning(f"Reviewer user not found for response notification: user_id={reviewer_user_id}, work_item={work_item.public_id}")
        return False

    if not user.email:
        logger.warning(f"Reviewer has no email for response notification: user_id={reviewer_user_id}, work_item={work_item.public_id}")
        return False

    subject = f'[MAGFest Budget] Response Received - {work_item.public_id}'
    body = render_template(
        'email/response_received.txt',
        work_item=work_item,
        base_url=get_base_url(),
    )

    success = send_email(
        to=user.email,
        subject=subject,
        body_text=body,
        template_key='response_received',
        work_item_id=work_item.id,
        recipient_user_id=user.id,
    )

    if success:
        logger.info(f"Sent response_received notification to {user.email} for {work_item.public_id}")

    return success


def notify_budget_finalized(work_item: WorkItem) -> int:
    """
    Notify department members that their budget has been finalized.

    Called after: admin finalizes the work item
    Returns: Number of emails sent
    """
    recipients = _get_department_member_emails(
        department_id=work_item.portfolio.department_id,
        event_cycle_id=work_item.portfolio.event_cycle_id,
    )

    if not recipients:
        logger.warning(f"No department member recipients found for finalized notification: {work_item.public_id}")
        return 0

    subject = f'[MAGFest Budget] Finalized - {work_item.public_id}'
    body = render_template(
        'email/finalized.txt',
        work_item=work_item,
        base_url=get_base_url(),
    )

    sent_count = 0
    for email in recipients:
        if send_email(
            to=email,
            subject=subject,
            body_text=body,
            template_key='finalized',
            work_item_id=work_item.id,
        ):
            sent_count += 1

    logger.info(f"Sent {sent_count}/{len(recipients)} finalized notifications for {work_item.public_id}")
    return sent_count


# ============================================================
# Recipient Helpers
# ============================================================

def _get_budget_admin_emails() -> List[str]:
    """
    Get emails of users who should receive budget submission notifications.

    Includes: SUPER_ADMIN and WORKTYPE_ADMIN (for budget work type)
    """
    from app.models import WorkType

    emails: Set[str] = set()

    # Get the budget work type ID
    budget_wt = db.session.query(WorkType).filter_by(code="BUDGET").first()

    # Find all admin users
    admin_roles = db.session.query(UserRole).filter(
        UserRole.role_code.in_([ROLE_SUPER_ADMIN, ROLE_WORKTYPE_ADMIN])
    ).all()

    # Filter roles to those we want to notify
    relevant_user_ids = []
    for role in admin_roles:
        if role.role_code == ROLE_SUPER_ADMIN:
            relevant_user_ids.append(role.user_id)
        elif role.role_code == ROLE_WORKTYPE_ADMIN:
            # Only include if this is the budget work type admin or unscoped
            if budget_wt and (role.work_type_id == budget_wt.id or role.work_type_id is None):
                relevant_user_ids.append(role.user_id)

    # Batch load all users in one query
    if relevant_user_ids:
        users = db.session.query(User).filter(User.id.in_(relevant_user_ids)).all()
        for user in users:
            if user.is_active and user.email:
                emails.add(user.email)

    return list(emails)


def _get_approval_group_emails(group_ids: List[int]) -> List[str]:
    """
    Get emails of users who are approvers for the given approval groups.
    """
    if not group_ids:
        return []

    emails: Set[str] = set()

    # Find users with APPROVER role for these groups
    approver_roles = db.session.query(UserRole).filter(
        UserRole.role_code == ROLE_APPROVER,
        UserRole.approval_group_id.in_(group_ids),
    ).all()

    # Batch load all users in one query
    user_ids = [role.user_id for role in approver_roles]
    if user_ids:
        users = db.session.query(User).filter(User.id.in_(user_ids)).all()
        for user in users:
            if user.is_active and user.email:
                emails.add(user.email)

    return list(emails)


def _get_department_member_emails(department_id: int, event_cycle_id: int) -> List[str]:
    """
    Get emails of department members (direct or via division membership).
    """
    from app.models import Department

    emails: Set[str] = set()
    user_ids: Set[str] = set()

    # Direct department memberships
    dept_memberships = db.session.query(DepartmentMembership).filter_by(
        department_id=department_id,
        event_cycle_id=event_cycle_id,
    ).all()

    for m in dept_memberships:
        user_ids.add(m.user_id)

    # Division memberships (for departments within that division)
    dept = db.session.query(Department).get(department_id)
    if dept and dept.division_id:
        div_memberships = db.session.query(DivisionMembership).filter_by(
            division_id=dept.division_id,
            event_cycle_id=event_cycle_id,
        ).all()

        for m in div_memberships:
            user_ids.add(m.user_id)

    # Batch load all users in one query
    if user_ids:
        users = db.session.query(User).filter(User.id.in_(user_ids)).all()
        for user in users:
            if user.is_active and user.email:
                emails.add(user.email)

    return list(emails)
