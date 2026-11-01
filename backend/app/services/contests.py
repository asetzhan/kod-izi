"""Contests (ОТ-02) and virtual contests (ОТ-03): who may write when, and the standings.

A contest is an assessment of kind `contest`. The official round is its time window; a
virtual participant starts later and gets the same duration from their own start.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import AssessmentKind, ContestFormat, ParticipationKind, SubmissionStatus
from app.models import (
    Assessment,
    AssessmentTask,
    ContestParticipation,
    CourseGroup,
    GroupMember,
    Submission,
    Task,
    User,
)
from app.services import contest_scoring
from app.services.access import studies_course


@dataclass(frozen=True)
class Window:
    kind: ParticipationKind
    start: datetime
    end: datetime


def is_contest(assessment: Assessment | None) -> bool:
    return assessment is not None and assessment.kind == AssessmentKind.CONTEST.value


def duration(contest: Assessment) -> timedelta:
    return contest.ends_at - contest.starts_at


def participation(
    db: Session, user_id: int, contest: Assessment, kind: ParticipationKind
) -> ContestParticipation | None:
    return db.scalar(
        select(ContestParticipation).where(
            ContestParticipation.assessment_id == contest.id,
            ContestParticipation.user_id == user_id,
            ContestParticipation.kind == kind.value,
        )
    )


def active_window(db: Session, user_id: int, contest: Assessment, now: datetime) -> Window | None:
    """The round the user is writing right now, official or virtual."""
    if contest.starts_at <= now <= contest.ends_at:
        return Window(ParticipationKind.OFFICIAL, contest.starts_at, contest.ends_at)
    virtual = participation(db, user_id, contest, ParticipationKind.VIRTUAL)
    if virtual is not None:
        end = virtual.started_at + duration(contest)
        if virtual.started_at <= now <= end:
            return Window(ParticipationKind.VIRTUAL, virtual.started_at, end)
    return None


def join_official(db: Session, user: User, contest: Assessment, now: datetime) -> None:
    """The first opened problem registers the student in the official standings."""
    if participation(db, user.id, contest, ParticipationKind.OFFICIAL) is not None:
        return
    db.add(
        ContestParticipation(
            assessment_id=contest.id,
            user_id=user.id,
            kind=ParticipationKind.OFFICIAL.value,
            started_at=contest.starts_at,
        )
    )
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        pass  # registered by a parallel request


class ContestError(Exception):
    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


def start_virtual(db: Session, user: User, contest: Assessment, now: datetime) -> Window:
    """ОТ-03: a past contest, once per student, under the same conditions."""
    if not is_contest(contest) or not studies_course(db, user.id, contest.course_id):
        raise ContestError(403, "forbidden")
    if now <= contest.ends_at:
        raise ContestError(409, "contest_not_finished")
    if participation(db, user.id, contest, ParticipationKind.VIRTUAL) is not None:
        raise ContestError(409, "virtual_already_used")
    if participation(db, user.id, contest, ParticipationKind.OFFICIAL) is not None:
        # The official participant already knows the problems and the results.
        raise ContestError(409, "already_participated")
    if writing_any_contest(db, user.id, now):
        raise ContestError(409, "in_contest")
    db.add(
        ContestParticipation(
            assessment_id=contest.id,
            user_id=user.id,
            kind=ParticipationKind.VIRTUAL.value,
            started_at=now,
        )
    )
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        raise ContestError(409, "virtual_already_used") from None
    return Window(ParticipationKind.VIRTUAL, now, now + duration(contest))


def in_unfinished_contest(db: Session, task_id: int, now: datetime) -> bool:
    """The problem belongs to a contest that has not ended: students must not see it in
    practice before or during the round (statement, editorial, hints, penalty-free tries)."""
    return (
        db.scalar(
            select(Assessment.id)
            .join(AssessmentTask, AssessmentTask.assessment_id == Assessment.id)
            .where(
                Assessment.kind == AssessmentKind.CONTEST.value,
                AssessmentTask.task_id == task_id,
                Assessment.ends_at > now,
            )
            .limit(1)
        )
        is not None
    )


def in_unfinished_assessment(db: Session, task_id: int, now: datetime) -> bool:
    """The task is in a control work or contest that has not ended (upcoming or running)."""
    return (
        db.scalar(
            select(Assessment.id)
            .join(AssessmentTask, AssessmentTask.assessment_id == Assessment.id)
            .where(AssessmentTask.task_id == task_id, Assessment.ends_at >= now)
            .limit(1)
        )
        is not None
    )


def in_running_contest(db: Session, user_id: int, task_id: int, now: datetime) -> bool:
    """ОТ-02: while the user writes a contest with this problem, the AI stays off for it
    everywhere, practice included."""
    contests = db.scalars(
        select(Assessment)
        .join(AssessmentTask, AssessmentTask.assessment_id == Assessment.id)
        .where(
            Assessment.kind == AssessmentKind.CONTEST.value,
            AssessmentTask.task_id == task_id,
        )
    )
    return any(active_window(db, user_id, c, now) is not None for c in contests)


def writing_any_contest(db: Session, user_id: int, now: datetime) -> bool:
    """True while the user is inside any official or virtual round (ОТ-02: no AI at all,
    for any problem, during the round)."""
    my_courses = (
        select(CourseGroup.course_id)
        .join(GroupMember, GroupMember.group_id == CourseGroup.group_id)
        .where(GroupMember.user_id == user_id)
    )
    # An official round of the student's course counts even before they open a problem:
    # its statements are readable from the start, so the AI must be off already.
    running = db.scalar(
        select(Assessment.id)
        .where(
            Assessment.kind == AssessmentKind.CONTEST.value,
            Assessment.course_id.in_(my_courses),
            Assessment.starts_at <= now,
            Assessment.ends_at >= now,
        )
        .limit(1)
    )
    if running is not None:
        return True
    joined = db.scalars(
        select(Assessment)
        .join(ContestParticipation, ContestParticipation.assessment_id == Assessment.id)
        .where(ContestParticipation.user_id == user_id)
        .distinct()
    )
    return any(active_window(db, user_id, c, now) is not None for c in joined)


# Standings -------------------------------------------------------------------------------


def _points(db: Session, contest_tasks: list[Task], submission: Submission) -> float:
    task = next(t for t in contest_tasks if t.id == submission.task_id)
    subtasks = {t.id: t.subtask for t in task.tests}
    results = [
        (subtasks.get(r.test_case_id or 0, 1), r.verdict == "OK") for r in submission.results
    ]
    # Tests that did not run (a compilation error stops early) count as failed.
    missing = len(task.tests) - len(results)
    if missing > 0 and submission.status == SubmissionStatus.DONE.value:
        ran = {r.test_case_id for r in submission.results}
        results += [(t.subtask, False) for t in task.tests if t.id not in ran]
    return contest_scoring.submission_points(task.subtask_points, results)


def standings(
    db: Session, contest: Assessment, viewer: User, staff: bool, now: datetime
) -> dict[str, Any]:
    """The standings as the viewer may see them.

    Students: the last `freeze_minutes` of the official round are hidden until it ends;
    a virtual participant sees the official participants as they were at the same
    minute of their own round. Other students are shown without names (spec 14.3).
    The caller has checked access and switched to the system context, because the
    standings read other students' rows (row-level security, migration 0006).
    """
    tasks = [t for link in contest.task_links if (t := db.get(Task, link.task_id))]
    task_ids = [t.id for t in tasks]
    rows = db.scalars(
        select(ContestParticipation).where(ContestParticipation.assessment_id == contest.id)
    ).all()
    official = {p.user_id: p for p in rows if p.kind == ParticipationKind.OFFICIAL.value}
    virtual_mine = next(
        (p for p in rows if p.kind == ParticipationKind.VIRTUAL.value and p.user_id == viewer.id),
        None,
    )
    submissions = db.scalars(
        select(Submission)
        .where(
            Submission.assessment_id == contest.id,
            Submission.status != SubmissionStatus.ERROR.value,
        )
        .order_by(Submission.id)
    ).all()

    length = duration(contest).total_seconds()
    attempts: list[contest_scoring.Attempt] = []
    virtual_key = -viewer.id  # the viewer's virtual row has its own key
    for s in submissions:
        done = s.status == SubmissionStatus.DONE.value
        verdict = s.verdict if done else None
        score = _points(db, tasks, s) if done and contest.contest_format == "ioi" else 0.0
        if s.created_at <= contest.ends_at and s.user_id in official:
            elapsed = (s.created_at - contest.starts_at).total_seconds()
            attempts.append(contest_scoring.Attempt(s.user_id, s.task_id, elapsed, verdict, score))
        elif virtual_mine is not None and s.user_id == viewer.id:
            # After the official end a submission can only be from the single virtual round.
            elapsed = max((s.created_at - virtual_mine.started_at).total_seconds(), 0.0)
            attempts.append(
                contest_scoring.Attempt(virtual_key, s.task_id, elapsed, verdict, score)
            )

    participants = list(official)
    cutoff = frozen_after = None
    virtual_running = False
    if virtual_mine is not None:
        participants.append(virtual_key)
        mine_elapsed = (now - virtual_mine.started_at).total_seconds()
        if mine_elapsed < length:
            virtual_running = True
            cutoff = mine_elapsed
    official_running = now < contest.ends_at
    if not staff and (official_running or virtual_running):
        frozen_after = max(length - contest.freeze_minutes * 60, 0)

    mine = {viewer.id, virtual_key}  # the freeze never hides the viewer's own verdicts
    if contest.contest_format == ContestFormat.IOI.value:
        ranked = contest_scoring.ioi(participants, task_ids, attempts, frozen_after, cutoff, mine)
    else:
        ranked = contest_scoring.icpc(
            participants, task_ids, attempts, contest.penalty_minutes, frozen_after, cutoff, mine
        )
    names: dict[int, str] = {}
    if staff:
        ids = [u for u in participants if u > 0]
        names = {u.id: u.full_name for u in db.scalars(select(User).where(User.id.in_(ids)))}

    return {
        "format": contest.contest_format,
        "frozen": frozen_after is not None,
        "virtual": virtual_mine is not None,
        "tasks": [{"id": t.id, "label": chr(ord("A") + i)} for i, t in enumerate(tasks)],
        "rows": [
            {
                "rank": r.rank,
                "me": r.user_id in mine,
                "virtual": r.user_id < 0,
                "name": names.get(r.user_id) if staff else None,
                "solved": r.solved,
                "penalty": r.penalty,
                "score": r.score,
                "cells": [
                    {
                        "solved": c.solved,
                        "wrong": c.wrong,
                        "minute": c.minute,
                        "score": c.score,
                        "pending": c.pending,
                        "tried": c.tried,
                    }
                    for c in (r.cells[t] for t in task_ids)
                ],
            }
            for r in ranked
        ],
    }
