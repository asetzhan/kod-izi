"""Stage 5: second factor, consent, non-superuser application role and row-level security.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

APP_ROLE = "kodizi_app"

# Tables with a student's own rows; staff and background jobs see every row.
OWN_ROWS = ["work_sessions", "trace_events", "submissions", "ai_messages", "llm_usage"]
# Rows that belong to a student through their submission.
VIA_SUBMISSION = ["submission_test_results", "explanations", "teacher_grades"]
# Rows students never read directly.
STAFF_ONLY = ["ai_grades", "observations", "component_entries", "component_entry_versions"]

FUNCTIONS = """
CREATE OR REPLACE FUNCTION app_user_id() RETURNS bigint LANGUAGE sql STABLE AS
$$ SELECT NULLIF(current_setting('app.user_id', true), '')::bigint $$;
CREATE OR REPLACE FUNCTION app_privileged() RETURNS boolean LANGUAGE sql STABLE AS
$$ SELECT coalesce(current_setting('app.privileged', true), '') = 'on' $$;
"""


def _rls_up() -> None:
    op.execute(
        f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') "
        f"THEN CREATE ROLE {APP_ROLE} NOLOGIN; END IF; END $$"
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}"
    )
    # Append-only tables: the application may only add rows (the trigger stays as well).
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON audit_log, trace_events FROM {APP_ROLE}")
    op.execute(FUNCTIONS)
    for table in OWN_ROWS:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_owner ON {table} "
            f"USING (app_privileged() OR user_id = app_user_id()) "
            f"WITH CHECK (app_privileged() OR user_id = app_user_id())"
        )
    for table in VIA_SUBMISSION:
        condition = (
            "app_privileged() OR EXISTS (SELECT 1 FROM submissions s "
            "WHERE s.id = submission_id AND s.user_id = app_user_id())"
        )
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_owner ON {table} USING ({condition}) WITH CHECK ({condition})"
        )
    for table in STAFF_ONLY:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_staff ON {table} "
            f"USING (app_privileged()) WITH CHECK (app_privileged())"
        )


def _rls_down() -> None:
    for table in OWN_ROWS + VIA_SUBMISSION:
        op.execute(f"DROP POLICY IF EXISTS {table}_owner ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    for table in STAFF_ONLY:
        op.execute(f"DROP POLICY IF EXISTS {table}_staff ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP FUNCTION IF EXISTS app_user_id()")
    op.execute("DROP FUNCTION IF EXISTS app_privileged()")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {APP_ROLE}")


revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("totp_pending_secret", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("totp_enabled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("consent_version", sa.String(length=16), nullable=True))
    op.add_column("users", sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users", sa.Column("consent_withdrawn_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("users", sa.Column("anonymized_at", sa.DateTime(timezone=True), nullable=True))
    _rls_up()


def downgrade() -> None:
    _rls_down()
    op.drop_column("users", "anonymized_at")
    op.drop_column("users", "consent_withdrawn_at")
    op.drop_column("users", "consent_at")
    op.drop_column("users", "consent_version")
    op.drop_column("users", "totp_enabled_at")
    op.drop_column("users", "totp_pending_secret")
    op.drop_column("users", "totp_secret")
