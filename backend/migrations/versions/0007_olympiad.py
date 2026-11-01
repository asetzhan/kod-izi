"""Stage 6a: olympiad bank fields, contests, participations, own tests, module references.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A student's own rows (row-level security as in 0006).
OWN_ROWS = ["contest_participations", "student_tests"]


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("tasks", sa.Column("cf_rating", sa.Integer(), nullable=True))
    op.add_column(
        "tasks", sa.Column("in_bank", sa.Boolean(), server_default=sa.true(), nullable=False)
    )
    op.add_column("tasks", sa.Column("editorial_md", sa.Text(), server_default="", nullable=False))
    op.add_column(
        "tasks",
        sa.Column(
            "subtask_points",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_tasks_memory_limit_range"), "tasks", "memory_limit_kb BETWEEN 16384 AND 1048576"
    )
    op.create_check_constraint(
        op.f("ck_tasks_cf_rating_range"),
        "tasks",
        "cf_rating IS NULL OR cf_rating BETWEEN 800 AND 3500",
    )
    op.add_column(
        "test_cases",
        sa.Column("subtask", sa.SmallInteger(), server_default="1", nullable=False),
    )
    op.add_column("ai_messages", sa.Column("hint_level", sa.SmallInteger(), nullable=True))

    op.add_column(
        "assessments",
        sa.Column("kind", sa.String(length=16), server_default="control", nullable=False),
    )
    op.add_column("assessments", sa.Column("contest_format", sa.String(length=8), nullable=True))
    op.add_column(
        "assessments",
        sa.Column("freeze_minutes", sa.Integer(), server_default="60", nullable=False),
    )
    op.add_column(
        "assessments",
        sa.Column("penalty_minutes", sa.Integer(), server_default="20", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_assessments_kind_valid"), "assessments", "kind IN ('control', 'contest')"
    )
    op.create_check_constraint(
        op.f("ck_assessments_contest_format_valid"),
        "assessments",
        "contest_format IS NULL OR contest_format IN ('icpc', 'ioi')",
    )
    op.create_check_constraint(
        op.f("ck_assessments_contest_valid"),
        "assessments",
        "kind <> 'contest' OR (contest_format IS NOT NULL AND genai_mode = 'forbidden')",
    )

    op.create_check_constraint(
        op.f("ck_assessments_contest_minutes_valid"),
        "assessments",
        "freeze_minutes >= 0 AND penalty_minutes >= 0",
    )

    op.create_table(
        "contest_participations",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("assessment_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "kind IN ('official', 'virtual')", name=op.f("ck_contest_participations_kind_valid")
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_contest_participations_assessment_id_assessments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_contest_participations_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contest_participations")),
        sa.UniqueConstraint(
            "assessment_id", "user_id", "kind", name=op.f("uq_contest_participations_assessment_id")
        ),
    )
    op.create_index(
        op.f("ix_contest_participations_assessment_id"), "contest_participations", ["assessment_id"]
    )
    op.create_index(
        op.f("ix_contest_participations_user_id"), "contest_participations", ["user_id"]
    )

    op.create_table(
        "student_tests",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("expected_output", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_student_tests_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_student_tests_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_student_tests")),
    )
    op.create_index(op.f("ix_student_tests_task_id"), "student_tests", ["task_id"])
    op.create_index(op.f("ix_student_tests_user_id"), "student_tests", ["user_id"])

    op.create_table(
        "topic_resources",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("topic_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("purpose", sa.Text(), server_default="", nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_topic_resources_topic_id_topics"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_topic_resources")),
        sa.UniqueConstraint("topic_id", "url", name=op.f("uq_topic_resources_topic_id")),
    )
    op.create_index(op.f("ix_topic_resources_topic_id"), "topic_resources", ["topic_id"])

    for table in OWN_ROWS:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_owner ON {table} "
            f"USING (app_privileged() OR user_id = app_user_id()) "
            f"WITH CHECK (app_privileged() OR user_id = app_user_id())"
        )


def downgrade() -> None:
    for table in OWN_ROWS:
        op.execute(f"DROP POLICY IF EXISTS {table}_owner ON {table}")
    op.drop_table("topic_resources")
    op.drop_table("student_tests")
    op.drop_table("contest_participations")
    op.drop_constraint(op.f("ck_assessments_contest_minutes_valid"), "assessments", type_="check")
    op.drop_constraint(op.f("ck_assessments_contest_valid"), "assessments", type_="check")
    op.drop_constraint(op.f("ck_assessments_contest_format_valid"), "assessments", type_="check")
    op.drop_constraint(op.f("ck_assessments_kind_valid"), "assessments", type_="check")
    op.drop_column("assessments", "penalty_minutes")
    op.drop_column("assessments", "freeze_minutes")
    op.drop_column("assessments", "contest_format")
    op.drop_column("assessments", "kind")
    op.drop_column("ai_messages", "hint_level")
    op.drop_column("test_cases", "subtask")
    op.drop_constraint(op.f("ck_tasks_cf_rating_range"), "tasks", type_="check")
    op.drop_constraint(op.f("ck_tasks_memory_limit_range"), "tasks", type_="check")
    op.drop_column("tasks", "subtask_points")
    op.drop_column("tasks", "editorial_md")
    op.drop_column("tasks", "in_bank")
    op.drop_column("tasks", "cf_rating")
    op.drop_column("tasks", "tags")
