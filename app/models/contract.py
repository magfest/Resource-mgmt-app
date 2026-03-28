"""
Contract-specific models: contract types and line details.

These models support the contract management workflow (future feature).
"""
from __future__ import annotations

from datetime import datetime

from app import db


class ContractType(db.Model):
    """Contract types for categorization and routing."""
    __tablename__ = "contract_types"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False, index=True)
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text, nullable=True)

    approval_group_id = db.Column(
        db.Integer,
        db.ForeignKey("approval_groups.id", name="fk_contract_types_approval_group_id"),
        nullable=True,
        index=True,
    )

    is_active = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.Integer, nullable=True, default=None)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_by_user_id = db.Column(db.String(64), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by_user_id = db.Column(db.String(64), nullable=True)

    approval_group = db.relationship("ApprovalGroup", foreign_keys=[approval_group_id])


class ContractLineDetail(db.Model):
    """Contract-specific line details."""
    __tablename__ = "contract_line_details"

    work_line_id = db.Column(
        db.Integer,
        db.ForeignKey("work_lines.id", name="fk_contract_line_details_work_line_id"),
        primary_key=True,
    )

    contract_type_id = db.Column(
        db.Integer,
        db.ForeignKey("contract_types.id", name="fk_contract_line_details_contract_type_id"),
        nullable=False,
        index=True,
    )

    # Snapshot of routing at submission/review time
    routed_approval_group_id = db.Column(
        db.Integer,
        db.ForeignKey("approval_groups.id", name="fk_contract_line_details_routed_approval_group_id"),
        nullable=True,
        index=True,
    )

    vendor_name = db.Column(db.String(256), nullable=False)
    vendor_contact = db.Column(db.String(256), nullable=True)
    contract_amount_cents = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    terms_summary = db.Column(db.Text, nullable=True)
    description = db.Column(db.Text, nullable=True)

    work_line = db.relationship("WorkLine", backref=db.backref("contract_detail", uselist=False, cascade="all, delete-orphan"))
    contract_type = db.relationship("ContractType")
    routed_approval_group = db.relationship("ApprovalGroup", foreign_keys=[routed_approval_group_id])

    __table_args__ = (
        db.Index("ix_contract_line_details_approval_routing", "routed_approval_group_id", "contract_type_id"),
    )
