"""Stage 1: courses, topics, Stepik lessons, knowledge components, task bank, assessments.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "courses",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("part", sa.String(length=16), nullable=False),
        sa.Column("stepik_course_id", sa.Integer(), nullable=True),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "part IN ('part1', 'part2', 'other')", name=op.f("ck_courses_part_valid")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_courses")),
        sa.UniqueConstraint("stepik_course_id", name=op.f("uq_courses_stepik_course_id")),
    )
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_app_settings_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_app_settings")),
    )
    op.create_table(
        "assessments",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("course_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("genai_mode", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "genai_mode IN ('forbidden', 'hints_only', 'open')",
            name=op.f("ck_assessments_genai_mode_valid"),
        ),
        sa.CheckConstraint("ends_at > starts_at", name=op.f("ck_assessments_window_valid")),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_assessments_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_assessments_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessments")),
    )
    op.create_index(op.f("ix_assessments_course_id"), "assessments", ["course_id"], unique=False)
    op.create_table(
        "course_groups",
        sa.Column("course_id", sa.BigInteger(), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_course_groups_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            name=op.f("fk_course_groups_group_id_groups"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("course_id", "group_id", name=op.f("pk_course_groups")),
    )
    op.create_index(op.f("ix_course_groups_group_id"), "course_groups", ["group_id"], unique=False)
    op.create_table(
        "course_teachers",
        sa.Column("course_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_course_teachers_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_course_teachers_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("course_id", "user_id", name=op.f("pk_course_teachers")),
    )
    op.create_index(
        op.f("ix_course_teachers_user_id"), "course_teachers", ["user_id"], unique=False
    )
    op.create_table(
        "topics",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("course_id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("learning_outcomes", sa.Text(), server_default="", nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_topics_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_topics")),
        sa.UniqueConstraint("course_id", "code", name=op.f("uq_topics_course_id")),
    )
    op.create_index(op.f("ix_topics_course_id"), "topics", ["course_id"], unique=False)
    op.create_table(
        "external_lessons",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("topic_id", sa.BigInteger(), nullable=False),
        sa.Column("stepik_lesson_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_external_lessons_topic_id_topics"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_lessons")),
    )
    op.create_index(
        op.f("ix_external_lessons_topic_id"), "external_lessons", ["topic_id"], unique=False
    )
    op.create_table(
        "knowledge_components",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("topic_id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_knowledge_components_topic_id_topics"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_components")),
        sa.UniqueConstraint("topic_id", "code", name=op.f("uq_knowledge_components_topic_id")),
    )
    op.create_index(
        op.f("ix_knowledge_components_topic_id"), "knowledge_components", ["topic_id"], unique=False
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("course_id", sa.BigInteger(), nullable=False),
        sa.Column("topic_id", sa.BigInteger(), nullable=True),
        sa.Column("external_key", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("statement_md", sa.Text(), nullable=False),
        sa.Column("input_format", sa.Text(), server_default="", nullable=False),
        sa.Column("output_format", sa.Text(), server_default="", nullable=False),
        sa.Column("time_limit_ms", sa.Integer(), nullable=False),
        sa.Column("memory_limit_kb", sa.Integer(), nullable=False),
        sa.Column("reference_solution", sa.Text(), server_default="", nullable=False),
        sa.Column("reference_language", sa.String(length=16), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("source_note", sa.Text(), server_default="", nullable=False),
        sa.Column("feat_knowledge_actions", sa.SmallInteger(), nullable=True),
        sa.Column("feat_algorithm_freedom", sa.SmallInteger(), nullable=True),
        sa.Column("feat_edge_cases", sa.SmallInteger(), nullable=True),
        sa.Column("feat_justification", sa.SmallInteger(), nullable=True),
        sa.Column("level_rationale", sa.Text(), server_default="", nullable=False),
        sa.Column("level", sa.String(length=3), nullable=True),
        sa.Column("level_status", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("author_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "level IS NULL OR level IN ('I', 'II', 'III', 'IV')", name=op.f("ck_tasks_level_valid")
        ),
        sa.CheckConstraint(
            "level_status IN ('unrated', 'suggested', 'confirmed')",
            name=op.f("ck_tasks_level_status_valid"),
        ),
        sa.CheckConstraint("status IN ('draft', 'approved')", name=op.f("ck_tasks_status_valid")),
        sa.CheckConstraint(
            "feat_algorithm_freedom BETWEEN 0 AND 2",
            name=op.f("ck_tasks_feat_algorithm_freedom_range"),
        ),
        sa.CheckConstraint(
            "feat_edge_cases BETWEEN 0 AND 2", name=op.f("ck_tasks_feat_edge_cases_range")
        ),
        sa.CheckConstraint(
            "feat_justification BETWEEN 0 AND 2", name=op.f("ck_tasks_feat_justification_range")
        ),
        sa.CheckConstraint(
            "feat_knowledge_actions BETWEEN 0 AND 2",
            name=op.f("ck_tasks_feat_knowledge_actions_range"),
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_tasks_author_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_tasks_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"], ["topics.id"], name=op.f("fk_tasks_topic_id_topics"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
        sa.UniqueConstraint("external_key", name=op.f("uq_tasks_external_key")),
    )
    op.create_index(op.f("ix_tasks_course_id"), "tasks", ["course_id"], unique=False)
    op.create_index(op.f("ix_tasks_topic_id"), "tasks", ["topic_id"], unique=False)
    op.create_table(
        "assessment_tasks",
        sa.Column("assessment_id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_assessment_tasks_assessment_id_assessments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_assessment_tasks_task_id_tasks"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("assessment_id", "task_id", name=op.f("pk_assessment_tasks")),
    )
    op.create_index(
        op.f("ix_assessment_tasks_task_id"), "assessment_tasks", ["task_id"], unique=False
    )
    op.create_table(
        "task_knowledge_components",
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("knowledge_component_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["knowledge_component_id"],
            ["knowledge_components.id"],
            name=op.f("fk_task_knowledge_components_knowledge_component_id_knowledge_components"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_task_knowledge_components_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "task_id", "knowledge_component_id", name=op.f("pk_task_knowledge_components")
        ),
    )
    op.create_index(
        op.f("ix_task_knowledge_components_knowledge_component_id"),
        "task_knowledge_components",
        ["knowledge_component_id"],
        unique=False,
    )
    op.create_table(
        "test_cases",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("expected_output", sa.Text(), nullable=False),
        sa.Column("is_hidden", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name=op.f("fk_test_cases_task_id_tasks"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_test_cases")),
    )
    op.create_index(op.f("ix_test_cases_task_id"), "test_cases", ["task_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_test_cases_task_id"), table_name="test_cases")
    op.drop_table("test_cases")
    op.drop_index(
        op.f("ix_task_knowledge_components_knowledge_component_id"),
        table_name="task_knowledge_components",
    )
    op.drop_table("task_knowledge_components")
    op.drop_index(op.f("ix_assessment_tasks_task_id"), table_name="assessment_tasks")
    op.drop_table("assessment_tasks")
    op.drop_index(op.f("ix_tasks_topic_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_course_id"), table_name="tasks")
    op.drop_table("tasks")
    op.drop_index(op.f("ix_knowledge_components_topic_id"), table_name="knowledge_components")
    op.drop_table("knowledge_components")
    op.drop_index(op.f("ix_external_lessons_topic_id"), table_name="external_lessons")
    op.drop_table("external_lessons")
    op.drop_index(op.f("ix_topics_course_id"), table_name="topics")
    op.drop_table("topics")
    op.drop_index(op.f("ix_course_teachers_user_id"), table_name="course_teachers")
    op.drop_table("course_teachers")
    op.drop_index(op.f("ix_course_groups_group_id"), table_name="course_groups")
    op.drop_table("course_groups")
    op.drop_index(op.f("ix_assessments_course_id"), table_name="assessments")
    op.drop_table("assessments")
    op.drop_table("app_settings")
    op.drop_table("courses")
