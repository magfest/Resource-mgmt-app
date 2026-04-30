"""
TechOps portfolio landing — list of a department's TechOps service requests
for an event.
"""
from flask import render_template
from sqlalchemy.orm import selectinload, joinedload

from app.models import (
    WorkItem,
    WorkLine,
    TechOpsLineDetail,
    TechOpsServiceType,
)
from .. import work_bp
from ..helpers import (
    get_portfolio_context,
    require_portfolio_view,
    compute_work_item_totals,
    compute_line_status_summary,
    format_currency,
    friendly_status,
)


@work_bp.get("/<event>/<dept>/techops")
def techops_portfolio_landing(event: str, dept: str):
    """
    Landing page for a department's TechOps requests.

    Lists all non-archived TechOps work items, newest first. Departments
    can submit multiple TechOps requests over time (no PRIMARY/SUPPLEMENTARY
    distinction — each request is self-contained), so the page presents
    a flat list with a "New Request" call to action.
    """
    ctx = get_portfolio_context(event, dept, "techops")
    perms = require_portfolio_view(ctx)

    # All work items in this portfolio. Eager load lines + their TechOps
    # detail (and the service type) so the cards can show what was requested
    # without N+1 queries.
    work_items = WorkItem.query.filter_by(
        portfolio_id=ctx.portfolio.id,
        is_archived=False,
    ).options(
        selectinload(WorkItem.lines)
            .joinedload(WorkLine.techops_detail)
            .joinedload(TechOpsLineDetail.service_type),
    ).order_by(WorkItem.created_at.desc()).all()

    item_totals = {
        item.id: compute_work_item_totals(item) for item in work_items
    }
    item_line_summaries = {
        item.id: compute_line_status_summary(item) for item in work_items
    }

    return render_template(
        "techops/portfolio_landing.html",
        ctx=ctx,
        perms=perms,
        work_items=work_items,
        item_totals=item_totals,
        item_line_summaries=item_line_summaries,
        format_currency=format_currency,
        friendly_status=friendly_status,
    )
