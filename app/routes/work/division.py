"""
Division landing page - shows all departments in a division for an event.
"""
from __future__ import annotations

from flask import abort

from app import db
from app.models import (
    EventCycle,
    Division,
    Department,
    DivisionMembership,
    WorkType,
    WorkPortfolio,
)
from app.routes import get_user_ctx, render_page
from app.routes.work.helpers import (
    get_active_work_types,
    compute_portfolio_status_summary,
    is_budget_admin,
    get_enabled_department_ids_for_event,
)
from . import work_bp


@work_bp.get("/<event>/division/<div_code>/")
def division_home(event: str, div_code: str):
    """
    Division landing page - shows departments in a division with budget status.

    URL: /<event>/division/<div_code>/
    """
    user_ctx = get_user_ctx()

    # Look up event cycle
    event_cycle = EventCycle.query.filter_by(code=event.upper()).first()
    if not event_cycle:
        abort(404, f"Event cycle not found: {event}")

    # Look up division
    division = Division.query.filter_by(code=div_code.upper()).first()
    if not division:
        abort(404, f"Division not found: {div_code}")

    # Check access: user must be a division member, budget admin, or super admin
    div_membership = DivisionMembership.query.filter_by(
        user_id=user_ctx.user_id,
        division_id=division.id,
        event_cycle_id=event_cycle.id,
    ).first()

    is_admin = user_ctx.is_super_admin or is_budget_admin(user_ctx)

    if not div_membership and not is_admin:
        abort(403, "You do not have access to this division.")

    # Get departments in this division that are enabled for this event
    enabled_dept_ids = get_enabled_department_ids_for_event(event_cycle.id)
    departments = (
        Department.query
        .filter(Department.division_id == division.id)
        .filter(Department.is_active.is_(True))
        .filter(Department.id.in_(enabled_dept_ids))
        .order_by(Department.name)
        .all()
    )

    # Get active work types and compute status for each dept/work type
    active_work_types = get_active_work_types()
    dept_work_type_status = {}

    for dept in departments:
        for wt in active_work_types:
            portfolio = WorkPortfolio.query.filter_by(
                work_type_id=wt.id,
                event_cycle_id=event_cycle.id,
                department_id=dept.id,
                is_archived=False,
            ).first()
            if portfolio:
                status = compute_portfolio_status_summary(portfolio)
                if status:
                    dept_work_type_status[(dept.id, wt.id)] = status

    return render_page(
        "budget/division_home.html",
        event_cycle=event_cycle,
        division=division,
        div_membership=div_membership,
        departments=departments,
        active_work_types=active_work_types,
        dept_work_type_status=dept_work_type_status,
    )
