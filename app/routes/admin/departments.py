"""
Admin routes for department management.
"""
from __future__ import annotations

from flask import Blueprint, redirect, url_for, request, abort, flash

from app import db
from app.models import (
    Department,
    DepartmentMembership,
    DepartmentMembershipWorkTypeAccess,
    Division,
    EventCycle,
    User,
    WorkType,
    CONFIG_AUDIT_CREATE,
    CONFIG_AUDIT_UPDATE,
    CONFIG_AUDIT_ARCHIVE,
    CONFIG_AUDIT_RESTORE,
)
from app.routes import h
from .helpers import (
    require_super_admin,
    render_admin_config_page,
    log_config_change,
    track_changes,
    validate_code_length,
    CODE_MAX_LENGTH,
    safe_int,
)

departments_bp = Blueprint('departments', __name__, url_prefix='/departments')


def _get_department_or_404(dept_id: int) -> Department:
    """Get department by ID or abort with 404."""
    dept = db.session.get(Department, dept_id)
    if not dept:
        abort(404, "Department not found")
    return dept


def _dept_to_dict(dept: Department) -> dict:
    """Convert department to dict for change tracking."""
    return {
        "code": dept.code,
        "name": dept.name,
        "division_id": dept.division_id,
        "description": dept.description,
        "mailing_list": dept.mailing_list,
        "slack_channel": dept.slack_channel,
        "is_active": dept.is_active,
        "sort_order": dept.sort_order,
    }


def _get_active_divisions():
    """Get all active divisions for dropdown."""
    return (
        db.session.query(Division)
        .filter(Division.is_active == True)
        .order_by(Division.sort_order, Division.name)
        .all()
    )


def _get_active_work_types():
    """Get all active work types for access configuration."""
    return (
        db.session.query(WorkType)
        .filter(WorkType.is_active == True)
        .order_by(WorkType.sort_order, WorkType.name)
        .all()
    )


@departments_bp.get("/")
@require_super_admin
def list_departments():
    """List all departments."""
    show_inactive = request.args.get("show_inactive") == "1"

    query = db.session.query(Department)
    if not show_inactive:
        query = query.filter(Department.is_active == True)

    departments = query.order_by(Department.sort_order, Department.name).all()

    # Get member counts per department
    member_counts = {}
    for dept in departments:
        count = (
            db.session.query(DepartmentMembership)
            .filter(DepartmentMembership.department_id == dept.id)
            .count()
        )
        member_counts[dept.id] = count

    return render_admin_config_page(
        "admin/departments/list.html",
        departments=departments,
        member_counts=member_counts,
        show_inactive=show_inactive,
    )


@departments_bp.get("/new")
@require_super_admin
def new_department():
    """Show new department form."""
    return render_admin_config_page(
        "admin/departments/form.html",
        department=None,
        divisions=_get_active_divisions(),
    )


@departments_bp.post("/")
@require_super_admin
def create_department():
    """Create a new department."""
    code = (request.form.get("code") or "").strip().upper()
    name = (request.form.get("name") or "").strip()

    if not code or not name:
        flash("Code and name are required", "error")
        return redirect(url_for(".new_department"))

    # Validate code length
    if not validate_code_length(code, "Code"):
        return redirect(url_for(".new_department"))

    # Check for duplicate code
    existing = db.session.query(Department).filter_by(code=code).first()
    if existing:
        flash(f"A department with code '{code}' already exists", "error")
        return redirect(url_for(".new_department"))

    # Parse division_id
    division_id_str = request.form.get("division_id") or ""
    division_id = int(division_id_str) if division_id_str.strip() else None

    dept = Department(
        code=code,
        name=name,
        division_id=division_id,
        description=(request.form.get("description") or "").strip() or None,
        mailing_list=(request.form.get("mailing_list") or "").strip() or None,
        slack_channel=(request.form.get("slack_channel") or "").strip() or None,
        is_active=request.form.get("is_active") == "1",
        sort_order=safe_int(request.form.get("sort_order")),
        created_by_user_id=h.get_active_user_id(),
        updated_by_user_id=h.get_active_user_id(),
    )

    db.session.add(dept)
    db.session.flush()

    log_config_change("department", dept.id, CONFIG_AUDIT_CREATE)

    db.session.commit()
    flash(f"Created department: {dept.name}", "success")
    return redirect(url_for(".list_departments"))


@departments_bp.get("/<int:dept_id>")
@require_super_admin
def edit_department(dept_id: int):
    """Show edit form for department."""
    dept = _get_department_or_404(dept_id)

    # Get member count
    member_count = (
        db.session.query(DepartmentMembership)
        .filter(DepartmentMembership.department_id == dept_id)
        .count()
    )

    return render_admin_config_page(
        "admin/departments/form.html",
        department=dept,
        member_count=member_count,
        divisions=_get_active_divisions(),
    )


@departments_bp.post("/<int:dept_id>")
@require_super_admin
def update_department(dept_id: int):
    """Update a department."""
    dept = _get_department_or_404(dept_id)

    old_values = _dept_to_dict(dept)

    code = (request.form.get("code") or "").strip().upper()
    name = (request.form.get("name") or "").strip()

    if not code or not name:
        flash("Code and name are required", "error")
        return redirect(url_for(".edit_department", dept_id=dept_id))

    # Validate code length
    if not validate_code_length(code, "Code"):
        return redirect(url_for(".edit_department", dept_id=dept_id))

    # Check for duplicate code
    existing = db.session.query(Department).filter(
        Department.code == code,
        Department.id != dept_id
    ).first()
    if existing:
        flash(f"A department with code '{code}' already exists", "error")
        return redirect(url_for(".edit_department", dept_id=dept_id))

    # Parse division_id
    division_id_str = request.form.get("division_id") or ""
    division_id = int(division_id_str) if division_id_str.strip() else None

    dept.code = code
    dept.name = name
    dept.division_id = division_id
    dept.description = (request.form.get("description") or "").strip() or None
    dept.mailing_list = (request.form.get("mailing_list") or "").strip() or None
    dept.slack_channel = (request.form.get("slack_channel") or "").strip() or None
    dept.is_active = request.form.get("is_active") == "1"
    dept.sort_order = safe_int(request.form.get("sort_order"))
    dept.updated_by_user_id = h.get_active_user_id()

    new_values = _dept_to_dict(dept)
    changes = track_changes(old_values, new_values)
    if changes:
        log_config_change("department", dept.id, CONFIG_AUDIT_UPDATE, changes)

    db.session.commit()
    flash(f"Updated department: {dept.name}", "success")
    return redirect(url_for(".list_departments"))


@departments_bp.post("/<int:dept_id>/archive")
@require_super_admin
def archive_department(dept_id: int):
    """Archive (soft-delete) a department."""
    dept = _get_department_or_404(dept_id)

    if not dept.is_active:
        flash("Department is already archived", "warning")
        return redirect(url_for(".list_departments"))

    dept.is_active = False
    dept.updated_by_user_id = h.get_active_user_id()

    log_config_change("department", dept.id, CONFIG_AUDIT_ARCHIVE)

    db.session.commit()
    flash(f"Archived department: {dept.name}", "success")
    return redirect(url_for(".list_departments"))


@departments_bp.post("/<int:dept_id>/restore")
@require_super_admin
def restore_department(dept_id: int):
    """Restore an archived department."""
    dept = _get_department_or_404(dept_id)

    if dept.is_active:
        flash("Department is already active", "warning")
        return redirect(url_for(".list_departments"))

    dept.is_active = True
    dept.updated_by_user_id = h.get_active_user_id()

    log_config_change("department", dept.id, CONFIG_AUDIT_RESTORE)

    db.session.commit()
    flash(f"Restored department: {dept.name}", "success")
    return redirect(url_for(".list_departments"))


# ============================================================
# Department Membership Management
# ============================================================

@departments_bp.get("/<int:dept_id>/members")
@require_super_admin
def list_members(dept_id: int):
    """List all members of a department."""
    dept = _get_department_or_404(dept_id)

    # Get all memberships for this department
    memberships = (
        db.session.query(DepartmentMembership)
        .filter(DepartmentMembership.department_id == dept_id)
        .join(User)
        .join(EventCycle)
        .order_by(EventCycle.sort_order, User.display_name)
        .all()
    )

    # Get available event cycles for adding new members
    event_cycles = (
        db.session.query(EventCycle)
        .filter(EventCycle.is_active == True)
        .order_by(EventCycle.sort_order)
        .all()
    )

    # Get active work types for display
    work_types = _get_active_work_types()

    return render_admin_config_page(
        "admin/departments/members.html",
        department=dept,
        memberships=memberships,
        event_cycles=event_cycles,
        work_types=work_types,
    )


@departments_bp.get("/<int:dept_id>/members/add")
@require_super_admin
def add_member_form(dept_id: int):
    """Show form to add a department member."""
    dept = _get_department_or_404(dept_id)

    # Get available users (all active users)
    users = (
        db.session.query(User)
        .filter(User.is_active == True)
        .order_by(User.display_name)
        .all()
    )

    # Get available event cycles
    event_cycles = (
        db.session.query(EventCycle)
        .filter(EventCycle.is_active == True)
        .order_by(EventCycle.sort_order)
        .all()
    )

    # Get active work types for access configuration
    work_types = _get_active_work_types()

    return render_admin_config_page(
        "admin/departments/member_form.html",
        department=dept,
        membership=None,
        users=users,
        event_cycles=event_cycles,
        work_types=work_types,
    )


@departments_bp.post("/<int:dept_id>/members")
@require_super_admin
def add_member(dept_id: int):
    """Add a member to the department."""
    dept = _get_department_or_404(dept_id)

    user_id = request.form.get("user_id")
    event_cycle_id = request.form.get("event_cycle_id")

    if not user_id or not event_cycle_id:
        flash("User and event cycle are required", "error")
        return redirect(url_for(".add_member_form", dept_id=dept_id))

    # Check for existing membership
    existing = db.session.query(DepartmentMembership).filter_by(
        user_id=user_id,
        department_id=dept_id,
        event_cycle_id=int(event_cycle_id),
    ).first()

    if existing:
        flash("This user is already a member of this department for this event cycle", "error")
        return redirect(url_for(".add_member_form", dept_id=dept_id))

    membership = DepartmentMembership(
        user_id=user_id,
        department_id=dept_id,
        event_cycle_id=int(event_cycle_id),
        can_view=request.form.get("can_view") == "1",
        can_edit=request.form.get("can_edit") == "1",
        is_department_head=request.form.get("is_department_head") == "1",
    )

    db.session.add(membership)
    db.session.flush()  # Get the membership ID

    # Add work type access records
    work_types = _get_active_work_types()
    for wt in work_types:
        wt_can_view = request.form.get(f"wt_{wt.id}_view") == "1"
        wt_can_edit = request.form.get(f"wt_{wt.id}_edit") == "1"

        if wt_can_view or wt_can_edit:
            wta = DepartmentMembershipWorkTypeAccess(
                department_membership_id=membership.id,
                work_type_id=wt.id,
                can_view=wt_can_view,
                can_edit=wt_can_edit,
            )
            db.session.add(wta)

    db.session.commit()

    user = db.session.get(User, user_id)
    flash(f"Added {user.display_name} to {dept.name}", "success")
    return redirect(url_for(".list_members", dept_id=dept_id))


@departments_bp.get("/<int:dept_id>/members/<int:membership_id>")
@require_super_admin
def edit_member(dept_id: int, membership_id: int):
    """Show form to edit a department membership."""
    dept = _get_department_or_404(dept_id)

    membership = db.session.get(DepartmentMembership, membership_id)
    if not membership or membership.department_id != dept_id:
        abort(404, "Membership not found")

    # Get active work types for access configuration
    work_types = _get_active_work_types()

    return render_admin_config_page(
        "admin/departments/member_form.html",
        department=dept,
        membership=membership,
        users=None,  # Can't change user on edit
        event_cycles=None,  # Can't change event cycle on edit
        work_types=work_types,
    )


@departments_bp.post("/<int:dept_id>/members/<int:membership_id>")
@require_super_admin
def update_member(dept_id: int, membership_id: int):
    """Update a department membership."""
    dept = _get_department_or_404(dept_id)

    membership = db.session.get(DepartmentMembership, membership_id)
    if not membership or membership.department_id != dept_id:
        abort(404, "Membership not found")

    membership.can_view = request.form.get("can_view") == "1"
    membership.can_edit = request.form.get("can_edit") == "1"
    membership.is_department_head = request.form.get("is_department_head") == "1"

    # Update work type access records
    work_types = _get_active_work_types()
    for wt in work_types:
        wt_can_view = request.form.get(f"wt_{wt.id}_view") == "1"
        wt_can_edit = request.form.get(f"wt_{wt.id}_edit") == "1"

        # Find existing access record
        existing_wta = membership.get_work_type_access(wt.id)

        if wt_can_view or wt_can_edit:
            if existing_wta:
                existing_wta.can_view = wt_can_view
                existing_wta.can_edit = wt_can_edit
            else:
                wta = DepartmentMembershipWorkTypeAccess(
                    department_membership_id=membership.id,
                    work_type_id=wt.id,
                    can_view=wt_can_view,
                    can_edit=wt_can_edit,
                )
                db.session.add(wta)
        else:
            # Remove access if both are unchecked
            if existing_wta:
                db.session.delete(existing_wta)

    db.session.commit()

    flash(f"Updated membership for {membership.user.display_name}", "success")
    return redirect(url_for(".list_members", dept_id=dept_id))


@departments_bp.post("/<int:dept_id>/members/<int:membership_id>/delete")
@require_super_admin
def delete_member(dept_id: int, membership_id: int):
    """Remove a member from the department."""
    dept = _get_department_or_404(dept_id)

    membership = db.session.get(DepartmentMembership, membership_id)
    if not membership or membership.department_id != dept_id:
        abort(404, "Membership not found")

    user_name = membership.user.display_name
    db.session.delete(membership)
    db.session.commit()

    flash(f"Removed {user_name} from {dept.name}", "success")
    return redirect(url_for(".list_members", dept_id=dept_id))
