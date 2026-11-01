"""Olympiad part (spec 4, 10): contest participations, own tests, module references."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    UniqueConstraint,
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
