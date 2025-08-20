from flask_admin import Admin

from app.admin.models import ADMIN_MODELS
from app.admin.views import (
    SecureAdminIndexView,
    SecureModelView,
    inject_environment_banner,
)

admin = Admin()


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
    env = app.config.get("FLASK_ENV", "production").capitalize()
    admin.name = f"CAP Colorado Admin - {env}"
    admin.index_view = SecureAdminIndexView(name="Dashboard", url="/admin")
    admin.init_app(app)
    init_admin_views(app)
    app.context_processor(inject_environment_banner)
