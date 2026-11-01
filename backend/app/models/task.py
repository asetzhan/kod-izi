"""Task bank (model component 3; ФТ-10, ФТ-18, ФТ-19)."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    SmallInteger,
    String,
    Text,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import LevelStatus, TaskLevel, TaskStatus, check_in
from app.db.base import Base

FEATURE_CODES = ("knowledge_actions", "algorithm_freedom", "edge_cases", "justification")


def _feature_check(code: str) -> CheckConstraint:
    return CheckConstraint(f"feat_{code} BETWEEN 0 AND 2", name=f"feat_{code}_range")


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(f"level IS NULL OR {check_in('level', TaskLevel)}", name="level_valid"),
        CheckConstraint(check_in("level_status", LevelStatus), name="level_status_valid"),
        CheckConstraint(check_in("status", TaskStatus), name="status_valid"),
        *(_feature_check(code) for code in FEATURE_CODES),
        CheckConstraint(
            "memory_limit_kb BETWEEN 16384 AND 1048576", name="memory_limit_range"
        ),  # ОТ-01: from 16 MB (ACMP) to 1024 MB (ICPC)
        CheckConstraint(
            "cf_rating IS NULL OR cf_rating BETWEEN 800 AND 3500", name="cf_rating_range"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"), index=True
    )
    # Stable key for seeded and imported tasks, e.g. EXP-I-1.
    external_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    statement_md: Mapped[str] = mapped_column(Text)
    input_format: Mapped[str] = mapped_column(Text, default="", server_default="")
    output_format: Mapped[str] = mapped_column(Text, default="", server_default="")
    time_limit_ms: Mapped[int] = mapped_column(Integer, default=1000)
    memory_limit_kb: Mapped[int] = mapped_column(Integer, default=262144)
    reference_solution: Mapped[str] = mapped_column(Text, default="", server_default="")
    reference_language: Mapped[str] = mapped_column(String(16), default="cpp17")
    source_url: Mapped[str | None] = mapped_column(String(500))
    source_note: Mapped[str] = mapped_column(Text, default="", server_default="")
    # ФТ-16: the teacher's book-based requirements (required method, style, banned tools).
    teacher_requirements: Mapped[str] = mapped_column(Text, default="", server_default="")

    # Level features (spec 5.2), 0–2 each. NULL until suggested or set.
    feat_knowledge_actions: Mapped[int | None] = mapped_column(SmallInteger)
    feat_algorithm_freedom: Mapped[int | None] = mapped_column(SmallInteger)
    feat_edge_cases: Mapped[int | None] = mapped_column(SmallInteger)
    feat_justification: Mapped[int | None] = mapped_column(SmallInteger)
    level_rationale: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Olympiad bank (ОТ-01): topic tags and Codeforces difficulty rating.
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    cf_rating: Mapped[int | None] = mapped_column(Integer)
    # ОТ-05: the tutorial, shown after the student spent an hour on the problem.
    editorial_md: Mapped[str] = mapped_column(Text, default="", server_default="")
    # ОТ-02, IOI: points per subtask ("1": 30, "2": 70); empty means per test.
    subtask_points: Mapped[dict[str, int]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    level: Mapped[str | None] = mapped_column(String(3))
    level_status: Mapped[str] = mapped_column(String(16), default=LevelStatus.UNRATED.value)

    status: Mapped[str] = mapped_column(String(16), default=TaskStatus.DRAFT.value)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tests: Mapped[list["TestCase"]] = relationship(
        order_by="TestCase.position", cascade="all, delete-orphan", lazy="selectin"
    )
    kc_links: Mapped[list["TaskKnowledgeComponent"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )

    def features(self) -> dict[str, int | None]:
        return {code: getattr(self, f"feat_{code}") for code in FEATURE_CODES}

    def set_features(self, scores: dict[str, int]) -> None:
        for code in FEATURE_CODES:
            setattr(self, f"feat_{code}", scores[code])


class TestCase(Base):
    __tablename__ = "test_cases"
    __test__ = False  # not a pytest class

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    input: Mapped[str] = mapped_column(Text)
    expected_output: Mapped[str] = mapped_column(Text)
    # Hidden tests never leave the server for students (spec 14.1).
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=True, server_default=false())
    # IOI subtask the test belongs to (ОТ-02).
    subtask: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")


class TaskKnowledgeComponent(Base):
    """ФТ-10: a task is linked to one or more knowledge components."""

    __tablename__ = "task_knowledge_components"

    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    knowledge_component_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_components.id", ondelete="CASCADE"), primary_key=True, index=True
    )
