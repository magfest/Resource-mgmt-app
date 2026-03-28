"""
Admin routes for approval group management.
"""
from __future__ import annotations

from flask import Blueprint, redirect, url_for, request, abort, flash

from app import db
from app.models import (
    ApprovalGroup,
    ExpenseAccount,
    CONFIG_AUDIT_CREATE,
    CONFIG_AUDIT_UPDATE,
    CONFIG_AUDIT_ARCHIVE,
    CONFIG_AUDIT_RESTORE,
)
from app.routes import h
from .helpers import (
    require_budget_admin,
    render_budget_admin_page,
    log_config_change,
    track_changes,
    validate_code_length,
    CODE_MAX_LENGTH,
    safe_int,
    safe_int_or_none,
    sort_with_override,
)

approval_groups_bp = Blueprint('approval_groups', __name__, url_prefix='/approval-groups')


def _get_approval_group_or_404(group_id: int) -> ApprovalGroup:
    """Get approval group by ID or abort with 404."""
    group = db.session.get(ApprovalGroup, group_id)
    if not group:
        abort(404, "Approval group not found")
    return group


def _group_to_dict(group: ApprovalGroup) -> dict:
    """Convert approval group to dict for change tracking."""
    return {
        "code": group.code,
        "name": group.name,
        "description": group.description,
        "is_active": group.is_active,
        "sort_order": group.sort_order,
    }


@approval_groups_bp.get("/")
@require_budget_admin
def list_approval_groups():
    """List all approval groups."""
    show_inactive = request.args.get("show_inactive") == "1"
    sort_by = request.args.get("sort_by", "sort_order")
    sort_dir = request.args.get("sort_dir", "asc")

    query = db.session.query(ApprovalGroup)
    if not show_inactive:
        query = query.filter(ApprovalGroup.is_active == True)

    # Sortable columns whitelist
    sortable = {
        "code": ApprovalGroup.code,
        "name": ApprovalGroup.name,
        "sort_order": ApprovalGroup.sort_order,
    }

    if sort_by in sortable:
        col = sortable[sort_by]
        order = col.desc() if sort_dir == "desc" else col.asc()
        query = query.order_by(order)
    else:
        query = query.order_by(*sort_with_override(ApprovalGroup))

    groups = query.all()

    # Get expense account counts per group
    account_counts = {}
    for group in groups:
        count = (
            db.session.query(ExpenseAccount)
            .filter(ExpenseAccount.approval_group_id == group.id)
            .filter(ExpenseAccount.is_active == True)
            .count()
        )
        account_counts[group.id] = count

    return render_budget_admin_page(
        "admin/approval_groups/list.html",
        groups=groups,
        account_counts=account_counts,
        show_inactive=show_inactive,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@approval_groups_bp.get("/new")
@require_budget_admin
def new_approval_group():
    """Show new approval group form."""
    return render_budget_admin_page(
        "admin/approval_groups/form.html",
        group=None,
    )


@approval_groups_bp.post("/")
@require_budget_admin
def create_approval_group():
    """Create a new approval group."""
    code = (request.form.get("code") or "").strip().upper()
    name = (request.form.get("name") or "").strip()

    if not code or not name:
        flash("Code and name are required", "error")
        return redirect(url_for(".new_approval_group"))

    # Validate code length
    if not validate_code_length(code, "Code"):
        return redirect(url_for(".new_approval_group"))

    # Check for duplicate code
    existing = db.session.query(ApprovalGroup).filter_by(code=code).first()
    if existing:
        flash(f"An approval group with code '{code}' already exists", "error")
        return redirect(url_for(".new_approval_group"))

    group = ApprovalGroup(
        code=code,
        name=name,
        description=(request.form.get("description") or "").strip() or None,
        is_active=request.form.get("is_active") == "1",
        sort_order=safe_int_or_none(request.form.get("sort_order")),
        created_by_user_id=h.get_active_user_id(),
        updated_by_user_id=h.get_active_user_id(),
    )

    db.session.add(group)
    db.session.flush()

    log_config_change("approval_group", group.id, CONFIG_AUDIT_CREATE)

    db.session.commit()
    flash(f"Created approval group: {group.name}", "success")
    return redirect(url_for(".list_approval_groups"))


@approval_groups_bp.get("/<int:group_id>")
@require_budget_admin
def edit_approval_group(group_id: int):
    """Show edit form for approval group."""
    group = _get_approval_group_or_404(group_id)

    # Count linked expense accounts
    account_count = (
        db.session.query(ExpenseAccount)
        .filter(ExpenseAccount.approval_group_id == group_id)
        .count()
    )

    return render_budget_admin_page(
        "admin/approval_groups/form.html",
        group=group,
        account_count=account_count,
    )


@approval_groups_bp.post("/<int:group_id>")
@require_budget_admin
def update_approval_group(group_id: int):
    """Update an approval group."""
    group = _get_approval_group_or_404(group_id)

    old_values = _group_to_dict(group)

    code = (request.form.get("code") or "").strip().upper()
    name = (request.form.get("name") or "").strip()

    if not code or not name:
        flash("Code and name are required", "error")
        return redirect(url_for(".edit_approval_group", group_id=group_id))

    # Validate code length
    if not validate_code_length(code, "Code"):
        return redirect(url_for(".edit_approval_group", group_id=group_id))

    # Check for duplicate code
    existing = db.session.query(ApprovalGroup).filter(
        ApprovalGroup.code == code,
        ApprovalGroup.id != group_id
    ).first()
    if existing:
        flash(f"An approval group with code '{code}' already exists", "error")
        return redirect(url_for(".edit_approval_group", group_id=group_id))

    group.code = code
    group.name = name
    group.description = (request.form.get("description") or "").strip() or None
    group.is_active = request.form.get("is_active") == "1"
    group.sort_order = safe_int_or_none(request.form.get("sort_order"))
    group.updated_by_user_id = h.get_active_user_id()

    new_values = _group_to_dict(group)
    changes = track_changes(old_values, new_values)
    if changes:
        log_config_change("approval_group", group.id, CONFIG_AUDIT_UPDATE, changes)

    db.session.commit()
    flash(f"Updated approval group: {group.name}", "success")
    return redirect(url_for(".list_approval_groups"))


@approval_groups_bp.post("/<int:group_id>/archive")
@require_budget_admin
def archive_approval_group(group_id: int):
    """Archive (soft-delete) an approval group."""
    group = _get_approval_group_or_404(group_id)

    if not group.is_active:
        flash("Approval group is already archived", "warning")
        return redirect(url_for(".list_approval_groups"))

    group.is_active = False
    group.updated_by_user_id = h.get_active_user_id()

    log_config_change("approval_group", group.id, CONFIG_AUDIT_ARCHIVE)

    db.session.commit()
    flash(f"Archived approval group: {group.name}", "success")
    return redirect(url_for(".list_approval_groups"))


@approval_groups_bp.post("/<int:group_id>/restore")
@require_budget_admin
def restore_approval_group(group_id: int):
    """Restore an archived approval group."""
    group = _get_approval_group_or_404(group_id)

    if group.is_active:
        flash("Approval group is already active", "warning")
        return redirect(url_for(".list_approval_groups"))

    group.is_active = True
    group.updated_by_user_id = h.get_active_user_id()

    log_config_change("approval_group", group.id, CONFIG_AUDIT_RESTORE)

    db.session.commit()
    flash(f"Restored approval group: {group.name}", "success")
    return redirect(url_for(".list_approval_groups"))
