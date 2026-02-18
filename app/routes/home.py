"""
Home page route - adapts based on user role.
"""
from __future__ import annotations

from flask import Blueprint, redirect, url_for

from app import db
from app.models import (
    User,
    Department,
    Division,
    DepartmentMembership,
    DivisionMembership,
    EventCycle,
    ApprovalGroup,
    UserRole,
    WorkItem,
    WorkLine,
    BudgetLineDetail,
    ExpenseAccount,
    ROLE_SUPER_ADMIN,
    ROLE_APPROVER,
)
from app.routes import h, get_user_ctx, render_page

home_bp = Blueprint('home', __name__)


@home_bp.get("/")
def index():
    """Home page - shows personalized dashboard based on user role."""
    h.ensure_demo_users()

    user_ctx = get_user_ctx()
    user = user_ctx.user

    # Get the default event cycle
    default_cycle = (
        db.session.query(EventCycle)
        .filter(EventCycle.is_default == True)
        .first()
    )

    if not default_cycle:
        default_cycle = (
            db.session.query(EventCycle)
            .filter(EventCycle.is_active == True)
            .order_by(EventCycle.sort_order)
            .first()
        )

    # Build context based on user's access
    context = {
        "user": user,
        "default_cycle": default_cycle,
    }

    # Check if super admin
    is_super_admin = ROLE_SUPER_ADMIN in user_ctx.roles
    context["is_super_admin"] = is_super_admin

    # Get approval groups user can review
    approval_groups = []
    if user_ctx.approval_group_ids:
        approval_groups = (
            db.session.query(ApprovalGroup)
            .filter(ApprovalGroup.id.in_(user_ctx.approval_group_ids))
            .filter(ApprovalGroup.is_active == True)
            .order_by(ApprovalGroup.sort_order)
            .all()
        )
    context["approval_groups"] = approval_groups

    # Get departments user has access to (via department membership)
    dept_memberships = []
    if default_cycle:
        dept_memberships = (
            db.session.query(DepartmentMembership)
            .join(Department)
            .filter(DepartmentMembership.user_id == user_ctx.user_id)
            .filter(DepartmentMembership.event_cycle_id == default_cycle.id)
            .filter(Department.is_active == True)
            .order_by(Department.sort_order, Department.name)
            .all()
        )
    context["dept_memberships"] = dept_memberships

    # Get divisions user has access to (via division membership)
    div_memberships = []
    if default_cycle:
        div_memberships = (
            db.session.query(DivisionMembership)
            .join(Division)
            .filter(DivisionMembership.user_id == user_ctx.user_id)
            .filter(DivisionMembership.event_cycle_id == default_cycle.id)
            .filter(Division.is_active == True)
            .order_by(Division.sort_order, Division.name)
            .all()
        )
    context["div_memberships"] = div_memberships

    # Get stats for admins
    if is_super_admin:
        # Count submitted work items
        submitted_count = (
            db.session.query(WorkItem)
            .filter(WorkItem.status == "SUBMITTED")
            .count()
        )
        context["submitted_count"] = submitted_count

        # Count pending work lines
        pending_lines = (
            db.session.query(WorkLine)
            .filter(WorkLine.status == "PENDING")
            .count()
        )
        context["pending_lines"] = pending_lines

    # Get stats for approvers
    if approval_groups:
        # Count lines pending review in user's approval groups
        pending_for_approver = (
            db.session.query(WorkLine)
            .join(BudgetLineDetail, BudgetLineDetail.work_line_id == WorkLine.id)
            .join(ExpenseAccount, ExpenseAccount.id == BudgetLineDetail.expense_account_id)
            .filter(ExpenseAccount.approval_group_id.in_(user_ctx.approval_group_ids))
            .filter(WorkLine.status == "PENDING")
            .count()
        )
        context["pending_for_approver"] = pending_for_approver

    # Determine if user has any access
    has_any_access = (
        is_super_admin or
        bool(approval_groups) or
        bool(dept_memberships) or
        bool(div_memberships)
    )
    context["has_any_access"] = has_any_access

    return render_page("home.html", **context)
