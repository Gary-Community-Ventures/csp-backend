"""
Webhook endpoints for third-party integrations.
"""

from flask import Blueprint

bp = Blueprint("webhooks", __name__)

# Import webhook handlers to register routes
from app.routes.webhooks import clerk  # noqa: E402, F401
