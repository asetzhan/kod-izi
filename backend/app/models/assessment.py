"""Assessments (ФТ-02): tasks, time window, GenAI mode."""

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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import AssessmentKind, ContestFormat, GenAiMode, check_in
from app.db.base import Base


class Assessment(Base):
    __tablename__ = "assessments"
    __table_args__ = (
        CheckConstraint(check_in("genai_mode", GenAiMode), name="genai_mode_valid"),
        CheckConstraint("ends_at > starts_at", name="window_valid"),
        CheckConstraint(check_in("kind", AssessmentKind), name="kind_valid"),
        CheckConstraint(
            f"contest_format IS NULL OR {check_in('contest_format', ContestFormat)}",
            name="contest_format_valid",
        ),
        # ОТ-02: the AI assistant is off during a contest.
        CheckConstraint(
            "kind <> 'contest' OR (contest_format IS NOT NULL AND genai_mode = 'forbidden')",
            name="contest_valid",
        ),
        CheckConstraint(
            "freeze_minutes >= 0 AND penalty_minutes >= 0", name="contest_minutes_valid"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    genai_mode: Mapped[str] = mapped_column(String(16), default=GenAiMode.FORBIDDEN.value)
    kind: Mapped[str] = mapped_column(
        String(16), default=AssessmentKind.CONTROL.value, server_default="control"
    )
    # Contest settings (ОТ-02).
    contest_format: Mapped[str | None] = mapped_column(String(8))
    freeze_minutes: Mapped[int] = mapped_column(Integer, default=60, server_default="60")
    penalty_minutes: Mapped[int] = mapped_column(Integer, default=20, server_default="20")
    # ФТ-16: requirements for the whole assessment, added to those of each task.
    teacher_requirements: Mapped[str] = mapped_column(Text, default="", server_default="")
    # ФТ-36: which data and methods the analysis of this assessment uses.
    analysis_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task_links: Mapped[list["AssessmentTask"]] = relationship(
        order_by="AssessmentTask.position", cascade="all, delete-orphan", lazy="selectin"
    )


class AssessmentTask(Base):
    __tablename__ = "assessment_tasks"

    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), primary_key=True
    )
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
