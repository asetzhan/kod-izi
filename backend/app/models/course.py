"""Course structure (model component 1; ФТ-01, ФТ-08, ФТ-12)."""

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
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import CoursePart, check_in
from app.db.base import Base


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (CheckConstraint(check_in("part", CoursePart), name="part_valid"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    part: Mapped[str] = mapped_column(String(16), default=CoursePart.OTHER.value)
    # Source course on Stepik; seeded courses are matched on it.
    stepik_course_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    source_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    topics: Mapped[list["Topic"]] = relationship(
        back_populates="course",
        order_by="Topic.position",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class CourseTeacher(Base):
    """Teachers who manage a course and its tasks."""

    __tablename__ = "course_teachers"

    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class CourseGroup(Base):
    """Groups studying a course (ФТ-01)."""

    __tablename__ = "course_groups"

    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (UniqueConstraint("course_id", "code"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer, default=0)
    learning_outcomes: Mapped[str] = mapped_column(Text, default="", server_default="")

    course: Mapped[Course] = relationship(back_populates="topics")
    lessons: Mapped[list["ExternalLesson"]] = relationship(
        order_by="ExternalLesson.position", cascade="all, delete-orphan", lazy="selectin"
    )
    knowledge_components: Mapped[list["KnowledgeComponent"]] = relationship(
        order_by="KnowledgeComponent.position", cascade="all, delete-orphan", lazy="selectin"
    )


class ExternalLesson(Base):
    """A Stepik lesson: link only, its content is not copied (Q-05)."""

    __tablename__ = "external_lessons"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    stepik_lesson_id: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(32), default="lecture_and_practice")
    position: Mapped[int] = mapped_column(Integer, default=0)


class KnowledgeComponent(Base):
    __tablename__ = "knowledge_components"
    __table_args__ = (UniqueConstraint("topic_id", "code"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(300))
    position: Mapped[int] = mapped_column(Integer, default=0)
