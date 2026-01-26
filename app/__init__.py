from __future__ import annotations

import os
from datetime import datetime, timedelta

from flask import Flask, session, render_template, abort, request, redirect, url_for
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()


def create_app() -> Flask:
    app = Flask(__name__, instance_relative_config=True)

    os.makedirs(app.instance_path, exist_ok=True)

    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-secret-key")

    db_path = os.path.join(app.instance_path, "magfest_budget.sqlite3")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", f"sqlite:///{db_path}"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    migrate.init_app(app, db)

    # Import models so migrations can detect them
    from . import models  # noqa: F401

    # -----------------------------
    # Helpers (demo auth + scoping)
    # -----------------------------

    def ensure_demo_budget_data():
        from .models import ApprovalGroup, BudgetItemType

        any_group = db.session.query(ApprovalGroup).first()

        if not any_group:
            groups = [
                ("TECH", "Tech", True, 10),
                ("HOTEL", "Hotel", True, 20),
                ("OTHER", "Other", True, 30),
            ]
            for code, name, active, sort in groups:
                db.session.add(
                    ApprovalGroup(code=code, name=name, is_active=active, sort_order=sort)
                )
            db.session.flush()

        any_type = db.session.query(BudgetItemType).first()
        if any_type:
            db.session.commit()
            return

        groups_by_code = {g.code: g for g in db.session.query(ApprovalGroup).all()}

        demo_types = [
            ("ITM-TECH-001", "Radios (Rental)", "Divvy", "TECH", "Handheld radios rental for operations"),
            ("ITM-TECH-002", "iPads / Laptops (Rental)", "Divvy", "TECH", "Hartford rental computing devices"),
            ("ITM-HOTEL-001", "Ethernet Drops", "Hotel Fee", "HOTEL", "Hardline internet drops from venue"),
            ("ITM-OTH-001", "Office Supplies", "Bank", "OTHER", "General office supplies"),
        ]

        for item_id, name, spend, group_code, desc in demo_types:
            g = groups_by_code[group_code]
            db.session.add(
                BudgetItemType(
                    item_id=item_id,
                    item_name=name,
                    item_description=desc,
                    spend_type=spend,
                    approval_group_id=g.id,
                    is_active=True,
                )
            )

        db.session.commit()

    def ensure_demo_users():
        from .models import User, UserRole, ApprovalGroup

        ensure_demo_budget_data()
        ensure_demo_org_data()

        any_user = db.session.query(User).first()
        if any_user:
            return

        groups_by_code = {g.code: g for g in db.session.query(ApprovalGroup).all()}
        tech_group_id = groups_by_code["TECH"].id
        hotel_group_id = groups_by_code["HOTEL"].id

        demo_users = [
            ("dev:requester", "Requester (Demo)", True, [("REQUESTER", None)]),
            ("dev:tech_approver", "Tech Approver (Demo)", True, [("APPROVER", tech_group_id)]),
            ("dev:hotel_approver", "Hotel Approver (Demo)", True, [("APPROVER", hotel_group_id)]),
            ("dev:admin", "Admin (Demo)", True, [("ADMIN", None)]),
            ("dev:finance", "Finance (Demo)", True, [("FINANCE", None)]),
            ("dev:alex", "Alex (Demo)", True, [("REQUESTER", None)]),
        ]

        for user_id, display_name, is_active, roles in demo_users:
            u = User(id=user_id, display_name=display_name, is_active=is_active)
            db.session.add(u)
            db.session.flush()

            for role_code, group_id in roles:
                db.session.add(
                    UserRole(
                        user_id=u.id,
                        role_code=role_code,
                        approval_group_id=group_id
                    )
                )

        db.session.commit()

    def ensure_demo_org_data():
        # Requires Department + EventCycle models to exist in models.py
        from .models import Department, EventCycle

        # Seed EventCycles if empty
        any_cycle = db.session.query(EventCycle).first()
        if not any_cycle:
            cycles = [
                # code, name, active, default, sort
                ("SMF2026", "Super MAGFest 2026", True, True, 10),
                ("SMF2027", "Super MAGFest 2027", True, False, 20),
            ]
            for code, name, active, is_default, sort in cycles:
                db.session.add(
                    EventCycle(
                        code=code,
                        name=name,
                        is_active=active,
                        is_default=is_default,
                        sort_order=sort,
                    )
                )
            db.session.flush()

        # Seed Departments if empty
        any_dept = db.session.query(Department).first()
        if not any_dept:
            depts = [
                # code, name, active, sort
                ("TECHOPS", "TechOps", True, 10),
                ("HOTELS", "Hotels", True, 20),
                ("BROADCAST", "BroadcastOps", True, 30),
                ("FESTOPS", "FestOps", True, 40),
                ("SUPPLY", "SupplyOps", True, 50),
                ("REG", "Registration", True, 60),
                ("PANEL", "Panels", True, 70),
                ("GUEST", "Guests", True, 80),
                ("ARCADE", "Arcades", True, 90),
            ]
            for code, name, active, sort in depts:
                db.session.add(
                    Department(
                        code=code,
                        name=name,
                        is_active=active,
                        sort_order=sort,
                    )
                )

        db.session.commit()

    def get_active_user_id() -> str:
        return session.get("active_user_id") or "dev:alex"

    def get_active_user():
        from .models import User
        return db.session.get(User, get_active_user_id())

    def active_user_roles() -> list[str]:
        from .models import UserRole
        uid = get_active_user_id()
        rows = db.session.query(UserRole.role_code).filter(UserRole.user_id == uid).all()
        return [r[0] for r in rows]

    def has_role(role_code: str) -> bool:
        return role_code in set(active_user_roles())

    def is_admin() -> bool:
        return has_role("ADMIN")

    def is_finance() -> bool:
        return has_role("FINANCE")

    def active_user_approval_group_ids() -> set[int]:
        from .models import UserRole
        uid = get_active_user_id()
        rows = (
            db.session.query(UserRole.approval_group_id)
            .filter(UserRole.user_id == uid)
            .filter(UserRole.role_code == "APPROVER")
            .filter(UserRole.approval_group_id.isnot(None))
            .all()
        )
        return {int(r[0]) for r in rows if r[0] is not None}

    def can_review_group(approval_group_id: int) -> bool:
        return is_admin() or (approval_group_id in active_user_approval_group_ids())

    @app.context_processor
    def inject_active_user():
        u = get_active_user()
        roles = active_user_roles()
        return {
            "active_user": u,
            "active_user_id": get_active_user_id(),
            "active_user_roles": roles,
            "is_admin": is_admin(),
            "is_finance": is_finance(),
        }

    def _recalculate_request_status_from_lines(revision):
        """
        Derive request.current_status from line review statuses for a revision.

        Rules:
        - NEEDS_REVISION is request-level only; do not overwrite it here.
        - Do not auto-promote to APPROVED. Final approval is explicit via /requests/<id>/approve.
        - Do not auto-downgrade APPROVED.
        - Otherwise, request stays SUBMITTED while any line review exists (regardless of mix).
        """
        from .models import LineReview, Request

        reviews = (
            db.session.query(LineReview.status)
            .join(LineReview.request_line)
            .filter(LineReview.request_line.has(revision_id=revision.id))
            .all()
        )

        if not reviews:
            return

        req = db.session.get(Request, revision.request_id)
        if not req:
            return

        cur = (req.current_status or "").upper()
        if cur == "NEEDS_REVISION":
            return
        if cur == "APPROVED":
            return

        # Under review state; line status detail is expressed in the UI
        req.current_status = "SUBMITTED"

    from .routes import register_routes, RouteHelpers

    register_routes(
        app,
        RouteHelpers(
            ensure_demo_users=ensure_demo_users,
            ensure_demo_budget_data=ensure_demo_budget_data,
            ensure_demo_org_data=ensure_demo_org_data,
            get_active_user_id=get_active_user_id,
            get_active_user=get_active_user,
            active_user_roles=active_user_roles,
            is_admin=is_admin,
            is_finance=is_finance,
            active_user_approval_group_ids=active_user_approval_group_ids,
            can_review_group=can_review_group,
            recalc_request_status_from_lines=_recalculate_request_status_from_lines,
        ),
    )

    return app
