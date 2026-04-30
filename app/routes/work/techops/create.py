"""
TechOps request creation — the "New Request" sectioned form.

GET renders the empty (or default-populated) form. POST validates and
creates the WorkItem + TechOpsRequestDetail + per-service WorkLines.
Save Draft leaves the request in DRAFT; Submit calls the engine
submit_work_item helper to transition to SUBMITTED (or, when the
no_services_needed affirmation is set, lets T4e's submit branch
synthesize the OTHER affirmation line).
"""
from flask import abort, flash, redirect, render_template, request, url_for

from app import db
from app.models import (
    TechOpsLineDetail,
    TechOpsRequestDetail,
    TechOpsServiceType,
    WorkItem,
    WorkLine,
    REQUEST_KIND_PRIMARY,
    WORK_ITEM_STATUS_DRAFT,
    WORK_LINE_STATUS_PENDING,
)
from app.routes import get_user_ctx
from .. import work_bp
from ..helpers import (
    generate_public_id_for_portfolio,
    get_portfolio_context,
    require_portfolio_edit,
    require_portfolio_view,
)


# Form action values controlling whether the request is saved as a draft
# or submitted for review on POST.
_ACTION_SAVE_DRAFT = "save_draft"
_ACTION_SUBMIT = "submit"


def _active_service_types() -> list[TechOpsServiceType]:
    return (
        TechOpsServiceType.query
        .filter_by(is_active=True)
        .order_by(TechOpsServiceType.sort_order, TechOpsServiceType.id)
        .all()
    )


def _build_line_config(service_code: str, form) -> dict | None:
    """Per-service-type extras pulled out of form data into the JSON config
    column. Returns None when the service type has no extras."""
    if service_code == "PHONE":
        return {
            "external_callable": form.get("service_PHONE_external_callable") == "1",
        }
    return None


def _parse_quantity(raw: str) -> int | None:
    """Parse the optional quantity input; non-integer or empty → None."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


@work_bp.get("/<event>/<dept>/techops/new")
def techops_request_new(event: str, dept: str):
    """Render the New TechOps Request form."""
    ctx = get_portfolio_context(event, dept, "techops")
    perms = require_portfolio_view(ctx)

    if not perms.can_create_primary:
        abort(403, "You do not have permission to create a TechOps request for this department.")

    user_ctx = get_user_ctx()
    user = user_ctx.user

    return render_template(
        "techops/work_item_form.html",
        ctx=ctx,
        perms=perms,
        work_item=None,
        service_types=_active_service_types(),
        # Defaults: account display name + email. Help text in the template
        # explains why someone might change these for a specific request.
        default_contact_name=user.display_name if user else "",
        default_contact_email=user.email if user else "",
    )


@work_bp.post("/<event>/<dept>/techops/new")
def techops_request_create(event: str, dept: str):
    """Process the New TechOps Request form."""
    ctx = get_portfolio_context(event, dept, "techops")
    perms = require_portfolio_edit(ctx)

    if not perms.can_create_primary:
        abort(403, "You do not have permission to create a TechOps request for this department.")

    user_ctx = get_user_ctx()

    # Collect submitted fields
    primary_contact_name = (request.form.get("primary_contact_name") or "").strip()
    primary_contact_email = (request.form.get("primary_contact_email") or "").strip()
    additional_notes = (request.form.get("additional_notes") or "").strip()
    no_services_needed = request.form.get("no_services_needed") == "1"
    action = request.form.get("action") or _ACTION_SAVE_DRAFT

    # Discover which service-type sections the requester filled in
    service_types = _active_service_types()
    selected = []
    for st in service_types:
        if request.form.get(f"service_{st.code}_enabled") == "1":
            selected.append({
                "service_type": st,
                "description": (request.form.get(f"service_{st.code}_description") or "").strip(),
                "quantity": _parse_quantity(request.form.get(f"service_{st.code}_quantity")),
                "config": _build_line_config(st.code, request.form),
            })

    # Validation
    errors: list[str] = []
    if not primary_contact_name:
        errors.append("Primary contact name is required.")
    if not primary_contact_email:
        errors.append("Primary contact email is required.")

    if no_services_needed and selected:
        errors.append(
            "You can't both check 'no services needed' and request a specific service. Uncheck one."
        )

    if action == _ACTION_SUBMIT and not no_services_needed and not selected:
        errors.append(
            "Check at least one service, or affirm that no TechOps services are needed, before submitting."
        )

    for s in selected:
        if not s["description"]:
            errors.append(f"{s['service_type'].name}: please describe what you need.")

    if errors:
        for err in errors:
            flash(err, "error")
        # Redirect back to the empty form. Field preservation across error
        # redirects can come later; for first cut the validation failures
        # are infrequent enough not to justify the extra plumbing.
        return redirect(url_for("work.techops_request_new", event=event, dept=dept))

    # Build the work item and its detail rows in one transaction
    work_item = WorkItem(
        portfolio_id=ctx.portfolio.id,
        request_kind=REQUEST_KIND_PRIMARY,
        status=WORK_ITEM_STATUS_DRAFT,
        public_id=generate_public_id_for_portfolio(ctx.portfolio),
        created_by_user_id=user_ctx.user_id,
    )
    db.session.add(work_item)
    db.session.flush()

    db.session.add(TechOpsRequestDetail(
        work_item_id=work_item.id,
        primary_contact_name=primary_contact_name,
        primary_contact_email=primary_contact_email,
        additional_notes=additional_notes or None,
        no_services_needed=no_services_needed,
        created_by_user_id=user_ctx.user_id,
    ))

    for idx, s in enumerate(selected, start=1):
        line = WorkLine(
            work_item_id=work_item.id,
            line_number=idx,
            status=WORK_LINE_STATUS_PENDING,
        )
        db.session.add(line)
        db.session.flush()

        db.session.add(TechOpsLineDetail(
            work_line_id=line.id,
            service_type_id=s["service_type"].id,
            description=s["description"],
            quantity=s["quantity"],
            config=s["config"],
        ))

    db.session.commit()

    if action == _ACTION_SUBMIT:
        # T3 lifecycle: branches on uses_dispatch=False to route + create
        # reviews inline. Wired to send the submit notification afterward.
        from app.routes.work.helpers.lifecycle import submit_work_item
        submit_work_item(work_item, user_ctx)
        db.session.commit()

        try:
            from app.services.notifications import notify_work_item_submitted
            notify_work_item_submitted(work_item)
            db.session.commit()
        except Exception:
            db.session.rollback()
            import logging
            logging.getLogger(__name__).exception(
                "Failed to send submission notification for %s", work_item.public_id
            )

        flash(
            "TechOps request submitted! TechOps will reach out if any clarifications are needed.",
            "success",
        )
    else:
        flash("Draft saved.", "success")

    # T4d will add a work_item_detail page; for now the portfolio landing
    # surfaces the new draft/submitted item.
    return redirect(url_for(
        "work.techops_portfolio_landing",
        event=event, dept=dept,
    ))
