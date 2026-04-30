"""
TechOps draft edit — render the same sectioned form pre-populated with
existing values, then on POST delete-and-recreate the line rows.

Drafts have no audit/review history (lines aren't reviewed until
submission), so destructive replace-on-save is safe and avoids the
diff-and-update plumbing that would only be needed if reviewers had
already touched anything.
"""
from flask import abort, flash, redirect, render_template, request, url_for
from sqlalchemy.orm import joinedload, selectinload

from app import db
from app.models import (
    TechOpsLineDetail,
    WorkItem,
    WorkLine,
    WORK_ITEM_STATUS_DRAFT,
)
from app.routes import get_user_ctx
from .. import work_bp
from ..helpers import (
    build_work_item_perms,
    get_portfolio_context,
    require_portfolio_view,
)
from .create import _do_submit
from .form_utils import (
    ACTION_SUBMIT,
    active_service_types,
    audit_draft_edit,
    capture_form_snapshot,
    capture_state_snapshot,
    form_render_kwargs,
    parse_form,
    replace_lines,
    upsert_request_detail,
    validate,
)


def _load_draft(event: str, dept: str, public_id: str):
    """Load a TechOps draft work item with everything the edit form needs."""
    ctx = get_portfolio_context(event, dept, "techops")
    require_portfolio_view(ctx)

    work_item = (
        WorkItem.query
        .filter_by(
            public_id=public_id,
            portfolio_id=ctx.portfolio.id,
            is_archived=False,
        )
        .options(
            selectinload(WorkItem.lines)
                .joinedload(WorkLine.techops_detail)
                .joinedload(TechOpsLineDetail.service_type),
            joinedload(WorkItem.techops_detail),
        )
        .first()
    )

    if not work_item:
        abort(404, f"TechOps work item not found: {public_id}")

    if work_item.status != WORK_ITEM_STATUS_DRAFT:
        abort(409, "Only DRAFT TechOps requests can be edited.")

    perms = build_work_item_perms(work_item, ctx)
    if not perms.can_edit:
        abort(403, "You do not have permission to edit this TechOps request.")

    return work_item, ctx, perms


@work_bp.get("/<event>/<dept>/techops/item/<public_id>/edit")
def techops_request_edit(event: str, dept: str, public_id: str):
    """Render the TechOps edit form pre-populated with the draft's values."""
    work_item, ctx, perms = _load_draft(event, dept, public_id)

    # Build {service_code: [row_dict, ...]} for the form template. Single-
    # line services collect into a 1-element list; per-instance services
    # (instance_noun set) collect into one entry per existing WorkLine, in
    # line_number order, so the repeating-group section pre-fills.
    existing_lines_by_code: dict[str, list[dict]] = {}
    for line in sorted(work_item.lines, key=lambda l: l.line_number):
        d = line.techops_detail
        if not d or not d.service_type:
            continue
        st = d.service_type
        bucket = existing_lines_by_code.setdefault(st.code, [])
        if st.instance_noun:
            bucket.append({
                "location": d.location or "",
                "usage": d.usage or "",
                "config": d.config or {},
            })
        else:
            # Single-line service — keep only the first (there should be
            # at most one line per single-line service code).
            if not bucket:
                bucket.append({"description": d.description or ""})

    rd = work_item.techops_detail
    return render_template(
        "techops/work_item_form.html",
        ctx=ctx,
        perms=perms,
        work_item=work_item,
        request_detail=rd,
        existing_lines_by_code=existing_lines_by_code,
        service_types=active_service_types(),
        default_contact_name=(rd.primary_contact_name if rd else ""),
        default_contact_email=(rd.primary_contact_email if rd else ""),
    )


@work_bp.post("/<event>/<dept>/techops/item/<public_id>/edit")
def techops_request_update(event: str, dept: str, public_id: str):
    """Process the TechOps edit form (delete-and-recreate semantics)."""
    work_item, ctx, perms = _load_draft(event, dept, public_id)
    user_ctx = get_user_ctx()

    service_types = active_service_types()
    data = parse_form(request.form, service_types)

    errors = validate(data)
    if errors:
        for err in errors:
            flash(err, "error")
        return render_template(
            "techops/work_item_form.html",
            **form_render_kwargs(data, ctx, perms, service_types, work_item=work_item),
        )

    # Capture the pre-edit state from the ORM before delete-and-recreate.
    # The after-snapshot is built from the parsed form data instead of
    # re-querying work_item — replace_lines's delete-and-recreate leaves
    # work_item.lines stale in memory, so reading it back would give an
    # incorrect snapshot.
    before_snapshot = capture_state_snapshot(work_item)

    upsert_request_detail(work_item, data, user_ctx)
    replace_lines(work_item, data)

    after_snapshot = capture_form_snapshot(data)
    audit_draft_edit(work_item, before_snapshot, after_snapshot, user_ctx)

    db.session.commit()

    if data.action == ACTION_SUBMIT:
        if not _do_submit(work_item, user_ctx):
            return redirect(url_for(
                "work.techops_work_item_detail",
                event=event, dept=dept, public_id=work_item.public_id,
            ))
        flash(
            "TechOps request submitted! TechOps will reach out if any clarifications are needed.",
            "success",
        )
    else:
        flash("Draft updated.", "success")

    return redirect(url_for(
        "work.techops_work_item_detail",
        event=event, dept=dept, public_id=work_item.public_id,
    ))
