"""Restrict ai_readonly to analytics schema

Revision ID: 623f80a44902
Revises: 802e3181c595
Create Date: 2026-05-13 11:43:30.000000

"""

from pathlib import Path

from alembic import op

# revision identifiers, used by Alembic.
revision = "623f80a44902"
down_revision = "802e3181c595"
branch_labels = None
depends_on = None


SQL_FILE = Path(__file__).resolve().parent.parent / "sql" / "002_ai_readonly_analytics_only.sql"


def upgrade():
    sql = SQL_FILE.read_text()
    op.execute(sql)


def downgrade():
    # Best-effort restoration of the pre-migration grants: broad SELECT on
    # public, no analytics access, and ai_readonly's role-level GUCs reset to
    # the cluster defaults.
    op.execute(
        """
        REVOKE SELECT ON ALL TABLES IN SCHEMA analytics FROM ai_readonly;
        REVOKE USAGE ON SCHEMA analytics FROM ai_readonly;
        ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA analytics
          REVOKE SELECT ON TABLES FROM ai_readonly;

        GRANT USAGE ON SCHEMA public TO ai_readonly;
        GRANT SELECT ON ALL TABLES IN SCHEMA public TO ai_readonly;
        ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
          GRANT SELECT ON TABLES TO ai_readonly;

        ALTER ROLE ai_readonly RESET statement_timeout;
        ALTER ROLE ai_readonly RESET idle_in_transaction_session_timeout;
        ALTER ROLE ai_readonly RESET lock_timeout;
        ALTER ROLE ai_readonly RESET search_path;
        """
    )
"""Restrict ai_readonly to analytics schema

Revision ID: 623f80a44902
Revises: 802e3181c595
Create Date: 2026-05-13 11:43:30.000000

"""

from pathlib import Path

from alembic import op

# revision identifiers, used by Alembic.
revision = "623f80a44902"
down_revision = "802e3181c595"
branch_labels = None
depends_on = None


SQL_FILE = Path(__file__).resolve().parent.parent / "sql" / "002_ai_readonly_analytics_only.sql"


def upgrade():
    sql = SQL_FILE.read_text()
    op.execute(sql)


def downgrade():
    # Best-effort restoration of the pre-migration grants: broad SELECT on
    # public, no analytics access, and ai_readonly's role-level GUCs reset to
    # the cluster defaults.
    op.execute(
        """
        REVOKE SELECT ON ALL TABLES IN SCHEMA analytics FROM ai_readonly;
        REVOKE USAGE ON SCHEMA analytics FROM ai_readonly;
        ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA analytics
          REVOKE SELECT ON TABLES FROM ai_readonly;

        GRANT USAGE ON SCHEMA public TO ai_readonly;
        GRANT SELECT ON ALL TABLES IN SCHEMA public TO ai_readonly;
        ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
          GRANT SELECT ON TABLES TO ai_readonly;

        ALTER ROLE ai_readonly RESET statement_timeout;
        ALTER ROLE ai_readonly RESET idle_in_transaction_session_timeout;
        ALTER ROLE ai_readonly RESET lock_timeout;
        ALTER ROLE ai_readonly RESET search_path;
        """
    )
