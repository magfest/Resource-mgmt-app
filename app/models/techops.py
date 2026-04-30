"""
TechOps-specific models: service types, line details, request details.

These models support the TechOps services workflow (network/phone/radio
channel requests). TechOps uses category routing — each TechOpsServiceType
carries a default approval group, snapshotted onto the line at submit time.
"""
from __future__ import annotations

from datetime import datetime

from app import db


class TechOpsServiceType(db.Model):
    """Catalog of TechOps service types (WIFI, ETHERNET, BANDWIDTH, PHONE, RADIO_CHANNEL, OTHER)."""
    __tablename__ = "techops_service_types"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False, index=True)
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text, nullable=True)

    default_approval_group_id = db.Column(
        db.Integer,
        db.ForeignKey("approval_groups.id", name="fk_techops_service_types_default_approval_group_id"),
        nullable=False,
        index=True,
    )

    is_active = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.Integer, nullable=True, default=None)

    # When set, the New Request form renders a quantity input under this
    # service with this label as its caption (e.g. "Number of drops"). When
    # NULL the quantity field is hidden — meaningful for services where qty
    # has no requester-side semantics (WiFi coverage, bandwidth, generic
    # consultation).
    quantity_label = db.Column(db.String(64), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_by_user_id = db.Column(db.String(64), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by_user_id = db.Column(db.String(64), nullable=True)

    default_approval_group = db.relationship("ApprovalGroup", foreign_keys=[default_approval_group_id])


class TechOpsLineDetail(db.Model):
    """TechOps-specific line details: one row per WorkLine in a TechOps request."""
    __tablename__ = "techops_line_details"

    work_line_id = db.Column(
        db.Integer,
        db.ForeignKey("work_lines.id", name="fk_techops_line_details_work_line_id"),
        primary_key=True,
    )

    service_type_id = db.Column(
        db.Integer,
        db.ForeignKey("techops_service_types.id", name="fk_techops_line_details_service_type_id"),
        nullable=False,
        index=True,
    )

    description = db.Column(db.Text, nullable=True)

    # Null = boolean/yes-no semantics (most TechOps services are inherently 1)
    quantity = db.Column(db.Integer, nullable=True)

    # Service-specific extras (e.g. {"external_callable": true} for PHONE)
    config = db.Column(db.JSON, nullable=True)

    # Snapshot of routing at submission/review time
    routed_approval_group_id = db.Column(
        db.Integer,
        db.ForeignKey("approval_groups.id", name="fk_techops_line_details_routed_approval_group_id"),
        nullable=True,
        index=True,
    )

    work_line = db.relationship("WorkLine", backref=db.backref("techops_detail", uselist=False, cascade="all, delete-orphan"))
    service_type = db.relationship("TechOpsServiceType")
    routed_approval_group = db.relationship("ApprovalGroup", foreign_keys=[routed_approval_group_id])

    __table_args__ = (
        db.Index("ix_techops_line_details_approval_routing", "routed_approval_group_id", "service_type_id"),
    )


class TechOpsRequestDetail(db.Model):
    """TechOps-specific request-level details: one row per WorkItem in a TechOps request."""
    __tablename__ = "techops_request_details"

    work_item_id = db.Column(
        db.Integer,
        db.ForeignKey("work_items.id", name="fk_techops_request_details_work_item_id"),
        primary_key=True,
    )

    # Asked per-request because submitter is not always the right point of contact
    primary_contact_name = db.Column(db.String(256), nullable=False)
    primary_contact_email = db.Column(db.String(256), nullable=False)

    # True when the requester affirmed their department needs no TechOps services
    # this event. Submit synthesizes a TECHOPS_GEN-routed OTHER line so the
    # affirmation goes through normal review (admins verify the department
    # actually thought it through).
    no_services_needed = db.Column(db.Boolean, nullable=False, default=False)

    additional_notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_by_user_id = db.Column(db.String(64), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by_user_id = db.Column(db.String(64), nullable=True)

    work_item = db.relationship("WorkItem", backref=db.backref("techops_detail", uselist=False, cascade="all, delete-orphan"))
