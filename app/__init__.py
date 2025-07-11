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
            debug=app.config.get("DEBUG", False),
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

    # --- Initialize Flask Extensions (after app config) ---
    db.init_app(app)
    migrate.init_app(app, db)
    
    # --- CORS Configuration ---
    # For production, use the configured origins, credentials, and headers
    if app.config["FLASK_ENV"] == ENV_PRODUCTION or app.config["FLASK_ENV"] == ENV_STAGING:
        cors.init_app(
            app,
            resources={r"/*": {
                "origins": app.config.get("CORS_ORIGINS", []),
                "supports_credentials": app.config.get("CORS_SUPPORTS_CREDENTIALS", False),
                "allow_headers": app.config.get("CORS_ALLOW_HEADERS", ["Content-Type"])
            }},
        )
        print(f"DEBUG: Configured CORS_ORIGINS: {app.config.get('CORS_ORIGINS')}") # Added this specifically
        print(f"DEBUG: CORS instance origins: {cors.origins}")
        print(f"DEBUG: CORS instance supports_credentials: {cors.supports_credentials}")
        print(f"DEBUG: CORS instance allow_headers: {cors.default_allow_headers}")
        print(f"CORS initialized for production with origins: {app.config.get('CORS_ORIGINS')}")
    else: # For development, use simpler CORS or specific dev settings
        cors.init_app(
            app,
            resources={r"/*": {
                "origins": "*",  # Allow all for development
                "supports_credentials": True,
                "allow_headers": ["Content-Type", "Authorization"] # Be explicit for dev
            }},
        )
        print("CORS initialized for development (allowing all origins).")

    print(f"DEBUG: CORS origins applied: {cors.origins}")

    # --- Register Blueprints ---
    from .routes.main import main_bp
    from .routes.auth import auth_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)

    return app