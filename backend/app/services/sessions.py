"""Work sessions (ФТ-24, ФТ-25): who may work on which task, and when.

In an assessment a student has one active session: opening a new one (another tab or
computer) closes the previous one, and the old one can no longer write (spec 14.1).
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import TaskStatus, TraceKind
from app.core.roles import Role
from app.models import Assessment, AssessmentTask, Task, TraceEvent, User, WorkSession
from app.services.access import can_edit_course, is_staff, studies_course
from app.services.trace import record_server_event


class SessionError(Exception):
    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


def _check_access(db: Session, user: User, task: Task, assessment: Assessment | None) -> None:
    if assessment is None:
        # Practice outside an assessment: only for staff checking their tasks for now.
        if not is_staff(user):
            raise SessionError(403, "forbidden")
        return
    if user.has_role(Role.STUDENT) and not is_staff(user):
        in_assessment = db.get(AssessmentTask, (assessment.id, task.id)) is not None
        if (
            not in_assessment
            or task.status != TaskStatus.APPROVED.value
            or not studies_course(db, user.id, assessment.course_id)
        ):
            raise SessionError(403, "forbidden")
        now = datetime.now(UTC)
        if now < assessment.starts_at:
            raise SessionError(403, "forbidden")
        if now > assessment.ends_at:
            raise SessionError(409, "assessment_closed")
    elif not can_edit_course(db, user, assessment.course_id):
        raise SessionError(403, "forbidden")


def open_session(
    db: Session, user: User, task_id: int, assessment_id: int | None, user_agent: str | None
) -> WorkSession:
    task = db.get(Task, task_id)
    assessment = db.get(Assessment, assessment_id) if assessment_id is not None else None
    if task is None or (assessment_id is not None and assessment is None):
        raise SessionError(403, "forbidden")
    _check_access(db, user, task, assessment)

    if assessment is not None:
        previous = db.scalars(
            select(WorkSession)
            .where(
                WorkSession.user_id == user.id,
                WorkSession.assessment_id == assessment.id,
                WorkSession.closed_at.is_(None),
            )
            .with_for_update()
        ).all()
        for old in previous:
            old.closed_at = datetime.now(UTC)
            old.closed_reason = "replaced"
            record_server_event(db, old, TraceKind.SESSION_CLOSED, {"reason": "replaced"})

    session = WorkSession(
        user_id=user.id,
        task_id=task.id,
        assessment_id=assessment_id,
        user_agent=(user_agent or "")[:255] or None,
    )
    db.add(session)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        # Another request opened a session at the same moment (unique index).
        raise SessionError(409, "session_conflict") from None
    record_server_event(db, session, TraceKind.SESSION_START, {"user_agent": session.user_agent})
    return session


def writable_session(db: Session, user: User, session_id: object) -> WorkSession:
    session = db.get(WorkSession, session_id)
    if session is None or session.user_id != user.id:
        raise SessionError(403, "forbidden")
    if session.closed_at is not None:
        raise SessionError(409, "session_closed")
    if session.assessment_id is not None:
        assessment = db.get(Assessment, session.assessment_id)
        if assessment is not None and datetime.now(UTC) > assessment.ends_at:
            raise SessionError(409, "assessment_closed")
    return session


def latest_code(db: Session, user_id: int, task_id: int, assessment_id: int | None) -> str:
    """Code of the last snapshot or submission, to resume after a reload or a new tab."""
    row = db.scalar(
        select(TraceEvent.payload)
        .where(
            TraceEvent.user_id == user_id,
            TraceEvent.task_id == task_id,
            TraceEvent.assessment_id.is_(None)
            if assessment_id is None
            else TraceEvent.assessment_id == assessment_id,
            TraceEvent.kind.in_([TraceKind.SNAPSHOT.value, TraceKind.SUBMIT.value]),
        )
        .order_by(TraceEvent.id.desc())
        .limit(1)
    )
    return str(row.get("code", "")) if row else ""
