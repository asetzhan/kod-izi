"""Assessments (ФТ-02): tasks, time window, GenAI mode."""

from datetime import datetime

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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import GenAiMode, check_in
from app.db.base import Base


class Assessment(Base):
    __tablename__ = "assessments"
    __table_args__ = (
        CheckConstraint(check_in("genai_mode", GenAiMode), name="genai_mode_valid"),
        CheckConstraint("ends_at > starts_at", name="window_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    genai_mode: Mapped[str] = mapped_column(String(16), default=GenAiMode.FORBIDDEN.value)
    # ФТ-16: requirements for the whole assessment, added to those of each task.
    teacher_requirements: Mapped[str] = mapped_column(Text, default="", server_default="")
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
