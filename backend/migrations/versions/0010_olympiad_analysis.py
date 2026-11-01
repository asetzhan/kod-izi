"""Stage 7a: external accounts and solves (ОТ-08), rating history (ОТ-09), contest
analyses (ОТ-07).

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "external_accounts",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("handle", sa.String(length=64), nullable=False),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("max_rating", sa.Integer(), nullable=True),
        sa.Column("sync_status", sa.String(length=16), nullable=False),
        sa.Column("sync_error", sa.Text(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verify_token", sa.String(length=32), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_external_accounts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_accounts")),
        sa.UniqueConstraint("user_id", "platform", name=op.f("uq_external_accounts_user_id")),
    )
    # A handle belongs to one student: only one verified account per handle.
    op.execute(
        "CREATE UNIQUE INDEX uq_external_accounts_verified_handle ON external_accounts "
        "(platform, lower(handle)) WHERE verified_at IS NOT NULL"
    )
    op.create_index(
        op.f("ix_external_accounts_user_id"), "external_accounts", ["user_id"], unique=False
    )
    op.create_table(
        "external_solves",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("problem_key", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("solved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("verified_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('api', 'manual')", name=op.f("ck_external_solves_source_valid")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_external_solves_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["verified_by"],
            ["users.id"],
            name=op.f("fk_external_solves_verified_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_solves")),
        sa.UniqueConstraint(
            "user_id", "platform", "problem_key", name=op.f("uq_external_solves_user_id")
        ),
    )
    op.create_index(
        op.f("ix_external_solves_user_id"), "external_solves", ["user_id"], unique=False
    )
    op.create_table(
        "rating_points",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("contest", sa.String(length=300), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_rating_points_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rating_points")),
        sa.UniqueConstraint("user_id", "platform", "at", name=op.f("uq_rating_points_user_id")),
    )
    op.create_index(op.f("ix_rating_points_user_id"), "rating_points", ["user_id"], unique=False)
    op.create_table(
        "contest_analyses",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("assessment_id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("editorial_md", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("published", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_contest_analyses_assessment_id_assessments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_contest_analyses_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_contest_analyses_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contest_analyses")),
        sa.UniqueConstraint(
            "assessment_id", "task_id", name=op.f("uq_contest_analyses_assessment_id")
        ),
    )
    op.create_index(
        op.f("ix_contest_analyses_assessment_id"),
        "contest_analyses",
        ["assessment_id"],
        unique=False,
    )

    # A student's own rows (row-level security as in 0006).
    op.execute("ALTER TABLE external_accounts ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY external_accounts_owner ON external_accounts "
        "USING (app_privileged() OR user_id = app_user_id()) "
        "WITH CHECK (app_privileged() OR user_id = app_user_id())"
    )
    op.execute("ALTER TABLE external_solves ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY external_solves_owner ON external_solves "
        "USING (app_privileged() OR user_id = app_user_id()) "
        "WITH CHECK (app_privileged() OR user_id = app_user_id())"
    )
    op.execute("ALTER TABLE rating_points ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY rating_points_owner ON rating_points "
        "USING (app_privileged() OR user_id = app_user_id()) "
        "WITH CHECK (app_privileged() OR user_id = app_user_id())"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS external_accounts_owner ON external_accounts")
    op.execute("DROP POLICY IF EXISTS external_solves_owner ON external_solves")
    op.execute("DROP POLICY IF EXISTS rating_points_owner ON rating_points")
    op.drop_index(op.f("ix_contest_analyses_assessment_id"), table_name="contest_analyses")
    op.drop_table("contest_analyses")
    op.drop_index(op.f("ix_rating_points_user_id"), table_name="rating_points")
    op.drop_table("rating_points")
    op.drop_index(op.f("ix_external_solves_user_id"), table_name="external_solves")
    op.drop_table("external_solves")
    op.drop_index(op.f("ix_external_accounts_user_id"), table_name="external_accounts")
    op.drop_table("external_accounts")
