import os


class Config:
    """Base configuration."""

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    SENTRY_DSN = os.getenv("SENTRY_DSN")
    SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "1.0"))
    SENTRY_PROFILES_SAMPLE_RATE = float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "1.0"))
    APP_VERSION = os.getenv("HEROKU_SLUG_COMMIT", "local")
    FRONTEND_DOMAIN = os.getenv("FRONTEND_DOMAIN", "http://localhost:5173")
    BACKEND_DOMAIN = os.getenv("BACKEND_DOMAIN", "http://localhost:5000")
    AUTH_AUTHORIZED_PARTIES = [
        os.getenv("FRONTEND_DOMAIN", "http://localhost:5173"),
        os.getenv("BACKEND_DOMAIN", "http://localhost:5000"),
    ]
    GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    GOOGLE_SPREADSHEET_ID = os.getenv("GOOGLE_SPREADSHEET_ID")
    EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "sendgrid")
    SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
    POSTMARK_API_KEY = os.getenv("POSTMARK_API_KEY")
    POSTMARK_STREAM_INTERNAL = os.getenv("POSTMARK_STREAM_INTERNAL", "internal")
    POSTMARK_STREAM_EXTERNAL = os.getenv("POSTMARK_STREAM_EXTERNAL", "notifications")
    FROM_EMAIL_INTERNAL = os.getenv("FROM_EMAIL_INTERNAL")
    FROM_EMAIL_EXTERNAL = os.getenv("FROM_EMAIL_EXTERNAL")
    REPLY_TO_EMAIL = os.getenv("REPLY_TO_EMAIL", "support@capcolorado.org")
    INTERNAL_EMAIL_RECIPIENTS = os.getenv("INTERNAL_EMAIL_RECIPIENTS", "").split(",")
    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
    TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
    API_KEY = os.getenv("API_KEY")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    EXAMPLE_JOB_CRON = os.getenv("EXAMPLE_JOB_CRON", "*/5 * * * *")
    EXAMPLE_JOB_SLEEP_TIME = int(os.getenv("EXAMPLE_JOB_SLEEP_TIME", 10))

    # Clerk Configuration
    CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY")

    # Supabase Configuration
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")

    # For Flask-Admin
    SECRET_KEY = os.getenv("SECRET_KEY")

    # Chek Configuration
    CHEK_BASE_URL = os.getenv("CHEK_BASE_URL")
    CHEK_ACCOUNT_ID = os.getenv("CHEK_ACCOUNT_ID")
    CHEK_API_KEY = os.getenv("CHEK_API_KEY")
    CHEK_WRITE_KEY = os.getenv("CHEK_WRITE_KEY")
    CHEK_PROGRAM_ID = os.getenv("CHEK_PROGRAM_ID")


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "postgresql://dev:dev@localhost/myapp")  # Fallback for local
    CORS_HEADERS = "Content-Type"  # Example CORS setting


class TestingConfig(Config):
    """Testing configuration."""

    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    WTF_CSRF_ENABLED = False


class StagingConfig(Config):
    """Staging configuration."""

    DEBUG = True
    # Fix for Heroku's 'postgres://' scheme
    db_url = os.getenv("DATABASE_URL")
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = db_url
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
    # Fix for Heroku's 'postgres://' scheme
    db_url = os.getenv("DATABASE_URL")
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = db_url
    SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))  # Lower sample rate for prod
    SENTRY_PROFILES_SAMPLE_RATE = float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.05"))
    CORS_ORIGINS = os.getenv(
        "CORS_ORIGINS",
        "",
    ).split(",")
    CORS_SUPPORTS_CREDENTIALS = True
    CORS_ALLOW_HEADERS = ["Content-Type", "Authorization"]
