"""The core of the model: the student's programming activity (ФТ-24, ФТ-25, ФТ-27, ФТ-31)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import SubmissionStatus, TraceKind, Verdict, check_in
from app.db.base import Base


class WorkSession(Base):
    """One editor session of a student on a task. In an assessment only one is active."""

    __tablename__ = "work_sessions"
    __table_args__ = (
        Index(
            "uq_work_sessions_one_active",
            "user_id",
            "assessment_id",
            unique=True,
            postgresql_where=text("closed_at IS NULL AND assessment_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_reason: Mapped[str | None] = mapped_column(String(32))
    user_agent: Mapped[str | None] = mapped_column(String(255))


class TraceEvent(Base):
    """Digital trace (ФТ-25). Append-only: a database trigger rejects UPDATE and DELETE.

    Browser events carry the client's sequence number, so a resent batch is not stored
    twice; events written by the server (compile, run, submit) have no sequence number.
    """

    __tablename__ = "trace_events"
    __table_args__ = (
        CheckConstraint(check_in("kind", TraceKind), name="kind_valid"),
        Index(
            "uq_trace_events_session_seq",
            "session_id",
            "seq",
            unique=True,
            postgresql_where=text("seq IS NOT NULL"),
        ),
        Index("ix_trace_events_session_time", "session_id", "server_ts"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_sessions.id", ondelete="RESTRICT")
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"), index=True)
    assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("assessments.id", ondelete="RESTRICT"), index=True
    )
    seq: Mapped[int | None] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(24))
    # Cycle stage (understand, plan, code, test, debug, explain) is labelled in stage 6b.
    stage: Mapped[str | None] = mapped_column(String(16))
    client_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    server_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Academic integrity mark (ФТ-29), computed on insert. Shown to teachers only.
    flagged: Mapped[bool] = mapped_column(default=False, server_default=text("false"))


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        CheckConstraint(check_in("status", SubmissionStatus), name="status_valid"),
        CheckConstraint(f"verdict IS NULL OR {check_in('verdict', Verdict)}", name="verdict_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_sessions.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"), index=True)
    assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("assessments.id", ondelete="RESTRICT"), index=True
    )
    code: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default=SubmissionStatus.QUEUED.value)
    verdict: Mapped[str | None] = mapped_column(String(4))
    tests_passed: Mapped[int] = mapped_column(Integer, default=0)
    tests_total: Mapped[int] = mapped_column(Integer, default=0)
    max_time_ms: Mapped[int | None] = mapped_column(Integer)
    max_memory_kb: Mapped[int | None] = mapped_column(Integer)
    compile_output: Mapped[str] = mapped_column(Text, default="", server_default="")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    results: Mapped[list["SubmissionTestResult"]] = relationship(
        order_by="SubmissionTestResult.position", cascade="all, delete-orphan", lazy="selectin"
    )
    explanation: Mapped["Explanation | None"] = relationship(
        back_populates="submission", lazy="selectin", uselist=False
    )


class SubmissionTestResult(Base):
    __tablename__ = "submission_test_results"
    __table_args__ = (CheckConstraint(check_in("verdict", Verdict), name="verdict_valid"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), index=True
    )
    test_case_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_cases.id", ondelete="SET NULL")
    )
    position: Mapped[int] = mapped_column(Integer)
    is_hidden: Mapped[bool] = mapped_column()
    verdict: Mapped[str] = mapped_column(String(4))
    time_ms: Mapped[int | None] = mapped_column(Integer)
    memory_kb: Mapped[int | None] = mapped_column(Integer)
    # Program output, kept for the teacher and the analysis; truncated.
    stdout: Mapped[str] = mapped_column(Text, default="", server_default="")
    stderr: Mapped[str] = mapped_column(Text, default="", server_default="")


class Explanation(Base):
    """ФТ-27: the student's explanation and answers to questions about their own code."""

    __tablename__ = "explanations"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), unique=True
    )
    text: Mapped[str] = mapped_column(Text)
    # [{"question": str, "answer": str | null}]
    questions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    question_source: Mapped[str] = mapped_column(String(32))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    submission: Mapped[Submission] = relationship(back_populates="explanation")
