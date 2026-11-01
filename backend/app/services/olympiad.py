"""Olympiad practice (spec 4, 10): access to part 2, the student's rating, recommendations
(ОТ-04) and the "one hour" rule (ОТ-05).

The coach's advice: spend at least an hour on a problem before reading the tutorial, and
pick problems slightly above your level.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import CoursePart, TaskStatus, Verdict
from app.models import (
    AiMessage,
    AppSetting,
    Course,
    CourseGroup,
    GroupMember,
    Submission,
    Task,
    User,
    WorkSession,
)
from app.services.access import is_staff
from app.services.results import mastery

OLYMPIAD_KEY = "olympiad"
PART1_STEPIK_ID = 363
HINT_LEVELS = 3  # direction, idea, pseudocode (ОТ-05)


class OlympiadSettings(BaseModel):
    """Changed by an administrator or a coach; defaults follow spec 4 and 10."""

    # Part 2 opens when these part 1 topics are mastered (empty: open to everyone).
    unlock_topics: list[str] = Field(default=["1.11", "1.12"], max_length=20)
    # ОТ-04: recommended problems are this much above the student's rating.
    recommend_min: int = Field(default=100, ge=-1000, le=1000)
    recommend_max: int = Field(default=300, ge=-1000, le=1500)
    start_rating: int = Field(default=800, ge=800, le=3500)
    # ОТ-05: minutes on a problem before the tutorial opens.
    editorial_after_minutes: int = Field(default=60, ge=0, le=600)
    # ОТ-05: minutes between two hint steps.
    hint_step_minutes: int = Field(default=15, ge=0, le=240)


def get_olympiad_settings(db: Session) -> OlympiadSettings:
    stored = db.get(AppSetting, OLYMPIAD_KEY)
    return OlympiadSettings.model_validate(stored.value if stored else {})


def resources_seed() -> dict[str, Any]:
    path = get_settings().seed_dir / "olympiad_resources.json"
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


# Access ------------------------------------------------------------------------------------


def part2_courses(db: Session, user: User) -> list[Course]:
    """Part 2 courses the user may open: staff see all, students those of their groups."""
    query = select(Course).where(Course.part == CoursePart.PART2.value).order_by(Course.id)
    if not is_staff(user):
        mine = (
            select(CourseGroup.course_id)
            .join(GroupMember, GroupMember.group_id == CourseGroup.group_id)
            .where(GroupMember.user_id == user.id)
        )
        query = query.where(Course.id.in_(mine))
    return list(db.scalars(query))


def unlock_state(db: Session, user: User) -> dict[str, Any]:
    """Spec 4: part 2 opens when topics 1.11 and 1.12 of part 1 are mastered (K ≥ 0,7)."""
    settings = get_olympiad_settings(db)
    if is_staff(user) or not settings.unlock_topics:
        return {"unlocked": True, "required": settings.unlock_topics, "missing": []}
    part1 = db.scalar(select(Course).where(Course.stepik_course_id == PART1_STEPIK_ID))
    missing = list(settings.unlock_topics)
    if part1 is not None:
        codes = {t.id: t.code for t in part1.topics}
        rows: dict[str, list[bool]] = {}
        for row in mastery(db, part1.id, user.id):
            code = codes.get(row["topic_id"])
            if code is not None:
                rows.setdefault(code, []).append(bool(row["mastered"]))
        missing = [c for c in settings.unlock_topics if not (rows.get(c) and all(rows[c]))]
    return {"unlocked": not missing, "required": settings.unlock_topics, "missing": missing}


def can_practice(db: Session, user: User, task: Task) -> bool:
    """A student practises approved problems of an unlocked part 2 course they study."""
    if is_staff(user):
        return True
    course = db.get(Course, task.course_id)
    return (
        course is not None
        and course.part == CoursePart.PART2.value
        and task.status == TaskStatus.APPROVED.value
        and course in part2_courses(db, user)
        and bool(unlock_state(db, user)["unlocked"])
    )


# Rating and recommendations (ОТ-04) --------------------------------------------------------


def solved_task_ids(db: Session, user_id: int) -> set[int]:
    return set(
        db.scalars(
            select(Submission.task_id)
            .where(Submission.user_id == user_id, Submission.verdict == Verdict.OK.value)
            .distinct()
        )
    )


def rating(db: Session, user_id: int, settings: OlympiadSettings) -> int:
    """Mean Codeforces rating of the five hardest solved problems, never below the start.

    A simple estimate until Codeforces accounts are linked (ОТ-08, stage 3 of part 2)."""
    solved = solved_task_ids(db, user_id)
    ratings = sorted(
        (
            r
            for r in db.scalars(
                select(Task.cf_rating).where(Task.id.in_(solved), Task.cf_rating.is_not(None))
            )
            if r is not None
        ),
        reverse=True,
    )[:5]
    if not ratings:
        return settings.start_rating
    return max(settings.start_rating, round(sum(ratings) / len(ratings) / 10) * 10)


def bank(db: Session, user: User) -> list[Task]:
    """Approved problems of the part 2 courses the user may open."""
    course_ids = [c.id for c in part2_courses(db, user)]
    return list(
        db.scalars(
            select(Task)
            .where(Task.course_id.in_(course_ids), Task.status == TaskStatus.APPROVED.value)
            .order_by(Task.cf_rating.nulls_last(), Task.id)
        )
    )


def recommend(db: Session, user: User, limit: int = 10) -> dict[str, Any]:
    """Unsolved problems rated slightly above the student, weak topics first."""
    settings = get_olympiad_settings(db)
    current = rating(db, user.id, settings)
    solved = solved_task_ids(db, user.id)
    problems = bank(db, user)
    by_topic: dict[int | None, list[Task]] = {}
    for task in problems:
        by_topic.setdefault(task.topic_id, []).append(task)
    topic_share = {
        topic: sum(1 for t in tasks if t.id in solved) / len(tasks)
        for topic, tasks in by_topic.items()
    }
    low, high = current + settings.recommend_min, current + settings.recommend_max
    picked = [
        t
        for t in problems
        if t.id not in solved and t.cf_rating is not None and low <= t.cf_rating <= high
    ]
    picked.sort(key=lambda t: (topic_share[t.topic_id], t.cf_rating or 0, t.id))
    return {"rating": current, "range": [low, high], "tasks": picked[:limit]}


# The "one hour" rule (ОТ-05) ---------------------------------------------------------------


def first_opened(db: Session, user_id: int, task_id: int) -> datetime | None:
    started: datetime | None = db.scalar(
        select(func.min(WorkSession.started_at)).where(
            WorkSession.user_id == user_id, WorkSession.task_id == task_id
        )
    )
    return started


@dataclass(frozen=True)
class EditorialState:
    available: bool
    minutes_spent: int
    opens_at: datetime | None


def editorial_state(
    db: Session, user: User, task: Task, now: datetime | None = None
) -> EditorialState:
    """The tutorial opens an hour after the student first opened the problem, or once
    they solved it. Staff always see it."""
    now = now or datetime.now(UTC)
    settings = get_olympiad_settings(db)
    started = first_opened(db, user.id, task.id)
    spent = int((now - started).total_seconds() // 60) if started else 0
    opens_at = started + timedelta(minutes=settings.editorial_after_minutes) if started else None
    available = (
        is_staff(user)
        or task.id in solved_task_ids(db, user.id)
        or (opens_at is not None and now >= opens_at)
    )
    return EditorialState(available, spent, None if available else opens_at)


def hints_given(db: Session, user_id: int, task_id: int) -> list[AiMessage]:
    return list(
        db.scalars(
            select(AiMessage)
            .where(
                AiMessage.user_id == user_id,
                AiMessage.task_id == task_id,
                AiMessage.hint_level.is_not(None),
            )
            .order_by(AiMessage.id)
        )
    )


def next_hint(
    db: Session, user: User, task: Task, now: datetime | None = None
) -> tuple[int | None, datetime | None]:
    """The next hint step and when it opens: steps go in order, `hint_step_minutes` apart."""
    now = now or datetime.now(UTC)
    settings = get_olympiad_settings(db)
    given = hints_given(db, user.id, task.id)
    if len(given) >= HINT_LEVELS:
        return None, None
    if not given:
        return 1, None
    opens = given[-1].created_at + timedelta(minutes=settings.hint_step_minutes)
    return len(given) + 1, (opens if now < opens else None)
