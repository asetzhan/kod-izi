"""Stage 2: work sessions, append-only trace events, submissions, explanations.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "work_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("assessment_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_reason", sa.String(length=32), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_work_sessions_assessment_id_assessments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_work_sessions_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_work_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_sessions")),
    )
    op.create_index(
        op.f("ix_work_sessions_assessment_id"), "work_sessions", ["assessment_id"], unique=False
    )
    op.create_index(op.f("ix_work_sessions_task_id"), "work_sessions", ["task_id"], unique=False)
    op.create_index(op.f("ix_work_sessions_user_id"), "work_sessions", ["user_id"], unique=False)
    op.create_table(
        "submissions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("assessment_id", sa.BigInteger(), nullable=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("verdict", sa.String(length=4), nullable=True),
        sa.Column("tests_passed", sa.Integer(), nullable=False),
        sa.Column("tests_total", sa.Integer(), nullable=False),
        sa.Column("max_time_ms", sa.Integer(), nullable=True),
        sa.Column("max_memory_kb", sa.Integer(), nullable=True),
        sa.Column("compile_output", sa.Text(), server_default="", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'error')",
            name=op.f("ck_submissions_status_valid"),
        ),
        sa.CheckConstraint(
            "verdict IS NULL OR verdict IN ('OK', 'WA', 'TLE', 'MLE', 'RE', 'CE')",
            name=op.f("ck_submissions_verdict_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_submissions_assessment_id_assessments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["work_sessions.id"],
            name=op.f("fk_submissions_session_id_work_sessions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_submissions_task_id_tasks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_submissions_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submissions")),
    )
    op.create_index(
        op.f("ix_submissions_assessment_id"), "submissions", ["assessment_id"], unique=False
    )
    op.create_index(op.f("ix_submissions_session_id"), "submissions", ["session_id"], unique=False)
    op.create_index(op.f("ix_submissions_task_id"), "submissions", ["task_id"], unique=False)
    op.create_index(op.f("ix_submissions_user_id"), "submissions", ["user_id"], unique=False)
    op.create_table(
        "trace_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("assessment_id", sa.BigInteger(), nullable=True),
        sa.Column("seq", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("stage", sa.String(length=16), nullable=True),
        sa.Column("client_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "server_ts", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("flagged", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.CheckConstraint(
            "kind IN ('session_start', 'snapshot', 'paste', 'focus_lost', 'focus_back', 'compile', 'run', 'test', 'submit', 'verdict', 'explanation', 'answers', 'session_closed')",
            name=op.f("ck_trace_events_kind_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_trace_events_assessment_id_assessments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["work_sessions.id"],
            name=op.f("fk_trace_events_session_id_work_sessions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_trace_events_task_id_tasks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_trace_events_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trace_events")),
    )
    op.create_index(
        op.f("ix_trace_events_assessment_id"), "trace_events", ["assessment_id"], unique=False
    )
    op.create_index(
        "ix_trace_events_session_time", "trace_events", ["session_id", "server_ts"], unique=False
    )
    op.create_index(op.f("ix_trace_events_task_id"), "trace_events", ["task_id"], unique=False)
    op.create_index(op.f("ix_trace_events_user_id"), "trace_events", ["user_id"], unique=False)
    op.execute(
        "CREATE TRIGGER trace_events_append_only BEFORE UPDATE OR DELETE ON trace_events "
        "FOR EACH ROW EXECUTE FUNCTION forbid_modification()"
    )
    op.execute(
        "CREATE TRIGGER trace_events_no_truncate BEFORE TRUNCATE ON trace_events "
        "FOR EACH STATEMENT EXECUTE FUNCTION forbid_modification()"
    )
    op.create_index(
        "uq_trace_events_session_seq",
        "trace_events",
        ["session_id", "seq"],
        unique=True,
        postgresql_where=sa.text("seq IS NOT NULL"),
    )
    op.create_table(
        "explanations",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("submission_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("questions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("question_source", sa.String(length=32), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_explanations_submission_id_submissions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_explanations")),
        sa.UniqueConstraint("submission_id", name=op.f("uq_explanations_submission_id")),
    )
    op.create_table(
        "submission_test_results",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("submission_id", sa.BigInteger(), nullable=False),
        sa.Column("test_case_id", sa.BigInteger(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_hidden", sa.Boolean(), nullable=False),
        sa.Column("verdict", sa.String(length=4), nullable=False),
        sa.Column("time_ms", sa.Integer(), nullable=True),
        sa.Column("memory_kb", sa.Integer(), nullable=True),
        sa.Column("stdout", sa.Text(), server_default="", nullable=False),
        sa.Column("stderr", sa.Text(), server_default="", nullable=False),
        sa.CheckConstraint(
            "verdict IN ('OK', 'WA', 'TLE', 'MLE', 'RE', 'CE')",
            name=op.f("ck_submission_test_results_verdict_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_submission_test_results_submission_id_submissions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["test_case_id"],
            ["test_cases.id"],
            name=op.f("fk_submission_test_results_test_case_id_test_cases"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submission_test_results")),
    )
    op.create_index(
        op.f("ix_submission_test_results_submission_id"),
        "submission_test_results",
        ["submission_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_submission_test_results_submission_id"), table_name="submission_test_results"
    )
    op.drop_table("submission_test_results")
    op.drop_table("explanations")
    op.drop_index(
        "uq_trace_events_session_seq",
        table_name="trace_events",
        postgresql_where=sa.text("seq IS NOT NULL"),
    )
    op.drop_index(op.f("ix_trace_events_user_id"), table_name="trace_events")
    op.drop_index(op.f("ix_trace_events_task_id"), table_name="trace_events")
    op.drop_index("ix_trace_events_session_time", table_name="trace_events")
    op.drop_index(op.f("ix_trace_events_assessment_id"), table_name="trace_events")
    op.drop_table("trace_events")
    op.drop_index(op.f("ix_submissions_user_id"), table_name="submissions")
    op.drop_index(op.f("ix_submissions_task_id"), table_name="submissions")
    op.drop_index(op.f("ix_submissions_session_id"), table_name="submissions")
    op.drop_index(op.f("ix_submissions_assessment_id"), table_name="submissions")
    op.drop_table("submissions")
    op.drop_index(op.f("ix_work_sessions_user_id"), table_name="work_sessions")
    op.drop_index(op.f("ix_work_sessions_task_id"), table_name="work_sessions")
    op.drop_index(op.f("ix_work_sessions_assessment_id"), table_name="work_sessions")
    op.drop_table("work_sessions")
