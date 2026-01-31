from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Any
from dataclasses import dataclass
from typing import Optional, Set


from flask import Flask, session, render_template, abort, request, redirect, url_for
from . import db


@dataclass
class RouteHelpers:
    ensure_demo_users: Callable[[], None]
    ensure_demo_budget_data: Callable[[], None]
    ensure_demo_org_data: Callable[[], None]
    get_active_user_id: Callable[[], str]
    get_active_user: Callable[[], Any]
    active_user_roles: Callable[[], list[str]]
    is_admin: Callable[[], bool]
    is_finance: Callable[[], bool]
    active_user_approval_group_ids: Callable[[], set[int]]
    can_review_group: Callable[[int], bool]
    recalc_request_status_from_lines: Callable[[Any], None]


h: RouteHelpers | None = None

@dataclass(frozen=True)
class UserContext:
    user_id: str
    user: object | None
    roles: tuple[str, ...]
    is_admin: bool
    is_finance: bool
    approval_group_ids: Set[int]

@dataclass(frozen=True)
class RequestPerms:
    can_view: bool
    can_edit: bool
    can_submit: bool
    can_finalize: bool

    # convenience flags
    is_owner: bool
    is_admin: bool
    is_finance: bool
    is_finalized: bool

def get_user_ctx() -> UserContext:
    _require_helpers()
    uid = h.get_active_user_id()
    u = h.get_active_user()
    roles = tuple(h.active_user_roles() or [])
    return UserContext(
        user_id=uid,
        user=u,
        roles=roles,
        is_admin=h.is_admin(),
        is_finance=h.is_finance(),
        approval_group_ids=set(h.active_user_approval_group_ids() or []),
    )

def build_request_perms(req, *, user_ctx: UserContext, review_summary: dict | None = None) -> RequestPerms:
    status = (req.current_status or "").upper()
    is_finalized = (status == "APPROVED")  # your current “finalized” meaning

    is_owner = (user_ctx.user_id == req.created_by_user_id)

    # view rules (tighten later if needed)
    can_view = user_ctx.is_admin or user_ctx.is_finance or is_owner

    # edit rules must match enforced route rules (owner draft/revision, admin until finalized)
    can_edit = (not is_finalized) and (
        user_ctx.is_admin or (is_owner and status in ("DRAFT", "NEEDS_REVISION"))
    )

    # submit rules should mirror your submit route rules
    can_submit = (not is_finalized) and (
        (user_ctx.is_admin and status in ("DRAFT", "NEEDS_REVISION", "SUBMITTED")) or
        (is_owner and status in ("DRAFT", "NEEDS_REVISION"))
    )

    ready = bool(review_summary and review_summary.get("ready_to_finalize"))
    can_finalize = (not is_finalized) and (status == "SUBMITTED") and ready and (user_ctx.is_admin or user_ctx.is_finance)

    return RequestPerms(
        can_view=can_view,
        can_edit=can_edit,
        can_submit=can_submit,
        can_finalize=can_finalize,
        is_owner=is_owner,
        is_admin=user_ctx.is_admin,
        is_finance=user_ctx.is_finance,
        is_finalized=is_finalized,
    )


"""
Non Specific Helpers, that can be used by all routes
Specific helpers should be placed above the route
"""
LINE_TERMINAL_STATUSES = {"APPROVED", "REJECTED"}
LINE_ACTIVE_STATUSES = {"PENDING", "NEEDS_INFO"} | LINE_TERMINAL_STATUSES
PRIORITY_OPTIONS = [
    ("CRITICAL", "Critical"),
    ("HIGH", "High"),
    ("MEDIUM", "Medium"),
    ("LOW", "Low"),
]


def _require_helpers():
    if h is None:
        raise RuntimeError("Route helpers not initialized. Did you call register_routes()?")


def _user_can_edit_line_review(lr) -> bool:
    # Admin always can
    if h.is_admin():
        return True
    # Must be in the owning approval group
    my_group_ids = set(h.active_user_approval_group_ids() or [])
    return (lr.approval_group_id is not None) and (lr.approval_group_id in my_group_ids)


def _validate_line_transition(current_status: str, action: str, note: str | None):
    """
    Returns (new_status, note_required_bool, clears_final_note_bool)
    Raises ValueError with a user-friendly message for invalid transitions.
    """
    s = (current_status or "PENDING").upper()
    a = (action or "").upper()
    note = (note or "").strip()

    if s not in LINE_ACTIVE_STATUSES:
        raise ValueError(f"Unknown line status: {s}")

    # Terminal states: only allow MARK_PENDING
    if s in LINE_TERMINAL_STATUSES:
        if a != "MARK_PENDING":
            raise ValueError(f"Invalid transition: {s} -> {a}")
        return ("PENDING", False, True)  # clear final decision note

    # Non-terminal
    if a == "APPROVE":
        if not note:
            raise ValueError("Approval note is required.")
        return ("APPROVED", True, False)

    if a == "REJECT":
        if not note:
            raise ValueError("Rejection note is required.")
        return ("REJECTED", True, False)

    if a == "REQUEST_INFO":
        if not note:
            raise ValueError("A message is required when requesting info.")
        return ("NEEDS_INFO", True, False)

    if a == "MARK_PENDING":
        # allow from PENDING/NEEDS_INFO back to PENDING, no note required
        return ("PENDING", False, False)

    if a == "UPDATE_DECISION_NOTE":
        # only meaningful for terminal states (you already gate this in template)
        raise ValueError("Invalid action in this state.")

    raise ValueError("Invalid action.")


def _apply_line_review_transition(*, lr, action: str, note: str | None, internal_note: str | None = None):
    """
    Canonical line review transition implementation.

    Enforces:
      - unified statuses: PENDING/NEEDS_INFO/APPROVED/REJECTED
      - note requirements via _validate_line_transition
      - audit logging
      - public comment when requesting info
      - final_decision_note storage for terminal statuses
    """
    from datetime import datetime
    from .models import LineAuditEvent, LineComment

    uid = h.get_active_user_id()

    old_status = (lr.status or "PENDING").upper()
    action_u = (action or "").upper()
    note_clean = (note or "").strip()

    new_status, _note_required, clear_final_note = _validate_line_transition(old_status, action_u, note_clean)

    # Apply status
    lr.status = new_status
    lr.updated_by_user_id = uid

    # Clear terminal decision note if reopening from terminal
    if clear_final_note and hasattr(lr, "final_decision_note"):
        lr.final_decision_note = None
        lr.final_decision_at = None
        lr.final_decision_by_user_id = None

    # If reviewer marks pending (re-open / return to queue), clear stale "needs info" notes.
    # This prevents old REQUEST_INFO prompts from lingering after the requester responds.
    if action_u == "MARK_PENDING":
        # only clear external ask if we are coming from NEEDS_INFO or terminal reopen
        if old_status in ("NEEDS_INFO", "APPROVED", "REJECTED"):
            lr.external_admin_note = None
            lr.internal_admin_note = None

    # REQUEST_INFO -> store requester-visible ask + add a public comment
    if action_u == "REQUEST_INFO":
        lr.external_admin_note = note_clean
        lr.internal_admin_note = (internal_note or "").strip() or None

        db.session.add(LineComment(
            request_line_id=lr.request_line_id,
            visibility="PUBLIC",
            body=f"[Needs info] {note_clean}",
            created_by_user_id=uid,
        ))

    # Terminal decision note storage (prefer final_decision_* fields when present)
    if new_status in ("APPROVED", "REJECTED"):
        if hasattr(lr, "final_decision_note"):
            lr.final_decision_note = note_clean
            lr.final_decision_at = datetime.utcnow()
            lr.final_decision_by_user_id = uid
            # IMPORTANT: do not overwrite external_admin_note (it may contain prior REQUEST_INFO ask)
        else:
            # Legacy fallback: if no final_decision_note fields exist, store decision note somewhere visible.
            # Do not overwrite an existing REQUEST_INFO ask unless it's empty.
            if not (lr.external_admin_note or "").strip():
                lr.external_admin_note = note_clean

    # Audit: status change always
    db.session.add(LineAuditEvent(
        request_line_id=lr.request_line_id,
        event_type="STATUS_CHANGE",
        old_value=old_status,
        new_value=f"{new_status} :: {note_clean}" if note_clean else new_status,
        created_by_user_id=uid,
    ))


def register_routes(app: Flask, helpers: RouteHelpers) -> None:
    global h
    h = helpers

    # ---Routes

    @app.get("/")
    def home():
        from .models import Request

        uid = h.get_active_user_id()
        if not uid:
            return redirect(url_for("dev_login"))

        q = db.session.query(Request)

        # Admin/finance see all requests; everyone else sees only their own
        if not (h.is_admin() or h.is_finance()):
            q = q.filter(Request.created_by_user_id == uid)

        requests = (
            q.order_by(Request.id.desc())
            .limit(200)  # bump for demo; adjust as needed
            .all()
        )

        is_admin = h.is_admin() or h.is_finance()

        return render_template("home.html",
                               my_requests=requests,
                               is_admin=is_admin
                               )


    @app.get("/dev/login")
    def dev_login():
        from .models import User

        h.ensure_demo_users()

        users = (
            db.session.query(User)
            .filter(User.is_active == True)  # noqa: E712
            .order_by(User.display_name.asc())
            .all()
        )

        return render_template(
            "dev_login.html",
            users=users,
            current_user_id=h.get_active_user_id(),
        )

    @app.post("/dev/login")
    def dev_login_post():
        from .models import User

        h.ensure_demo_users()

        chosen = (request.form.get("user_id") or "").strip()
        if not chosen:
            return redirect(url_for("dev_login"))

        u = db.session.get(User, chosen)
        if not u or not u.is_active:
            return "Unknown or inactive user", 400

        session["active_user_id"] = u.id
        return redirect(url_for("dev_login"))

    def _get_or_create_line_review_for_line(line):
        """
        Returns (LineReview, created_bool).
        Ensures there is a LineReview row for this line for the owning approval group.
        """
        from .models import LineReview, BudgetItemType, ApprovalGroup

        if not getattr(line, "id", None):
            raise RuntimeError("RequestLine must be flushed before creating LineReview.")

        group_id = None
        if line.budget_item_type_id:
            bit = db.session.get(BudgetItemType, line.budget_item_type_id)
            if bit and bit.approval_group_id:
                group_id = bit.approval_group_id

        if group_id is None:
            other = (
                db.session.query(ApprovalGroup)
                .filter(ApprovalGroup.code == "OTHER")
                .one_or_none()
            )
            if not other:
                raise RuntimeError("Missing ApprovalGroup code=OTHER. Seed demo data.")
            group_id = other.id

        lr = (
            db.session.query(LineReview)
            .filter(LineReview.request_line_id == line.id)
            .filter(LineReview.approval_group_id == group_id)
            .one_or_none()
        )
        if lr:
            return lr, False

        lr = LineReview(
            request_line_id=line.id,
            approval_group_id=group_id,
            status="PENDING",
            updated_by_user_id=h.get_active_user_id(),
        )
        db.session.add(lr)
        return lr, True

    def _ensure_line_reviews_for_revision(revision_id: int) -> int:
        """
        Ensures each RequestLine in the revision has the required LineReview row.
        Returns number of newly created LineReview rows.
        """
        from .models import RequestLine

        lines = (
            db.session.query(RequestLine)
            .filter(RequestLine.revision_id == revision_id)
            .order_by(RequestLine.id.asc())
            .all()
        )

        created = 0
        for line in lines:
            _lr, was_created = _get_or_create_line_review_for_line(line)
            if was_created:
                created += 1

        return created

    @app.get("/requests/<int:request_id>/lines/<int:line_id>")
    def line_detail(request_id: int, line_id: int):
        from .models import (
            Request,
            RequestLine,
            LineReview,
            LineComment,
            LineAuditEvent,
            User,
            BudgetItemType,
        )

        req = db.session.get(Request, request_id)
        if not req:
            abort(404)

        line = db.session.get(RequestLine, line_id)
        if not line or line.revision.request_id != req.id:
            abort(404)

        # Find the workflow record for this line (should be exactly one per group)
        # For now we pick the first (you can tighten later).
        line_review = (
            db.session.query(LineReview)
            .filter(LineReview.request_line_id == line.id)
            .order_by(LineReview.id.asc())
            .first()
        )

        owning_group_code = None
        can_review_this_line = False
        if line_review:
            try:
                owning_group_code = line_review.approval_group.code
            except Exception:
                owning_group_code = str(line_review.approval_group_id)
            can_review_this_line = (h.is_admin() or h.is_finance() or h.can_review_group(line_review.approval_group_id))

        # Identify which group owns this line (via item type)
        approval_group_id = None
        if line.budget_item_type_id:
            bit = db.session.get(BudgetItemType, line.budget_item_type_id)
            approval_group_id = bit.approval_group_id if bit else None
        elif line_review:
            approval_group_id = line_review.approval_group_id

        # Permissions
        uid = h.get_active_user_id()
        roles = set(h.active_user_roles())
        is_requester = "REQUESTER" in roles
        is_reviewer = h.is_admin() or h.is_finance() or (approval_group_id and h.can_review_group(approval_group_id))

        # Comments
        public_comments = (
            db.session.query(LineComment)
            .filter(LineComment.request_line_id == line.id)
            .filter(LineComment.visibility == "PUBLIC")
            .order_by(LineComment.created_at.asc())
            .all()
        )

        admin_comments = []
        audit_events = []
        if not is_requester:  # requester cannot see admin-only info
            admin_comments = (
                db.session.query(LineComment)
                .filter(LineComment.request_line_id == line.id)
                .filter(LineComment.visibility == "ADMIN")
                .order_by(LineComment.created_at.asc())
                .all()
            )

            audit_events = (
                db.session.query(LineAuditEvent)
                .filter(LineAuditEvent.request_line_id == line.id)
                .order_by(LineAuditEvent.created_at.desc())
                .all()
            )

        # Resolve user display names in-template (simple map)
        user_ids = {c.created_by_user_id for c in public_comments} | {c.created_by_user_id for c in admin_comments}
        user_ids |= {e.created_by_user_id for e in audit_events}
        users = (
            db.session.query(User)
            .filter(User.id.in_(list(user_ids)) if user_ids else False)
            .all()
        )
        user_by_id = {u.id: u for u in users}

        is_finalized = (req.current_status or "").upper() == "APPROVED"

        return render_template(
            "line_detail.html",
            req=req,
            line=line,
            line_review=line_review,
            approval_group_id=approval_group_id,
            is_requester=is_requester,
            is_reviewer=is_reviewer,
            public_comments=public_comments,
            admin_comments=admin_comments,
            audit_events=audit_events,
            user_by_id=user_by_id,
            owning_group_code=owning_group_code,
            can_review_this_line=can_review_this_line,
            is_finalized=is_finalized,
        )

    @app.post("/requests/<int:request_id>/lines/<int:line_id>/comment")
    def add_line_comment(request_id: int, line_id: int):
        from .models import Request, RequestLine, LineComment, LineAuditEvent

        req = db.session.get(Request, request_id)
        if not req:
            abort(404)

        line = db.session.get(RequestLine, line_id)
        if not line or line.revision.request_id != req.id:
            abort(404)

        body = (request.form.get("body") or "").strip()
        visibility = (request.form.get("visibility") or "PUBLIC").strip().upper()

        if not body:
            return redirect(url_for("line_detail", request_id=req.id, line_id=line.id))

        roles = set(h.active_user_roles())
        is_requester = "REQUESTER" in roles

        # Enforce visibility
        if is_requester:
            visibility = "PUBLIC"
        elif visibility not in ("PUBLIC", "ADMIN"):
            visibility = "PUBLIC"

        uid = h.get_active_user_id()

        c = LineComment(
            request_line_id=line.id,
            visibility=visibility,
            body=body,
            created_by_user_id=uid,
        )
        db.session.add(c)

        # Audit (optional but strongly recommended)
        db.session.add(LineAuditEvent(
            request_line_id=line.id,
            event_type="COMMENT_ADDED",
            old_value=None,
            new_value=f"{visibility} comment added",
            created_by_user_id=uid,
        ))

        db.session.commit()
        return redirect(url_for("line_detail", request_id=req.id, line_id=line.id))

    @app.post("/requests/<int:request_id>/lines/<int:line_id>/request-info")
    def request_line_info(request_id: int, line_id: int):
        from .models import Request, RequestLine, LineReview, LineAuditEvent, BudgetItemType

        req = db.session.get(Request, request_id)
        if not req:
            abort(404)

        line = db.session.get(RequestLine, line_id)
        if not line or line.revision.request_id != req.id:
            abort(404)

        lr = (
            db.session.query(LineReview)
            .filter(LineReview.request_line_id == line.id)
            .order_by(LineReview.id.asc())
            .first()
        )
        if not lr:
            return "Missing LineReview for this line", 400

        # Determine approval group ownership
        approval_group_id = lr.approval_group_id
        if line.budget_item_type_id:
            bit = db.session.get(BudgetItemType, line.budget_item_type_id)
            if bit:
                approval_group_id = bit.approval_group_id

        # Permission: admin/finance OR approver for that group
        if not (h.is_admin() or h.is_finance() or h.can_review_group(approval_group_id)):
            abort(403)

        uid = h.get_active_user_id()

        old_status = lr.status
        lr.status = "NEEDS_INFO"
        lr.updated_by_user_id = uid

        note = (request.form.get("note") or "").strip()

        db.session.add(LineAuditEvent(
            request_line_id=line.id,
            event_type="REQUEST_INFO",
            old_value=old_status,
            new_value=note or "Requested additional information.",
            created_by_user_id=uid,
        ))

        db.session.commit()
        return redirect(url_for("line_detail", request_id=req.id, line_id=line.id))

    @app.post("/requests/<int:request_id>/lines/<int:line_id>/transition")
    def transition_line_review(request_id: int, line_id: int):
        """
        Canonical line-review transition endpoint.

        Unified line statuses:
          PENDING / NEEDS_INFO / APPROVED / REJECTED

        Expected form fields:
          action: APPROVE | REJECT | REQUEST_INFO | MARK_PENDING
          note:   free text (required for REQUEST_INFO and for APPROVE/REJECT, per rules)
        """
        from flask import request, redirect, url_for, abort
        from .models import Request, RequestLine, LineReview

        req = db.session.get(Request, request_id)
        if not req:
            abort(404)

        line = db.session.get(RequestLine, line_id)
        if not line:
            abort(404)

        # Correct ownership check: RequestLine is tied to a Revision, not directly to Request
        if not line.revision or line.revision.request_id != req.id:
            abort(404)

        lr = (
            db.session.query(LineReview)
            .filter(LineReview.request_line_id == line.id)
            .one_or_none()
        )
        if not lr:
            abort(404)

        # Authorization:
        # - Admin can transition anything
        # - Group reviewer can transition only their own group
        if not (h.is_admin() or h.can_review_group(lr.approval_group_id)):
            abort(403)

        action = (request.form.get("action") or "").strip().upper()
        note = (request.form.get("note") or "").strip()

        # IMPORTANT: use MARK_PENDING (matches _validate_line_transition)
        allowed_actions = {"APPROVE", "REJECT", "REQUEST_INFO", "MARK_PENDING"}
        if action not in allowed_actions:
            abort(400)

        _apply_line_review_transition(lr=lr, action=action, note=note)

        # Recalc request status using the revision relationship
        if line.revision_id:
            h.recalc_request_status_from_lines(line.revision)

        db.session.commit()

        return redirect(request.referrer or url_for("line_detail", request_id=req.id, line_id=line.id))

    @app.post("/dev/create-sample-request")
    def dev_create_sample_request():
        from .models import Request

        r = Request(
            event_cycle="Super MAGFest 2026",
            requesting_department="TechOps",
            created_by_user_id=h.get_active_user_id(),
        )
        db.session.add(r)
        db.session.commit()
        return {"ok": True, "id": r.id}

    @app.post("/dev/create-sample-request-with-revision")
    def dev_create_sample_request_with_revision():
        from .models import Request, RequestRevision

        r = Request(
            event_cycle="Super MAGFest 2026",
            requesting_department="TechOps",
            created_by_user_id=h.get_active_user_id(),
            current_status="SUBMITTED",
        )
        db.session.add(r)
        db.session.flush()  # gets r.id without committing

        rev = RequestRevision(
            request_id=r.id,
            revision_number=1,
            submitted_by_user_id=h.get_active_user_id(),
            revision_note="Initial submission",
            status_at_submission="SUBMITTED",
        )
        db.session.add(rev)
        db.session.flush()

        r.current_revision_id = rev.id
        db.session.commit()

        return {
            "ok": True,
            "request_id": r.id,
            "revision_id": rev.id,
            "current_revision_id": r.current_revision_id,
        }

    @app.post("/dev/create-techops-sample-v1")
    def dev_create_techops_sample_v1():
        from .models import Request, RequestRevision, RequestLine

        r = Request(
            event_cycle="Super MAGFest 2026",
            requesting_department="TechOps",
            created_by_user_id=h.get_active_user_id(),
            current_status="SUBMITTED",
        )
        db.session.add(r)
        db.session.flush()

        rev = RequestRevision(
            request_id=r.id,
            revision_number=1,
            submitted_by_user_id=h.get_active_user_id(),
            revision_note="TechOps sample based on FY25 lines",
            status_at_submission="SUBMITTED",
        )
        db.session.add(rev)
        db.session.flush()

        lines = [
            ("Tech Equipment", 38000, "Critical (we cannot operate without this)",
             "We are requesting apx 30% increase over last year's budgeted amount to account for the current economic conditions and other uncertainty related to supply chain changes."),
            ("Equipment Rental", 8000, "Critical (we cannot operate without this)", "Radios"),
            ("Equipment Rental", 15000, "Critical (we cannot operate without this)",
             "iPads, Laptops, and other Hartford equipment"),
            ("Supplies", 5000, "Critical (we cannot operate without this)",
             "Office Supplies (assuming this comes under FestOps now?)"),
            ("Food Stuffs", 4000, "Critical (we cannot operate without this)",
             "Water/Gatorade (assuming this comes under FestOps now?)"),
            ("Printing & Copying", 2500, "Critical (we cannot operate without this)",
             "Bulk Printing (assuming this comes under FestOps now?)"),
            ("Truck Rental", 1000, "Medium",
             "Week long panel van rental for twice daily supply runs (assuming this comes under FestOps now?)"),
            ("Venue Rental Fees/Tips", 35000, "Critical (we cannot operate without this)",
             "Misc. Hotel Costs (Ethernet Drops, Power costs, etc.) - NOTE: BOPS now should have a line for all digital signage, thus not included here"),
        ]

        for category, amount, priority_text, details in lines:
            db.session.add(RequestLine(
                revision_id=rev.id,
                category=category,
                description=details,
                requested_amount=amount,
                justification=priority_text,
            ))

        # No buckets in this sample yet; we’ll add one in Step 7 if you want.

        r.current_revision_id = rev.id
        db.session.commit()

        return {
            "ok": True,
            "request_id": r.id,
            "revision_id": rev.id,
            "lines_created": len(lines),
        }

    def _norm(s: str) -> str:
        return " ".join((s or "").strip().lower().split())

    def _line_match_key(line) -> str:
        """
        Best-effort stable-ish key between revisions.
        For MVP/demo this is fine. Later: add a real stable key (e.g. source_draft_line_id).
        """
        return "|".join([
            str(line.budget_item_type_id or ""),
            _norm(line.item_name or ""),
            _norm(line.description or ""),
        ])

    @app.get("/revisions/<int:revision_id>")
    def revision_snapshot(revision_id: int):
        from .models import RequestRevision, Request, RequestLine, LineReview, ApprovalGroup

        revision = db.session.get(RequestRevision, revision_id)
        if not revision:
            abort(404)

        request = db.session.get(Request, revision.request_id)
        if not request:
            abort(404)

        lines = (
            db.session.query(RequestLine)
            .filter(RequestLine.revision_id == revision.id)
            .order_by(RequestLine.id.asc())
            .all()
        )

        requested_total = sum(l.requested_amount for l in lines)

        line_ids = [l.id for l in lines]
        reviews = []
        if line_ids:
            reviews = (
                db.session.query(LineReview)
                .filter(LineReview.request_line_id.in_(line_ids))
                .all()
            )

        reviews_by_line_id = {}
        for r in reviews:
            reviews_by_line_id.setdefault(r.request_line_id, []).append(r)

        groups_by_id = {g.id: g for g in db.session.query(ApprovalGroup).all()}

        # --- Diff against previous revision (Rev N-1) ---
        prev_revision = None
        prev_lines = []

        if revision.revision_number and revision.revision_number > 1:
            prev_revision = (
                db.session.query(RequestRevision)
                .filter(RequestRevision.request_id == request.id)
                .filter(RequestRevision.revision_number == (revision.revision_number - 1))
                .one_or_none()
            )

        if prev_revision:
            prev_lines = (
                db.session.query(RequestLine)
                .filter(RequestLine.revision_id == prev_revision.id)
                .order_by(RequestLine.id.asc())
                .all()
            )

        # Build maps by match key
        curr_by_key = {}
        for l in lines:
            curr_by_key[_line_match_key(l)] = l

        prev_by_key = {}
        for l in prev_lines:
            prev_by_key[_line_match_key(l)] = l

        added_keys = [k for k in curr_by_key.keys() if k not in prev_by_key]
        removed_keys = [k for k in prev_by_key.keys() if k not in curr_by_key]
        common_keys = [k for k in curr_by_key.keys() if k in prev_by_key]

        added_lines = [curr_by_key[k] for k in added_keys]
        removed_lines = [prev_by_key[k] for k in removed_keys]

        changed_lines = []
        for k in common_keys:
            a = prev_by_key[k]
            b = curr_by_key[k]

            diffs = []

            if (a.requested_amount or 0) != (b.requested_amount or 0):
                diffs.append({
                    "field": "Amount",
                    "before": a.requested_amount or 0,
                    "after": b.requested_amount or 0,
                })

            if (a.budget_item_type_id or None) != (b.budget_item_type_id or None):
                diffs.append({
                    "field": "Item type",
                    "before": a.budget_item_type.item_name if a.budget_item_type else "",
                    "after": b.budget_item_type.item_name if b.budget_item_type else "",
                })

            if _norm(a.item_name) != _norm(b.item_name):
                diffs.append({"field": "Item name", "before": a.item_name or "", "after": b.item_name or ""})

            # These are big fields; only include if changed.
            if _norm(a.description) != _norm(b.description):
                diffs.append({"field": "Description", "before": a.description or "", "after": b.description or ""})

            if _norm(a.justification) != _norm(b.justification):
                diffs.append(
                    {"field": "Justification", "before": a.justification or "", "after": b.justification or ""})

            if diffs:
                changed_lines.append({
                    "prev": a,
                    "curr": b,
                    "diffs": diffs,
                })

        prev_total = sum((l.requested_amount or 0) for l in prev_lines) if prev_lines else None

        return render_template(
            "revision_snapshot.html",
            revision=revision,
            request=request,
            lines=lines,
            requested_total=requested_total,
            reviews_by_line_id=reviews_by_line_id,
            groups_by_id=groups_by_id,
            is_admin=h.is_admin(),
            active_user_approval_group_ids=h.active_user_approval_group_ids(),
            prev_revision=prev_revision,
            prev_total=prev_total,
            added_lines=added_lines,
            removed_lines=removed_lines,
            changed_lines=changed_lines,
        )

    def _apply_request_edit_form_to_draft(req, draft):
        """
        Reads request.form and mutates DraftLine rows (update/add/delete) for this draft.
        Returns nothing; caller commits.
        """
        from .models import DraftLine

    @app.get("/requests/<int:request_id>/edit")
    def edit_request_draft(request_id: int):
        from .models import Request, RequestDraft, DraftLine, RequestLine, BudgetItemType
        h.ensure_demo_budget_data()

        req = db.session.get(Request, request_id)

        if not req:
            abort(404)

        if (req.current_status or "").upper() == "APPROVED":
            abort(400, "Request is finalized and cannot be modified.")

        uid = h.get_active_user_id()
        is_owner = (uid == req.created_by_user_id)
        if not (h.is_admin() or is_owner):
            abort(403)

        if is_owner and not h.is_admin() and req.current_status not in ("DRAFT", "NEEDS_REVISION"):
            return "Request is under review and cannot be edited unless kicked back.", 403


        item_types = (
            db.session.query(BudgetItemType)
            .filter(BudgetItemType.is_active == True)  # noqa: E712
            .order_by(BudgetItemType.item_name.asc())
            .all()
        )

        draft = (
            db.session.query(RequestDraft)
            .filter(RequestDraft.request_id == req.id)
            .one_or_none()
        )

        # Create draft if missing. If there is a current revision, seed the draft from it.
        if draft is None:
            draft = RequestDraft(request_id=req.id)
            db.session.add(draft)
            db.session.flush()

            if req.current_revision_id:
                snapshot_lines = (
                    db.session.query(RequestLine)
                    .filter(RequestLine.revision_id == req.current_revision_id)
                    .order_by(RequestLine.public_line_number.asc().nullslast(), RequestLine.id.asc())
                    .all()
                )
                for i, l in enumerate(snapshot_lines, start=1):
                    priority = (getattr(l, "priority", "") or (l.justification or "") or "").strip()
                    reason = (getattr(l, "reason", "") or (l.description or "") or "").strip()

                    bit_id = getattr(l, "budget_item_type_id", None)
                    bit = db.session.get(BudgetItemType, bit_id) if bit_id else None

                    category = (bit.spend_type if bit and bit.spend_type else (
                            l.category or "Other")).strip() or "Other"
                    description = reason or (l.description or "").strip() or ""
                    justification = priority or (l.justification or "").strip() or ""

                    db.session.add(DraftLine(
                        draft_id=draft.id,
                        budget_item_type_id=bit_id,
                        requested_amount=l.requested_amount or 0,
                        priority=priority,
                        reason=reason,
                        category=category,
                        description=description,
                        justification=justification,
                        sort_order=i,
                    ))
            db.session.commit()

        lines = (
            db.session.query(DraftLine)
            .filter(DraftLine.draft_id == draft.id)
            .order_by(DraftLine.sort_order.asc(), DraftLine.id.asc())
            .all()
        )

        requested_total = sum((l.requested_amount or 0) for l in lines)

        return render_template(
            "request_edit.html",
            req=req,
            draft=draft,
            lines=lines,
            requested_total=requested_total,
            item_types=item_types,
            priority_options=PRIORITY_OPTIONS,
        )

    @app.post("/requests/<int:request_id>/edit")
    def save_request_draft(request_id: int):
        import re
        from flask import request, redirect, url_for, abort
        from .models import Request, RequestDraft, DraftLine, RequestLine, BudgetItemType

        req = db.session.get(Request, request_id)
        if not req:
            abort(404)

        uid = h.get_active_user_id()
        is_owner = (uid == req.created_by_user_id)
        if not (h.is_admin() or is_owner):
            abort(403)

        if (req.current_status or "").upper() == "APPROVED":
            abort(400, "Request is finalized and cannot be modified.")

        if is_owner and not h.is_admin() and req.current_status not in ("DRAFT", "NEEDS_REVISION"):
            return "Request is under review and cannot be edited unless kicked back.", 403

        draft = (
            db.session.query(RequestDraft)
            .filter(RequestDraft.request_id == req.id)
            .one_or_none()
        )

        # Same behavior as GET: create if missing, seed from current revision.
        if draft is None:
            draft = RequestDraft(request_id=req.id)
            db.session.add(draft)
            db.session.flush()

            if req.current_revision_id:
                snapshot_lines = (
                    db.session.query(RequestLine)
                    .filter(RequestLine.revision_id == req.current_revision_id)
                    .order_by(RequestLine.public_line_number.asc().nullslast(), RequestLine.id.asc())
                    .all()
                )
                for i, l in enumerate(snapshot_lines, start=1):
                    priority = (getattr(l, "priority", "") or (l.justification or "") or "").strip()
                    reason = (getattr(l, "reason", "") or (l.description or "") or "").strip()

                    bit_id = getattr(l, "budget_item_type_id", None)
                    bit = db.session.get(BudgetItemType, bit_id) if bit_id else None

                    category = (bit.spend_type if bit and bit.spend_type else (
                            l.category or "Other")).strip() or "Other"
                    description = reason or (l.description or "").strip() or ""
                    justification = priority or (l.justification or "").strip() or ""

                    db.session.add(DraftLine(
                        draft_id=draft.id,
                        budget_item_type_id=bit_id,
                        requested_amount=int(l.requested_amount or 0),

                        # new fields
                        priority=priority,
                        reason=reason,

                        # legacy required fields (mirrors)
                        category=category,
                        description=description,
                        justification=justification,

                        item_name=getattr(l, "item_name", "") or "",
                        sort_order=i,
                    ))

            db.session.commit()

        # Parse indices based on budget_item_type_id field (matches new template)
        index_re = re.compile(r"^line-(\d+)-budget_item_type_id$")
        indices = sorted({
            int(m.group(1))
            for k in request.form.keys()
            for m in [index_re.match(k)]
            if m
        })

        next_sort = 1

        for idx in indices:
            line_id = (request.form.get(f"line-{idx}-id") or "").strip()
            delete_checked = request.form.get(f"line-{idx}-delete") == "on"

            bit_raw = (request.form.get(f"line-{idx}-budget_item_type_id") or "").strip()
            priority = (request.form.get(f"line-{idx}-priority") or "").strip()
            reason = (request.form.get(f"line-{idx}-reason") or "").strip()
            amount_raw = (request.form.get(f"line-{idx}-amount") or "").strip()

            # If it’s a totally blank new row, ignore it.
            is_blank_new = (not line_id) and (not bit_raw) and (not priority) and (not reason) and (not amount_raw)
            if is_blank_new:
                continue

            # Parse budget item type id
            try:
                budget_item_type_id = int(bit_raw) if bit_raw else None
            except ValueError:
                budget_item_type_id = None

            # Parse amount (dollars int)
            try:
                amount = int(amount_raw) if amount_raw else 0
            except ValueError:
                amount = 0

            # Determine category from selected budget item type (or fallback)
            bit = db.session.get(BudgetItemType, budget_item_type_id) if budget_item_type_id else None
            category = (bit.spend_type if bit and bit.spend_type else "Other").strip() or "Other"

            # Legacy required mirrors
            description = reason
            justification = priority

            if line_id:
                # Update existing draft line
                try:
                    line_pk = int(line_id)
                except ValueError:
                    continue

                line = db.session.get(DraftLine, line_pk)
                if not line or line.draft_id != draft.id:
                    continue

                if delete_checked:
                    db.session.delete(line)
                    continue

                line.budget_item_type_id = budget_item_type_id
                line.priority = priority
                line.reason = reason
                line.requested_amount = amount

                # legacy required fields (mirrors)
                line.category = category
                line.description = description
                line.justification = justification

                line.sort_order = next_sort
                next_sort += 1

            else:
                # Create new draft line
                if delete_checked:
                    continue

                db.session.add(DraftLine(
                    draft_id=draft.id,
                    budget_item_type_id=budget_item_type_id,
                    priority=priority,
                    reason=reason,
                    requested_amount=amount,

                    # legacy required fields (mirrors)
                    category=category,
                    description=description,
                    justification=justification,

                    sort_order=next_sort,
                ))
                next_sort += 1

        db.session.commit()
        return redirect(url_for("edit_request_draft", request_id=req.id))

    @app.get("/requests/<int:request_id>")
    def request_detail(request_id: int):
        from flask import render_template, abort
        from sqlalchemy.orm import joinedload

        from .models import (
            Request,
            RequestRevision,
            RequestLine,
            LineReview,
        )

        h.ensure_demo_budget_data()

        req = db.session.get(Request, request_id)
        if not req:
            abort(404)

        # Revisions list for the bottom table
        revisions = (
            db.session.query(RequestRevision)
            .filter(RequestRevision.request_id == req.id)
            .order_by(RequestRevision.revision_number.desc())
            .all()
        )

        # Totals per revision (for the revisions table)
        totals_by_revision_id = {}
        if revisions:
            rev_ids = [r.id for r in revisions]
            lines_for_all_revs = (
                db.session.query(RequestLine.revision_id, RequestLine.requested_amount)
                .filter(RequestLine.revision_id.in_(rev_ids))
                .all()
            )
            for rev_id, amt in lines_for_all_revs:
                totals_by_revision_id[rev_id] = totals_by_revision_id.get(rev_id, 0) + (amt or 0)

        # Current revision + lines
        current_revision = None
        current_lines = []
        current_total = 0

        if req.current_revision_id:
            current_revision = db.session.get(RequestRevision, req.current_revision_id)

            current_lines = (
                db.session.query(RequestLine)
                .options(joinedload(RequestLine.budget_item_type))
                .filter(RequestLine.revision_id == req.current_revision_id)
                .order_by(RequestLine.public_line_number.asc().nullslast(), RequestLine.id.asc())
                .all()
            )
            current_total = sum((l.requested_amount or 0) for l in current_lines)

            # ✅ Heal BEFORE fetching reviews / computing readiness
            if current_lines:
                created = _ensure_line_reviews_for_revision(current_revision.id)
                if created:
                    db.session.flush()

        # Line reviews (for current revision lines only) -> grouped by line id
        line_reviews_by_line_id = {}
        if current_lines:
            line_ids = [l.id for l in current_lines]
            reviews = (
                db.session.query(LineReview)
                .options(joinedload(LineReview.approval_group))
                .filter(LineReview.request_line_id.in_(line_ids))
                .order_by(LineReview.approval_group_id.asc(), LineReview.updated_at.desc())
                .all()
            )
            for lr in reviews:
                line_reviews_by_line_id.setdefault(lr.request_line_id, []).append(lr)

        # --- C6.A: Review summary + "ready for final approval" ---
        review_status_counts = {"PENDING": 0, "NEEDS_INFO": 0, "APPROVED": 0, "REJECTED": 0}
        lines_without_any_reviews = 0
        lines_with_any_blockers = 0  # any NEEDS_INFO / REJECTED / PENDING

        blocking_lines = []

        if current_lines:
            for line in current_lines:
                lrs = line_reviews_by_line_id.get(line.id, [])
                if not lrs:
                    lines_without_any_reviews += 1
                    lines_with_any_blockers += 1
                    blocking_lines.append({
                        "line_id": line.id,
                        "reason": "No reviews yet",
                        "statuses": [],
                    })
                    continue

                # A line is "clean" only if ALL its group reviews are APPROVED
                all_approved_for_line = True
                blocking_statuses = []
                for lr in lrs:
                    st = (lr.status or "PENDING").upper()
                    if st not in review_status_counts:
                        # Unknown statuses should be treated as blockers until handled explicitly
                        st = "PENDING"
                    review_status_counts[st] += 1

                    if st != "APPROVED":
                        all_approved_for_line = False
                        group_code = lr.approval_group.code if lr.approval_group else "GROUP"
                        blocking_statuses.append(f"{group_code}:{st}")

                if not all_approved_for_line:
                    lines_with_any_blockers += 1
                    blocking_lines.append({
                        "line_id": line.id,
                        "reason": "Not fully approved",
                        "statuses": blocking_statuses,
                    })

        ready_to_finalize = (
                bool(current_lines)
                and lines_without_any_reviews == 0
                and review_status_counts["PENDING"] == 0
                and review_status_counts["NEEDS_INFO"] == 0
        )

        review_summary = {
            "pending": review_status_counts["PENDING"],
            "needs_info": review_status_counts["NEEDS_INFO"],
            "approved": review_status_counts["APPROVED"],
            "rejected": review_status_counts["REJECTED"],
            "no_review": lines_without_any_reviews,
            "ready_to_finalize": ready_to_finalize,
        }

        # Kickback reason (for NEEDS_REVISION callout)
        kickback_reason = getattr(req, "kickback_reason", None)

        can_admin_edit = h.is_admin()

        return render_template(
            "request_detail.html",
            req=req,
            revisions=revisions,
            totals_by_revision_id=totals_by_revision_id,
            current_revision=current_revision,
            current_lines=current_lines,
            current_total=current_total,
            line_reviews_by_line_id=line_reviews_by_line_id,
            kickback_reason=kickback_reason,
            review_summary=review_summary,
            blocking_lines=blocking_lines,
            can_admin_edit=can_admin_edit,

        )

    @app.post("/requests/<int:request_id>/submit")
    def submit_request_draft(request_id: int):
        from sqlalchemy import func
        from flask import redirect, url_for, abort
        from .models import (
            Request, RequestDraft, DraftLine,
            RequestRevision, RequestLine,
            BudgetItemType,
            RequestAuditEvent,
        )

        req = db.session.get(Request, request_id)
        if not req:
            abort(404)

        uid = h.get_active_user_id()
        is_admin = h.is_admin()

        if not (is_admin or uid == req.created_by_user_id):
            abort(403)

        if (req.current_status or "").upper() == "APPROVED":
            abort(400, "Request is finalized and cannot be modified.")

        old_status = (req.current_status or "").upper()
        allowed = {"DRAFT", "NEEDS_REVISION", "SUBMITTED"} if is_admin else {"DRAFT", "NEEDS_REVISION"}
        if old_status not in allowed:
            return f"Cannot submit from status {old_status}.", 400

        draft = (
            db.session.query(RequestDraft)
            .filter(RequestDraft.request_id == req.id)
            .one_or_none()
        )
        if not draft:
            return "No draft exists for this request.", 400

        draft_lines = (
            db.session.query(DraftLine)
            .filter(DraftLine.draft_id == draft.id)
            .order_by(DraftLine.sort_order.asc(), DraftLine.id.asc())
            .all()
        )
        if not draft_lines:
            return "Cannot submit: draft has no lines.", 400

        max_rev = (
            db.session.query(func.max(RequestRevision.revision_number))
            .filter(RequestRevision.request_id == req.id)
            .scalar()
        )
        next_rev_num = int(max_rev or 0) + 1

        clean_lines = []
        errors = []

        for dl in draft_lines:
            bit_id = getattr(dl, "budget_item_type_id", None)
            priority = (getattr(dl, "priority", "") or "").strip()
            reason = (getattr(dl, "reason", "") or "").strip()
            amt = int(dl.requested_amount or 0)

            is_fully_blank = (bit_id is None) and (not priority) and (not reason) and (amt == 0)
            if is_fully_blank:
                continue

            missing = []
            if bit_id is None: missing.append("Item type")
            if not priority: missing.append("Priority")
            if not reason: missing.append("Reason")
            if amt <= 0: missing.append("Amount (> 0)")

            if missing:
                errors.append(f"Draft line {dl.sort_order or dl.id}: missing {', '.join(missing)}.")
                continue

            clean_lines.append(dl)

        if errors:
            return "Cannot submit:\n" + "\n".join(errors), 400
        if not clean_lines:
            return "Cannot submit: draft has no valid lines.", 400

        new_rev = RequestRevision(
            request_id=req.id,
            revision_number=next_rev_num,
            submitted_by_user_id=uid,
            status_at_submission="SUBMITTED",
        )
        db.session.add(new_rev)
        db.session.flush()

        created_lines = []
        public_n = 1

        for dl in clean_lines:
            bit = db.session.get(BudgetItemType, dl.budget_item_type_id)
            if not bit:
                return f"Invalid BudgetItemType id={dl.budget_item_type_id}.", 400

            rl = RequestLine(
                revision_id=new_rev.id,
                public_line_number=public_n,
                budget_item_type_id=dl.budget_item_type_id,
                category=(bit.spend_type or "Other"),
                item_name="",
                description=(dl.reason or ""),
                justification=(dl.priority or ""),
                priority=(dl.priority or ""),
                reason=(dl.reason or ""),
                requested_amount=int(dl.requested_amount or 0),
                requester_comment=None,
            )
            db.session.add(rl)
            created_lines.append(rl)
            public_n += 1

        db.session.flush()

        for rl in created_lines:
            _get_or_create_line_review_for_line(rl)  # returns (lr, created)

        req.current_revision_id = new_rev.id
        req.current_status = "SUBMITTED"
        if old_status == "NEEDS_REVISION":
            req.kickback_reason = None

        event_type = "SUBMITTED_REVISION"
        if is_admin and old_status == "SUBMITTED":
            event_type = "ADMIN_RESUBMITTED_REVISION"

        db.session.add(RequestAuditEvent(
            request_id=req.id,
            event_type=event_type,
            old_value=old_status,
            new_value=f"Rev {next_rev_num} submitted (draft {draft.id})",
            created_by_user_id=uid,
        ))

        db.session.commit()
        return redirect(url_for("revision_snapshot", revision_id=new_rev.id))

    @app.post("/requests/<int:request_id>/kickback")
    def kickback_request(request_id: int):
        from flask import request, redirect, url_for, abort
        from .models import Request, RequestAuditEvent

        req = db.session.get(Request, request_id)
        if not req:
            abort(404)

        # Permission: finance or admin can kick back the whole request
        if not (h.is_admin() or h.is_finance()):
            abort(403)
        if (req.current_status or "").upper() == "APPROVED":
            abort(400, "Request is finalized and cannot be modified.")

        old_status = (req.current_status or "").upper()
        if old_status != "SUBMITTED":
            return f"Invalid transition: {old_status} -> NEEDS_REVISION", 400

        reason = (request.form.get("kickback_reason") or "").strip()
        if not reason:
            return "Kickback reason is required.", 400

        req.current_status = "NEEDS_REVISION"
        req.kickback_reason = reason

        db.session.add(RequestAuditEvent(
            request_id=req.id,
            event_type="STATUS_CHANGE",
            old_value=old_status,
            new_value=f"NEEDS_REVISION :: {reason}",
            created_by_user_id=h.get_active_user_id(),
        ))

        db.session.commit()
        return redirect(url_for("request_detail", request_id=req.id))

    @app.post("/requests/<int:request_id>/approve")
    def approve_request(request_id: int):
        from flask import redirect, url_for, abort
        from datetime import datetime
        from .models import Request, RequestLine, LineReview

        req = db.session.get(Request, request_id)
        if not req:
            abort(404)

        final_note = (request.form.get("final_approval_note") or "").strip()
        if not final_note:
            abort(400, "Final approval note is required.")

        req.final_approval_note = final_note

        if (req.current_status or "").upper() == "APPROVED":
            abort(400, "Request is finalized and cannot be modified.")

        # Optional but recommended: only approve from SUBMITTED
        if (req.current_status or "").upper() != "SUBMITTED":
            abort(400, "Cannot approve request unless it is SUBMITTED.")

        if not req.current_revision_id:
            abort(400, "Cannot approve request without a current revision.")

        if not (h.is_admin() or h.is_finance()):
            abort(403)

        lines = (
            db.session.query(RequestLine)
            .filter(RequestLine.revision_id == req.current_revision_id)
            .all()
        )
        if not lines:
            abort(400, "Cannot approve request with no lines.")

        line_ids = [l.id for l in lines]

        reviews = (
            db.session.query(LineReview)
            .filter(LineReview.request_line_id.in_(line_ids))
            .all()
        )

        reviews_by_line = {}
        for lr in reviews:
            reviews_by_line.setdefault(lr.request_line_id, []).append(lr)

        # All lines must have at least one review, and all reviews must be APPROVED
        for line in lines:
            lrs = reviews_by_line.get(line.id)
            if not lrs:
                abort(400, "Cannot approve request: some lines have no reviews.")
            for lr in lrs:
                st = (lr.status or "PENDING").upper()

                # Block if any reviewer is still waiting on something
                if st in ("PENDING", "NEEDS_INFO"):
                    abort(400, "Cannot finalize request: some line reviews are still pending or need info.")

                # Only allow terminal decisions at the time of finalization
                if st not in ("APPROVED", "REJECTED"):
                    abort(400, "Cannot finalize request: invalid line review status.")

        req.current_status = "APPROVED"
        req.approved_revision_id = req.current_revision_id
        req.approved_at = datetime.utcnow()
        req.approved_by_user_id = h.get_active_user_id()

        db.session.commit()
        return redirect(url_for("request_detail", request_id=req.id))

    @app.post("/line-reviews/<int:line_review_id>/approve")
    def approve_line_review(line_review_id: int):
        from flask import redirect, url_for, abort, request
        from .models import LineReview

        lr = db.session.get(LineReview, line_review_id)
        if not lr:
            abort(404)

        # Permission: admin OR owning approver group
        if not (h.is_admin() or h.can_review_group(lr.approval_group_id)):
            abort(403)

        note = (request.form.get("note") or "").strip()

        # Canonical transition (validation + audit handled inside helper)
        _apply_line_review_transition(lr=lr, action="APPROVE", note=note)

        db.session.commit()

        # Redirect back to the revision snapshot
        rev_id = lr.request_line.revision_id
        return redirect(url_for("revision_snapshot", revision_id=rev_id))

    @app.post("/line-reviews/<int:line_review_id>/kickback")
    def kickback_line_review(line_review_id: int):
        from flask import request, redirect, url_for, abort
        from .models import LineReview

        lr = db.session.get(LineReview, line_review_id)
        if not lr:
            abort(404)

        # Permission: admin OR owning approver group
        if not (h.is_admin() or h.can_review_group(lr.approval_group_id)):
            abort(403)

        external_note = (request.form.get("external_admin_note") or "").strip()
        internal_note = (request.form.get("internal_admin_note") or "").strip()

        # Canonical transition:
        # - sets status NEEDS_INFO
        # - stores external_admin_note
        # - posts the public LineComment
        # - logs STATUS_CHANGE audit
        _apply_line_review_transition(
            lr=lr,
            action="REQUEST_INFO",
            note=external_note,
            internal_note=internal_note,
        )

        db.session.commit()

        rev_id = lr.request_line.revision_id
        return redirect(url_for("revision_snapshot", revision_id=rev_id))

    @app.post("/revisions/<int:revision_id>/approve-my-lines")
    def approve_my_lines_for_revision(revision_id: int):
        from datetime import datetime
        from flask import redirect, url_for, abort
        from .models import LineReview, RequestRevision, LineAuditEvent

        revision = db.session.get(RequestRevision, revision_id)
        if not revision:
            abort(404)

        user_id = h.get_active_user_id()

        # Permission: must be admin or have at least one approval group
        if not h.is_admin():
            group_ids = list(h.active_user_approval_group_ids() or [])
            if not group_ids:
                abort(403)
        else:
            group_ids = None  # admin scopes to all

        # Pending reviews tied to this revision
        q = (
            db.session.query(LineReview)
            .join(LineReview.request_line)
            .filter(LineReview.status == "PENDING")
            .filter(LineReview.request_line.has(revision_id=revision_id))
        )

        if group_ids is not None:
            q = q.filter(LineReview.approval_group_id.in_(group_ids))

        reviews = q.all()

        # Nothing to do → redirect back (idempotent)
        if not reviews:
            return redirect(url_for("revision_snapshot", revision_id=revision_id))

        bulk_note = "Approved (bulk)"

        for r in reviews:
            old_status = (r.status or "PENDING").upper()

            # Safety: we queried PENDING, but keep it tight.
            if old_status != "PENDING":
                continue

            r.status = "APPROVED"
            r.updated_by_user_id = user_id

            # C9 note requirement: store an approval note even in bulk.
            # Prefer final_decision_* fields if present.
            if hasattr(r, "final_decision_note"):
                r.final_decision_note = bulk_note
                r.final_decision_at = datetime.utcnow()
                r.final_decision_by_user_id = user_id
                # Do not clear external_admin_note; it may contain a prior NEEDS_INFO ask.
            else:
                # Legacy fallback if final_decision_* fields not present
                r.external_admin_note = bulk_note

            db.session.add(LineAuditEvent(
                request_line_id=r.request_line_id,
                event_type="STATUS_CHANGE",
                old_value=old_status,
                new_value=f"APPROVED :: {bulk_note}",
                created_by_user_id=user_id,
            ))

        db.session.commit()

        # OPTIONAL: re-derive request-level status after bulk approval
        # (Keep if you already have it and it behaves.)
        if hasattr(h, "recalc_request_status_from_lines"):
            h.recalc_request_status_from_lines(revision)
            db.session.commit()

        return redirect(url_for("revision_snapshot", revision_id=revision_id))

    @app.get("/dashboard/approvals")
    def approvals_dashboard():
        from flask import render_template
        from .models import (
            ApprovalGroup,
            LineReview,
            RequestLine,
            RequestRevision,
            Request,
            BudgetItemType,
        )

        # Scope groups by role
        if h.is_admin():
            groups = (
                db.session.query(ApprovalGroup)
                .filter(ApprovalGroup.is_active == True)  # noqa: E712
                .order_by(ApprovalGroup.sort_order.asc(), ApprovalGroup.name.asc())
                .all()
            )
        else:
            group_ids = h.active_user_approval_group_ids()
            if not group_ids:
                return "Forbidden", 403

            groups = (
                db.session.query(ApprovalGroup)
                .filter(ApprovalGroup.id.in_(group_ids))
                .filter(ApprovalGroup.is_active == True)  # noqa: E712
                .order_by(ApprovalGroup.sort_order.asc(), ApprovalGroup.name.asc())
                .all()
            )

        cutoff = datetime.utcnow() - timedelta(hours=72)

        # Helper: base query limited to "current revision lines" for each request
        def base_q_for_group(group_id: int):
            # We join all the way to Request so we can enforce:
            # Request.current_revision_id == RequestLine.revision_id
            return (
                db.session.query(LineReview, RequestLine, Request, BudgetItemType)
                .join(RequestLine, LineReview.request_line_id == RequestLine.id)
                .join(RequestRevision, RequestLine.revision_id == RequestRevision.id)
                .join(Request, RequestRevision.request_id == Request.id)
                .outerjoin(BudgetItemType, RequestLine.budget_item_type_id == BudgetItemType.id)
                .filter(LineReview.approval_group_id == group_id)
                .filter(Request.current_revision_id == RequestLine.revision_id)
            )

        queues_by_group_id = {}

        for g in groups:
            q = base_q_for_group(g.id)

            needs_review = (
                q.filter(LineReview.status == "PENDING")
                .order_by(Request.id.asc(), RequestLine.id.asc())
                .all()
            )

            needs_info = (
                q.filter(LineReview.status == "NEEDS_INFO")
                .order_by(LineReview.updated_at.desc(), Request.id.asc(), RequestLine.id.asc())
                .all()
            )

            recently_updated = (
                q.filter(LineReview.updated_at >= cutoff)
                .order_by(LineReview.updated_at.desc(), Request.id.asc(), RequestLine.id.asc())
                .all()
            )

            queues_by_group_id[g.id] = {
                "needs_review": needs_review,
                "kicked_back": needs_info,
                "recently_updated": recently_updated,
            }

        return render_template(
            "approvals_dashboard.html",
            groups=groups,
            queues_by_group_id=queues_by_group_id,
            cutoff=cutoff,
        )

    @app.post("/requests/<int:request_id>/lines/<int:line_id>/requester-respond")
    def requester_respond_to_needs_info(request_id: int, line_id: int):
        from .models import Request, RequestLine, LineReview, LineComment, LineAuditEvent

        req = db.session.get(Request, request_id)
        if not req:
            abort(404)

        line = db.session.get(RequestLine, line_id)
        if not line or line.revision.request_id != req.id:
            abort(404)

        # Permissions: requester (or admin for demo)
        roles = set(h.active_user_roles())
        if ("REQUESTER" not in roles) and (not h.is_admin()):
            abort(403)

        lr = (
            db.session.query(LineReview)
            .filter(LineReview.request_line_id == line.id)
            .order_by(LineReview.id.asc())
            .first()
        )
        if not lr:
            return "No review record for this line.", 400

        if lr.status != "NEEDS_INFO":
            return "This line is not currently in NEEDS_INFO.", 400

        body = (request.form.get("body") or "").strip()
        if not body:
            return "Response is required.", 400

        uid = h.get_active_user_id()

        # 1) Post a PUBLIC comment (so reviewers see the response in the normal thread)
        c = LineComment(
            request_line_id=line.id,
            visibility="PUBLIC",
            body=body,
            created_by_user_id=uid,
        )
        db.session.add(c)

        # 2) Audit: requester responded
        db.session.add(LineAuditEvent(
            request_line_id=line.id,
            event_type="REQUESTER_RESPONSE",
            old_value="",
            new_value=body,
            created_by_user_id=uid,
        ))

        # 3) Move NEEDS_INFO -> PENDING (reviewable again)
        old_status = lr.status
        lr.status = "PENDING"
        lr.updated_by_user_id = uid

        db.session.add(LineAuditEvent(
            request_line_id=line.id,
            event_type="STATUS_CHANGE",
            old_value=old_status,
            new_value="PENDING :: requester responded",
            created_by_user_id=uid,
        ))

        db.session.commit()
        return redirect(url_for("line_detail", request_id=req.id, line_id=line.id))

    @app.get("/requests/new")
    def new_request():
        from .models import Department, EventCycle
        h.ensure_demo_users()
        h.ensure_demo_org_data()

        # Minimal auth: require an active user (matches the rest of your app assumptions)
        uid = h.get_active_user_id()
        if not uid:
            return redirect(url_for("dev_login"))

        cycles = (
            db.session.query(EventCycle)
            .filter(EventCycle.is_active == True)  # noqa: E712
            .order_by(EventCycle.sort_order.asc(), EventCycle.name.asc())
            .all()
        )

        departments = (
            db.session.query(Department)
            .filter(Department.is_active == True)  # noqa: E712
            .order_by(Department.sort_order.asc(), Department.name.asc())
            .all()
        )

        default_cycle_id = None
        for c in cycles:
            if c.is_default:
                default_cycle_id = c.id
                break

        return render_template(
            "request_new.html",
            cycles=cycles,
            departments=departments,
            default_cycle_id=default_cycle_id,
        )

    @app.post("/requests/new")
    def new_request_post():
        from .models import Department, EventCycle, Request, RequestDraft
        h.ensure_demo_users()
        h.ensure_demo_org_data()

        uid = h.get_active_user_id()
        if not uid:
            return redirect(url_for("dev_login"))

        # Read selections
        cycle_raw = (request.form.get("event_cycle_id") or "").strip()
        dept_raw = (request.form.get("department_id") or "").strip()

        try:
            event_cycle_id = int(cycle_raw)
            department_id = int(dept_raw)
        except ValueError:
            return "Invalid event cycle or department.", 400

        cycle = db.session.get(EventCycle, event_cycle_id)
        dept = db.session.get(Department, department_id)

        if not cycle or not cycle.is_active:
            return "Unknown or inactive event cycle.", 400
        if not dept or not dept.is_active:
            return "Unknown or inactive department.", 400

        approved_existing = (
            db.session.query(Request)
            .filter(Request.current_status == "APPROVED")
            .filter(Request.event_cycle_id == cycle.id)
            .filter(Request.department_id == dept.id)
            .order_by(Request.id.desc())
            .first()
        )

        if approved_existing:
            return render_template(
                "request_new_blocked.html",
                cycle=cycle,
                dept=dept,
                approved_request=approved_existing,
            ), 409

        # Create request
        r = Request(
            created_by_user_id=uid,
            current_status="DRAFT",

            # New FK fields (preferred)
            event_cycle_id=cycle.id,
            department_id=dept.id,

            # Legacy string fields (keep in sync for now)
            event_cycle=cycle.name,
            requesting_department=dept.name,
        )
        db.session.add(r)
        db.session.flush()

        # Create empty draft so edit page is immediately ready
        d = RequestDraft(request_id=r.id)
        db.session.add(d)

        db.session.commit()
        return redirect(url_for("edit_request_draft", request_id=r.id))

    @app.get("/dev/requests/<int:request_id>/debug")
    def dev_request_debug(request_id: int):
        # DEV ONLY
        h.ensure_demo_users()

        def iso(dt):
            try:
                return dt.isoformat() if dt else None
            except Exception:
                return None

        def safe_int(x, default=None):
            try:
                return int(x)
            except Exception:
                return default

        from .models import (
            Request,
            RequestDraft,
            DraftLine,
            RequestRevision,
            RequestLine,
            LineReview,
        )

        req = db.session.get(Request, request_id)
        if not req:
            return {"error": "Request not found"}, 404

        # Optional models/fields (may not exist yet depending on your migration state)
        Department = None
        EventCycle = None
        try:
            from .models import Department, EventCycle  # type: ignore
        except Exception:
            pass

        department_id = getattr(req, "department_id", None)
        event_cycle_id = getattr(req, "event_cycle_id", None)

        dept = db.session.get(Department, department_id) if Department and department_id else None
        cycle = db.session.get(EventCycle, event_cycle_id) if EventCycle and event_cycle_id else None

        draft = (
            db.session.query(RequestDraft)
            .filter(RequestDraft.request_id == req.id)
            .one_or_none()
        )

        draft_lines = []
        if draft:
            draft_lines = (
                db.session.query(DraftLine)
                .filter(DraftLine.draft_id == draft.id)
                .all()
            )

        def draft_line_amount(l):
            # DraftLine has requested_amount in your models
            return safe_int(getattr(l, "requested_amount", 0), 0) or 0

        revisions = (
            db.session.query(RequestRevision)
            .filter(RequestRevision.request_id == req.id)
            .order_by(RequestRevision.revision_number.asc())
            .all()
        )

        revision_summaries = []
        for rev in revisions:
            lines = (
                db.session.query(RequestLine)
                .filter(RequestLine.revision_id == rev.id)
                .all()
            )
            reviews = (
                db.session.query(LineReview)
                .join(RequestLine, LineReview.request_line_id == RequestLine.id)
                .filter(RequestLine.revision_id == rev.id)
                .all()
            )

            # RequestRevision uses submitted_at (per your current models)
            ts = getattr(rev, "submitted_at", None) or getattr(rev, "created_at", None)

            revision_summaries.append(
                {
                    "revision_id": rev.id,
                    "revision_number": rev.revision_number,
                    "submitted_at": iso(ts),
                    "submitted_by_user_id": getattr(rev, "submitted_by_user_id", None),
                    "line_count": len(lines),
                    "review_count": len(reviews),
                }
            )

        status = getattr(req, "current_status", None)

        invariants = {
            "has_department_fk": department_id is not None,
            "has_event_cycle_fk": event_cycle_id is not None,
            "legacy_department_matches_fk": (
                    dept is not None and getattr(req, "requesting_department", None) == getattr(dept, "name", None)
            ),
            "legacy_event_cycle_matches_fk": (
                    cycle is not None and getattr(req, "event_cycle", None) == getattr(cycle, "name", None)
            ),
            "draft_exists_when_editable": (status in ("DRAFT", "NEEDS_REVISION") and draft is not None),
        }

        health = "OK" if all(v is True for v in invariants.values()) else "WARN"

        return {
            "health": health,
            "request": {
                "id": req.id,
                "status": status,
                "created_at": iso(getattr(req, "created_at", None)),
                "created_by_user_id": getattr(req, "created_by_user_id", None),

                # FK fields (if present)
                "department_id": department_id,
                "department_name_fk": getattr(dept, "name", None) if dept else None,
                "event_cycle_id": event_cycle_id,
                "event_cycle_name_fk": getattr(cycle, "name", None) if cycle else None,

                # legacy strings
                "department_name_legacy": getattr(req, "requesting_department", None),
                "event_cycle_name_legacy": getattr(req, "event_cycle", None),

                "current_revision_id": getattr(req, "current_revision_id", None),
                "approved_revision_id": getattr(req, "approved_revision_id", None),
                "kickback_reason": getattr(req, "kickback_reason", None),
            },
            "draft": {
                "exists": bool(draft),
                "draft_id": draft.id if draft else None,
                "updated_at": iso(getattr(draft, "updated_at", None)) if draft else None,
                "draft_line_count": len(draft_lines),
                "draft_total": sum(draft_line_amount(l) for l in draft_lines),
            },
            "revisions": revision_summaries,
            "invariants": invariants,
        }

    @app.get("/admin/demo/approval-summary")
    def admin_demo_approval_summary():
        from sqlalchemy import func, case
        from .models import ApprovalGroup, LineReview, RequestLine, RequestRevision, Request

        # Demo guard: admin OR finance only
        if (not h.is_admin()) and (not h.is_finance()):
            return "Forbidden", 403

        # Base joins scoped to "current revision lines"
        base = (
            db.session.query(
                ApprovalGroup.id.label("group_id"),
                ApprovalGroup.name.label("group_name"),

                # counts
                func.sum(case((LineReview.status == "PENDING", 1), else_=0)).label("pending_count"),
                func.sum(case((LineReview.status == "NEEDS_INFO", 1), else_=0)).label("needs_info_count"),
                func.sum(case((LineReview.status == "APPROVED", 1), else_=0)).label("approved_count"),
                func.sum(case((LineReview.status == "REJECTED", 1), else_=0)).label("rejected_count"),

                # dollars (requested_amount on RequestLine) :contentReference[oaicite:1]{index=1}
                func.sum(case((LineReview.status == "PENDING", RequestLine.requested_amount), else_=0)).label(
                    "pending_amount"),
                func.sum(case((LineReview.status == "NEEDS_INFO", RequestLine.requested_amount), else_=0)).label(
                    "needs_info_amount"),
                func.sum(case((LineReview.status == "APPROVED", RequestLine.requested_amount), else_=0)).label(
                    "approved_amount"),
                func.sum(case((LineReview.status == "REJECTED", RequestLine.requested_amount), else_=0)).label(
                    "rejected_amount"),

                # number of distinct requests represented in this group (current rev only)
                func.count(func.distinct(Request.id)).label("request_count"),
            )
            .select_from(ApprovalGroup)
            .join(LineReview, LineReview.approval_group_id == ApprovalGroup.id)
            .join(RequestLine, LineReview.request_line_id == RequestLine.id)
            .join(RequestRevision, RequestLine.revision_id == RequestRevision.id)
            .join(Request, RequestRevision.request_id == Request.id)
            .filter(ApprovalGroup.is_active == True)  # noqa: E712
            .filter(Request.current_revision_id == RequestLine.revision_id)
            .group_by(ApprovalGroup.id, ApprovalGroup.name, ApprovalGroup.sort_order)
            .order_by(ApprovalGroup.sort_order.asc(), ApprovalGroup.name.asc())
        )

        rows = []
        for r in base.all():
            # normalize None -> 0 (sqlite sometimes returns None for empty sums)
            def nz(x): return int(x or 0)

            rows.append({
                "group_id": r.group_id,
                "group_name": r.group_name,
                "request_count": nz(r.request_count),

                "pending_count": nz(r.pending_count),
                "needs_info_count": nz(r.needs_info_count),
                "approved_count": nz(r.approved_count),
                "rejected_count": nz(r.rejected_count),

                "pending_amount": nz(r.pending_amount),
                "needs_info_amount": nz(r.needs_info_amount),
                "approved_amount": nz(r.approved_amount),
                "rejected_amount": nz(r.rejected_amount),
            })

        # Totals row
        totals = {
            "request_count": sum(x["request_count"] for x in rows),
            "pending_count": sum(x["pending_count"] for x in rows),
            "needs_info_count": sum(x["needs_info_count"] for x in rows),
            "approved_count": sum(x["approved_count"] for x in rows),
            "rejected_count": sum(x["rejected_count"] for x in rows),
            "pending_amount": sum(x["pending_amount"] for x in rows),
            "needs_info_amount": sum(x["needs_info_amount"] for x in rows),
            "approved_amount": sum(x["approved_amount"] for x in rows),
            "rejected_amount": sum(x["rejected_amount"] for x in rows),
        }

        return render_template(
            "admin_demo_approval_summary.html",
            rows=rows,
            totals=totals,
        )

    @app.get("/admin/demo/spend-summary")
    def admin_demo_spend_summary():
        from sqlalchemy import func, case
        from .models import Request, RequestRevision, RequestLine, BudgetItemType

        # Finance/admin only
        if (not h.is_admin()) and (not h.is_finance()):
            return "Forbidden", 403

        # Which request statuses to include (override via query param if you want)
        include_statuses = ("SUBMITTED", "NEEDS_REVISION", "APPROVED")

        # spend_type bucket (outer join because budget_item_type_id can be NULL)
        spend_type_expr = func.coalesce(BudgetItemType.spend_type, "Unassigned").label("spend_type")

        q = (
            db.session.query(
                spend_type_expr,
                func.count(RequestLine.id).label("line_count"),
                func.sum(RequestLine.requested_amount).label("total_amount"),
            )
            .select_from(RequestLine)
            .join(RequestRevision, RequestLine.revision_id == RequestRevision.id)
            .join(Request, RequestRevision.request_id == Request.id)
            .outerjoin(BudgetItemType, RequestLine.budget_item_type_id == BudgetItemType.id)
            .filter(Request.current_status.in_(include_statuses))
            .filter(Request.current_revision_id == RequestLine.revision_id)
            .group_by(spend_type_expr)
            .order_by(func.sum(RequestLine.requested_amount).desc())
        )

        rows = []
        for r in q.all():
            total = int(r.total_amount or 0)
            rows.append(
                {
                    "spend_type": r.spend_type,
                    "line_count": int(r.line_count or 0),
                    "total_amount": total,
                }
            )

        grand_total = sum(x["total_amount"] for x in rows)
        max_total = max([x["total_amount"] for x in rows], default=0)

        return render_template(
            "admin_demo_spend_summary.html",
            rows=rows,
            grand_total=grand_total,
            max_total=max_total,
            include_statuses=list(include_statuses),
        )

    def _require_admin_or_finance():
        if (not h.is_admin()) and (not h.is_finance()):
            abort(403)

    @app.get("/admin/budget-items")
    def admin_budget_items():
        from .models import BudgetItemType, ApprovalGroup

        _require_admin_or_finance()

        q = (request.args.get("q") or "").strip()
        show_inactive = (request.args.get("show_inactive") == "1")

        query = db.session.query(BudgetItemType).join(ApprovalGroup)
        if not show_inactive:
            query = query.filter(BudgetItemType.is_active == True)  # noqa: E712

        if q:
            like = f"%{q}%"
            query = query.filter(
                (BudgetItemType.item_id.ilike(like))
                | (BudgetItemType.item_name.ilike(like))
                | (BudgetItemType.spend_type.ilike(like))
            )

        items = query.order_by(BudgetItemType.item_id.asc()).all()

        return render_template(
            "admin_budget_items.html",
            items=items,
            q=q,
            show_inactive=show_inactive,
        )

    @app.get("/admin/budget-items/new")
    def admin_budget_items_new():
        from .models import ApprovalGroup
        _require_admin_or_finance()

        groups = (
            db.session.query(ApprovalGroup)
            .filter(ApprovalGroup.is_active == True)  # noqa: E712
            .order_by(ApprovalGroup.sort_order.asc(), ApprovalGroup.name.asc())
            .all()
        )
        return render_template("admin_budget_item_form.html", item=None, groups=groups)

    @app.post("/admin/budget-items/new")
    def admin_budget_items_new_post():
        from .models import BudgetItemType, ApprovalGroup
        _require_admin_or_finance()

        item_id = (request.form.get("item_id") or "").strip()
        item_name = (request.form.get("item_name") or "").strip()
        item_description = (request.form.get("item_description") or "").strip() or None
        spend_type = (request.form.get("spend_type") or "").strip()
        spend_group = (request.form.get("spend_group") or "").strip() or None
        approval_group_id = request.form.get("approval_group_id")
        is_active = (request.form.get("is_active") == "1")

        if not item_id or not item_name or not spend_type or not approval_group_id:
            return "Missing required fields.", 400

        if db.session.query(BudgetItemType).filter(BudgetItemType.item_id == item_id).first():
            return f"item_id already exists: {item_id}", 400

        group = db.session.get(ApprovalGroup, int(approval_group_id))
        if not group or not group.is_active:
            return "Invalid approval group.", 400

        item = BudgetItemType(
            item_id=item_id,
            item_name=item_name,
            item_description=item_description,
            spend_type=spend_type,
            spend_group=spend_group,
            approval_group_id=group.id,
            is_active=is_active,
        )
        db.session.add(item)
        db.session.commit()
        return redirect(url_for("admin_budget_items"))

    @app.get("/admin/budget-items/<int:item_type_id>/edit")
    def admin_budget_items_edit(item_type_id: int):
        from .models import BudgetItemType, ApprovalGroup
        _require_admin_or_finance()

        item = db.session.get(BudgetItemType, item_type_id)
        if not item:
            abort(404)

        groups = (
            db.session.query(ApprovalGroup)
            .filter(ApprovalGroup.is_active == True)  # noqa: E712
            .order_by(ApprovalGroup.sort_order.asc(), ApprovalGroup.name.asc())
            .all()
        )
        return render_template("admin_budget_item_form.html", item=item, groups=groups)

    @app.post("/admin/budget-items/<int:item_type_id>/edit")
    def admin_budget_items_edit_post(item_type_id: int):
        from .models import BudgetItemType, ApprovalGroup
        _require_admin_or_finance()

        item = db.session.get(BudgetItemType, item_type_id)
        if not item:
            abort(404)

        item_id = (request.form.get("item_id") or "").strip()
        item_name = (request.form.get("item_name") or "").strip()
        item_description = (request.form.get("item_description") or "").strip() or None
        spend_type = (request.form.get("spend_type") or "").strip()
        spend_group = (request.form.get("spend_group") or "").strip() or None
        approval_group_id = request.form.get("approval_group_id")
        is_active = (request.form.get("is_active") == "1")

        if not item_id or not item_name or not spend_type or not approval_group_id:
            return "Missing required fields.", 400

        # enforce unique item_id if changed
        existing = (
            db.session.query(BudgetItemType)
            .filter(BudgetItemType.item_id == item_id, BudgetItemType.id != item.id)
            .first()
        )
        if existing:
            return f"item_id already exists: {item_id}", 400

        group = db.session.get(ApprovalGroup, int(approval_group_id))
        if not group or not group.is_active:
            return "Invalid approval group.", 400

        item.item_id = item_id
        item.item_name = item_name
        item.item_description = item_description
        item.spend_type = spend_type
        item.spend_group = spend_group
        item.approval_group_id = group.id
        item.is_active = is_active

        db.session.commit()
        return redirect(url_for("admin_budget_items"))

@app.context_processor
def inject_user_context():
    u = get_active_user()
    roles = active_user_roles()
    ctx = {
        # Canonical names
        "current_user": u,
        "current_user_id": get_active_user_id(),
        "current_user_roles": roles,
        "is_admin": is_admin(),
        "is_finance": is_finance(),

        # Back-compat aliases (delete later)
        "active_user": u,
        "active_user_id": get_active_user_id(),
        "active_user_roles": roles,
    }
    return ctx

