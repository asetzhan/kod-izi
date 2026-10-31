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


def check_in(column: str, values: type[StrEnum]) -> str:
    return f"{column} IN ({', '.join(repr(v.value) for v in values)})"
