"""Contests (ОТ-02) and virtual contests (ОТ-03).

A contest is an assessment of kind `contest`: problems are opened and submitted through
the usual workspace (/api/sessions), the AI assistant is off for its whole duration.
"""

from datetime import UTC, datetime
from typing import Any, Self

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from app.api.content_schemas import StudentTaskOut
from app.api.deps import CurrentUser, DbSession, client_ip
from app.core.enums import AssessmentKind, ContestFormat, GenAiMode, ParticipationKind, TaskStatus
from app.db.context import set_system
from app.models import Assessment, AssessmentTask, CourseGroup, GroupMember, Task, User
from app.services import audit, contests
from app.services.access import can_edit_course, can_view_course, is_staff, studies_course
from app.services.audit import AuditAction

router = APIRouter(prefix="/api", tags=["contests"])


def _forbidden() -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")


class ContestIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    format: ContestFormat = ContestFormat.ICPC
    starts_at: datetime
    ends_at: datetime
    # ОТ-02: the standings stop for students this many minutes before the end.
    freeze_minutes: int = Field(default=60, ge=0, le=600)
    penalty_minutes: int = Field(default=20, ge=0, le=120)
    task_ids: list[int] = Field(min_length=1, max_length=26)

    @model_validator(mode="after")
    def _window(self) -> Self:
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("times must include a time zone")
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        if self.freeze_minutes * 60 > (self.ends_at - self.starts_at).total_seconds():
            raise ValueError("the freeze is longer than the contest")
        return self


class VirtualOut(BaseModel):
    started_at: datetime
    ends_at: datetime


class ContestOut(BaseModel):
    id: int
    course_id: int
    title: str
    format: ContestFormat
    starts_at: datetime
    ends_at: datetime
    freeze_minutes: int
    penalty_minutes: int
    task_count: int
    state: str  # upcoming, running, finished
    task_ids: list[int] = []  # staff only
    my_virtual: VirtualOut | None = None

    @classmethod
    def build(
        cls, contest: Assessment, now: datetime, staff: bool, virtual: VirtualOut | None = None
    ) -> "ContestOut":
        state = (
            "upcoming"
            if now < contest.starts_at
            else ("running" if now <= contest.ends_at else "finished")
        )
        return cls(
            id=contest.id,
            course_id=contest.course_id,
            title=contest.title,
            format=ContestFormat(contest.contest_format or "icpc"),
            starts_at=contest.starts_at,
            ends_at=contest.ends_at,
            freeze_minutes=contest.freeze_minutes,
            penalty_minutes=contest.penalty_minutes,
            task_count=len(contest.task_links),
            state=state,
            task_ids=[link.task_id for link in contest.task_links] if staff else [],
            my_virtual=virtual,
        )


def _virtual(db: DbSession, user: User, contest: Assessment) -> VirtualOut | None:
    mine = contests.participation(db, user.id, contest, ParticipationKind.VIRTUAL)
    if mine is None:
        return None
    return VirtualOut(
        started_at=mine.started_at, ends_at=mine.started_at + contests.duration(contest)
    )


def _contest(db: DbSession, contest_id: int) -> Assessment:
    contest = db.get(Assessment, contest_id)
    if contest is None or not contests.is_contest(contest):
        raise _forbidden()
    return contest


def _fill(db: DbSession, contest: Assessment, body: ContestIn) -> None:
    tasks = {t.id: t for t in db.scalars(select(Task).where(Task.id.in_(body.task_ids)))}
    for task_id in body.task_ids:
        task = tasks.get(task_id)
        if task is None or task.course_id != contest.course_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "task_not_in_course", "message": f"task {task_id}"},
            )
        if task.status != TaskStatus.APPROVED.value:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "task_not_approved", "message": f"task {task_id}"},
            )
    contest.title = body.title
    contest.kind = AssessmentKind.CONTEST.value
    contest.contest_format = body.format.value
    contest.genai_mode = GenAiMode.FORBIDDEN.value  # ОТ-02
    contest.starts_at = body.starts_at
    contest.ends_at = body.ends_at
    contest.freeze_minutes = body.freeze_minutes
    contest.penalty_minutes = body.penalty_minutes
    contest.task_links = [
        AssessmentTask(task_id=task_id, position=i)
        for i, task_id in enumerate(dict.fromkeys(body.task_ids), start=1)
    ]


def _save(db: DbSession, request: Request, user: User, contest: Assessment) -> ContestOut:
    db.flush()
    audit.record(
        db,
        AuditAction.CONTEST_SAVED,
        actor_id=user.id,
        object_type="assessment",
        object_id=contest.id,
        ip=client_ip(request),
        details={
            "format": contest.contest_format,
            "starts_at": contest.starts_at.isoformat(),
            "ends_at": contest.ends_at.isoformat(),
            "task_ids": [link.task_id for link in contest.task_links],
        },
    )
    db.commit()
    db.refresh(contest)
    return ContestOut.build(contest, datetime.now(UTC), staff=True)


@router.post("/courses/{course_id}/contests", status_code=status.HTTP_201_CREATED)
def create_contest(
    course_id: int, body: ContestIn, request: Request, user: CurrentUser, db: DbSession
) -> ContestOut:
    if not can_edit_course(db, user, course_id):
        raise _forbidden()
    contest = Assessment(course_id=course_id, created_by=user.id)
    _fill(db, contest, body)
    db.add(contest)
    return _save(db, request, user, contest)


@router.put("/contests/{contest_id}")
def update_contest(
    contest_id: int, body: ContestIn, request: Request, user: CurrentUser, db: DbSession
) -> ContestOut:
    contest = _contest(db, contest_id)
    if not can_edit_course(db, user, contest.course_id):
        raise _forbidden()
    if datetime.now(UTC) >= contest.starts_at:
        # Changing problems or times of a started round would change everyone's results.
        raise HTTPException(status.HTTP_409_CONFLICT, detail="contest_started")
    _fill(db, contest, body)
    return _save(db, request, user, contest)


@router.get("/contests")
def list_contests(
    user: CurrentUser, db: DbSession, course_id: int | None = None
) -> list[ContestOut]:
    now = datetime.now(UTC)
    query = (
        select(Assessment)
        .where(Assessment.kind == AssessmentKind.CONTEST.value)
        .order_by(Assessment.starts_at.desc())
    )
    if course_id is not None:
        query = query.where(Assessment.course_id == course_id)
    staff = is_staff(user)
    if not staff:
        mine = (
            select(CourseGroup.course_id)
            .join(GroupMember, GroupMember.group_id == CourseGroup.group_id)
            .where(GroupMember.user_id == user.id)
        )
        query = query.where(Assessment.course_id.in_(mine))
    return [
        ContestOut.build(c, now, staff, None if staff else _virtual(db, user, c))
        for c in db.scalars(query)
    ]


class ContestDetail(ContestOut):
    problems: list[StudentTaskOut]
    writing: bool  # the user is inside their official or virtual round now


@router.get("/contests/{contest_id}")
def get_contest(contest_id: int, user: CurrentUser, db: DbSession) -> ContestDetail:
    """Problems are shown from the start: during a round and afterwards for upsolving."""
    contest = _contest(db, contest_id)
    now = datetime.now(UTC)
    staff = is_staff(user) and can_view_course(db, user, contest.course_id)
    if not staff:
        if not studies_course(db, user.id, contest.course_id):
            raise _forbidden()
        if now < contest.starts_at:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="contest_not_started")
    tasks = [t for link in contest.task_links if (t := db.get(Task, link.task_id))]
    base = ContestOut.build(contest, now, staff, None if staff else _virtual(db, user, contest))
    return ContestDetail(
        **base.model_dump(),
        problems=[StudentTaskOut.build(t) for t in tasks],
        writing=contests.active_window(db, user.id, contest, now) is not None,
    )


@router.post("/contests/{contest_id}/virtual", status_code=status.HTTP_201_CREATED)
def start_virtual(
    contest_id: int, request: Request, user: CurrentUser, db: DbSession
) -> VirtualOut:
    """ОТ-03: write a finished contest under the same conditions, from now on."""
    contest = _contest(db, contest_id)
    try:
        window = contests.start_virtual(db, user, contest, datetime.now(UTC))
    except contests.ContestError as exc:
        raise HTTPException(exc.status, detail=exc.code) from None
    audit.record(
        db,
        AuditAction.VIRTUAL_CONTEST_STARTED,
        actor_id=user.id,
        object_type="assessment",
        object_id=contest.id,
        ip=client_ip(request),
    )
    db.commit()
    return VirtualOut(started_at=window.start, ends_at=window.end)


@router.get("/contests/{contest_id}/standings")
def get_standings(contest_id: int, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    contest = _contest(db, contest_id)
    now = datetime.now(UTC)
    staff = is_staff(user) and can_view_course(db, user, contest.course_id)
    if not staff and (
        not studies_course(db, user.id, contest.course_id) or now < contest.starts_at
    ):
        raise _forbidden()
    # Access is checked above; the standings read other participants' rows, which
    # row-level security hides from a student (migration 0006). Names stay hidden.
    set_system(db)
    return contests.standings(db, contest, user, staff, now)
