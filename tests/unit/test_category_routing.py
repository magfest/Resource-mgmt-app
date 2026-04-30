"""
Tests for CategoryRoutingStrategy — covers both the SUPPLY (item → category)
and TECHOPS (service_type → default_approval_group) dispatch paths, plus
the None-return when no recognized detail is attached.
"""
from __future__ import annotations

import pytest

from app import db
from app.models import (
    ApprovalGroup,
    Department,
    EventCycle,
    SupplyCategory,
    SupplyItem,
    SupplyOrderLineDetail,
    TechOpsLineDetail,
    TechOpsServiceType,
    User,
    WorkItem,
    WorkLine,
    WorkPortfolio,
    WorkType,
    WorkTypeConfig,
    REQUEST_KIND_PRIMARY,
    ROUTING_STRATEGY_CATEGORY,
    WORK_ITEM_STATUS_DRAFT,
    WORK_LINE_STATUS_PENDING,
)
from app.routing.category import CategoryRoutingStrategy


def _make_work_line(work_type_code: str, line_number: int = 1):
    """Build the chain WorkType → Portfolio → WorkItem → WorkLine for tests
    that need a real line to attach a detail row to."""
    user = User(
        id=f"test:user_{work_type_code.lower()}",
        email=f"{work_type_code.lower()}@test.local",
        display_name="Test User", is_active=True,
    )
    cycle = EventCycle(
        code=f"TST_{work_type_code}", name=f"Test {work_type_code}",
        is_active=True, is_default=False, sort_order=1,
    )
    dept = Department(
        code=f"DEPT_{work_type_code}", name=f"Test Dept {work_type_code}",
        is_active=True,
    )
    db.session.add_all([user, cycle, dept])

    wt = WorkType(code=work_type_code, name=work_type_code, is_active=True)
    db.session.add(wt)
    db.session.flush()

    wtc = WorkTypeConfig(
        work_type_id=wt.id, url_slug=work_type_code.lower(),
        public_id_prefix=work_type_code[:3], line_detail_type=work_type_code.lower(),
        routing_strategy=ROUTING_STRATEGY_CATEGORY,
        uses_dispatch=False, has_admin_final=False,
    )
    db.session.add(wtc)

    portfolio = WorkPortfolio(
        work_type_id=wt.id, event_cycle_id=cycle.id,
        department_id=dept.id, created_by_user_id=user.id,
    )
    db.session.add(portfolio)
    db.session.flush()

    work_item = WorkItem(
        portfolio_id=portfolio.id, request_kind=REQUEST_KIND_PRIMARY,
        status=WORK_ITEM_STATUS_DRAFT,
        public_id=f"TST_{work_type_code}-DEPT-{line_number}",
        created_by_user_id=user.id,
    )
    db.session.add(work_item)
    db.session.flush()

    line = WorkLine(
        work_item_id=work_item.id, line_number=line_number,
        status=WORK_LINE_STATUS_PENDING,
    )
    db.session.add(line)
    db.session.commit()

    return wt, line


def test_techops_line_routes_to_service_type_default_group(app):
    """A TechOps line returns its service_type's default_approval_group."""
    wt, line = _make_work_line("TECHOPS")

    net_group = ApprovalGroup(
        work_type_id=wt.id, code="TECHOPS_NET",
        name="TechOps Networking", is_active=True,
    )
    db.session.add(net_group)
    db.session.flush()

    wifi = TechOpsServiceType(
        code="WIFI", name="WiFi",
        default_approval_group_id=net_group.id, is_active=True,
    )
    db.session.add(wifi)
    db.session.flush()

    db.session.add(TechOpsLineDetail(
        work_line_id=line.id,
        service_type_id=wifi.id,
    ))
    db.session.commit()

    strategy = CategoryRoutingStrategy()
    result = strategy.get_approval_group(line)

    assert result is not None
    assert result.code == "TECHOPS_NET"


def test_supply_line_routes_to_item_category_group(app):
    """A Supply line returns its item's category.approval_group (regression
    check that the file rename and dispatch extension didn't break SUPPLY)."""
    wt, line = _make_work_line("SUPPLY")

    tech_group = ApprovalGroup(
        work_type_id=wt.id, code="TECH",
        name="Tech Team", is_active=True,
    )
    db.session.add(tech_group)
    db.session.flush()

    category = SupplyCategory(
        code="TECH_GEAR", name="Tech Gear",
        approval_group_id=tech_group.id, is_active=True,
    )
    db.session.add(category)
    db.session.flush()

    item = SupplyItem(
        category_id=category.id, item_name="HDMI Cable",
        unit="each", is_active=True,
    )
    db.session.add(item)
    db.session.flush()

    db.session.add(SupplyOrderLineDetail(
        work_line_id=line.id,
        item_id=item.id,
        quantity_requested=2,
    ))
    db.session.commit()

    strategy = CategoryRoutingStrategy()
    result = strategy.get_approval_group(line)

    assert result is not None
    assert result.code == "TECH"


def test_line_without_recognized_detail_returns_none(app):
    """A line with no supply_detail or techops_detail attached returns None."""
    wt, line = _make_work_line("TECHOPS")

    strategy = CategoryRoutingStrategy()
    result = strategy.get_approval_group(line)

    assert result is None
