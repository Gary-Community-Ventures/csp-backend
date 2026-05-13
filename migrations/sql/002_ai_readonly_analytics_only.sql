-- 002_ai_readonly_analytics_only.sql
-- Tightens ai_readonly so it can query analytics views but not raw public tables.
--
-- Apply only after 001_analytics_schema.sql.
-- The owning role (typically `postgres`) must already exist and own the
-- underlying tables, and the `ai_readonly` role must already exist.
--
-- Sourced from scry/db/migrations/002_ai_readonly_analytics_only.sql. The
-- original BEGIN/COMMIT wrapper is intentionally omitted here: this file is
-- executed inside an Alembic-managed transaction (see
-- migrations/versions/623f80a44902_restrict_ai_readonly_to_analytics.py).

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres') THEN
    CREATE ROLE postgres;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_readonly') THEN
    CREATE ROLE ai_readonly;
  END IF;
END
$$;

REVOKE ALL ON SCHEMA public FROM ai_readonly;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM ai_readonly;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM ai_readonly;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE SELECT ON TABLES FROM ai_readonly;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE SELECT ON SEQUENCES FROM ai_readonly;

GRANT USAGE ON SCHEMA analytics TO ai_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO ai_readonly;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA analytics
  GRANT SELECT ON TABLES TO ai_readonly;

ALTER ROLE ai_readonly SET statement_timeout = '15s';
ALTER ROLE ai_readonly SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE ai_readonly SET lock_timeout = '5s';
ALTER ROLE ai_readonly SET search_path = analytics;
