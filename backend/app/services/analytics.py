"""Stage 6b analytics: activity stages of the trace (ФТ-26), process metrics (ФТ-33),
GenAI use (ФТ-38), solve rates (ФТ-20) and the group monitoring board (ФТ-04).

The stages follow the dissertation's table of task stages (docs/spec/dissertation/
task-stages.md): understanding, planning, coding, testing, debugging, explaining.
Labels are computed from the trace when it is read; trace rows are never changed.
"""

import difflib
import json
import re
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from itertools import pairwise
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import ActivityStage, TaskStatus, TraceKind, Verdict
from app.models import (
    AiMessage,
    AppSetting,
    Assessment,
    AssessmentTask,
    Submission,
    Task,
    TeacherGrade,
    TraceEvent,
)

# Stage labelling (ФТ-26) ----------------------------------------------------------------------

# Code that is still mostly comments is a plan written in the editor.
COMMENT = re.compile(r"^\s*(//|/\*|\*)")


def _mostly_comments(code: str) -> bool:
    lines = [line for line in code.splitlines() if line.strip()]
    return bool(lines) and sum(1 for line in lines if COMMENT.match(line)) * 2 >= len(lines)


def _failed(event: TraceEvent) -> bool:
    """A run or test that shows something is wrong: a compile error, a wrong test."""
    if event.kind == TraceKind.COMPILE.value:
        return True
    if event.kind in (TraceKind.TEST.value, TraceKind.VERDICT.value):
        return any(v != Verdict.OK.value for v in event.payload.get("per_test", []))
    if event.kind == TraceKind.RUN.value:
        return event.payload.get("status") not in (None, "finished")
    return False


def label_stages(events: Sequence[TraceEvent]) -> list[ActivityStage | None]:
    """One stage per event, in order. Rules:

    - before the first code: understanding (reading the statement, focus changes);
    - code that is mostly comments, before the first run: planning;
    - typing and pasting: coding, or debugging after a failed run until a clean one;
    - runs, tests, submissions and verdicts: testing;
    - the explanation and the answers about the code: explaining;
    - AI requests and responses take the stage the student was in.
    Session start and end get no stage.
    """
    labels: list[ActivityStage | None] = []
    stage = ActivityStage.UNDERSTAND
    ran = False
    broken = False
    for event in events:
        kind = event.kind
        if kind in (TraceKind.SESSION_START.value, TraceKind.SESSION_CLOSED.value):
            labels.append(None)
            continue
        if kind in (TraceKind.EXPLANATION.value, TraceKind.ANSWERS.value):
            stage = ActivityStage.EXPLAIN
        elif kind in (
            TraceKind.RUN.value,
            TraceKind.TEST.value,
            TraceKind.COMPILE.value,
            TraceKind.SUBMIT.value,
            TraceKind.VERDICT.value,
        ):
            ran = True
            broken = _failed(event)
            stage = ActivityStage.TEST
        elif kind in (TraceKind.SNAPSHOT.value, TraceKind.PASTE.value):
            code = str(event.payload.get("code", ""))
            if broken:
                stage = ActivityStage.DEBUG
            elif not ran and kind == TraceKind.SNAPSHOT.value and _mostly_comments(code):
                stage = ActivityStage.PLAN
            else:
                stage = ActivityStage.CODE
        # focus changes and AI messages keep the current stage
        labels.append(stage)
    return labels


# Process metrics (ФТ-33) ---------------------------------------------------------------------

# Kinds of g++ errors; the first match names the error.
ERROR_KINDS = (
    ("missing_semicolon", re.compile(r"expected ['‘]?;['’]?")),
    ("undeclared", re.compile(r"was not declared|undeclared|not declared in this scope")),
    (
        "type_mismatch",
        re.compile(r"cannot convert|invalid conversion|no match for|invalid operands"),
    ),
    ("no_function", re.compile(r"no matching function|too (many|few) arguments")),
    ("brackets", re.compile(r"expected ['‘]?[)}\]]['’]?|expected primary-expression")),
    ("redeclared", re.compile(r"redeclaration|redefinition|conflicting declaration")),
    ("missing_return", re.compile(r"no return statement|control reaches end")),
)


def error_kind(compile_output: str) -> str:
    for name, pattern in ERROR_KINDS:
        if pattern.search(compile_output):
            return name
    return "other"


def process_report(events: Sequence[TraceEvent]) -> dict[str, Any]:
    """Actions, compile errors by kind and their repetition, time spent fixing errors."""
    counts = Counter(e.kind for e in events)
    errors: list[str] = []
    fix_seconds = 0.0
    fixes = 0
    failing_since: datetime | None = None
    for event in events:
        if event.kind not in (TraceKind.COMPILE.value, TraceKind.TEST.value, TraceKind.RUN.value):
            continue
        output = str(event.payload.get("compile_output", ""))
        if output:
            errors.append(error_kind(output))
        if _failed(event):
            failing_since = failing_since or event.server_ts
        elif failing_since is not None:
            fixes += 1
            fix_seconds += (event.server_ts - failing_since).total_seconds()
            failing_since = None
    repeated = sum(1 for a, b in pairwise(errors) if a == b)
    stages = Counter(s.value for s in label_stages(events) if s is not None)
    minutes = (events[-1].server_ts - events[0].server_ts).total_seconds() / 60 if events else 0
    return {
        "events": dict(counts),
        "attempts": counts[TraceKind.RUN.value]
        + counts[TraceKind.TEST.value]
        + counts[TraceKind.COMPILE.value]
        + counts[TraceKind.SUBMIT.value],
        "compile_errors": len(errors),
        "compile_error_kinds": dict(Counter(errors)),
        "repeated_compile_errors": repeated,
        "fix_cycles": fixes,
        "fix_minutes": round(fix_seconds / 60, 1),
        "large_pastes": sum(1 for e in events if e.kind == TraceKind.PASTE.value and e.flagged),
        "stage_events": dict(stages),
        "minutes": round(minutes, 1),
    }


def work_events(
    db: Session, user_id: int, task_id: int, assessment_id: int | None
) -> list[TraceEvent]:
    return list(
        db.scalars(
            select(TraceEvent)
            .where(
                TraceEvent.user_id == user_id,
                TraceEvent.task_id == task_id,
                TraceEvent.assessment_id.is_(None)
                if assessment_id is None
                else TraceEvent.assessment_id == assessment_id,
            )
            .order_by(TraceEvent.id)
        )
    )


# GenAI use (ФТ-38) ---------------------------------------------------------------------------


def genai_report(
    events: Sequence[TraceEvent], messages: Sequence[AiMessage], final_code: str
) -> dict[str, Any]:
    """Requests per activity stage (the dissertation's GenAI-by-stage table) and how close
    the final code is to the AI's answers."""
    labels = label_stages(events)
    by_stage: Counter[str] = Counter()
    for event, label in zip(events, labels, strict=True):
        if event.kind == TraceKind.AI_REQUEST.value and label is not None:
            by_stage[label.value] += 1
    similarity = max(
        (difflib.SequenceMatcher(None, m.answer, final_code).ratio() for m in messages),
        default=0.0,
    )
    return {
        "requests": len(messages),
        "blocked": sum(1 for m in messages if m.blocked),
        "hints": sum(1 for m in messages if m.hint_level is not None),
        "by_stage": dict(by_stage),
        "max_similarity_to_final_code": round(similarity, 2),
        "log": [
            {
                "at": m.created_at.isoformat(),
                "question": m.question[:1000],
                "answer": m.answer[:1500],
                "blocked": m.blocked,
            }
            for m in messages[-30:]
        ],
    }


# Solve rates (ФТ-20) -------------------------------------------------------------------------

SOLVE_RATE_KEY = "solve_rate"


class SolveRateSettings(BaseModel):
    """A task is flagged when its solve rate differs from the reference of its level by more
    than `tolerance`, once at least `min_students` tried it. The reference comes from the
    authors' earlier study (seed/task_levels.json, empirical_reference)."""

    tolerance: float = Field(default=0.25, ge=0.01, le=1.0)
    min_students: int = Field(default=10, ge=1, le=1000)


def solve_rate_settings(db: Session) -> SolveRateSettings:
    stored = db.get(AppSetting, SOLVE_RATE_KEY)
    return SolveRateSettings.model_validate(stored.value if stored else {})


def reference_rates() -> dict[str, float]:
    path = get_settings().seed_dir / "task_levels.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    rates: dict[str, float] = data.get("empirical_reference", {}).get("solve_rate", {})
    return rates


def solve_rates(db: Session, course_id: int) -> list[dict[str, Any]]:
    """Share of students who solved each task among those who submitted it in assessments."""
    settings = solve_rate_settings(db)
    reference = reference_rates()
    tasks = db.scalars(
        select(Task)
        .where(Task.course_id == course_id, Task.status == TaskStatus.APPROVED.value)
        .order_by(Task.id)
    ).all()
    out = []
    for task in tasks:
        rows = db.execute(
            select(Submission.user_id, Submission.verdict).where(
                Submission.task_id == task.id, Submission.assessment_id.is_not(None)
            )
        ).all()
        tried = {user for user, _ in rows}
        solved = {user for user, verdict in rows if verdict == Verdict.OK.value}
        rate = len(solved) / len(tried) if tried else None
        expected = reference.get(task.level or "")
        flagged = (
            rate is not None
            and expected is not None
            and len(tried) >= settings.min_students
            and abs(rate - expected) > settings.tolerance
        )
        out.append(
            {
                "task_id": task.id,
                "title": task.title,
                "level": task.level,
                "students": len(tried),
                "solved": len(solved),
                "rate": None if rate is None else round(rate, 4),
                "expected": expected,
                "flagged": flagged,
                "direction": None
                if not flagged or rate is None or expected is None
                else ("easier" if rate > expected else "harder"),
            }
        )
    return out


# Monitoring board (ФТ-04) --------------------------------------------------------------------


def monitoring(db: Session, course_id: int, student_ids: Sequence[int]) -> dict[str, Any]:
    """Levels per criterion from the teachers' confirmed grades, and typical difficulties:
    failing verdicts, compile error kinds and the most frequent low criteria."""
    assessments = select(Assessment.id).where(Assessment.course_id == course_id)
    submissions = db.scalars(
        select(Submission)
        .where(Submission.user_id.in_(student_ids), Submission.assessment_id.in_(assessments))
        .order_by(Submission.id)
    ).all()
    criteria: dict[str, Counter[str]] = {}
    students: dict[int, dict[str, Any]] = {
        s: {"user_id": s, "submissions": 0, "solved": 0, "criteria": {}} for s in student_ids
    }
    verdicts: Counter[str] = Counter()
    low: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    for submission in submissions:
        row = students[submission.user_id]
        row["submissions"] += 1
        if submission.verdict == Verdict.OK.value:
            row["solved"] += 1
        elif submission.verdict:
            verdicts[submission.verdict] += 1
        if submission.compile_output:
            errors[error_kind(submission.compile_output)] += 1
        grade = db.scalar(
            select(TeacherGrade)
            .where(TeacherGrade.submission_id == submission.id)
            .order_by(TeacherGrade.id.desc())
        )
        if grade is None:
            continue
        for item in grade.criteria:
            criteria.setdefault(item["code"], Counter())[item["level"]] += 1
            row["criteria"][item["code"]] = item["level"]  # the latest confirmed level
            if item["level"] == "low":
                low[item["code"]] += 1
    return {
        "criteria": {code: dict(levels) for code, levels in criteria.items()},
        "difficulties": {
            "verdicts": dict(verdicts.most_common()),
            "compile_error_kinds": dict(errors.most_common()),
            "low_criteria": dict(low.most_common()),
        },
        "students": list(students.values()),
    }


def tasks_of_assessment(db: Session, assessment_id: int) -> list[int]:
    return list(
        db.scalars(
            select(AssessmentTask.task_id).where(AssessmentTask.assessment_id == assessment_id)
        )
    )
