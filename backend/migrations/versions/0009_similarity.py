"""Stage 6b part 2: code similarity reports (ФТ-30), staff only.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "similarity_reports",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("assessment_id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("engine", sa.String(length=32), nullable=False),
        sa.Column(
            "pairs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'done', 'failed')",
            name=op.f("ck_similarity_reports_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_similarity_reports_assessment_id_assessments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_similarity_reports_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_similarity_reports_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_similarity_reports")),
    )
    op.create_index(
        op.f("ix_similarity_reports_assessment_id"),
        "similarity_reports",
        ["assessment_id"],
        unique=False,
    )
    # Pairs of students' names are for staff only (row-level security as in 0006).
    op.execute("ALTER TABLE similarity_reports ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY similarity_reports_staff ON similarity_reports "
        "USING (app_privileged()) WITH CHECK (app_privileged())"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS similarity_reports_staff ON similarity_reports")
    op.drop_index(op.f("ix_similarity_reports_assessment_id"), table_name="similarity_reports")
    op.drop_table("similarity_reports")
