"""Next task (ФТ-44) and the student's trajectory (ФТ-45).

Spec 5.3: the next task comes from the level after the mastered one, or by the weakest
criterion; the student model (ФТ-39) says which knowledge components are not mastered.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import TaskLevel, TaskStatus, Verdict
from app.models import (
    Assessment,
    Course,
    Submission,
    Task,
    TaskKnowledgeComponent,
    TeacherGrade,
    Topic,
)
from app.services.contests import in_unfinished_assessment
from app.services.results import mastery
from app.services.student_model import student_model

LEVEL_SCORE = {"low": 0, "mid": 1, "high": 2}
LEVELS = [level.value for level in TaskLevel]


def confirmed_grades(
    db: Session, course_id: int, user_id: int
) -> list[tuple[Submission, TeacherGrade]]:
    """The latest confirmed grade of each graded submission of the course, oldest first."""
    rows = db.execute(
        select(Submission, TeacherGrade)
        .join(TeacherGrade, TeacherGrade.submission_id == Submission.id)
        .join(Task, Task.id == Submission.task_id)
        .where(Submission.user_id == user_id, Task.course_id == course_id)
        .order_by(TeacherGrade.confirmed_at, TeacherGrade.id)
    ).all()
    latest: dict[int, tuple[Submission, TeacherGrade]] = {}
    for submission, grade in rows:
        latest[submission.id] = (submission, grade)
    return list(latest.values())


def weakest_criterion(grades: list[tuple[Submission, TeacherGrade]]) -> str | None:
    """The criterion with the lowest average confirmed level (ties: the most recent low)."""
    totals: dict[str, list[int]] = {}
    for _, grade in grades:
        for item in grade.criteria:
            totals.setdefault(item["code"], []).append(LEVEL_SCORE.get(item["level"], 1))
    if not totals:
        return None
    return min(totals, key=lambda code: (sum(totals[code]) / len(totals[code]), code))


def _target_level(rows: list[dict[str, Any]], topic_id: int) -> str:
    """The level after the highest one mastered in the topic (K ≥ threshold)."""
    mastered = [r["level"] for r in rows if r["topic_id"] == topic_id and r["mastered"]]
    if not mastered:
        return LEVELS[0]
    highest = max(LEVELS.index(level) for level in mastered if level in LEVELS)
    return LEVELS[min(highest + 1, len(LEVELS) - 1)]


Model = tuple[str, list[dict[str, Any]]]


def next_step(
    db: Session, course_id: int, user_id: int, limit: int = 5, model_rows: Model | None = None
) -> dict[str, Any]:
    engine, model = model_rows or student_model(db, course_id, user_id)
    weak = sorted(
        (m for m in model if not m["mastered"]), key=lambda m: (m["p_learned"], m["kc_id"])
    )
    grades = confirmed_grades(db, course_id, user_id)
    criterion = weakest_criterion(grades)
    k_rows = mastery(db, course_id, user_id)
    focus = weak[0] if weak else None
    target = _target_level(k_rows, focus["topic_id"]) if focus else None

    solved = set(
        db.scalars(
            select(Submission.task_id).where(
                Submission.user_id == user_id, Submission.verdict == Verdict.OK.value
            )
        )
    )
    weak_ids = {m["kc_id"]: rank for rank, m in enumerate(weak)}
    now = datetime.now(UTC)
    candidates = []
    for task, kc_id in db.execute(
        select(Task, TaskKnowledgeComponent.knowledge_component_id)
        .join(TaskKnowledgeComponent, TaskKnowledgeComponent.task_id == Task.id)
        .where(Task.course_id == course_id, Task.status == TaskStatus.APPROVED.value)
    ).all():
        if kc_id not in weak_ids or task.id in solved or in_unfinished_assessment(db, task.id, now):
            continue
        level_gap = (
            abs(LEVELS.index(task.level) - LEVELS.index(target))
            if task.level in LEVELS and target in LEVELS
            else 9
        )
        candidates.append((level_gap, weak_ids[kc_id], task.id, task))
    seen: set[int] = set()
    tasks = []
    for _, _, _, task in sorted(candidates, key=lambda c: c[:3]):
        if task.id in seen:
            continue
        seen.add(task.id)
        tasks.append({"id": task.id, "title": task.title, "level": task.level})
    lessons = []
    if focus is not None:
        topic = db.get(Topic, focus["topic_id"])
        if topic is not None:
            lessons = [{"title": lesson.title, "url": lesson.url} for lesson in topic.lessons]
    return {
        "engine": engine,
        "weakest_criterion": criterion,
        "weak_components": [
            {k: m[k] for k in ("kc_id", "code", "name", "topic_code", "p_learned")}
            for m in weak[:5]
        ],
        "target_level": target,
        "tasks": tasks[:limit],
        "lessons": lessons,
    }


def trajectory(
    db: Session, course_id: int, user_id: int, model_rows: Model | None = None
) -> dict[str, Any]:
    """Confirmed results over time, mastery per topic and level, and the student model."""
    points = []
    for submission, grade in confirmed_grades(db, course_id, user_id):
        assessment = (
            db.get(Assessment, submission.assessment_id) if submission.assessment_id else None
        )
        task = db.get(Task, submission.task_id)
        points.append(
            {
                "at": grade.confirmed_at.isoformat(),
                "task": task.title if task else "",
                "level": task.level if task else None,
                "assessment": assessment.title if assessment else None,
                "score": grade.score,
                "components": {
                    "F": grade.component_f,
                    "E": grade.component_e,
                    "A": grade.component_a,
                },
                "criteria": {c["code"]: c["level"] for c in grade.criteria},
            }
        )
    course = db.get(Course, course_id)
    engine, model = model_rows or student_model(db, course_id, user_id)
    return {
        "engine": engine,
        "course": course.title if course else "",
        "results": points,
        "mastery": mastery(db, course_id, user_id),
        "components": model,
        "mastered_components": sum(1 for m in model if m["mastered"]),
    }
