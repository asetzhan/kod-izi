"""Student model (ФТ-39): Bayesian Knowledge Tracing per knowledge component.

The standard BKT model (Corbett & Anderson), the same one pyBKT fits (spec 11): a
component is either learned or not; after each attempt the probability is updated with
the slip and guess probabilities, then the student may learn it (transit). A component
with P(L) ≥ 0,95 counts as mastered (spec 5.3; seed/task_levels.json).

Observations are the student's graded submissions of tasks linked to the component
(ФТ-10), in time order. An attempt is correct when all tests pass and, if the teacher has
confirmed the grade, no criterion is "low" (spec 5.3, the extra condition).
"""

import json
import math
from collections.abc import Iterable, Sequence
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import Verdict
from app.models import (
    AppSetting,
    KnowledgeComponent,
    Submission,
    Task,
    TaskKnowledgeComponent,
    TeacherGrade,
    Topic,
)

BKT_KEY = "bkt"


class BktParams(BaseModel):
    """Changed by an administrator; to be fitted on pilot data (`fit`)."""

    # Strictly between 0 and 1: 0 or 1 would make the update divide by zero.
    p_init: float = Field(default=0.2, ge=0.001, le=0.999)  # P(L0): known before the course
    p_transit: float = Field(default=0.15, ge=0.0, le=0.999)  # learns it after an attempt
    p_slip: float = Field(default=0.1, ge=0.001, le=0.5)  # knows it, still fails
    p_guess: float = Field(default=0.2, ge=0.001, le=0.5)  # does not know it, still passes
    threshold: float = Field(default=0.95, ge=0.5, le=1.0)


def default_threshold() -> float:
    path = get_settings().seed_dir / "task_levels.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return float(data.get("student_mastery", {}).get("bkt_mastery_threshold", 0.95))


def get_params(db: Session) -> BktParams:
    stored = db.get(AppSetting, BKT_KEY)
    if stored is not None:
        return BktParams.model_validate(stored.value)
    return BktParams(threshold=default_threshold())


def update(p_learned: float, correct: bool, params: BktParams) -> float:
    """P(L) after one observed attempt: Bayes with slip/guess, then the transit."""
    if correct:
        known = p_learned * (1 - params.p_slip)
        posterior = known / (known + (1 - p_learned) * params.p_guess)
    else:
        known = p_learned * params.p_slip
        posterior = known / (known + (1 - p_learned) * (1 - params.p_guess))
    return posterior + (1 - posterior) * params.p_transit


def trace(observations: Sequence[bool], params: BktParams) -> list[float]:
    """P(L) after each attempt, starting from P(L0)."""
    p = params.p_init
    out = []
    for correct in observations:
        p = update(p, correct, params)
        out.append(p)
    return out


def log_likelihood(sequences: Iterable[Sequence[bool]], params: BktParams) -> float:
    total = 0.0
    for sequence in sequences:
        p = params.p_init
        for correct in sequence:
            p_correct = p * (1 - params.p_slip) + (1 - p) * params.p_guess
            p_correct = min(max(p_correct, 1e-9), 1 - 1e-9)
            total += math.log(p_correct if correct else 1 - p_correct)
            p = update(p, correct, params)
    return total


def fit(sequences: Sequence[Sequence[bool]], threshold: float = 0.95) -> BktParams:
    """Maximum-likelihood parameters on a grid (enough for pilot-sized data; pyBKT's EM
    can replace it later). Slip and guess stay below 0,5 so the model is identifiable."""
    grid = [0.05, 0.1, 0.2, 0.3, 0.4]
    small = [0.05, 0.1, 0.2, 0.3]
    best: tuple[float, BktParams] | None = None
    for p_init in grid:
        for p_transit in grid:
            for p_slip in small:
                for p_guess in small:
                    params = BktParams(
                        p_init=p_init,
                        p_transit=p_transit,
                        p_slip=p_slip,
                        p_guess=p_guess,
                        threshold=threshold,
                    )
                    score = log_likelihood(sequences, params)
                    if best is None or score > best[0]:
                        best = (score, params)
    if best is None:  # the grid is never empty
        raise ValueError("no parameters")
    return best[1]


# The student model from the database ---------------------------------------------------------


def _correct(db: Session, submission: Submission) -> bool:
    if submission.verdict != Verdict.OK.value:
        return False
    grade = db.scalar(
        select(TeacherGrade)
        .where(TeacherGrade.submission_id == submission.id)
        .order_by(TeacherGrade.id.desc())
    )
    return grade is None or not any(c["level"] == "low" for c in grade.criteria)


def observations(db: Session, course_id: int, user_id: int) -> dict[int, list[bool]]:
    """Graded attempts per knowledge component of the course, in time order."""
    links = db.execute(
        select(TaskKnowledgeComponent.task_id, TaskKnowledgeComponent.knowledge_component_id)
        .join(Task, Task.id == TaskKnowledgeComponent.task_id)
        .where(Task.course_id == course_id)
    ).all()
    by_task: dict[int, list[int]] = {}
    for task_id, kc_id in links:
        by_task.setdefault(task_id, []).append(kc_id)
    out: dict[int, list[bool]] = {}
    submissions = db.scalars(
        select(Submission)
        .where(
            Submission.user_id == user_id,
            Submission.task_id.in_(list(by_task)),
            Submission.verdict.is_not(None),
        )
        .order_by(Submission.created_at, Submission.id)
    )
    for submission in submissions:
        correct = _correct(db, submission)
        for kc_id in by_task[submission.task_id]:
            out.setdefault(kc_id, []).append(correct)
    return out


def student_model(db: Session, course_id: int, user_id: int) -> list[dict[str, Any]]:
    """P(L) of every knowledge component of the course for one student."""
    params = get_params(db)
    seen = observations(db, course_id, user_id)
    components = db.execute(
        select(KnowledgeComponent, Topic)
        .join(Topic, Topic.id == KnowledgeComponent.topic_id)
        .where(Topic.course_id == course_id)
        .order_by(Topic.position, KnowledgeComponent.position)
    ).all()
    out = []
    for kc, topic in components:
        history = trace(seen.get(kc.id, []), params)
        p = history[-1] if history else params.p_init
        out.append(
            {
                "kc_id": kc.id,
                "code": kc.code,
                "name": kc.name,
                "topic_id": topic.id,
                "topic_code": topic.code,
                "attempts": len(history),
                "p_learned": round(p, 4),
                "history": [round(x, 4) for x in history],
                "mastered": p >= params.threshold,
            }
        )
    return out
