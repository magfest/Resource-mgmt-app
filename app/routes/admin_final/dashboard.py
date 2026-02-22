"""
Admin Final Review dashboard routes.
"""
from flask import render_template, redirect, url_for, request, flash

from app import db
from app.models import (
    WorkItem,
    WorkLine,
    EventCycle,
    Department,
    ApprovalGroup,
    WORK_ITEM_STATUS_SUBMITTED,
    WORK_ITEM_STATUS_FINALIZED,
    WORK_LINE_STATUS_PENDING,
    WORK_LINE_STATUS_NEEDS_INFO,
    WORK_LINE_STATUS_NEEDS_ADJUSTMENT,
    WORK_LINE_STATUS_APPROVED,
    WORK_LINE_STATUS_REJECTED,
)
from app.routes import get_user_ctx
from app.routes.work.helpers import format_currency
from . import admin_final_bp
from .helpers import (
    require_admin,
    build_admin_queues,
    get_active_event_cycles,
    get_active_departments,
    get_finalization_summary,
    finalize_work_item,
    unfinalize_work_item,
)


@admin_final_bp.get("/admin/final-review/")
def dashboard():
    """
    Admin Final Review dashboard.
    """
    user_ctx = get_user_ctx()
    require_admin(user_ctx)

    # Get filter values from query params
    event_code = request.args.get("event", "").strip()
    dept_code = request.args.get("dept", "").strip()

    # Resolve filters to IDs
    event_cycle_id = None
    department_id = None

    if event_code:
        event_cycle = EventCycle.query.filter_by(code=event_code.upper()).first()
        if event_cycle:
            event_cycle_id = event_cycle.id

    if dept_code:
        department = Department.query.filter_by(code=dept_code.upper()).first()
        if department:
            department_id = department.id

    # Build queues
    queues = build_admin_queues(
        event_cycle_id=event_cycle_id,
        department_id=department_id,
    )

    # Get filter options
    event_cycles = get_active_event_cycles()
    departments = get_active_departments()

    return render_template(
        "admin_final/dashboard.html",
        user_ctx=user_ctx,
        queues=queues,
        event_cycles=event_cycles,
        departments=departments,
        selected_event=event_code,
        selected_dept=dept_code,
        format_currency=format_currency,
        get_finalization_summary=get_finalization_summary,
    )


@admin_final_bp.post("/admin/final-review/finalize/<int:work_item_id>")
def finalize(work_item_id: int):
    """
    Finalize a work item.
    """
    user_ctx = get_user_ctx()
    require_admin(user_ctx)

    work_item = WorkItem.query.get_or_404(work_item_id)
    note = (request.form.get("note") or "").strip()

    success, error = finalize_work_item(work_item, user_ctx, note)

    if not success:
        flash(error, "error")
    else:
        flash(f"Work item {work_item.public_id} finalized.", "success")
        db.session.commit()

    # Redirect back to referrer or dashboard
    referrer = request.form.get("referrer") or url_for("admin_final.dashboard")
    return redirect(referrer)


@admin_final_bp.get("/admin/final-review/unfinalize/<int:work_item_id>")
def unfinalize_form(work_item_id: int):
    """
    Show unfinalize form.
    """
    user_ctx = get_user_ctx()
    require_admin(user_ctx)

    work_item = WorkItem.query.get_or_404(work_item_id)

    return render_template(
        "admin_final/unfinalize.html",
        user_ctx=user_ctx,
        work_item=work_item,
        format_currency=format_currency,
        get_finalization_summary=get_finalization_summary,
    )


@admin_final_bp.post("/admin/final-review/unfinalize/<int:work_item_id>")
def unfinalize(work_item_id: int):
    """
    Unfinalize a work item.
    """
    user_ctx = get_user_ctx()
    require_admin(user_ctx)

    work_item = WorkItem.query.get_or_404(work_item_id)

    reason = (request.form.get("reason") or "").strip()
    reset_lines = request.form.get("reset_lines") == "yes"

    success, error = unfinalize_work_item(work_item, reason, reset_lines, user_ctx)

    if not success:
        flash(error, "error")
        return redirect(url_for("admin_final.unfinalize_form", work_item_id=work_item_id))
    else:
        flash(f"Work item {work_item.public_id} unfinalized.", "success")
        db.session.commit()

    return redirect(url_for("admin_final.dashboard"))


# ============================================================
# Super Admin Home / Landing Page
# ============================================================

@admin_final_bp.get("/admin/")
def admin_home():
    """
    Super-admin landing page with links and overview.
    """
    user_ctx = get_user_ctx()
    require_admin(user_ctx)

    # Gather summary statistics
    stats = {
        "submitted_items": WorkItem.query.filter_by(
            status=WORK_ITEM_STATUS_SUBMITTED,
            is_archived=False
        ).count(),
        "finalized_items": WorkItem.query.filter_by(
            status=WORK_ITEM_STATUS_FINALIZED,
            is_archived=False
        ).count(),
        "pending_lines": WorkLine.query.filter_by(
            status=WORK_LINE_STATUS_PENDING
        ).count(),
        "kicked_back_lines": WorkLine.query.filter(
            WorkLine.status.in_([WORK_LINE_STATUS_NEEDS_INFO, WORK_LINE_STATUS_NEEDS_ADJUSTMENT])
        ).count(),
        "approved_lines": WorkLine.query.filter_by(
            status=WORK_LINE_STATUS_APPROVED
        ).count(),
        "rejected_lines": WorkLine.query.filter_by(
            status=WORK_LINE_STATUS_REJECTED
        ).count(),
    }

    # Get approval groups for quick links
    approval_groups = ApprovalGroup.query.filter_by(is_active=True).order_by(
        ApprovalGroup.sort_order.asc(),
        ApprovalGroup.name.asc()
    ).all()

    # Get event cycles and departments for reference
    event_cycles = get_active_event_cycles()
    departments = get_active_departments()

    return render_template(
        "admin_final/admin_home.html",
        user_ctx=user_ctx,
        stats=stats,
        approval_groups=approval_groups,
        event_cycles=event_cycles,
        departments=departments,
    )
