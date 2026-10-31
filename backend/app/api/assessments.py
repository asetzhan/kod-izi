"""Assessments (ФТ-02): tasks, time window and GenAI mode. Taking them is stage 2."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.content_schemas import (
    AssessmentCreate,
    AssessmentIn,
    AssessmentOut,
    StudentAssessmentOut,
    StudentTaskOut,
)
from app.api.deps import CurrentUser, DbSession, client_ip
from app.core.enums import GenAiMode, TaskStatus
from app.models import Assessment, AssessmentTask, CourseGroup, GroupMember, Task, User
from app.services import audit
from app.services.access import can_edit_course, is_staff, studies_course
from app.services.audit import AuditAction

router = APIRouter(prefix="/api", tags=["assessments"])


def _forbidden() -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")


def _fill(db: DbSession, assessment: Assessment, body: AssessmentIn) -> None:
    tasks = {t.id: t for t in db.scalars(select(Task).where(Task.id.in_(body.task_ids)))}
    for task_id in body.task_ids:
        task = tasks.get(task_id)
        if task is None or task.course_id != assessment.course_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "task_not_in_course", "message": f"task {task_id}"},
            )
        if task.status != TaskStatus.APPROVED.value:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "task_not_approved", "message": f"task {task_id}"},
            )
    assessment.title = body.title
    assessment.starts_at = body.starts_at
    assessment.ends_at = body.ends_at
    assessment.genai_mode = body.genai_mode.value
    assessment.task_links = [
        AssessmentTask(task_id=task_id, position=i)
        for i, task_id in enumerate(dict.fromkeys(body.task_ids), start=1)
    ]


def _save(db: DbSession, request: Request, user: User, assessment: Assessment) -> AssessmentOut:
    db.flush()
    audit.record(
        db,
        AuditAction.ASSESSMENT_SAVED,
        actor_id=user.id,
        object_type="assessment",
        object_id=assessment.id,
        ip=client_ip(request),
        details={"genai_mode": assessment.genai_mode},
    )
    db.commit()
    db.refresh(assessment)
    return AssessmentOut.build(assessment)


@router.post("/assessments", status_code=status.HTTP_201_CREATED)
def create_assessment(
    body: AssessmentCreate, request: Request, user: CurrentUser, db: DbSession
) -> AssessmentOut:
    if not can_edit_course(db, user, body.course_id):
        raise _forbidden()
    assessment = Assessment(course_id=body.course_id, created_by=user.id)
    _fill(db, assessment, body)
    db.add(assessment)
    return _save(db, request, user, assessment)


@router.put("/assessments/{assessment_id}")
def update_assessment(
    assessment_id: int, body: AssessmentIn, request: Request, user: CurrentUser, db: DbSession
) -> AssessmentOut:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None or not can_edit_course(db, user, assessment.course_id):
        raise _forbidden()
    _fill(db, assessment, body)
    return _save(db, request, user, assessment)


@router.get("/assessments")
def list_assessments(
    user: CurrentUser, db: DbSession, course_id: int | None = None
) -> list[AssessmentOut]:
    """Staff: all assessments (optionally of one course). Students: those of their courses."""
    query = select(Assessment).order_by(Assessment.starts_at)
    if course_id is not None:
        query = query.where(Assessment.course_id == course_id)
    if not is_staff(user):
        my_courses = (
            select(CourseGroup.course_id)
            .join(GroupMember, GroupMember.group_id == CourseGroup.group_id)
            .where(GroupMember.user_id == user.id)
        )
        query = query.where(Assessment.course_id.in_(my_courses))
        # Students learn the schedule, not the task list, before the start.
        return [
            AssessmentOut.build(a).model_copy(update={"task_ids": []}) for a in db.scalars(query)
        ]
    return [AssessmentOut.build(a) for a in db.scalars(query)]


@router.get("/assessments/{assessment_id}", response_model=AssessmentOut | StudentAssessmentOut)
def get_assessment(
    assessment_id: int, user: CurrentUser, db: DbSession
) -> AssessmentOut | StudentAssessmentOut:
    assessment = db.get(Assessment, assessment_id)
    if is_staff(user):
        if assessment is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
        return AssessmentOut.build(assessment)
    if (
        assessment is None
        or not studies_course(db, user.id, assessment.course_id)
        or assessment.starts_at > datetime.now(UTC)
    ):
        raise _forbidden()
    tasks = [db.get(Task, link.task_id) for link in assessment.task_links]
    return StudentAssessmentOut(
        id=assessment.id,
        title=assessment.title,
        starts_at=assessment.starts_at,
        ends_at=assessment.ends_at,
        genai_mode=GenAiMode(assessment.genai_mode),
        tasks=[
            StudentTaskOut.build(t)
            for t in tasks
            if t is not None and t.status == TaskStatus.APPROVED.value
        ],
    )
