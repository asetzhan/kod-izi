"""Stage 3: rubric, teaching materials, AI grades, assistant log, LLM usage.

ФТ-06, ФТ-11, ФТ-13, ФТ-15, ФТ-16, ФТ-34, ФТ-35, ФТ-46, ФТ-47, ФТ-48.
"""

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import AiGradeStatus, MaterialKind, MaterialStatus, check_in
from app.db.base import Base

EMBEDDING_DIM = 1024  # bge-m3, the multilingual model named in spec 11


class Rubric(Base):
    """ФТ-13, ФТ-15: one rubric per course, filled from seed/rubric_default.json."""

    __tablename__ = "rubrics"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), unique=True
    )
    weight_f: Mapped[float] = mapped_column(Float)
    weight_e: Mapped[float] = mapped_column(Float)
    weight_a: Mapped[float] = mapped_column(Float)
    # Descriptions of the 0–100 scales for F, E, A given to the LLM (Q-10: draft).
    component_scales: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    criteria: Mapped[list["RubricCriterion"]] = relationship(
        order_by="RubricCriterion.position", cascade="all, delete-orphan", lazy="selectin"
    )


class RubricCriterion(Base):
    __tablename__ = "rubric_criteria"
    __table_args__ = (UniqueConstraint("rubric_id", "code"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    rubric_id: Mapped[int] = mapped_column(ForeignKey("rubrics.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(32))
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    indicators: Mapped[str] = mapped_column(Text, default="")
    data_sources: Mapped[str] = mapped_column(Text, default="")
    descriptor_low: Mapped[str] = mapped_column(Text)
    descriptor_mid: Mapped[str] = mapped_column(Text)
    descriptor_high: Mapped[str] = mapped_column(Text)


class Material(Base):
    """ФТ-06: a book, lecture or problem collection of one course."""

    __tablename__ = "materials"
    __table_args__ = (CheckConstraint(check_in("kind", MaterialKind), name="kind_valid"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    author: Mapped[str] = mapped_column(String(300), default="")
    kind: Mapped[str] = mapped_column(String(16))
    # Q-11: the uploading teacher confirms the right to use the material.
    rights_confirmed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    rights_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    versions: Mapped[list["MaterialVersion"]] = relationship(
        order_by="MaterialVersion.version", cascade="all, delete-orphan", lazy="selectin"
    )


class MaterialVersion(Base):
    """A file of a material. Grades keep the version they relied on (spec 9.4)."""

    __tablename__ = "material_versions"
    __table_args__ = (
        CheckConstraint(check_in("status", MaterialStatus), name="status_valid"),
        UniqueConstraint("material_id", "version"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    material_id: Mapped[int] = mapped_column(
        ForeignKey("materials.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(80))
    mime: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default=MaterialStatus.PENDING.value)
    error: Mapped[str | None] = mapped_column(Text)
    pages: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Chunk(Base):
    """A fragment of a material version with its place in the book (ФТ-35)."""

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("material_versions.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    chapter: Mapped[str] = mapped_column(String(300), default="")
    page: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))


class MaterialBinding(Base):
    """ФТ-11, ФТ-16: chapters/pages of a material bound to a topic, task or assessment."""

    __tablename__ = "material_bindings"
    __table_args__ = (
        CheckConstraint("num_nonnulls(topic_id, task_id, assessment_id) = 1", name="one_target"),
        CheckConstraint(
            "page_from IS NULL OR page_to IS NULL OR page_from <= page_to", name="page_range"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    material_id: Mapped[int] = mapped_column(
        ForeignKey("materials.id", ondelete="CASCADE"), index=True
    )
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE")
    )
    chapter: Mapped[str] = mapped_column(String(300), default="")
    page_from: Mapped[int | None] = mapped_column(Integer)
    page_to: Mapped[int | None] = mapped_column(Integer)
    is_assessment_basis: Mapped[bool] = mapped_column(default=False, server_default=false())
    requirements: Mapped[str] = mapped_column(Text, default="", server_default="")


class AiGrade(Base):
    """ФТ-34, ФТ-35, ФТ-48: the preliminary AI grade. Never shown to the student before
    the teacher confirms it (stage 4)."""

    __tablename__ = "ai_grades"
    __table_args__ = (CheckConstraint(check_in("status", AiGradeStatus), name="status_valid"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(16))
    criteria: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    component_f: Mapped[float | None] = mapped_column(Float)
    component_e: Mapped[float | None] = mapped_column(Float)
    component_a: Mapped[float | None] = mapped_column(Float)
    score: Mapped[float | None] = mapped_column(Float)
    interpretation: Mapped[str] = mapped_column(Text, default="")
    feedback: Mapped[str] = mapped_column(Text, default="")
    next_step: Mapped[str] = mapped_column(Text, default="")
    flags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    review_reasons: Mapped[list[str]] = mapped_column(JSONB, default=list)
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(64))
    weights: Mapped[dict[str, float]] = mapped_column(JSONB, default=dict)
    # Material versions the cited fragments came from (spec 9.4).
    fragment_ids: Mapped[list[int]] = mapped_column(JSONB, default=list)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    raw_response: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AiMessage(Base):
    """ФТ-47: every request to the AI assistant and its answer."""

    __tablename__ = "ai_messages"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    session_id: Mapped[Any] = mapped_column(
        ForeignKey("work_sessions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), index=True
    )
    mode: Mapped[str] = mapped_column(String(16))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    # hints_only: the model's answer contained ready code and was withheld.
    blocked: Mapped[bool] = mapped_column(default=False, server_default=false())
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LlmUsage(Base):
    """Every LLM call, for quotas and cost monitoring (spec 14.1, "LLM ресурсы")."""

    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
