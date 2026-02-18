"""
Approval workflow routes blueprint - line-by-line review for approval groups.
"""
from flask import Blueprint

# Create the blueprint
approvals_bp = Blueprint("approvals", __name__)

# Import route modules to register their routes with the blueprint
from . import dashboard
from . import reviews
