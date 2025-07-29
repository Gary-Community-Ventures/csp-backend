from flask import redirect, url_for
from flask_admin import Admin, AdminIndexView
from flask_admin.contrib.sqla import ModelView

from .auth.decorators import (
    _authenticate_request,
    _clear_user_context,
    _set_user_context,
    ClerkUserType,
)
from .extensions import db
from .models import Family, PaymentRequest, Provider


class ClerkAuthMixin:
    def is_accessible(self):
        try:
            # Use NONE user type to only check for a valid session
            request_state = _authenticate_request(user_type=ClerkUserType.NONE)
            if not request_state.is_signed_in:
                _clear_user_context()
                return False

            claims = request_state.payload
            # Roles are expected to be in the user's public metadata in the JWT
            user_roles = claims.get("public_metadata", {}).get("roles", [])

            if "admin" not in user_roles:
                _clear_user_context()
                return False

            # Set user context for the duration of the request
            _set_user_context(request_state)
            return True
        except (Exception):
            _clear_user_context()
            return False

    def _handle_view(self, name, **kwargs):
        if not self.is_accessible():
            return redirect(url_for("main.index"))


class AdminHomeView(ClerkAuthMixin, AdminIndexView):
    pass


class AdminModelView(ClerkAuthMixin, ModelView):
    pass


def init_admin(app):
    admin_index_view = AdminHomeView(
        name="Dashboard", url="/admin", endpoint="admin"
    )
    admin = Admin(
        app, name="CSP Admin", template_mode="bootstrap3", index_view=admin_index_view
    )

    admin.add_view(AdminModelView(Family, db.session, name="Families", endpoint="admin_family", url="family"))
    admin.add_view(AdminModelView(Provider, db.session, name="Providers", endpoint="admin_provider", url="provider"))
    admin.add_view(AdminModelView(PaymentRequest, db.session, name="Payment Requests", endpoint="admin_payment_request", url="payment-request"))
