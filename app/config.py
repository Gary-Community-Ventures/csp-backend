import os

# --- Environment Constants ---
ENV_DEVELOPMENT = "development"
ENV_STAGING = "staging"
ENV_PRODUCTION = "production"
# --- End Environment Constants ---


class Config:
    """Base configuration."""

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    SENTRY_DSN = os.getenv("SENTRY_DSN")
    SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "1.0"))
    SENTRY_PROFILES_SAMPLE_RATE = float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "1.0"))
    APP_VERSION = os.getenv("APP_VERSION", "1.0.0")  # Example for Sentry release tracking
    FRONTEND_DOMAIN = os.getenv("FRONTEND_DOMAIN", "http://localhost:5173")
    AUTH_AUTHORIZED_PARTIES = [os.getenv("FRONTEND_DOMAIN", "http://localhost:5173")]

    # Clerk Configuration
    CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY")


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "postgresql://dev:dev@localhost/myapp")  # Fallback for local
    CORS_HEADERS = "Content-Type"  # Example CORS setting


class StagingConfig(Config):
    """Staging configuration."""

    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.5"))
    SENTRY_PROFILES_SAMPLE_RATE = float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.25"))
    CORS_ORIGINS = os.getenv(
        "CORS_ORIGINS",
        "",
    ).split(",")
    CORS_SUPPORTS_CREDENTIALS = True
    CORS_ALLOW_HEADERS = ["Content-Type", "Authorization"]


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")  # No fallback, must be set in prod env
    SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))  # Lower sample rate for prod
    SENTRY_PROFILES_SAMPLE_RATE = float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.05"))
    CORS_ORIGINS = os.getenv(
        "CORS_ORIGINS",
        "",
    ).split(",")
    CORS_SUPPORTS_CREDENTIALS = True
    CORS_ALLOW_HEADERS = ["Content-Type", "Authorization"]
