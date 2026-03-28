"""
Integration tests for admin features: QuickBooks class fields, date visibility.
"""
from datetime import date

from app import db
from app.models import (
    User,
    UserRole,
    Department,
    Division,
    EventCycle,
    ROLE_SUPER_ADMIN,
)


def _seed_admin(app):
    """Seed a super admin user and basic org data."""
    with app.app_context():
        admin = User(
            id="test:admin", email="admin@test.local",
            display_name="Test Admin", is_active=True,
        )
        db.session.add(admin)
        db.session.flush()

        db.session.add(UserRole(
            user_id=admin.id, role_code=ROLE_SUPER_ADMIN,
        ))

        cycle = EventCycle(
            code="TST2026", name="Test Event 2026",
            is_active=True, is_default=True, sort_order=1,
            event_start_date=date(2026, 6, 1),
            event_end_date=date(2026, 6, 5),
        )
        db.session.add(cycle)

        div = Division(
            code="TESTDIV", name="Test Division", is_active=True,
        )
        db.session.add(div)

        dept = Department(
            code="TESTDEPT", name="Test Department",
            is_active=True, division_id=None,
        )
        db.session.add(dept)

        db.session.commit()


class TestQuickBooksClassFields:
    """Tests for qb_class field persistence on org models."""

    def test_event_cycle_qb_class_persists(self, app, db_session):
        """qb_class should be saved and loaded on EventCycle."""
        _seed_admin(app)

        cycle = EventCycle.query.filter_by(code="TST2026").one()
        assert cycle.qb_class is None

        cycle.qb_class = "Super_MAGFest"
        db_session.commit()

        reloaded = EventCycle.query.filter_by(code="TST2026").one()
        assert reloaded.qb_class == "Super_MAGFest"

    def test_division_qb_class_persists(self, app, db_session):
        """qb_class should be saved and loaded on Division."""
        _seed_admin(app)

        div = Division.query.filter_by(code="TESTDIV").one()
        div.qb_class = "Gaming"
        db_session.commit()

        reloaded = Division.query.filter_by(code="TESTDIV").one()
        assert reloaded.qb_class == "Gaming"

    def test_department_qb_class_persists(self, app, db_session):
        """qb_class should be saved and loaded on Department."""
        _seed_admin(app)

        dept = Department.query.filter_by(code="TESTDEPT").one()
        dept.qb_class = "Staff Services"
        db_session.commit()

        reloaded = Department.query.filter_by(code="TESTDEPT").one()
        assert reloaded.qb_class == "Staff Services"

    def test_multiple_entities_share_qb_class(self, app, db_session):
        """Multiple entities should be able to share the same qb_class value."""
        _seed_admin(app)

        div2 = Division(
            code="TESTDIV2", name="Test Division 2",
            is_active=True, qb_class="Gaming",
        )
        db_session.add(div2)

        div1 = Division.query.filter_by(code="TESTDIV").one()
        div1.qb_class = "Gaming"
        db_session.commit()

        gaming_divs = Division.query.filter_by(qb_class="Gaming").all()
        assert len(gaming_divs) == 2


class TestDatesArePublic:
    """Tests for the dates_are_public toggle on EventCycle."""

    def test_defaults_to_false(self, app, db_session):
        """dates_are_public should default to False."""
        _seed_admin(app)

        cycle = EventCycle.query.filter_by(code="TST2026").one()
        assert cycle.dates_are_public is False

    def test_toggle_persists(self, app, db_session):
        """dates_are_public should be toggleable and persist."""
        _seed_admin(app)

        cycle = EventCycle.query.filter_by(code="TST2026").one()
        cycle.dates_are_public = True
        db_session.commit()

        reloaded = EventCycle.query.filter_by(code="TST2026").one()
        assert reloaded.dates_are_public is True

    def test_dates_still_stored_when_not_public(self, app, db_session):
        """Event dates should be stored regardless of visibility setting."""
        _seed_admin(app)

        cycle = EventCycle.query.filter_by(code="TST2026").one()
        assert cycle.dates_are_public is False
        assert cycle.event_start_date == date(2026, 6, 1)
        assert cycle.event_end_date == date(2026, 6, 5)
