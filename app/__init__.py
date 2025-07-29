import os
from flask import Flask
from dotenv import load_dotenv

import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from clerk_backend_api import Clerk
from .config import ENV_DEVELOPMENT, ENV_STAGING, ENV_PRODUCTION

# Import extensions from the extensions module
from .extensions import db, migrate, cors

# Import models to ensure they are registered with SQLAlchemy
from . import models
from .admin import init_admin


def create_app(config_class=None):
    """
    Application factory function to create and configure the Flask app.
    """
    app = Flask(__name__)

    # Load environment variables early
    load_dotenv()

    # --- Configuration ---
    if config_class is None:
        # Determine configuration based on FLASK_ENV environment variable
        env = os.getenv("FLASK_ENV", ENV_DEVELOPMENT)
        if env == ENV_PRODUCTION:
            from .config import ProductionConfig

            config_class = ProductionConfig
        elif env == ENV_STAGING:
            from .config import StagingConfig

            config_class = StagingConfig
        else:  # Default to development
            from .config import DevelopmentConfig

            config_class = DevelopmentConfig

    app.config.from_object(config_class)

    # --- Sentry Initialization ---
    sentry_dsn = app.config.get("SENTRY_DSN")
    if sentry_dsn:
        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[
                FlaskIntegration(),
                SqlalchemyIntegration(),
            ],
            traces_sample_rate=app.config.get("SENTRY_TRACES_SAMPLE_RATE", 1.0),
            profiles_sample_rate=app.config.get("SENTRY_PROFILES_SAMPLE_RATE", 1.0),
            environment=app.config.get("FLASK_ENV"),
            release=app.config.get("APP_VERSION", None),
        )
        print("Sentry initialized for environment: ", f"{app.config.get('FLASK_ENV')}")
    else:
        print("SENTRY_DSN not found. Sentry will not be initialized.")

    # --- Clerk SDK Initialization ---
    clerk_secret_key = app.config.get("CLERK_SECRET_KEY")

    if not clerk_secret_key:
        print("WARNING: CLERK_SECRET_KEY not found. Clerk authentication will be disabled.")
        app.clerk_client = None
    else:
        app.clerk_client = Clerk(bearer_auth=clerk_secret_key)
        print("Clerk SDK initialized successfully.")

    app.config['API_KEY'] = os.environ.get('API_KEY')
    if not app.config['API_KEY']:
        raise ValueError("API_KEY environment variable must be set")

    # --- Initialize Flask Extensions (after app config) ---
    db.init_app(app)
    migrate.init_app(app, db)

    # --- CORS Configuration ---
    # For production, use the configured origins, credentials, and headers
    if app.config["FLASK_ENV"] == ENV_PRODUCTION or app.config["FLASK_ENV"] == ENV_STAGING:
        configured_origins = app.config.get("CORS_ORIGINS", [])
        configured_supports_credentials = app.config.get("CORS_SUPPORTS_CREDENTIALS", False)
        configured_allow_headers = app.config.get("CORS_ALLOW_HEADERS", ["Content-Type"])
        cors.init_app(
            app,
            resources={
                r"/*": {
                    "origins": configured_origins,
                    "supports_credentials": configured_supports_credentials,
                    "allow_headers": configured_allow_headers,
                }
            },
        )
    else:  # For development, use simpler CORS or specific dev settings
        cors.init_app(
            app,
            resources={
                r"/*": {
                    "origins": "*",  # Allow all for development
                    "supports_credentials": True,
                    "allow_headers": ["Content-Type", "Authorization"],  # Be explicit for dev
                }
            },
        )

    # --- Register Blueprints ---
    from .routes.main import bp as main_bp
    from .routes.auth import bp as auth_bp
    from .routes.family import bp as family_bp
    from .routes.provider import bp as provider_bp
    from .routes.payment_request import bp as payment_request_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(family_bp)
    app.register_blueprint(provider_bp)
    app.register_blueprint(payment_request_bp)

    init_admin(app)

    return app
