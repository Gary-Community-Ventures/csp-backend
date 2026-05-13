"""Create analytics schema with curated PII-light views

Revision ID: 802e3181c595
Revises: 008bacbec985
Create Date: 2026-05-13 11:43:00.000000

"""

from pathlib import Path

from alembic import op

# revision identifiers, used by Alembic.
revision = "802e3181c595"
down_revision = "008bacbec985"
branch_labels = None
depends_on = None


SQL_FILE = Path(__file__).resolve().parent.parent / "sql" / "001_analytics_schema.sql"

# Views that 001_analytics_schema.sql creates, in reverse dependency order
# (none depend on each other today, but listing them keeps the downgrade
# explicit instead of relying on DROP SCHEMA ... CASCADE).
_VIEW_NAMES = (
    "email_batches",
    "email_delivery_summary",
    "click_engagement",
    "user_activity_by_hour",
    "invitation_engagement",
    "fund_reclamations",
    "attendance_weeks",
    "payment_rates",
    "payment_attempts",
    "payment_intents",
    "payments",
    "lump_sums",
    "care_days",
    "monthly_allocations",
    "provider_child_relationships",
    "providers",
    "children",
    "families",
)


def upgrade():
    sql = SQL_FILE.read_text()
    op.execute(sql)


def downgrade():
    for view in _VIEW_NAMES:
        op.execute(f"DROP VIEW IF EXISTS analytics.{view}")
    op.execute("DROP SCHEMA IF EXISTS analytics")


"""Create analytics schema with curated PII-light views

Revision ID: 802e3181c595
Revises: 008bacbec985
Create Date: 2026-05-13 11:43:00.000000

"""

from pathlib import Path

from alembic import op

# revision identifiers, used by Alembic.
revision = "802e3181c595"
down_revision = "008bacbec985"
branch_labels = None
depends_on = None


SQL_FILE = Path(__file__).resolve().parent.parent / "sql" / "001_analytics_schema.sql"

# Views that 001_analytics_schema.sql creates, in reverse dependency order
# (none depend on each other today, but listing them keeps the downgrade
# explicit instead of relying on DROP SCHEMA ... CASCADE).
_VIEW_NAMES = (
    "email_batches",
    "email_delivery_summary",
    "click_engagement",
    "user_activity_by_hour",
    "invitation_engagement",
    "fund_reclamations",
    "attendance_weeks",
    "payment_rates",
    "payment_attempts",
    "payment_intents",
    "payments",
    "lump_sums",
    "care_days",
    "monthly_allocations",
    "provider_child_relationships",
    "providers",
    "children",
    "families",
)


def upgrade():
    sql = SQL_FILE.read_text()
    op.execute(sql)


def downgrade():
    for view in _VIEW_NAMES:
        op.execute(f"DROP VIEW IF EXISTS analytics.{view}")
    op.execute("DROP SCHEMA IF EXISTS analytics")
