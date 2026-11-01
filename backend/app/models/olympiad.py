"""Olympiad part (spec 4, 10): contest participations, own tests, module references."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import ParticipationKind, check_in
from app.db.base import Base


class ContestParticipation(Base):
    """ОТ-02, ОТ-03: a student in a contest; a virtual one has its own start."""

    __tablename__ = "contest_participations"
    __table_args__ = (
        UniqueConstraint("assessment_id", "user_id", "kind"),
        CheckConstraint(check_in("kind", ParticipationKind), name="kind_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StudentTest(Base):
    """ОТ-06: a test the student keeps for a problem (input and, optionally, the answer)."""

    __tablename__ = "student_tests"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    input: Mapped[str] = mapped_column(Text)
    expected_output: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TopicResource(Base):
    """ОТ-10: additional material of a module (e-maxx, USACO Guide, ...): link only."""

    __tablename__ = "topic_resources"
    __table_args__ = (UniqueConstraint("topic_id", "url"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(500))
    purpose: Mapped[str] = mapped_column(Text, default="", server_default="")
    position: Mapped[int] = mapped_column(Integer, default=0)


class SimilarityReport(Base):
    """ФТ-30: code similarity of an assessment's submissions (JPlag in an isolated worker)."""

    __tablename__ = "similarity_reports"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'done', 'failed')", name="status_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    engine: Mapped[str] = mapped_column(String(32), default="")
    # [{"a": user_id, "b": user_id, "similarity": 0.0–1.0}, ...], highest first.
    pairs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExternalAccount(Base):
    """ОТ-08: a student's account on an external platform (Codeforces), linked with their
    own consent (Q-18). Only the handle leaves the system."""

    __tablename__ = "external_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "platform"),
        Index(
            "uq_external_accounts_verified_handle",
            "platform",
            func.lower(text("handle")),
            unique=True,
            postgresql_where=text("verified_at IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(16))
    handle: Mapped[str] = mapped_column(String(64))
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    rating: Mapped[int | None] = mapped_column(Integer)
    max_rating: Mapped[int | None] = mapped_column(Integer)
    sync_status: Mapped[str] = mapped_column(String(16), default="pending")
    sync_error: Mapped[str | None] = mapped_column(Text)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The student proves the handle is theirs by putting this token in their Codeforces
    # profile (first name, last name or organization); nothing is gathered before that.
    verify_token: Mapped[str] = mapped_column(String(32))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExternalSolve(Base):
    """ОТ-08: a problem solved on an external platform, gathered from its API or marked by
    the student with a link (then a coach may verify it)."""

    __tablename__ = "external_solves"
    __table_args__ = (
        UniqueConstraint("user_id", "platform", "problem_key"),
        CheckConstraint("source IN ('api', 'manual')", name="source_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(16))
    problem_key: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(300), default="")
    url: Mapped[str] = mapped_column(String(500))
    rating: Mapped[int | None] = mapped_column(Integer)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    solved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(8))
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RatingPoint(Base):
    """ОТ-09: the student's rating after each rated contest on an external platform."""

    __tablename__ = "rating_points"
    __table_args__ = (UniqueConstraint("user_id", "platform", "at"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(16))
    contest: Mapped[str] = mapped_column(String(300), default="")
    rating: Mapped[int] = mapped_column(Integer)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ContestAnalysis(Base):
    """ОТ-07: the AI's analysis (editorial) of a contest problem, shown after the contest
    once a coach publishes it; marked as AI-written."""

    __tablename__ = "contest_analyses"
    __table_args__ = (UniqueConstraint("assessment_id", "task_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    editorial_md: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(64))
    published: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
