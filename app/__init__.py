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

    def ensure_demo_reference_data():
        """Seed all reference/lookup tables needed for the budget workflow."""
        from .models import (
            ApprovalGroup,
            WorkType,
            SpendType,
            FrequencyOption,
            ConfidenceLevel,
            PriorityLevel,
        )

        # ApprovalGroups
        if not db.session.query(ApprovalGroup).first():
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

        # WorkTypes
        if not db.session.query(WorkType).first():
            work_types = [
                ("BUDGET", "Budget Request", True, 10),
            ]
            for code, name, active, sort in work_types:
                db.session.add(
                    WorkType(code=code, name=name, is_active=active, sort_order=sort)
                )
            db.session.flush()

        # SpendTypes
        if not db.session.query(SpendType).first():
            spend_types = [
                ("DIVVY", "Divvy", "Corporate card purchases", True, 10),
                ("BANK", "Bank", "Direct bank transfers / checks", True, 20),
                ("HOTEL_FEE", "Hotel Fee", "Fees paid directly to hotel", True, 30),
            ]
            for code, name, desc, active, sort in spend_types:
                db.session.add(
                    SpendType(code=code, name=name, description=desc, is_active=active, sort_order=sort)
                )
            db.session.flush()

        # FrequencyOptions
        if not db.session.query(FrequencyOption).first():
            frequencies = [
                ("ONE_TIME", "One Time", "Single purchase", True, 10),
                ("RECURRING", "Recurring", "Recurring expense across events", True, 20),
            ]
            for code, name, desc, active, sort in frequencies:
                db.session.add(
                    FrequencyOption(code=code, name=name, description=desc, is_active=active, sort_order=sort)
                )
            db.session.flush()

        # ConfidenceLevels
        if not db.session.query(ConfidenceLevel).first():
            confidence_levels = [
                ("CONFIRMED", "Confirmed", "Price is confirmed/quoted", True, 10),
                ("ESTIMATED", "Estimated", "Price is estimated", True, 20),
                ("PLACEHOLDER", "Placeholder", "Rough placeholder amount", True, 30),
            ]
            for code, name, desc, active, sort in confidence_levels:
                db.session.add(
                    ConfidenceLevel(code=code, name=name, description=desc, is_active=active, sort_order=sort)
                )
            db.session.flush()

        # PriorityLevels
        if not db.session.query(PriorityLevel).first():
            priority_levels = [
                ("CRITICAL", "Critical", "Essential for event operations", True, 10),
                ("HIGH", "High", "Important but event can proceed without", True, 20),
                ("MEDIUM", "Medium", "Nice to have", True, 30),
                ("LOW", "Low", "Optional / stretch goal", True, 40),
            ]
            for code, name, desc, active, sort in priority_levels:
                db.session.add(
                    PriorityLevel(code=code, name=name, description=desc, is_active=active, sort_order=sort)
                )
            db.session.flush()

        db.session.commit()

    def ensure_demo_expense_accounts():
        """Seed expense accounts (replaces old BudgetItemType)."""
        from .models import (
            ExpenseAccount,
            ApprovalGroup,
            SpendType,
            SPEND_TYPE_MODE_SINGLE_LOCKED,
            SPEND_TYPE_MODE_ALLOW_LIST,
        )

        if db.session.query(ExpenseAccount).first():
            return

        groups_by_code = {g.code: g for g in db.session.query(ApprovalGroup).all()}
        spend_by_code = {s.code: s for s in db.session.query(SpendType).all()}

        # Demo expense accounts
        demo_accounts = [
            # code, name, desc, approval_group, default_spend_type, spend_mode, is_fixed, unit_price_cents
            ("RADIO_RENTAL", "Radios (Rental)", "Handheld radios rental for operations",
             "TECH", "DIVVY", SPEND_TYPE_MODE_SINGLE_LOCKED, True, 5000),
            ("LAPTOP_RENTAL", "iPads / Laptops (Rental)", "Hartford rental computing devices",
             "TECH", "DIVVY", SPEND_TYPE_MODE_SINGLE_LOCKED, True, 15000),
            ("ETHERNET_DROPS", "Ethernet Drops", "Hardline internet drops from venue",
             "HOTEL", "HOTEL_FEE", SPEND_TYPE_MODE_SINGLE_LOCKED, True, 7500),
            ("OFFICE_SUPPLIES", "Office Supplies", "General office supplies",
             "OTHER", "BANK", SPEND_TYPE_MODE_ALLOW_LIST, False, None),
        ]

        for code, name, desc, group_code, spend_code, spend_mode, is_fixed, unit_price in demo_accounts:
            group = groups_by_code.get(group_code)
            spend_type = spend_by_code.get(spend_code)

            db.session.add(
                ExpenseAccount(
                    code=code,
                    name=name,
                    description=desc,
                    approval_group_id=group.id if group else None,
                    default_spend_type_id=spend_type.id if spend_type else None,
                    spend_type_mode=spend_mode,
                    is_fixed_cost=is_fixed,
                    default_unit_price_cents=unit_price,
                    unit_price_locked=is_fixed,
                    is_active=True,
                )
            )

        db.session.commit()

    def ensure_demo_budget_data():
        """Combined seeder for all budget reference data."""
        ensure_demo_reference_data()
        ensure_demo_expense_accounts()

    def ensure_demo_users():
        from .models import User, UserRole, ApprovalGroup, ROLE_SUPER_ADMIN, ROLE_APPROVER

        ensure_demo_budget_data()
        ensure_demo_org_data()

        any_user = db.session.query(User).first()
        if any_user:
            return

        groups_by_code = {g.code: g for g in db.session.query(ApprovalGroup).all()}
        tech = groups_by_code.get("TECH")
        hotel = groups_by_code.get("HOTEL")
        if not tech or not hotel:
            raise RuntimeError("Demo ApprovalGroups missing: expected TECH and HOTEL to exist.")
        tech_group_id = tech.id
        hotel_group_id = hotel.id

        # role format: (role_code, work_type_id, approval_group_id)
        demo_users = [
            # Plain users (no special role)
            ("dev:pat", "pat@dev.local", "dev:pat", "Pat (No Dept)", True, []),

            # Arcades
            ("dev:alex", "alex@dev.local", "dev:alex", "Alex (Arcades DH)", True, []),
            ("dev:riley", "riley@dev.local", "dev:riley", "Riley (Arcades Editor)", True, []),
            ("dev:sam", "sam@dev.local", "dev:sam", "Sam (Arcades Viewer)", True, []),

            # Guests
            ("dev:jordan", "jordan@dev.local", "dev:jordan", "Jordan (Guests DH)", True, []),
            ("dev:casey", "casey@dev.local", "dev:casey", "Casey (Guests Editor)", True, []),

            # Mixed membership
            ("dev:morgan", "morgan@dev.local", "dev:morgan", "Morgan (Arcades View / Guests Edit)", True, []),

            # Approvers (scoped to approval group)
            ("dev:tech_approver", "tech.approver@dev.local", "dev:tech_approver", "Tech Approver (Demo)", True,
             [(ROLE_APPROVER, None, tech_group_id)]),
            ("dev:hotel_approver", "hotel.approver@dev.local", "dev:hotel_approver", "Hotel Approver (Demo)", True,
             [(ROLE_APPROVER, None, hotel_group_id)]),

            # Elevated
            ("dev:admin", "admin@dev.local", "dev:admin", "Admin (Demo)", True, [(ROLE_SUPER_ADMIN, None, None)]),
        ]

        for user_id, email, auth_subject, display_name, is_active, roles in demo_users:
            u = db.session.get(User, user_id)
            if not u:
                u = User(id=user_id)
                db.session.add(u)

            u.email = email
            u.auth_subject = auth_subject
            u.display_name = display_name
            u.is_active = is_active

            # roles: easiest is clear then recreate for demo users
            db.session.query(UserRole).filter_by(user_id=user_id).delete()
            for role_code, work_type_id, approval_group_id in roles:
                db.session.add(UserRole(
                    user_id=user_id,
                    role_code=role_code,
                    work_type_id=work_type_id,
                    approval_group_id=approval_group_id,
                ))

        db.session.commit()
        ensure_demo_department_memberships()

    def ensure_demo_org_data():
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

    def ensure_demo_department_memberships():
        from .models import (
            User,
            Department,
            EventCycle,
            DepartmentMembership,
        )

        # Ensure org data exists (departments + cycles)
        ensure_demo_org_data()

        # --- fetch the event cycle we want to test ---
        cycle = (
            db.session.query(EventCycle)
            .filter(EventCycle.code == "SMF2026")
            .one()
        )

        # --- fetch departments we want to test ---
        dept_by_code = {
            d.code: d
            for d in db.session.query(Department)
            .filter(Department.code.in_(["ARCADE", "GUEST"]))
            .all()
        }

        missing = [c for c in ["ARCADE", "GUEST"] if c not in dept_by_code]
        if missing:
            raise RuntimeError(f"Missing demo departments: {missing}")

        def upsert_membership(
                *, user_id: str, dept_code: str,
                can_view: bool, can_edit: bool, is_department_head: bool
        ):
            dept = dept_by_code[dept_code]

            row = (
                db.session.query(DepartmentMembership)
                .filter(DepartmentMembership.user_id == user_id)
                .filter(DepartmentMembership.department_id == dept.id)
                .filter(DepartmentMembership.event_cycle_id == cycle.id)
                .one_or_none()
            )

            if not row:
                row = DepartmentMembership(
                    user_id=user_id,
                    department_id=dept.id,
                    event_cycle_id=cycle.id,
                )
                db.session.add(row)

            row.can_view = bool(can_view)
            row.can_edit = bool(can_edit)
            row.is_department_head = bool(is_department_head)

        # --- membership plan (truth table) ---
        membership_plan = [
            # Arcades
            ("dev:alex", "ARCADE", True, True, True),  # DH
            ("dev:riley", "ARCADE", True, True, False),  # editor
            ("dev:sam", "ARCADE", True, False, False),  # viewer

            # Guests
            ("dev:jordan", "GUEST", True, True, True),  # DH
            ("dev:casey", "GUEST", True, True, False),  # editor

            # Mixed: Arcades view + Guests edit
            ("dev:morgan", "ARCADE", True, False, False),
            ("dev:morgan", "GUEST", True, True, False),
        ]

        # Validate users exist (fail loudly if demo users aren't seeded)
        user_ids = [u[0] for u in membership_plan]
        found = {u.id for u in db.session.query(User.id).filter(User.id.in_(user_ids)).all()}
        missing_users = [uid for uid in user_ids if uid not in found]
        if missing_users:
            raise RuntimeError(f"Missing demo users for memberships: {missing_users}")

        # Apply plan
        for user_id, dept_code, can_view, can_edit, is_dh in membership_plan:
            upsert_membership(
                user_id=user_id,
                dept_code=dept_code,
                can_view=can_view,
                can_edit=can_edit,
                is_department_head=is_dh,
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
        from .models import ROLE_SUPER_ADMIN, ROLE_WORKTYPE_ADMIN
        roles = set(active_user_roles())
        return ROLE_SUPER_ADMIN in roles or ROLE_WORKTYPE_ADMIN in roles

    def is_finance() -> bool:
        # Finance role removed in new schema; super admin covers this
        return is_admin()

    def active_user_approval_group_ids() -> set[int]:
        from .models import UserRole, ROLE_APPROVER
        uid = get_active_user_id()
        rows = (
            db.session.query(UserRole.approval_group_id)
            .filter(UserRole.user_id == uid)
            .filter(UserRole.role_code == ROLE_APPROVER)
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

    # Placeholder for legacy route helper - will be removed when routes are updated
    def _recalculate_work_item_status(work_item):
        """
        Placeholder for work item status recalculation.
        Will be implemented when routes are updated to use new models.
        """
        pass

    from .routes import register_all_routes, RouteHelpers

    register_all_routes(
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
            recalc_request_status_from_lines=_recalculate_work_item_status,
        ),
    )

    return app