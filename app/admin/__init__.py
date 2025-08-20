# app/admin/__init__.py
# Nuclear option: Complete bypass of Select2 widget with form widget override

from collections import defaultdict

from flask import current_app, redirect, request
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView


class ClerkAuthMixin:
    """Mixin to add Clerk authentication to Flask-Admin views"""

    def is_accessible(self):
        """Check if current user can access this view"""
        try:
            # Import here to avoid circular imports
            from app.auth.decorators import ClerkUserType, _authenticate_request

            # Try to authenticate the request
            _authenticate_request(ClerkUserType.ADMIN)

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

            request_state = _authenticate_request(ClerkUserType.ADMIN)

            if request_state.is_signed_in:
                user_data = request_state.payload.get("data", {})
                user_info = {
                    "user_id": request_state.payload.get("sub"),
                    "email": user_data.get("email_addresses", [{}])[0].get("email_address", "Unknown"),
                    "first_name": user_data.get("first_name", ""),
                    "last_name": user_data.get("last_name", ""),
                    "is_admin": (
                        user_data.get("public_metadata", {}).get("is_admin", False)
                        or user_data.get("private_metadata", {}).get("is_admin", False)
                    ),
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
        for category, views in sorted_categories:
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

            request_state = _authenticate_request(ClerkUserType.ADMIN)
            user_id = request_state.payload.get("sub")

            # Add audit fields if your models support them
            if hasattr(model, "modified_by"):
                model.modified_by = user_id
            if hasattr(model, "created_by") and is_created:
                model.created_by = user_id

        except Exception:
            pass  # Don't fail the operation if audit logging fails

        super().on_model_change(form, model, is_created)


# Create the admin instance
admin = Admin(
    name="CAP Colorado Admin",
    index_view=SecureAdminIndexView(name="Dashboard", url="/admin"),
)


def init_admin_views(app):
    """Initialize admin views with your models"""

    try:
        # Import your models here to avoid circular imports
        from app.extensions import db
        from app.models import (
            AllocatedCareDay,
            FamilyInvitation,
            MonthAllocation,
            PaymentRate,
            PaymentRequest,
            ProviderInvitation,
        )

        # Add model views with appropriate configurations
        admin.add_view(SecureModelView(PaymentRate, db.session, name="Payment Rates", category="Financial"))

        admin.add_view(SecureModelView(AllocatedCareDay, db.session, name="Allocated Care Days", category="Financial"))

        admin.add_view(SecureModelView(MonthAllocation, db.session, name="Month Allocations", category="Financial"))

        admin.add_view(SecureModelView(PaymentRequest, db.session, name="Payment Requests", category="Financial"))

        admin.add_view(SecureModelView(ProviderInvitation, db.session, name="Provider Invitations", category="Users"))

        admin.add_view(SecureModelView(FamilyInvitation, db.session, name="Family Invitations", category="Users"))

        print(f"✅ Flask-Admin initialized with {len(admin._views)} views")

    except ImportError as e:
        print(f"⚠️  Could not import some models for admin: {e}")
        print("Admin will still work, but some views may not be available")
    except Exception as e:
        print(f"❌ Error initializing admin views: {e}")


# This gets called from your main __init__.py
def init_app(app):
    """Initialize Flask-Admin with the app"""
    admin.init_app(app)
    init_admin_views(app)

    # Add any middleware or additional setup
    setup_admin_context_processors(app)


def setup_admin_context_processors(app):
    """Setup template context processors for admin templates"""

    @app.context_processor
    def inject_admin_user():
        """Make current admin user available in all admin templates"""
        if request.endpoint and request.endpoint.startswith("admin"):
            try:
                from app.auth.decorators import ClerkUserType, _authenticate_request

                request_state = _authenticate_request(ClerkUserType.ADMIN)

                if request_state.is_signed_in:
                    user_data = request_state.payload.get("data", {})
                    return {
                        "current_admin_user": {
                            "email": user_data.get("email_addresses", [{}])[0].get("email_address", ""),
                            "name": f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip(),
                            "user_id": request_state.payload.get("sub"),
                        }
                    }
            except Exception:
                pass

        return {}
