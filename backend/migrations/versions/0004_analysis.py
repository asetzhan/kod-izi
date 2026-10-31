"""Stage 3: rubric, materials and chunks (pgvector), bindings, AI grades, assistant log, LLM usage.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import pgvector.sqlalchemy.vector
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

OLD_KINDS = (
    "'session_start', 'snapshot', 'paste', 'focus_lost', 'focus_back', 'compile', 'run', "
    "'test', 'submit', 'verdict', 'explanation', 'answers', 'session_closed'"
)
NEW_KINDS = OLD_KINDS + ", 'ai_request', 'ai_response'"


def _kind_check(kinds: str) -> None:
    op.drop_constraint(op.f("ck_trace_events_kind_valid"), "trace_events", type_="check")
    op.create_check_constraint(
        op.f("ck_trace_events_kind_valid"), "trace_events", f"kind IN ({kinds})"
    )


revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_usage",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_llm_usage_user_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_usage")),
    )
    op.create_index(op.f("ix_llm_usage_created_at"), "llm_usage", ["created_at"], unique=False)
    op.create_index(op.f("ix_llm_usage_user_id"), "llm_usage", ["user_id"], unique=False)
    op.create_table(
        "materials",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("course_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("author", sa.String(length=300), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("rights_confirmed_by", sa.BigInteger(), nullable=True),
        sa.Column("rights_confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('book', 'lecture', 'problems')", name=op.f("ck_materials_kind_valid")
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_materials_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rights_confirmed_by"],
            ["users.id"],
            name=op.f("fk_materials_rights_confirmed_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_materials")),
    )
    op.create_index(op.f("ix_materials_course_id"), "materials", ["course_id"], unique=False)
    op.create_table(
        "rubrics",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("course_id", sa.BigInteger(), nullable=False),
        sa.Column("weight_f", sa.Float(), nullable=False),
        sa.Column("weight_e", sa.Float(), nullable=False),
        sa.Column("weight_a", sa.Float(), nullable=False),
        sa.Column("component_scales", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_rubrics_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_rubrics_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rubrics")),
        sa.UniqueConstraint("course_id", name=op.f("uq_rubrics_course_id")),
    )
    op.create_table(
        "material_versions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("material_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("stored_name", sa.String(length=80), nullable=False),
        sa.Column("mime", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("pages", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'ready', 'rejected', 'failed')",
            name=op.f("ck_material_versions_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["material_id"],
            ["materials.id"],
            name=op.f("fk_material_versions_material_id_materials"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_material_versions")),
        sa.UniqueConstraint(
            "material_id", "version", name=op.f("uq_material_versions_material_id")
        ),
    )
    op.create_index(
        op.f("ix_material_versions_material_id"), "material_versions", ["material_id"], unique=False
    )
    op.create_table(
        "rubric_criteria",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("rubric_id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("indicators", sa.Text(), nullable=False),
        sa.Column("data_sources", sa.Text(), nullable=False),
        sa.Column("descriptor_low", sa.Text(), nullable=False),
        sa.Column("descriptor_mid", sa.Text(), nullable=False),
        sa.Column("descriptor_high", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["rubric_id"],
            ["rubrics.id"],
            name=op.f("fk_rubric_criteria_rubric_id_rubrics"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rubric_criteria")),
        sa.UniqueConstraint("rubric_id", "code", name=op.f("uq_rubric_criteria_rubric_id")),
    )
    op.create_index(
        op.f("ix_rubric_criteria_rubric_id"), "rubric_criteria", ["rubric_id"], unique=False
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("version_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("chapter", sa.String(length=300), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1024), nullable=False),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["material_versions.id"],
            name=op.f("fk_chunks_version_id_material_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunks")),
    )
    op.create_index(op.f("ix_chunks_version_id"), "chunks", ["version_id"], unique=False)
    op.create_table(
        "material_bindings",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("material_id", sa.BigInteger(), nullable=False),
        sa.Column("topic_id", sa.BigInteger(), nullable=True),
        sa.Column("task_id", sa.BigInteger(), nullable=True),
        sa.Column("assessment_id", sa.BigInteger(), nullable=True),
        sa.Column("chapter", sa.String(length=300), nullable=False),
        sa.Column("page_from", sa.Integer(), nullable=True),
        sa.Column("page_to", sa.Integer(), nullable=True),
        sa.Column(
            "is_assessment_basis", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("requirements", sa.Text(), server_default="", nullable=False),
        sa.CheckConstraint(
            "num_nonnulls(topic_id, task_id, assessment_id) = 1",
            name=op.f("ck_material_bindings_one_target"),
        ),
        sa.CheckConstraint(
            "page_from IS NULL OR page_to IS NULL OR page_from <= page_to",
            name=op.f("ck_material_bindings_page_range"),
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_material_bindings_assessment_id_assessments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["material_id"],
            ["materials.id"],
            name=op.f("fk_material_bindings_material_id_materials"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_material_bindings_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_material_bindings_topic_id_topics"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_material_bindings")),
    )
    op.create_index(
        op.f("ix_material_bindings_material_id"), "material_bindings", ["material_id"], unique=False
    )
    op.create_table(
        "ai_messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("assessment_id", sa.BigInteger(), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("blocked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_ai_messages_assessment_id_assessments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["work_sessions.id"],
            name=op.f("fk_ai_messages_session_id_work_sessions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name=op.f("fk_ai_messages_task_id_tasks"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_ai_messages_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_messages")),
    )
    op.create_index(
        op.f("ix_ai_messages_assessment_id"), "ai_messages", ["assessment_id"], unique=False
    )
    op.create_index(op.f("ix_ai_messages_session_id"), "ai_messages", ["session_id"], unique=False)
    op.create_index(op.f("ix_ai_messages_user_id"), "ai_messages", ["user_id"], unique=False)
    op.create_table(
        "ai_grades",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("submission_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("criteria", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("component_f", sa.Float(), nullable=True),
        sa.Column("component_e", sa.Float(), nullable=True),
        sa.Column("component_a", sa.Float(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("interpretation", sa.Text(), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column("next_step", sa.Text(), nullable=False),
        sa.Column("flags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("review_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("weights", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fragment_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("raw_response", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('ready', 'needs_review', 'failed')", name=op.f("ck_ai_grades_status_valid")
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_ai_grades_submission_id_submissions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_grades")),
    )
    op.create_index(
        op.f("ix_ai_grades_submission_id"), "ai_grades", ["submission_id"], unique=False
    )
    op.add_column(
        "assessments",
        sa.Column("teacher_requirements", sa.Text(), server_default="", nullable=False),
    )
    op.add_column(
        "submissions",
        sa.Column("static_analysis", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "tasks", sa.Column("teacher_requirements", sa.Text(), server_default="", nullable=False)
    )
    _kind_check(NEW_KINDS)


def downgrade() -> None:
    _kind_check(OLD_KINDS)
    op.drop_column("tasks", "teacher_requirements")
    op.drop_column("submissions", "static_analysis")
    op.drop_column("assessments", "teacher_requirements")
    op.drop_index(op.f("ix_ai_grades_submission_id"), table_name="ai_grades")
    op.drop_table("ai_grades")
    op.drop_index(op.f("ix_ai_messages_user_id"), table_name="ai_messages")
    op.drop_index(op.f("ix_ai_messages_session_id"), table_name="ai_messages")
    op.drop_index(op.f("ix_ai_messages_assessment_id"), table_name="ai_messages")
    op.drop_table("ai_messages")
    op.drop_index(op.f("ix_material_bindings_material_id"), table_name="material_bindings")
    op.drop_table("material_bindings")
    op.drop_index(op.f("ix_chunks_version_id"), table_name="chunks")
    op.drop_table("chunks")
    op.drop_index(op.f("ix_rubric_criteria_rubric_id"), table_name="rubric_criteria")
    op.drop_table("rubric_criteria")
    op.drop_index(op.f("ix_material_versions_material_id"), table_name="material_versions")
    op.drop_table("material_versions")
    op.drop_table("rubrics")
    op.drop_index(op.f("ix_materials_course_id"), table_name="materials")
    op.drop_table("materials")
    op.drop_index(op.f("ix_llm_usage_user_id"), table_name="llm_usage")
    op.drop_index(op.f("ix_llm_usage_created_at"), table_name="llm_usage")
    op.drop_table("llm_usage")
