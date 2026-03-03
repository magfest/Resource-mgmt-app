"""
Work items routes package.

Routes are split into logical modules:
- create.py: PRIMARY and SUPPLEMENTARY work item creation
- view.py: Detail view, comments, quick review
- edit.py: Edit form, save, fixed costs, hotel wizard
- actions.py: Submit, checkout, checkin, needs_info

All routes are registered with the work_bp blueprint via decorators.
Importing this package causes all route modules to be imported,
which registers their routes.
"""

# Import common helpers for use by other modules
from .common import get_work_item_by_public_id, calculate_event_nights

# Import all route modules to register their routes with the blueprint
from . import create
from . import view
from . import edit
from . import actions

__all__ = [
    # Common helpers
    "get_work_item_by_public_id",
    "calculate_event_nights",
    # Modules (for explicit imports if needed)
    "create",
    "view",
    "edit",
    "actions",
]
