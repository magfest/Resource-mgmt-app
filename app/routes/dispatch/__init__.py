"""
Dispatch queue blueprint for budget requests.

Provides routes for admins to review and dispatch budget requests
from AWAITING_DISPATCH to the approval queue.
"""
from flask import Blueprint

dispatch_bp = Blueprint("dispatch", __name__, url_prefix="/admin/dispatch")

from . import dashboard  # noqa: E402, F401
