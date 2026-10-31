"""Teacher's decision and what the student sees (ФТ-03, ФТ-41, ФТ-42, ФТ-43; spec 5.3)."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import TaskStatus, Verdict
from app.models import (
    AiGrade,
    AppSetting,
    Assessment,
    AssessmentTask,
    Submission,
    Task,
    TeacherGrade,
)
from app.services.component_fill import book_refs, descriptors_for
from app.services.components import edit, find_entry
from app.services.rubrics import CRITERIA_CODES, final_score, get_or_create_rubric

MASTERY_KEY = "mastery"


class GradeError(ValueError):
    pass


def latest_ai_grade(db: Session, submission_id: int) -> AiGrade | None:
    return db.scalar(
        select(AiGrade).where(AiGrade.submission_id == submission_id).order_by(AiGrade.id.desc())
    )


def confirm(
    db: Session,
    submission: Submission,
    user_id: int,
    levels: dict[str, str],
    components: dict[str, float],
    feedback: str,
    next_step: str,
    reason: str,
) -> TeacherGrade:
    """ФТ-03: the teacher confirms or corrects; the AI grade stays as it was."""
    if set(levels) != set(CRITERIA_CODES) or not set(levels.values()) <= {"low", "mid", "high"}:
        raise GradeError("levels must give low, mid or high for all six criteria")
    task = db.get(Task, submission.task_id)
    if task is None:
        raise GradeError("submission without task")
    rubric = get_or_create_rubric(db, task.course_id)
    descriptors = descriptors_for(db, task)
    ai = latest_ai_grade(db, submission.id)
    ai_levels = {c["code"]: c["level"] for c in ai.criteria} if ai else {}
    ai_components = {"F": ai.component_f, "E": ai.component_e, "A": ai.component_a} if ai else {}
    same_components = all(
        ai_components.get(k) is not None and abs(float(ai_components[k] or 0) - components[k]) < 0.5
        for k in ("F", "E", "A")
    )
    agrees = ai is not None and ai_levels == levels and same_components
    if ai is not None and not agrees and not reason.strip():
        raise GradeError("write why the AI grade was changed")
    ai_feedback = ai.feedback.strip() if ai else ""
    if not ai_feedback:
        source = "teacher"
    elif feedback.strip() == ai_feedback:
        source = "ai"
    else:
        source = "ai_edited"
    grade = TeacherGrade(
        submission_id=submission.id,
        ai_grade_id=ai.id if ai else None,
        # The interpretation text is frozen with the grade: later edits of the
        # descriptors do not change what the student was shown.
        criteria=[
            {
                "code": code,
                "level": levels[code],
                "interpretation": descriptors.get(code, {}).get(levels[code], ""),
            }
            for code in CRITERIA_CODES
        ],
        component_f=components["F"],
        component_e=components["E"],
        component_a=components["A"],
        score=final_score(rubric, components),
        feedback=feedback,
        feedback_source=source,
        book_refs=book_refs(ai) if ai else [],
        next_step=next_step,
        reason=reason,
        agrees_with_ai=agrees,
        confirmed_by=user_id,
    )
    db.add(grade)
    entry = find_entry(db, 5, "submission", submission.id, "interpretation")
    if entry is not None and isinstance(entry.value, dict):
        value = dict(entry.value)
        value.update(
            criteria=[
                {**c, "level": levels.get(c.get("code", ""), c.get("level"))}
                for c in value.get("criteria", [])
                if isinstance(c, dict)
            ],
            feedback=feedback,
            next_step=next_step,
        )
        if value != entry.value:
            edit(db, entry, value, user_id, "confirmed by teacher")
    db.flush()
    return grade


def confirmed_grade(db: Session, submission_id: int) -> TeacherGrade | None:
    return db.scalar(
        select(TeacherGrade)
        .where(TeacherGrade.submission_id == submission_id)
        .order_by(TeacherGrade.id.desc())
    )


# Bespalko coefficient (ФТ-43, spec 5.3) -------------------------------------------------


@dataclass(frozen=True)
class MasterySettings:
    bespalko_threshold: float
    no_low_criterion: bool


def mastery_settings(db: Session) -> MasterySettings:
    stored = db.get(AppSetting, MASTERY_KEY)
    if stored is not None:
        return MasterySettings(**stored.value)
    seed = json.loads((get_settings().seed_dir / "task_levels.json").read_text(encoding="utf-8"))[
        "student_mastery"
    ]
    return MasterySettings(seed["bespalko_K_threshold"], no_low_criterion=True)


def bespalko(a: int, p: int, threshold: float) -> tuple[float | None, bool]:
    """K = a / p; the level is mastered when K ≥ threshold (0,7 by default)."""
    if p == 0:
        return None, False
    k = a / p
    return round(k, 4), k >= threshold - 1e-9


def fully_done(db: Session, student_id: int, task_id: int, require_no_low: bool) -> bool:
    """A task counts for `a` when its last confirmed grade has no `low` criterion and
    the graded submission passed all tests (spec 5.3)."""
    rows = db.execute(
        select(Submission, TeacherGrade)
        .join(TeacherGrade, TeacherGrade.submission_id == Submission.id)
        .where(Submission.user_id == student_id, Submission.task_id == task_id)
        .order_by(TeacherGrade.id.desc())
        .limit(1)
    ).first()
    if rows is None:
        return False
    submission, grade = rows
    if submission.verdict != Verdict.OK.value:
        return False
    return not (require_no_low and any(c["level"] == "low" for c in grade.criteria))


def mastery(db: Session, course_id: int, student_id: int) -> list[dict[str, Any]]:
    """K per topic and level over the tasks given to the student in started assessments."""
    settings = mastery_settings(db)
    tasks = db.scalars(
        select(Task)
        .join(AssessmentTask, AssessmentTask.task_id == Task.id)
        .join(Assessment, Assessment.id == AssessmentTask.assessment_id)
        .where(
            Assessment.course_id == course_id,
            Task.status == TaskStatus.APPROVED.value,
            Assessment.starts_at <= datetime.now(UTC),
        )
        .distinct()
    ).all()
    groups: dict[tuple[int | None, str | None], list[Task]] = {}
    for task in tasks:
        groups.setdefault((task.topic_id, task.level), []).append(task)
    out = []
    for (topic_id, level), group in sorted(
        groups.items(), key=lambda g: (g[0][0] or 0, g[0][1] or "")
    ):
        a = sum(1 for t in group if fully_done(db, student_id, t.id, settings.no_low_criterion))
        k, mastered = bespalko(a, len(group), settings.bespalko_threshold)
        out.append(
            {
                "topic_id": topic_id,
                "level": level,
                "a": a,
                "p": len(group),
                "k": k,
                "mastered": mastered,
            }
        )
    return out
