"""Value sets shared by models, API and services (glossary.md)."""

from enum import StrEnum


class TaskLevel(StrEnum):
    """Task complexity levels I–IV (spec 5.1; Q-04: IV is separate, for the olympiad part)."""

    I = "I"  # noqa: E741
    II = "II"
    III = "III"
    IV = "IV"


class LevelStatus(StrEnum):
    UNRATED = "unrated"
    SUGGESTED = "suggested"  # proposed by the rule or the LLM, not yet confirmed
    CONFIRMED = "confirmed"  # confirmed by a teacher (ФТ-19)


class TaskStatus(StrEnum):
    DRAFT = "draft"  # never shown to students (Q-07)
    APPROVED = "approved"


class GenAiMode(StrEnum):
    """AI assistant mode of an assessment (ФТ-02; the assistant itself is stage 3)."""

    FORBIDDEN = "forbidden"
    HINTS_ONLY = "hints_only"
    OPEN = "open"


class CoursePart(StrEnum):
    PART1 = "part1"  # C++ basics (spec 3)
    PART2 = "part2"  # olympiad preparation (spec 4)
    OTHER = "other"


class Verdict(StrEnum):
    """ФТ-31."""

    OK = "OK"
    WA = "WA"
    TLE = "TLE"
    MLE = "MLE"
    RE = "RE"
    CE = "CE"


class SubmissionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"  # the judge was unavailable; the student may submit again


class TraceKind(StrEnum):
    """Digital trace event kinds (ФТ-25, ФТ-29)."""

    SESSION_START = "session_start"
    SNAPSHOT = "snapshot"  # full code after a pause in typing
    PASTE = "paste"
    FOCUS_LOST = "focus_lost"
    FOCUS_BACK = "focus_back"
    COMPILE = "compile"
    RUN = "run"
    TEST = "test"
    SUBMIT = "submit"
    VERDICT = "verdict"
    EXPLANATION = "explanation"
    ANSWERS = "answers"
    SESSION_CLOSED = "session_closed"
    AI_REQUEST = "ai_request"  # ФТ-47, written by the server
    AI_RESPONSE = "ai_response"


class MaterialKind(StrEnum):
    BOOK = "book"
    LECTURE = "lecture"
    PROBLEMS = "problems"


class MaterialStatus(StrEnum):
    PENDING = "pending"  # uploaded, waiting for the antivirus and extraction
    READY = "ready"
    REJECTED = "rejected"  # antivirus or format check failed
    FAILED = "failed"  # text could not be extracted


class AiGradeStatus(StrEnum):
    READY = "ready"
    NEEDS_REVIEW = "needs_review"  # flagged for the teacher (invalid answer, injection, ...)
    FAILED = "failed"


class EntrySource(StrEnum):
    """Spec 6: «автоматты», «оқытушы», «автоматтыдан өзгертілген»."""

    AUTO = "auto"
    TEACHER = "teacher"
    AUTO_EDITED = "auto_edited"


def check_in(column: str, values: type[StrEnum]) -> str:
    return f"{column} IN ({', '.join(repr(v.value) for v in values)})"
