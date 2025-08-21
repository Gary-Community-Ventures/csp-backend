from collections import defaultdict

from flask import current_app, redirect, request
from flask_admin import AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView
from markupsafe import escape


def inject_environment_banner():
    """Inject environment banner variables into the template context"""
    env = current_app.config.get("FLASK_ENV", "production")

    if env == "staging":
        return {
            "env": env,
            "env_name": "Staging",
            "env_class": "bg-yellow-500",
        }
    elif env == "development":
        return {
            "env": env,
            "env_name": "Development",
            "env_class": "bg-blue-500",
        }
    else:
        return {"env": None}


class ClerkAuthMixin:
    """Mixin to add Clerk authentication to Flask-Admin views"""

    def is_accessible(self):
        """Check if current user can access this view"""
        try:
            # Import here to avoid circular imports
            from app.auth.decorators import ClerkUserType, _authenticate_request

            # Try to authenticate the request
            _authenticate_request(ClerkUserType.ADMIN, allow_cookies=True)

            return True

        except Exception as e:
            # Log the error for debugging
            current_app.logger.error(f"Admin authentication error: {e}")
            return False

    def inaccessible_callback(self, name, **kwargs):
        """Redirect to login if user doesn't have access"""
        return redirect(self.get_login_url())

    def get_login_url(self):
        """Generate login URL with proper redirect"""
        return_url = request.url
        frontend_url = current_app.config.get("FRONTEND_DOMAIN")

        return f"{frontend_url}/auth/sign-in?redirect_url={return_url}"


class SecureAdminIndexView(ClerkAuthMixin, AdminIndexView):
    """Secure admin index view that requires Clerk authentication"""

    @expose("/")
    def index(self):
        """Custom admin index page with user info"""
        try:
            from app.auth.decorators import ClerkUserType, _authenticate_request

            request_state = _authenticate_request(ClerkUserType.ADMIN, allow_cookies=True)
            payload_data = request_state.payload.get("data", {})

            if request_state.is_signed_in:
                user_info = {
                    "user_id": escape(request_state.payload.get("sub")),
                    "family_id": escape(payload_data.get("family_id")),
                    "provider_id": escape(payload_data.get("provider_id")),
                    "types": [escape(t) for t in payload_data.get("types", [])],
                }
            else:
                user_info = None

        except Exception as e:
            current_app.logger.error(f"Error getting user info: {e}")
            user_info = None

        # Group views by category
        categorized_views = defaultdict(list)
        for view in self.admin._views:
            if view.category:
                categorized_views[view.category].append(view)

        # Sort categories and views within categories by name
        sorted_categories = sorted(categorized_views.items())
        for _, views in sorted_categories:
            views.sort(key=lambda x: x.name)

        return self.render(
            "admin/index.html",
            user_info=user_info,
            categorized_views=sorted_categories,
        )


class SecureModelView(ClerkAuthMixin, ModelView):
    """Secure model view that requires admin authentication"""

    # Default permissions - you can override these per model
    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True

    # Add some basic column display settings
    column_display_pk = True
    column_hide_backrefs = False

    def on_model_change(self, form, model, is_created):
        """Called when model is changed - add audit logging"""
        try:
            from app.auth.decorators import ClerkUserType, _authenticate_request

            _authenticate_request(ClerkUserType.ADMIN, allow_cookies=True)
            # TODO in the future if we want to add audit logging, we can do it here
            # https://github.com/Gary-Community-Ventures/csp-backend/issues/66

        except Exception as e:
            current_app.logger.error(f"Audit logging error in on_model_change: {e}")
            pass  # Don't fail the operation if audit logging fails

        super().on_model_change(form, model, is_created)
