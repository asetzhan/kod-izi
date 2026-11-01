"""Stage 6b part 2: student model (ФТ-39), next task (ФТ-44), trajectory (ФТ-45), LLM task
drafts (ФТ-21) and problem extraction (ФТ-23), code similarity (ФТ-30).
"""

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.content_schemas import TaskSummary
from app.api.deps import AdminUser, CurrentUser, DbSession, client_ip
from app.api.privacy import _assessment_for_teacher
from app.core.enums import MaterialStatus, TaskLevel
from app.jobs import get_similarity_enqueue
from app.judge import get_judge
from app.judge.client import JudgeClient
from app.llm.ollama import LLMUnavailableError
from app.llm.registry import get_provider
from app.models import (
    AppSetting,
    AssessmentTask,
    CourseGroup,
    GroupMember,
    Material,
    MaterialVersion,
    SimilarityReport,
    Topic,
    User,
)
from app.services import audit, bkt
from app.services.access import can_edit_course, can_view_user, studies_course
from app.services.audit import AuditAction
from app.services.progress import next_step, trajectory
from app.services.task_generation import (
    GenerationError,
    chapters,
    extract_problems,
    generate_task,
)

router = APIRouter(prefix="/api", tags=["learning"])

Judge = Annotated[JudgeClient, Depends(get_judge)]
Enqueue = Annotated[Callable[[int], None], Depends(get_similarity_enqueue)]
# One generation per course at a time: each one calls the model and Judge0.
GENERATION_LOCK = 4_710_006


def _forbidden() -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")


# Student model, next task, trajectory (ФТ-39, ФТ-44, ФТ-45) ----------------------------------


@router.get("/courses/{course_id}/students/{student_id}/progress")
def student_progress(
    course_id: int, student_id: int, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    """For the student's own teachers: the model, the next task and the trajectory."""
    if not can_edit_course(db, user, course_id) or not can_view_user(db, user, student_id):
        raise _forbidden()
    if not studies_course(db, student_id, course_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    return {
        "next": next_step(db, course_id, student_id),
        "trajectory": trajectory(db, course_id, student_id),
    }


@router.get("/my/progress")
def my_progress(course_id: int, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """The student's own view. Task titles are left out: the teacher gives the task
    (ФТ-05), the student sees what to work on and which lessons to revisit."""
    if not studies_course(db, user.id, course_id):
        raise _forbidden()
    step = next_step(db, course_id, user.id)
    step["tasks"] = []
    return {"next": step, "trajectory": trajectory(db, course_id, user.id)}


@router.get("/settings/bkt")
def read_bkt(admin: AdminUser, db: DbSession) -> bkt.BktParams:
    return bkt.get_params(db)


@router.put("/settings/bkt")
def save_bkt(
    body: bkt.BktParams, request: Request, admin: AdminUser, db: DbSession
) -> bkt.BktParams:
    stored = db.get(AppSetting, bkt.BKT_KEY)
    if stored is None:
        db.add(AppSetting(key=bkt.BKT_KEY, value=body.model_dump(), updated_by=admin.id))
    else:
        stored.value = body.model_dump()
        stored.updated_by = admin.id
    audit.record(
        db,
        AuditAction.SETTING_CHANGED,
        actor_id=admin.id,
        object_type="setting",
        object_id=bkt.BKT_KEY,
        ip=client_ip(request),
        details=body.model_dump(),
    )
    db.commit()
    return body


@router.post("/courses/{course_id}/bkt/fit")
def fit_bkt(course_id: int, admin: AdminUser, db: DbSession) -> dict[str, Any]:
    """Parameters fitted on the course's attempts; the administrator decides to save them."""
    students = db.scalars(
        select(GroupMember.user_id)
        .join(CourseGroup, CourseGroup.group_id == GroupMember.group_id)
        .where(CourseGroup.course_id == course_id)
        .distinct()
    ).all()
    sequences = [
        seq
        for user_id in students
        for seq in bkt.observations(db, course_id, user_id).values()
        if seq
    ]
    current = bkt.get_params(db)
    fitted = bkt.fit(sequences, current.threshold) if sequences else current
    return {"sequences": len(sequences), "params": fitted.model_dump()}


# LLM task drafts (ФТ-21) and problem extraction (ФТ-23) --------------------------------------


def _generation_lock(db: DbSession, course_id: int) -> None:
    if not db.scalar(select(func.pg_try_advisory_xact_lock(GENERATION_LOCK, course_id))):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="generation_running")


def _ready_versions(db: DbSession, course_id: int) -> set[int]:
    return set(
        db.scalars(
            select(MaterialVersion.id)
            .join(Material, Material.id == MaterialVersion.material_id)
            .where(
                Material.course_id == course_id,
                MaterialVersion.status == MaterialStatus.READY.value,
            )
        )
    )


class GenerateIn(BaseModel):
    topic_id: int
    level: TaskLevel = TaskLevel.I
    language: str = Field(default="kk", pattern="^(kk|ru)$")
    # A chapter of a course book (spec 9.2, step 4); none: from the topic only.
    version_id: int | None = None
    chapter: str | None = Field(default=None, max_length=300)


class GeneratedOut(BaseModel):
    task: TaskSummary
    dropped_tests: int
    notes: list[str]


def _generation_error(exc: GenerationError) -> HTTPException:
    code = status.HTTP_503_SERVICE_UNAVAILABLE if exc.code == "judge_unavailable" else 422
    return HTTPException(code, detail=exc.code)


@router.post("/courses/{course_id}/tasks/generate", status_code=status.HTTP_201_CREATED)
def generate(
    course_id: int,
    body: GenerateIn,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    judge: Judge,
) -> GeneratedOut:
    if not can_edit_course(db, user, course_id):
        raise _forbidden()
    topic = db.get(Topic, body.topic_id)
    if topic is None or topic.course_id != course_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="topic_not_in_course")
    if body.version_id is not None and body.version_id not in _ready_versions(db, course_id):
        raise _forbidden()  # only a ready book of this course
    _generation_lock(db, course_id)
    try:
        result = generate_task(
            db,
            get_provider(),
            judge,
            topic,
            body.level.value,
            body.language,
            body.version_id,
            body.chapter,
            user.id,
        )
    except GenerationError as exc:
        raise _generation_error(exc) from None
    except LLMUnavailableError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="llm_unavailable") from None
    audit.record(
        db,
        AuditAction.TASK_GENERATED,
        actor_id=user.id,
        object_type="task",
        object_id=result.task.id,
        ip=client_ip(request),
        details={
            "topic_id": topic.id,
            "level": body.level.value,
            "version_id": body.version_id,
            "chapter": body.chapter,
        },
    )
    db.commit()
    db.refresh(result.task)
    return GeneratedOut(
        task=TaskSummary.model_validate(result.task),
        dropped_tests=result.dropped_tests,
        notes=result.notes,
    )


@router.get("/materials/{material_id}/versions/{version_id}/chapters")
def material_chapters(
    material_id: int, version_id: int, user: CurrentUser, db: DbSession
) -> list[dict[str, Any]]:
    material = db.get(Material, material_id)
    version = db.get(MaterialVersion, version_id)
    if (
        material is None
        or version is None
        or version.material_id != material.id
        or not can_edit_course(db, user, material.course_id)
    ):
        raise _forbidden()
    return chapters(db, version.id)


class ExtractIn(BaseModel):
    version_id: int
    offset: int = Field(default=0, ge=0)


class ExtractOut(BaseModel):
    tasks: list[TaskSummary]
    next_offset: int
    done: bool


@router.post("/materials/{material_id}/extract-problems", status_code=status.HTTP_201_CREATED)
def extract(
    material_id: int, body: ExtractIn, request: Request, user: CurrentUser, db: DbSession
) -> ExtractOut:
    """One batch of the collection per call; call again with `next_offset` until `done`."""
    material = db.get(Material, material_id)
    if material is None or not can_edit_course(db, user, material.course_id):
        raise _forbidden()
    version = db.get(MaterialVersion, body.version_id)
    if version is None or version.material_id != material.id:
        raise _forbidden()
    if version.status != MaterialStatus.READY.value:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="not_ready")
    _generation_lock(db, material.course_id)
    try:
        tasks, next_offset = extract_problems(
            db, get_provider(), version, material.course_id, body.offset, user.id
        )
    except GenerationError as exc:
        raise _generation_error(exc) from None
    except LLMUnavailableError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="llm_unavailable") from None
    if tasks:
        audit.record(
            db,
            AuditAction.TASK_GENERATED,
            actor_id=user.id,
            object_type="material_version",
            object_id=version.id,
            ip=client_ip(request),
            details={"extracted": [t.id for t in tasks], "offset": body.offset},
        )
    db.commit()
    for task in tasks:
        db.refresh(task)
    return ExtractOut(
        tasks=[TaskSummary.model_validate(t) for t in tasks],
        next_offset=next_offset,
        done=next_offset == body.offset,
    )


# Code similarity (ФТ-30) ---------------------------------------------------------------------


class SimilarityIn(BaseModel):
    task_id: int


class PairOut(BaseModel):
    a: int
    b: int
    a_name: str
    b_name: str
    similarity: float


class ReportOut(BaseModel):
    id: int
    task_id: int
    status: str
    engine: str
    error: str | None
    pairs: list[PairOut]


@router.post("/assessments/{assessment_id}/similarity", status_code=status.HTTP_202_ACCEPTED)
def start_similarity(
    assessment_id: int, body: SimilarityIn, user: CurrentUser, db: DbSession, enqueue: Enqueue
) -> ReportOut:
    assessment = _assessment_for_teacher(db, user, assessment_id)
    if db.get(AssessmentTask, (assessment.id, body.task_id)) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="task_not_in_assessment")
    running = db.scalar(
        select(SimilarityReport.id).where(
            SimilarityReport.assessment_id == assessment.id,
            SimilarityReport.task_id == body.task_id,
            SimilarityReport.status == "pending",
        )
    )
    if running is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="analysis_running")
    report = SimilarityReport(assessment_id=assessment.id, task_id=body.task_id, created_by=user.id)
    db.add(report)
    db.commit()
    enqueue(report.id)
    db.refresh(report)
    return _report_out(db, user, report)


def _report_out(db: DbSession, user: User, report: SimilarityReport) -> ReportOut:
    """Only pairs where the teacher teaches both students are shown."""
    pairs = []
    for pair in report.pairs:
        if not (can_view_user(db, user, pair["a"]) and can_view_user(db, user, pair["b"])):
            continue
        a, b = db.get(User, pair["a"]), db.get(User, pair["b"])
        pairs.append(
            PairOut(
                a=pair["a"],
                b=pair["b"],
                a_name=a.full_name if a else "",
                b_name=b.full_name if b else "",
                similarity=pair["similarity"],
            )
        )
    return ReportOut(
        id=report.id,
        task_id=report.task_id,
        status=report.status,
        engine=report.engine,
        error=report.error,
        pairs=pairs,
    )


@router.get("/assessments/{assessment_id}/similarity")
def list_similarity(assessment_id: int, user: CurrentUser, db: DbSession) -> list[ReportOut]:
    assessment = _assessment_for_teacher(db, user, assessment_id)
    reports = db.scalars(
        select(SimilarityReport)
        .where(SimilarityReport.assessment_id == assessment.id)
        .order_by(SimilarityReport.id.desc())
    )
    return [_report_out(db, user, r) for r in reports]
