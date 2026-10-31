"""Task bank (ФТ-10, ФТ-18, ФТ-19, ФТ-22).

Staff see full tasks. Students see a task only when it is approved and part of a started
assessment of their course, and then without hidden tests or the reference solution.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError

from app.api.content_schemas import (
    LevelConfirm,
    StudentTaskOut,
    TaskCreate,
    TaskIn,
    TaskOut,
    TaskSummary,
)
from app.api.deps import AppSettings, CurrentUser, DbSession, client_ip
from app.core.enums import LevelStatus, TaskLevel, TaskStatus
from app.llm.registry import get_provider
from app.models import Assessment, AssessmentTask, Task, User
from app.services import audit
from app.services.access import can_edit_course, is_staff, studies_course
from app.services.audit import AuditAction
from app.services.levels import RuleError, get_rule, suggest_features
from app.services.task_import import ImportedTest, TaskImportError, parse_package, read_zip
from app.services.tasks import (
    TaskError,
    apply_level,
    approve,
    create_from_draft,
    set_knowledge_components,
    set_tests,
    topic_in_course,
)

router = APIRouter(prefix="/api", tags=["tasks"])


def _forbidden() -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")


def _bad_request(code: str, message: str) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": code, "message": message}
    )


def _task_for_edit(db: DbSession, user: User, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        # Staff may learn that the id does not exist; others get the same 403 as always.
        raise (
            HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
            if is_staff(user)
            else _forbidden()
        )
    if not can_edit_course(db, user, task.course_id):
        raise _forbidden()
    return task


def student_can_see_task(db: DbSession, student_id: int, task: Task) -> bool:
    if task.status != TaskStatus.APPROVED.value:
        return False
    started = (
        select(Assessment.id)
        .join(AssessmentTask, AssessmentTask.assessment_id == Assessment.id)
        .where(AssessmentTask.task_id == task.id, Assessment.starts_at <= datetime.now(UTC))
    )
    return bool(db.scalar(select(exists(started)))) and studies_course(
        db, student_id, task.course_id
    )


@router.get("/tasks")
def list_tasks(
    user: CurrentUser,
    db: DbSession,
    course_id: int | None = None,
    topic_id: int | None = None,
    level: TaskLevel | None = None,
    task_status: Annotated[TaskStatus | None, Query(alias="status")] = None,
) -> list[TaskSummary]:
    if not is_staff(user):
        raise _forbidden()
    query = select(Task).order_by(Task.course_id, Task.topic_id, Task.id)
    if course_id is not None:
        query = query.where(Task.course_id == course_id)
    if topic_id is not None:
        query = query.where(Task.topic_id == topic_id)
    if level is not None:
        query = query.where(Task.level == level.value)
    if task_status is not None:
        query = query.where(Task.status == task_status.value)
    return [TaskSummary.model_validate(t) for t in db.scalars(query)]


def _fill(db: DbSession, task: Task, body: TaskIn) -> None:
    try:
        topic_in_course(db, task.course_id, body.topic_id)
    except TaskError as exc:
        raise _bad_request(exc.code, str(exc)) from None
    task.topic_id = body.topic_id
    for name in (
        "title",
        "statement_md",
        "input_format",
        "output_format",
        "time_limit_ms",
        "memory_limit_kb",
        "reference_solution",
        "reference_language",
        "source_note",
    ):
        setattr(task, name, getattr(body, name))
    task.source_url = str(body.source_url) if body.source_url else None
    set_tests(task, [ImportedTest(t.input, t.expected_output, t.is_hidden) for t in body.tests])
    try:
        set_knowledge_components(db, task, body.knowledge_component_ids)
    except TaskError as exc:
        raise _bad_request(exc.code, str(exc)) from None


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
def create_task(body: TaskCreate, request: Request, user: CurrentUser, db: DbSession) -> TaskOut:
    if not can_edit_course(db, user, body.course_id):
        raise _forbidden()
    task = Task(course_id=body.course_id, author_id=user.id, status=TaskStatus.DRAFT.value)
    db.add(task)
    _fill(db, task, body)
    db.flush()
    audit.record(
        db,
        AuditAction.TASK_CREATED,
        actor_id=user.id,
        object_type="task",
        object_id=task.id,
        ip=client_ip(request),
    )
    db.commit()
    return TaskOut.build(task)


@router.get("/tasks/{task_id}", response_model=TaskOut | StudentTaskOut)
def get_task(task_id: int, user: CurrentUser, db: DbSession) -> TaskOut | StudentTaskOut:
    task = db.get(Task, task_id)
    if is_staff(user):
        if task is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
        return TaskOut.build(task)
    if task is None or not student_can_see_task(db, user.id, task):
        raise _forbidden()
    return StudentTaskOut.build(task)


@router.put("/tasks/{task_id}")
def update_task(
    task_id: int, body: TaskIn, request: Request, user: CurrentUser, db: DbSession
) -> TaskOut:
    task = _task_for_edit(db, user, task_id)
    _fill(db, task, body)
    audit.record(
        db,
        AuditAction.TASK_UPDATED,
        actor_id=user.id,
        object_type="task",
        object_id=task.id,
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(task)
    return TaskOut.build(task)


class LevelSuggestionOut(BaseModel):
    features: dict[str, int]
    level: TaskLevel
    rationale: str
    saved: bool


@router.post("/tasks/{task_id}/level-suggestion")
def suggest_level(task_id: int, user: CurrentUser, db: DbSession) -> LevelSuggestionOut:
    """ФТ-19: the system proposes feature scores; a confirmed level is never overwritten."""
    task = _task_for_edit(db, user, task_id)
    rule = get_rule(db)
    try:
        scores, rationale = suggest_features(task, get_provider())
        level = rule.level_for(scores)
    except RuleError as exc:
        raise _bad_request("bad_suggestion", str(exc)) from None
    saved = task.level_status != LevelStatus.CONFIRMED.value
    if saved:
        apply_level(task, rule, scores, LevelStatus.SUGGESTED, rationale=rationale)
        db.commit()
    return LevelSuggestionOut(features=scores, level=level, rationale=rationale, saved=saved)


@router.put("/tasks/{task_id}/level")
def confirm_level(
    task_id: int, body: LevelConfirm, request: Request, user: CurrentUser, db: DbSession
) -> TaskOut:
    """ФТ-19: the teacher confirms or changes the feature scores and the level."""
    task = _task_for_edit(db, user, task_id)
    scores = body.features.model_dump()
    rule = get_rule(db)
    apply_level(task, rule, scores, LevelStatus.CONFIRMED, body.level, body.rationale)
    audit.record(
        db,
        AuditAction.TASK_LEVEL_CONFIRMED,
        actor_id=user.id,
        object_type="task",
        object_id=task.id,
        ip=client_ip(request),
        details={
            "features": scores,
            "level": task.level,
            "rule_level": rule.level_for(scores).value,
        },
    )
    db.commit()
    return TaskOut.build(task)


@router.post("/tasks/{task_id}/approve")
def approve_task(task_id: int, request: Request, user: CurrentUser, db: DbSession) -> TaskOut:
    task = _task_for_edit(db, user, task_id)
    try:
        approve(task)
    except TaskError as exc:
        raise _bad_request(exc.code, str(exc)) from None
    audit.record(
        db,
        AuditAction.TASK_APPROVED,
        actor_id=user.id,
        object_type="task",
        object_id=task.id,
        ip=client_ip(request),
    )
    db.commit()
    return TaskOut.build(task)


@router.post("/courses/{course_id}/tasks/import", status_code=status.HTTP_201_CREATED)
async def import_task(
    course_id: int,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
    file: Annotated[UploadFile, File()],
) -> TaskOut:
    """ФТ-22: ZIP package (docs/formats/task-package.md) or Polygon package."""
    if not can_edit_course(db, user, course_id):
        raise _forbidden()
    data = await file.read(settings.max_import_bytes + 1)
    if len(data) > settings.max_import_bytes:
        raise _bad_request("too_large", "the archive is larger than the allowed size")
    try:
        draft = parse_package(read_zip(data))
        task = create_from_draft(db, course_id, draft, get_rule(db), author_id=user.id)
    except (TaskImportError, TaskError, RuleError) as exc:
        db.rollback()
        code = getattr(exc, "code", "bad_package")
        raise _bad_request(code, str(exc)) from None
    except IntegrityError:
        db.rollback()
        raise _bad_request("duplicate_key", "a task with this key already exists") from None
    audit.record(
        db,
        AuditAction.TASK_IMPORTED,
        actor_id=user.id,
        object_type="task",
        object_id=task.id,
        ip=client_ip(request),
        details={"file": file.filename},
    )
    db.commit()
    db.refresh(task)
    return TaskOut.build(task)
