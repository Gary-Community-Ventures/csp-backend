from flask_admin import Admin

from app.admin.models import ADMIN_MODELS
from app.admin.views import (
    SecureAdminIndexView,
    SecureModelView,
    inject_environment_banner,
)

admin = Admin(index_view=SecureAdminIndexView(name="Dashboard", url="/admin"))


def init_admin_views(app):
    """Initialize admin views with your models"""

    try:
        from app.admin.payment_views import (
            PaymentAdminView,
            PaymentAttemptAdminView,
            PaymentIntentAdminView,
        )
        from app.extensions import db

        # Map view class names to actual classes
        view_classes = {
            "PaymentAdminView": PaymentAdminView,
            "PaymentAttemptAdminView": PaymentAttemptAdminView,
            "PaymentIntentAdminView": PaymentIntentAdminView,
        }

        for model_config in ADMIN_MODELS:
            # Use custom view class if specified, otherwise use default
            view_class = view_classes.get(model_config.view_class, SecureModelView)

            admin.add_view(
                view_class(
                    model_config.model,
                    db.session,
                    name=model_config.name,
                    category=model_config.category,
                )
            )

        app.logger.info(f"✅ Flask-Admin initialized with {len(admin._views)} views")

    except ImportError as e:
        app.logger.error(f"⚠️  Could not import some models for admin: {e}")
        app.logger.error("Admin will still work, but some views may not be available")
    except Exception as e:
        app.logger.error(f"❌ Error initializing admin views: {e}")


def init_app(app):
    """Initialize Flask-Admin with the app"""
    env = app.config.get("FLASK_ENV", "production").capitalize()
    admin.name = f"CAP Colorado Admin - {env}"
    admin.init_app(app)
    init_admin_views(app)
    app.context_processor(inject_environment_banner)
