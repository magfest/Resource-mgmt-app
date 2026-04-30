"""
Shared form-handling helpers for the TechOps create + edit routes.

Both create and edit accept the same single-page sectioned form, so the
parsing, validation, and write-to-DB steps are extracted here so the two
route handlers stay thin.

Two service modes coexist on the form:
- Single-line (WIFI, OTHER): one description text per service.
- Per-instance (ETHERNET, PHONE, RADIO_CHANNEL): each instance is its own
  WorkLine with location + usage + optional per-instance config (PHONE's
  external_callable). Rendered as a repeating-group section with an
  "+ Add another <noun>" button driven by service_type.instance_noun.

The "edit" path uses delete-and-recreate semantics for line rows: drafts
have no audit history yet (lines aren't reviewed until submission), so
diffing against existing rows would add code without adding value.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Optional

from app import db
from app.models import (
    TechOpsLineDetail,
    TechOpsRequestDetail,
    TechOpsServiceType,
    WorkItemAuditEvent,
    WorkLine,
    WorkLineAuditEvent,
    AUDIT_EVENT_FIELD_CHANGE,
    AUDIT_EVENT_LINE_CREATED,
    WORK_LINE_STATUS_PENDING,
)

if TYPE_CHECKING:
    from werkzeug.datastructures import MultiDict
    from app.models import WorkItem
    from app.routes.context_types import UserContext


# Form action values controlling whether the request is saved as a draft
# or submitted for review on POST.
ACTION_SAVE_DRAFT = "save_draft"
ACTION_SUBMIT = "submit"

# Service type code reserved for the no-services-needed affirmation line
# synthesized at submit time (see synthesize_no_services_line below).
NO_SERVICES_SERVICE_CODE = "OTHER"
NO_SERVICES_SYNTHESIZED_DESCRIPTION = (
    "Department affirmed no TechOps services are needed for this event. "
    "TechOps to verify before this is finalized."
)

# Upper bound on how many per-instance rows (drops/phones/channels) the
# form parser will look for under one service. The form's "+ Add another"
# JS could let users enumerate higher, but 50 is well past any realistic
# event ask and keeps validation cheap.
MAX_INSTANCES_PER_SERVICE = 50


@dataclass
class TechOpsFormData:
    """Parsed-and-validated form data ready to be written to the DB.

    Each entry in selected_services has one of two shapes depending on
    the service type's mode:

    Single-line (instance_noun is None):
        {"service_type": st, "description": str}

    Per-instance (instance_noun is set):
        {"service_type": st, "instances": [
            {"location": str, "usage": str, "config": dict | None},
            ...
        ]}

    `instances` is the list of *non-blank* rows the user filled — fully-
    blank trailing rows from the "+ Add another" JS are stripped at parse
    time so they don't reach validation or replace_lines.
    """
    primary_contact_name: str
    primary_contact_email: str
    additional_notes: str
    no_services_needed: bool
    action: str
    selected_services: list[dict]


def active_service_types() -> list[TechOpsServiceType]:
    return (
        TechOpsServiceType.query
        .filter_by(is_active=True)
        .order_by(TechOpsServiceType.sort_order, TechOpsServiceType.id)
        .all()
    )


def _parse_instance_config(service_code: str, idx: int, form: "MultiDict") -> Optional[dict]:
    """Per-instance config (e.g. PHONE.external_callable) pulled out of the
    form into the JSON config column for one specific instance."""
    if service_code == "PHONE":
        key = f"service_{service_code}_instance_{idx}_external_callable"
        return {"external_callable": form.get(key) == "1"}
    return None


def form_render_kwargs(
    data: "TechOpsFormData",
    ctx: Any,
    perms: Any,
    service_types: list[TechOpsServiceType],
    work_item: Optional[Any] = None,
) -> dict:
    """Build template kwargs that pre-fill the form from a parsed
    TechOpsFormData. Used after a validation error so the user sees their
    submitted values rather than a wiped form.

    existing_lines_by_code is the unified shape used by both the create-
    error redraw and the edit GET: {code: list[dict]} — single-line
    services have a single-element list, per-instance services have one
    entry per non-blank instance.
    """
    existing_lines_by_code: dict[str, list[dict]] = {}
    for s in data.selected_services:
        code = s["service_type"].code
        if "instances" in s:
            existing_lines_by_code[code] = [
                {
                    "location": inst["location"],
                    "usage": inst["usage"],
                    "config": inst.get("config") or {},
                }
                for inst in s["instances"]
            ]
        else:
            existing_lines_by_code[code] = [
                {"description": s.get("description") or ""},
            ]

    rd = SimpleNamespace(
        primary_contact_name=data.primary_contact_name,
        primary_contact_email=data.primary_contact_email,
        additional_notes=data.additional_notes,
        no_services_needed=data.no_services_needed,
    )
    return dict(
        ctx=ctx,
        perms=perms,
        work_item=work_item,
        request_detail=rd,
        existing_lines_by_code=existing_lines_by_code,
        service_types=service_types,
        default_contact_name=data.primary_contact_name,
        default_contact_email=data.primary_contact_email,
    )


def _parse_per_instance_rows(
    service_code: str, form: "MultiDict",
) -> list[dict]:
    """Walk indexed form fields service_<CODE>_instance_<idx>_(location|usage)
    up to MAX_INSTANCES_PER_SERVICE. Rows where both location and usage are
    blank are dropped; partial rows survive so validate() can flag them.
    """
    rows: list[dict] = []
    for idx in range(1, MAX_INSTANCES_PER_SERVICE + 1):
        loc = (form.get(f"service_{service_code}_instance_{idx}_location") or "").strip()
        use = (form.get(f"service_{service_code}_instance_{idx}_usage") or "").strip()
        # Drop rows that look fully-blank — these come from un-removed
        # placeholder rows that the JS "+ Add another" button cloned but
        # the user didn't actually fill in.
        if not loc and not use:
            continue
        rows.append({
            "location": loc,
            "usage": use,
            "config": _parse_instance_config(service_code, idx, form),
        })
    return rows


def parse_form(form: "MultiDict", service_types: list[TechOpsServiceType]) -> TechOpsFormData:
    """Pull TechOps form fields out of a request.form-like MultiDict.

    Dispatches on service_type.instance_noun: per-instance services collect
    arrays of {location, usage, config}; single-line services collect one
    description string.
    """
    selected: list[dict] = []
    for st in service_types:
        if form.get(f"service_{st.code}_enabled") != "1":
            continue
        if st.instance_noun:
            instances = _parse_per_instance_rows(st.code, form)
            selected.append({"service_type": st, "instances": instances})
        else:
            selected.append({
                "service_type": st,
                "description": (form.get(f"service_{st.code}_description") or "").strip(),
            })
    return TechOpsFormData(
        primary_contact_name=(form.get("primary_contact_name") or "").strip(),
        primary_contact_email=(form.get("primary_contact_email") or "").strip(),
        additional_notes=(form.get("additional_notes") or "").strip(),
        no_services_needed=form.get("no_services_needed") == "1",
        action=form.get("action") or ACTION_SAVE_DRAFT,
        selected_services=selected,
    )


def validate(data: TechOpsFormData) -> list[str]:
    """Return a list of human-readable validation errors (empty == ok)."""
    errors: list[str] = []
    if not data.primary_contact_name:
        errors.append("Primary contact name is required.")
    if not data.primary_contact_email:
        errors.append("Primary contact email is required.")

    if data.no_services_needed and data.selected_services:
        errors.append(
            "You can't both check 'no services needed' and request a specific service. Uncheck one."
        )

    if (
        data.action == ACTION_SUBMIT
        and not data.no_services_needed
        and not data.selected_services
    ):
        errors.append(
            "Check at least one service, or affirm that no TechOps services are needed, before submitting."
        )

    for s in data.selected_services:
        st = s["service_type"]
        if "instances" in s:
            instances = s["instances"]
            # Service was checked but the user didn't fill any rows. If
            # they meant to skip it, they should uncheck the box.
            if not instances:
                errors.append(
                    f"{st.name}: add at least one {st.instance_noun} (location + usage), "
                    "or uncheck the service."
                )
                continue
            for i, inst in enumerate(instances, start=1):
                if not inst["location"]:
                    errors.append(
                        f"{st.name} {st.instance_noun} #{i}: location is required."
                    )
                if not inst["usage"]:
                    errors.append(
                        f"{st.name} {st.instance_noun} #{i}: usage is required."
                    )
        else:
            if not s.get("description"):
                errors.append(f"{st.name}: please describe what you need.")

    return errors


def upsert_request_detail(
    work_item: "WorkItem",
    data: TechOpsFormData,
    user_ctx: "UserContext",
) -> None:
    """Create the TechOpsRequestDetail row for a brand-new item, or update
    the existing one in place when editing a draft."""
    detail = work_item.techops_detail
    if detail is None:
        detail = TechOpsRequestDetail(
            work_item_id=work_item.id,
            primary_contact_name=data.primary_contact_name,
            primary_contact_email=data.primary_contact_email,
            additional_notes=data.additional_notes or None,
            no_services_needed=data.no_services_needed,
            created_by_user_id=user_ctx.user_id,
        )
        db.session.add(detail)
    else:
        detail.primary_contact_name = data.primary_contact_name
        detail.primary_contact_email = data.primary_contact_email
        detail.additional_notes = data.additional_notes or None
        detail.no_services_needed = data.no_services_needed
        detail.updated_by_user_id = user_ctx.user_id


def _expand_to_lines(data: TechOpsFormData) -> list[dict]:
    """Flatten selected_services into one entry per WorkLine to be created.

    Single-line services contribute one entry; per-instance services
    contribute one entry per non-blank instance. Each entry holds the
    fields the WorkLine + TechOpsLineDetail rows will be built from.
    """
    expanded: list[dict] = []
    for s in data.selected_services:
        st = s["service_type"]
        if "instances" in s:
            for inst in s["instances"]:
                expanded.append({
                    "service_type": st,
                    "description": None,
                    "location": inst["location"],
                    "usage": inst["usage"],
                    "config": inst.get("config"),
                })
        else:
            expanded.append({
                "service_type": st,
                "description": s.get("description") or "",
                "location": None,
                "usage": None,
                "config": None,
            })
    return expanded


def replace_lines(work_item: "WorkItem", data: TechOpsFormData) -> None:
    """Delete-and-recreate WorkLines for the work item from form data.

    Safe on DRAFT-status items only — no audit/review rows exist to be
    orphaned. The TechOpsLineDetail rows cascade-delete via the relationship
    backref's cascade='all, delete-orphan'.

    Lines are appended via the .lines relationship (rather than setting
    work_item_id directly) so the parent's in-memory collection stays
    consistent with the DB. Code that reads work_item.lines after this
    call needs the fresh state.

    Per-instance services produce one WorkLine per filled instance;
    single-line services produce one WorkLine with description set.
    """
    for line in list(work_item.lines):
        db.session.delete(line)
    db.session.flush()

    expanded = _expand_to_lines(data)
    for idx, entry in enumerate(expanded, start=1):
        line = WorkLine(
            line_number=idx,
            status=WORK_LINE_STATUS_PENDING,
        )
        work_item.lines.append(line)
        db.session.flush()

        db.session.add(TechOpsLineDetail(
            work_line_id=line.id,
            service_type_id=entry["service_type"].id,
            description=entry["description"],
            location=entry["location"],
            usage=entry["usage"],
            quantity=None,
            config=entry["config"],
        ))


def synthesize_no_services_line(work_item: "WorkItem", user_ctx: "UserContext") -> bool:
    """For a no_services_needed=True request being submitted, add one
    OTHER-service line so the affirmation goes through normal review.

    Emits a WorkLineAuditEvent (LINE_CREATED) attributing the synthesized
    line to the submitting user, with a note explaining it was system-
    generated. Reviewers seeing the line in the queue can trace it back.

    Returns True if a line was synthesized, False otherwise. Callers should
    only invoke this on requests that have no real lines (the form
    validation prevents the no_services_needed + services combination).
    """
    other_st = (
        TechOpsServiceType.query
        .filter_by(code=NO_SERVICES_SERVICE_CODE, is_active=True)
        .first()
    )
    if other_st is None:
        # Catalog is broken — caller should have caught this. Refuse to
        # synthesize rather than create a malformed line.
        return False

    next_num = 1 + max((l.line_number for l in work_item.lines), default=0)
    line = WorkLine(
        line_number=next_num,
        status=WORK_LINE_STATUS_PENDING,
    )
    work_item.lines.append(line)
    db.session.flush()

    db.session.add(TechOpsLineDetail(
        work_line_id=line.id,
        service_type_id=other_st.id,
        description=NO_SERVICES_SYNTHESIZED_DESCRIPTION,
        location=None,
        usage=None,
        quantity=None,
        config=None,
    ))

    db.session.add(WorkLineAuditEvent(
        work_line_id=line.id,
        event_type=AUDIT_EVENT_LINE_CREATED,
        field_name="line",
        old_value=None,
        new_value=f"Line #{next_num}: OTHER (no-services-needed affirmation)",
        note=(
            "System-synthesized at submit because the requester affirmed "
            "no TechOps services are needed for this event."
        ),
        created_by_user_id=user_ctx.user_id,
    ))
    return True


def capture_state_snapshot(work_item: "WorkItem") -> dict:
    """Serialize the current draft state into a JSON-safe dict for audit.

    Reads from the ORM — used for the before-snapshot, when work_item
    reflects the on-disk state. Don't use this for the after-snapshot
    after replace_lines(): the in-memory collection can be stale because
    delete-and-recreate doesn't always refresh the parent's .lines
    collection in time. Use capture_form_snapshot(data) instead.
    """
    rd = work_item.techops_detail
    services = []
    for line in sorted(work_item.lines, key=lambda l: l.line_number):
        d = line.techops_detail
        if d is None:
            continue
        st = d.service_type
        services.append({
            "code": st.code if st else None,
            "name": st.name if st else None,
            "description": d.description or "",
            "location": d.location or "",
            "usage": d.usage or "",
            "config": d.config or {},
        })
    return {
        "primary_contact_name": rd.primary_contact_name if rd else None,
        "primary_contact_email": rd.primary_contact_email if rd else None,
        "additional_notes": rd.additional_notes if rd else None,
        "no_services_needed": rd.no_services_needed if rd else False,
        "services": services,
    }


def capture_form_snapshot(data: "TechOpsFormData") -> dict:
    """Serialize parsed form data into the same shape as
    capture_state_snapshot, for use as the after-snapshot in audit_draft_edit.

    Reading from the parsed form rather than re-querying the ORM after
    a write avoids the stale-collection trap (see capture_state_snapshot
    docstring). Each per-instance row contributes one services entry,
    matching the WorkLines that replace_lines will create.
    """
    services = []
    for entry in _expand_to_lines(data):
        st = entry["service_type"]
        services.append({
            "code": st.code,
            "name": st.name,
            "description": entry["description"] or "",
            "location": entry["location"] or "",
            "usage": entry["usage"] or "",
            "config": entry["config"] or {},
        })
    return {
        "primary_contact_name": data.primary_contact_name,
        "primary_contact_email": data.primary_contact_email,
        "additional_notes": data.additional_notes or None,
        "no_services_needed": data.no_services_needed,
        "services": services,
    }


def _summarize_state(snapshot: dict) -> str:
    """Render a one-line human summary of a state snapshot for audit
    old_value / new_value display. Full structured detail lives in the
    audit event's snapshot column for anyone who wants to drill in."""
    services = snapshot.get("services") or []
    if snapshot.get("no_services_needed"):
        services_part = "no services (affirmed)"
    elif not services:
        services_part = "0 lines"
    else:
        codes = ", ".join(s.get("code") or "?" for s in services)
        services_part = f"{len(services)} line(s): {codes}"

    contact = snapshot.get("primary_contact_name") or "(no contact)"
    return f"{services_part}; contact: {contact}"


def audit_draft_edit(
    work_item: "WorkItem",
    before: dict,
    after: dict,
    user_ctx: "UserContext",
) -> bool:
    """Emit one WorkItemAuditEvent capturing a draft edit, if state actually
    changed. Returns True if an event was emitted.

    Lives at the item level (not line level) so it survives the cascade
    delete done by replace_lines() — line-level audit rows would be wiped
    along with the lines they reference.
    """
    if before == after:
        return False

    db.session.add(WorkItemAuditEvent(
        work_item_id=work_item.id,
        event_type=AUDIT_EVENT_FIELD_CHANGE,
        old_value=_summarize_state(before),
        new_value=_summarize_state(after),
        # Use 'kind' rather than 'field' so we don't collide with the
        # audit_log macro's BUDGET-per-field rendering branch (which
        # expects snapshot.description + snapshot.field). The generic
        # else-branch ('old → new') is what we want.
        snapshot={
            "kind": "techops_draft_edit",
            "before": before,
            "after": after,
        },
        created_by_user_id=user_ctx.user_id,
    ))
    return True
