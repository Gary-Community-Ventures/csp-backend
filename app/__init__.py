import json
import os

import sentry_sdk
from clerk_backend_api import Clerk
from dotenv import load_dotenv
from flask import Flask
from google.oauth2 import service_account
from googleapiclient.discovery import build
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

# Import models to ensure they are registered with SQLAlchemy
from . import models
from .config import ENV_DEVELOPMENT, ENV_PRODUCTION, ENV_STAGING, ENV_TESTING

# Import extensions from the extensions module
from .extensions import cors, db, migrate


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
        elif env == ENV_TESTING:
            from .config import TestingConfig

            config_class = TestingConfig
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

    app.config["API_KEY"] = os.environ.get("API_KEY")
    if not app.config["API_KEY"]:
        raise ValueError("API_KEY environment variable must be set")

    # --- Initialize Flask Extensions (after app config) ---
    db.init_app(app)
    migrate.init_app(app, db)

    # --- Google Sheets Integration ---
    credentials = app.config.get("GOOGLE_APPLICATION_CREDENTIALS")
    if credentials:
        info = json.loads(credentials)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )

        app.google_sheets_service = build("sheets", "v4", credentials=creds).spreadsheets()

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
                    "allow_headers": [
                        "Content-Type",
                        "Authorization",
                    ],  # Be explicit for dev
                }
            },
        )

    # --- Initialize Job Queue ---
    from .jobs import job_manager
    job_manager.init_app(app)

    # --- Register Blueprints ---
    from .routes.auth import bp as auth_bp
    from .routes.care_day import bp as care_day_bp
    from .routes.child import bp as child_bp
    from .routes.family import bp as family_bp
    from .routes.main import bp as main_bp
    from .routes.payment_rate import payment_rate_bp
    from .routes.provider import bp as provider_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(family_bp)
    app.register_blueprint(provider_bp)
    app.register_blueprint(care_day_bp)
    app.register_blueprint(child_bp)
    app.register_blueprint(payment_rate_bp)

    return app
