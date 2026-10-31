"""Stage 4: model components panel, teacher grades, observations (spec 6).

ФТ-03, ФТ-07, ФТ-09, ФТ-14, ФТ-36, ФТ-41, ФТ-42, ФТ-43.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import EntrySource, check_in
from app.db.base import Base


class ComponentEntry(Base):
    """One piece of a model component (spec 6).

    `auto_value` is what the system produced last; `value` is what is in force. They
    are kept apart (spec 6: «Автоматты мән мен оқытушының соңғы мәні бөлек сақталады»).
    When the teacher owns the value, regeneration only fills `suggestion`.
    """

    __tablename__ = "component_entries"
    __table_args__ = (
        CheckConstraint("component BETWEEN 1 AND 5", name="component_range"),
        CheckConstraint(check_in("source", EntrySource), name="source_valid"),
        UniqueConstraint("component", "subject_type", "subject_id", "key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    component: Mapped[int] = mapped_column(SmallInteger)
    subject_type: Mapped[str] = mapped_column(String(16))  # course, topic, task, submission
    subject_id: Mapped[int] = mapped_column(BigInteger)
    key: Mapped[str] = mapped_column(String(64))
    value: Mapped[Any] = mapped_column(JSONB)
    auto_value: Mapped[Any | None] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(String(16))
    suggestion: Mapped[Any | None] = mapped_column(JSONB)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    versions: Mapped[list["ComponentEntryVersion"]] = relationship(
        order_by="ComponentEntryVersion.version", cascade="all, delete-orphan", lazy="selectin"
    )


class ComponentEntryVersion(Base):
    """Every change: who, when, what (spec 6). Never edited, only added."""

    __tablename__ = "component_entry_versions"
    __table_args__ = (UniqueConstraint("entry_id", "version"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("component_entries.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    value: Mapped[Any] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(String(16))
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ComponentSetting(Base):
    """The teacher may switch off automatic filling of a component (spec 6)."""

    __tablename__ = "component_settings"

    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True
    )
    component: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    auto_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())


class TeacherGrade(Base):
    """ФТ-03: the teacher's grade. The AI grade it started from is kept unchanged."""

    __tablename__ = "teacher_grades"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), index=True
    )
    ai_grade_id: Mapped[int | None] = mapped_column(ForeignKey("ai_grades.id", ondelete="SET NULL"))
    criteria: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)  # [{code, level}]
    component_f: Mapped[float] = mapped_column(Float)
    component_e: Mapped[float] = mapped_column(Float)
    component_a: Mapped[float] = mapped_column(Float)
    score: Mapped[float] = mapped_column(Float)
    feedback: Mapped[str] = mapped_column(Text)
    # Where the feedback text came from: ai, ai_edited, teacher (ФТ-41: AI text is marked).
    feedback_source: Mapped[str] = mapped_column(String(16))
    book_refs: Mapped[list[str]] = mapped_column(JSONB, default=list)  # ФТ-42
    next_step: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text, default="")  # why the AI grade was corrected
    agrees_with_ai: Mapped[bool] = mapped_column(Boolean)
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Observation(Base):
    """ФТ-36: the teacher's own observation (e.g. oral defence) or a comment on a signal."""

    __tablename__ = "observations"
    __table_args__ = (
        CheckConstraint("level IS NULL OR level IN ('low', 'mid', 'high')", name="level_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))  # oral_defense, signal_comment, note
    signal: Mapped[str | None] = mapped_column(String(64))
    criterion: Mapped[str | None] = mapped_column(String(32))
    level: Mapped[str | None] = mapped_column(String(4))
    text: Mapped[str] = mapped_column(Text)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
