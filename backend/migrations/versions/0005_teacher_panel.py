"""Stage 4: model component entries with versions, settings, teacher grades, observations.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "component_entries",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("course_id", sa.BigInteger(), nullable=False),
        sa.Column("component", sa.SmallInteger(), nullable=False),
        sa.Column("subject_type", sa.String(length=16), nullable=False),
        sa.Column("subject_id", sa.BigInteger(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("auto_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("suggestion", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('auto', 'teacher', 'auto_edited')",
            name=op.f("ck_component_entries_source_valid"),
        ),
        sa.CheckConstraint(
            "component BETWEEN 1 AND 5", name=op.f("ck_component_entries_component_range")
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_component_entries_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_component_entries_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_component_entries")),
        sa.UniqueConstraint(
            "component",
            "subject_type",
            "subject_id",
            "key",
            name=op.f("uq_component_entries_component"),
        ),
    )
    op.create_index(
        op.f("ix_component_entries_course_id"), "component_entries", ["course_id"], unique=False
    )
    op.create_table(
        "component_settings",
        sa.Column("course_id", sa.BigInteger(), nullable=False),
        sa.Column("component", sa.SmallInteger(), nullable=False),
        sa.Column("auto_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_component_settings_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("course_id", "component", name=op.f("pk_component_settings")),
    )
    op.create_table(
        "component_entry_versions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("entry_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("author_id", sa.BigInteger(), nullable=True),
        sa.Column("note", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_component_entry_versions_author_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["component_entries.id"],
            name=op.f("fk_component_entry_versions_entry_id_component_entries"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_component_entry_versions")),
        sa.UniqueConstraint(
            "entry_id", "version", name=op.f("uq_component_entry_versions_entry_id")
        ),
    )
    op.create_index(
        op.f("ix_component_entry_versions_entry_id"),
        "component_entry_versions",
        ["entry_id"],
        unique=False,
    )
    op.create_table(
        "observations",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("submission_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("signal", sa.String(length=64), nullable=True),
        sa.Column("criterion", sa.String(length=32), nullable=True),
        sa.Column("level", sa.String(length=4), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("author_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "level IS NULL OR level IN ('low', 'mid', 'high')",
            name=op.f("ck_observations_level_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_observations_author_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_observations_submission_id_submissions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_observations")),
    )
    op.create_index(
        op.f("ix_observations_submission_id"), "observations", ["submission_id"], unique=False
    )
    op.create_table(
        "teacher_grades",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("submission_id", sa.BigInteger(), nullable=False),
        sa.Column("ai_grade_id", sa.BigInteger(), nullable=True),
        sa.Column("criteria", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("component_f", sa.Float(), nullable=False),
        sa.Column("component_e", sa.Float(), nullable=False),
        sa.Column("component_a", sa.Float(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column("feedback_source", sa.String(length=16), nullable=False),
        sa.Column("book_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("next_step", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("agrees_with_ai", sa.Boolean(), nullable=False),
        sa.Column("confirmed_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["ai_grade_id"],
            ["ai_grades.id"],
            name=op.f("fk_teacher_grades_ai_grade_id_ai_grades"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by"],
            ["users.id"],
            name=op.f("fk_teacher_grades_confirmed_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_teacher_grades_submission_id_submissions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teacher_grades")),
    )
    op.create_index(
        op.f("ix_teacher_grades_submission_id"), "teacher_grades", ["submission_id"], unique=False
    )
    op.add_column(
        "assessments",
        sa.Column(
            "analysis_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("assessments", "analysis_config")
    op.drop_index(op.f("ix_teacher_grades_submission_id"), table_name="teacher_grades")
    op.drop_table("teacher_grades")
    op.drop_index(op.f("ix_observations_submission_id"), table_name="observations")
    op.drop_table("observations")
    op.drop_index(
        op.f("ix_component_entry_versions_entry_id"), table_name="component_entry_versions"
    )
    op.drop_table("component_entry_versions")
    op.drop_table("component_settings")
    op.drop_index(op.f("ix_component_entries_course_id"), table_name="component_entries")
    op.drop_table("component_entries")
