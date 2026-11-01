"""Stage 6b: individual assignments (ФТ-05) and graded works as rubric examples (ФТ-17).

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_assignments",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("assigned_by", sa.BigInteger(), nullable=True),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column("genai_mode", sa.String(length=16), server_default="hints_only", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "genai_mode IN ('forbidden', 'hints_only', 'open')",
            name=op.f("ck_task_assignments_genai_mode_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by"],
            ["users.id"],
            name=op.f("fk_task_assignments_assigned_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_task_assignments_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_task_assignments_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_assignments")),
        sa.UniqueConstraint("task_id", "user_id", name=op.f("uq_task_assignments_task_id")),
    )
    op.create_index(
        op.f("ix_task_assignments_task_id"), "task_assignments", ["task_id"], unique=False
    )
    op.create_index(
        op.f("ix_task_assignments_user_id"), "task_assignments", ["user_id"], unique=False
    )
    op.create_table(
        "rubric_examples",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("course_id", sa.BigInteger(), nullable=False),
        sa.Column("submission_id", sa.BigInteger(), nullable=False),
        sa.Column("criterion_code", sa.String(length=32), nullable=False),
        sa.Column("level", sa.String(length=8), nullable=False),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column("added_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "level IN ('low', 'mid', 'high')", name=op.f("ck_rubric_examples_level_valid")
        ),
        sa.ForeignKeyConstraint(
            ["added_by"],
            ["users.id"],
            name=op.f("fk_rubric_examples_added_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_rubric_examples_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_rubric_examples_submission_id_submissions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rubric_examples")),
        sa.UniqueConstraint(
            "submission_id", "criterion_code", name=op.f("uq_rubric_examples_submission_id")
        ),
    )
    op.create_index(
        op.f("ix_rubric_examples_course_id"), "rubric_examples", ["course_id"], unique=False
    )
    # Row-level security as in 0006: a student reads only their own assignments; the
    # examples (other students' graded code) are for staff only.
    op.execute("ALTER TABLE task_assignments ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY task_assignments_owner ON task_assignments "
        "USING (app_privileged() OR user_id = app_user_id()) "
        "WITH CHECK (app_privileged())"
    )
    op.execute("ALTER TABLE rubric_examples ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY rubric_examples_staff ON rubric_examples "
        "USING (app_privileged()) WITH CHECK (app_privileged())"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS rubric_examples_staff ON rubric_examples")
    op.execute("DROP POLICY IF EXISTS task_assignments_owner ON task_assignments")
    op.drop_index(op.f("ix_rubric_examples_course_id"), table_name="rubric_examples")
    op.drop_table("rubric_examples")
    op.drop_index(op.f("ix_task_assignments_user_id"), table_name="task_assignments")
    op.drop_index(op.f("ix_task_assignments_task_id"), table_name="task_assignments")
    op.drop_table("task_assignments")
