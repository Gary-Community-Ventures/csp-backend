from flask import current_app, request
from flask_admin import Admin

from app.admin.models import ADMIN_MODELS
from app.admin.views import SecureAdminIndexView, SecureModelView

# Create the admin instance
admin = Admin(
    name="CAP Colorado Admin",
    index_view=SecureAdminIndexView(name="Dashboard", url="/admin"),
)


def init_admin_views(app):
    """Initialize admin views with your models"""

    try:
        from app.extensions import db

        for model_config in ADMIN_MODELS:
            admin.add_view(
                SecureModelView(
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
    admin.init_app(app)
    init_admin_views(app)
