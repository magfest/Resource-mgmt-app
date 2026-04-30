"""
Category-based routing strategy.

Used by any worktype that routes lines via a category-shaped catalog row
that carries a default approval group:
- SUPPLY: line.supply_detail.item.category.approval_group
- TECHOPS: line.techops_detail.service_type.default_approval_group

When a new category-routed worktype lands, add a branch here pointing to
its detail table's relationship path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from app.routing import RoutingStrategy

if TYPE_CHECKING:
    from app.models import ApprovalGroup, WorkLine


class CategoryRoutingStrategy(RoutingStrategy):
    """Routes lines through their category's approval group, dispatching on
    which per-worktype detail table is attached to the line."""

    def get_approval_group(self, line: "WorkLine") -> Optional["ApprovalGroup"]:
        if line.supply_detail and line.supply_detail.item:
            return line.supply_detail.item.category.approval_group

        if line.techops_detail and line.techops_detail.service_type:
            return line.techops_detail.service_type.default_approval_group

        return None
