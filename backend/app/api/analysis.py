"""Stage 3 API: rubric, teaching materials, AI grades, assistant.

ФТ-06, ФТ-11, ФТ-13, ФТ-15, ФТ-16, ФТ-34, ФТ-35, ФТ-47, ФТ-48.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from app.api.deps import AppSettings, CurrentUser, DbSession, client_ip
from app.core.enums import MaterialKind, MaterialStatus
from app.jobs import get_material_enqueue
from app.llm import gateway
from app.llm.ollama import LLMUnavailableError
from app.llm.registry import get_provider
from app.models import (
    AiGrade,
    AiMessage,
    Assessment,
    Chunk,
    Material,
    MaterialBinding,
    MaterialVersion,
    Submission,
    Task,
    Topic,
    User,
    WorkSession,
)
from app.services import ai_grading, audit
from app.services.access import can_edit_course, can_view_course
from app.services.assistant import AssistantForbiddenError, ask
from app.services.audit import AuditAction
from app.services.component_fill import fill_submission
from app.services.extract import ExtractError
from app.services.materials import current_version, store_version
from app.services.rubrics import CRITERIA_CODES, get_or_create_rubric
from app.services.sessions import SessionError, writable_session

router = APIRouter(prefix="/api", tags=["analysis"])

MaterialEnqueue = Annotated[Callable[[int], None], Depends(get_material_enqueue)]


def _forbidden() -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")


def _unprocessable(code: str, message: str = "") -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": code, "message": message}
    )


def _require_edit(db: DbSession, user: User, course_id: int) -> None:
    if not can_edit_course(db, user, course_id):
        raise _forbidden()


# Rubric (ФТ-13, ФТ-15) -----------------------------------------------------------------


class CriterionIO(BaseModel):
    code: str
    name: str = Field(min_length=1, max_length=200)
    indicators: str = Field(default="", max_length=5000)
    data_sources: str = Field(default="", max_length=5000)
    descriptor_low: str = Field(min_length=1, max_length=5000)
    descriptor_mid: str = Field(min_length=1, max_length=5000)
    descriptor_high: str = Field(min_length=1, max_length=5000)


class RubricIO(BaseModel):
    weight_f: float = Field(ge=0, le=1)
    weight_e: float = Field(ge=0, le=1)
    weight_a: float = Field(ge=0, le=1)
    component_scales: dict[str, str]
    criteria: list[CriterionIO]

    @model_validator(mode="after")
    def _valid(self) -> "RubricIO":
        if abs(self.weight_f + self.weight_e + self.weight_a - 1) > 0.001:
            raise ValueError("weights must add up to 1")
        if sorted(c.code for c in self.criteria) != sorted(CRITERIA_CODES):
            raise ValueError(f"criteria must be exactly {list(CRITERIA_CODES)}")
        if set(self.component_scales) != {"F", "E", "A"}:
            raise ValueError("component_scales must describe F, E and A")
        return self


@router.get("/courses/{course_id}/rubric")
def read_rubric(course_id: int, user: CurrentUser, db: DbSession) -> RubricIO:
    _require_edit(db, user, course_id)
    rubric = get_or_create_rubric(db, course_id)
    db.commit()
    return RubricIO(
        weight_f=rubric.weight_f,
        weight_e=rubric.weight_e,
        weight_a=rubric.weight_a,
        component_scales=rubric.component_scales,
        criteria=[CriterionIO.model_validate(c, from_attributes=True) for c in rubric.criteria],
    )


@router.put("/courses/{course_id}/rubric")
def update_rubric(
    course_id: int, body: RubricIO, request: Request, user: CurrentUser, db: DbSession
) -> RubricIO:
    """The teacher adapts descriptors and weights; the six criteria stay (ФТ-13)."""
    _require_edit(db, user, course_id)
    rubric = get_or_create_rubric(db, course_id)
    rubric.weight_f, rubric.weight_e, rubric.weight_a = body.weight_f, body.weight_e, body.weight_a
    rubric.component_scales = body.component_scales
    rubric.updated_by = user.id
    by_code = {c.code: c for c in body.criteria}
    for criterion in rubric.criteria:
        new = by_code[criterion.code]
        for field in (
            "name",
            "indicators",
            "data_sources",
            "descriptor_low",
            "descriptor_mid",
            "descriptor_high",
        ):
            setattr(criterion, field, getattr(new, field))
    audit.record(
        db,
        AuditAction.RUBRIC_UPDATED,
        actor_id=user.id,
        object_type="course",
        object_id=course_id,
        ip=client_ip(request),
        details={"weights": [body.weight_f, body.weight_e, body.weight_a]},
    )
    db.commit()
    return body


# Materials (ФТ-06, ФТ-11) ----------------------------------------------------------------


class VersionOut(BaseModel):
    id: int
    version: int
    filename: str
    mime: str
    size_bytes: int
    status: MaterialStatus
    error: str | None
    pages: int | None
    created_at: datetime


class MaterialOut(BaseModel):
    id: int
    course_id: int
    title: str
    author: str
    kind: MaterialKind
    versions: list[VersionOut]

    @classmethod
    def build(cls, m: Material) -> "MaterialOut":
        return cls(
            id=m.id,
            course_id=m.course_id,
            title=m.title,
            author=m.author,
            kind=MaterialKind(m.kind),
            versions=[VersionOut.model_validate(v, from_attributes=True) for v in m.versions],
        )


async def _read_upload(file: UploadFile, limit: int) -> bytes:
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise _unprocessable("too_large", f"files up to {limit // (1024 * 1024)} MB")
    return data


@router.post("/courses/{course_id}/materials", status_code=status.HTTP_201_CREATED)
async def upload_material(
    course_id: int,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
    enqueue: MaterialEnqueue,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(min_length=1, max_length=300)],
    kind: Annotated[MaterialKind, Form()],
    rights_confirmed: Annotated[bool, Form()],
    author: Annotated[str, Form(max_length=300)] = "",
) -> MaterialOut:
    """ФТ-06. Q-11: the teacher confirms the right to use the material."""
    _require_edit(db, user, course_id)
    if not rights_confirmed:
        raise _unprocessable("rights_not_confirmed")
    data = await _read_upload(file, settings.max_material_bytes)
    material = Material(
        course_id=course_id,
        title=title,
        author=author,
        kind=kind.value,
        rights_confirmed_by=user.id,
        rights_confirmed_at=datetime.now(UTC),
    )
    db.add(material)
    db.flush()
    try:
        version = store_version(db, material, file.filename or "file", data)
    except ExtractError as exc:
        db.rollback()
        raise _unprocessable(str(exc)) from None
    audit.record(
        db,
        AuditAction.MATERIAL_UPLOADED,
        actor_id=user.id,
        object_type="material",
        object_id=material.id,
        ip=client_ip(request),
        details={"filename": version.filename, "sha256": version.sha256, "rights_confirmed": True},
    )
    db.commit()
    enqueue(version.id)
    db.refresh(material)
    return MaterialOut.build(material)


@router.post("/materials/{material_id}/versions", status_code=status.HTTP_201_CREATED)
async def replace_material(
    material_id: int,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
    enqueue: MaterialEnqueue,
    file: Annotated[UploadFile, File()],
    rights_confirmed: Annotated[bool, Form()],
) -> MaterialOut:
    """A new version; grades keep the version they cited (spec 9.4)."""
    material = db.get(Material, material_id)
    if material is None or not can_edit_course(db, user, material.course_id):
        raise _forbidden()
    if not rights_confirmed:
        raise _unprocessable("rights_not_confirmed")
    data = await _read_upload(file, settings.max_material_bytes)
    try:
        version = store_version(db, material, file.filename or "file", data)
    except ExtractError as exc:
        db.rollback()
        raise _unprocessable(str(exc)) from None
    material.rights_confirmed_by, material.rights_confirmed_at = user.id, datetime.now(UTC)
    audit.record(
        db,
        AuditAction.MATERIAL_UPLOADED,
        actor_id=user.id,
        object_type="material",
        object_id=material.id,
        ip=client_ip(request),
        details={"filename": version.filename, "version": version.version},
    )
    db.commit()
    enqueue(version.id)
    db.refresh(material)
    return MaterialOut.build(material)


@router.get("/courses/{course_id}/materials")
def list_materials(course_id: int, user: CurrentUser, db: DbSession) -> list[MaterialOut]:
    """ФТ-06: visible to the course's participants only."""
    if not can_view_course(db, user, course_id):
        raise _forbidden()
    materials = db.scalars(
        select(Material).where(Material.course_id == course_id).order_by(Material.id)
    )
    out = [MaterialOut.build(m) for m in materials]
    if can_edit_course(db, user, course_id):
        return out
    # Students: ready versions only, without internal processing errors.
    for material in out:
        material.versions = [v for v in material.versions if v.status == MaterialStatus.READY]
    return [m for m in out if m.versions]


@router.get("/materials/{material_id}/file")
def download_material(
    material_id: int, user: CurrentUser, db: DbSession, settings: AppSettings
) -> FileResponse:
    """Only the course's teachers download the whole file; students see fragments (spec 9.4)."""
    material = db.get(Material, material_id)
    if material is None or not can_edit_course(db, user, material.course_id):
        raise _forbidden()
    version = current_version(material)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_ready")
    return FileResponse(
        settings.material_dir / version.stored_name,
        media_type=version.mime,
        filename=version.filename,
        headers={"X-Content-Type-Options": "nosniff"},
        content_disposition_type="attachment",
    )


class ChunkOut(BaseModel):
    id: int
    material_id: int
    material_title: str
    version: int
    chapter: str
    page: int | None
    text: str


@router.get("/chunks/{chunk_id}")
def read_chunk(chunk_id: int, user: CurrentUser, db: DbSession) -> ChunkOut:
    """The fragment an AI grade cites, opened with one click by the teacher (spec 9.3)."""
    chunk = db.get(Chunk, chunk_id)
    version = db.get(MaterialVersion, chunk.version_id) if chunk else None
    material = db.get(Material, version.material_id) if version else None
    if chunk is None or version is None or material is None:
        raise _forbidden()
    if not can_edit_course(db, user, material.course_id):
        raise _forbidden()
    return ChunkOut(
        id=chunk.id,
        material_id=material.id,
        material_title=material.title,
        version=version.version,
        chapter=chunk.chapter,
        page=chunk.page,
        text=chunk.text,
    )


class BindingIO(BaseModel):
    id: int | None = None
    material_id: int | None = None
    topic_id: int | None = None
    task_id: int | None = None
    assessment_id: int | None = None
    chapter: str = Field(default="", max_length=300)
    page_from: int | None = Field(default=None, ge=1)
    page_to: int | None = Field(default=None, ge=1)
    is_assessment_basis: bool = False
    requirements: str = Field(default="", max_length=10_000)

    @model_validator(mode="after")
    def _valid(self) -> "BindingIO":
        targets = [t for t in (self.topic_id, self.task_id, self.assessment_id) if t is not None]
        if len(targets) != 1:
            raise ValueError("bind to exactly one of topic, task or assessment")
        if self.page_from and self.page_to and self.page_from > self.page_to:
            raise ValueError("page_from must not exceed page_to")
        return self


def _target_course(db: DbSession, body: BindingIO) -> int | None:
    if body.topic_id is not None:
        topic = db.get(Topic, body.topic_id)
        return topic.course_id if topic else None
    if body.task_id is not None:
        task = db.get(Task, body.task_id)
        return task.course_id if task else None
    assessment = db.get(Assessment, body.assessment_id)
    return assessment.course_id if assessment else None


@router.post("/materials/{material_id}/bindings", status_code=status.HTTP_201_CREATED)
def bind_material(
    material_id: int, body: BindingIO, request: Request, user: CurrentUser, db: DbSession
) -> BindingIO:
    """ФТ-11, ФТ-16: chapter/pages → topic, task or assessment; «бағалау негізі» mark."""
    material = db.get(Material, material_id)
    if material is None or not can_edit_course(db, user, material.course_id):
        raise _forbidden()
    if _target_course(db, body) != material.course_id:
        raise _unprocessable("target_not_in_course")
    binding = MaterialBinding(
        material_id=material_id,
        **body.model_dump(exclude={"id", "material_id"}),
    )
    db.add(binding)
    db.flush()
    audit.record(
        db,
        AuditAction.MATERIAL_BOUND,
        actor_id=user.id,
        object_type="material",
        object_id=material_id,
        ip=client_ip(request),
        details={"binding_id": binding.id},
    )
    db.commit()
    return BindingIO.model_validate(binding, from_attributes=True)


@router.get("/materials/{material_id}/bindings")
def list_bindings(material_id: int, user: CurrentUser, db: DbSession) -> list[BindingIO]:
    material = db.get(Material, material_id)
    if material is None or not can_edit_course(db, user, material.course_id):
        raise _forbidden()
    rows = db.scalars(select(MaterialBinding).where(MaterialBinding.material_id == material_id))
    return [BindingIO.model_validate(b, from_attributes=True) for b in rows]


@router.delete("/bindings/{binding_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_binding(binding_id: int, request: Request, user: CurrentUser, db: DbSession) -> None:
    binding = db.get(MaterialBinding, binding_id)
    material = db.get(Material, binding.material_id) if binding else None
    if binding is None or material is None or not can_edit_course(db, user, material.course_id):
        raise _forbidden()
    db.delete(binding)
    audit.record(
        db,
        AuditAction.MATERIAL_BOUND,
        actor_id=user.id,
        object_type="material",
        object_id=material.id,
        ip=client_ip(request),
        details={"removed_binding": binding_id},
    )
    db.commit()


# AI grades (ФТ-34, ФТ-35, ФТ-48) ------------------------------------------------------


class AiGradeOut(BaseModel):
    id: int
    submission_id: int
    status: str
    criteria: list[dict[str, Any]]
    components: dict[str, float | None]
    score: float | None
    interpretation: str
    feedback: str
    next_step: str
    flags: list[str]
    review_reasons: list[str]
    model: str
    prompt_version: str
    weights: dict[str, float]
    fragment_ids: list[int]
    attempts: int
    created_at: datetime

    @classmethod
    def build(cls, g: AiGrade) -> "AiGradeOut":
        return cls(
            id=g.id,
            submission_id=g.submission_id,
            status=g.status,
            criteria=g.criteria,
            components={"F": g.component_f, "E": g.component_e, "A": g.component_a},
            score=g.score,
            interpretation=g.interpretation,
            feedback=g.feedback,
            next_step=g.next_step,
            flags=g.flags,
            review_reasons=g.review_reasons,
            model=g.model,
            prompt_version=g.prompt_version,
            weights=g.weights,
            fragment_ids=g.fragment_ids,
            attempts=g.attempts,
            created_at=g.created_at,
        )


def _teacher_submission(db: DbSession, user: User, submission_id: int) -> Submission:
    """AI grades are for the course's teachers only until confirmed (CLAUDE.md, stage 4)."""
    submission = db.get(Submission, submission_id)
    task = db.get(Task, submission.task_id) if submission else None
    if submission is None or task is None or not can_edit_course(db, user, task.course_id):
        raise _forbidden()
    return submission


@router.get("/submissions/{submission_id}/ai-grades")
def list_ai_grades(submission_id: int, user: CurrentUser, db: DbSession) -> list[AiGradeOut]:
    _teacher_submission(db, user, submission_id)
    rows = db.scalars(
        select(AiGrade).where(AiGrade.submission_id == submission_id).order_by(AiGrade.id.desc())
    )
    return [AiGradeOut.build(g) for g in rows]


@router.post("/submissions/{submission_id}/ai-grades", status_code=status.HTTP_201_CREATED)
def regrade(submission_id: int, request: Request, user: CurrentUser, db: DbSession) -> AiGradeOut:
    """The teacher asks for a new preliminary grade, e.g. after binding a book chapter."""
    submission = _teacher_submission(db, user, submission_id)
    if submission.verdict is None:
        raise _unprocessable("not_tested")
    try:
        record = ai_grading.grade(db, get_provider(), submission)
        db.flush()
        fill_submission(db, submission, record)
    except LLMUnavailableError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="llm_unavailable") from None
    audit.record(
        db,
        AuditAction.AI_GRADE_REQUESTED,
        actor_id=user.id,
        object_type="submission",
        object_id=submission_id,
        ip=client_ip(request),
    )
    db.commit()
    return AiGradeOut.build(record)


# Assistant (ФТ-47) ----------------------------------------------------------------------


class AssistantIn(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    code: str = Field(default="", max_length=100_000)
    ui_language: str = Field(default="kk", pattern="^(kk|ru)$")


class AssistantMessageOut(BaseModel):
    id: int
    question: str
    answer: str
    blocked: bool
    created_at: datetime


@router.post("/sessions/{session_id}/assistant")
def ask_assistant(
    session_id: uuid.UUID, body: AssistantIn, user: CurrentUser, db: DbSession
) -> AssistantMessageOut:
    try:
        session = writable_session(db, user, session_id)
    except SessionError as exc:
        raise HTTPException(exc.status, detail=exc.code) from None
    try:
        message = ask(db, get_provider(), session, body.question, body.code, body.ui_language)
    except AssistantForbiddenError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="assistant_forbidden") from None
    except gateway.QuotaExceededError:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="llm_quota") from None
    db.commit()
    return AssistantMessageOut.model_validate(message, from_attributes=True)


@router.get("/sessions/{session_id}/assistant")
def assistant_history(
    session_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> list[AssistantMessageOut]:
    session = db.get(WorkSession, session_id)
    if session is None or session.user_id != user.id:
        raise _forbidden()
    rows = db.scalars(
        select(AiMessage).where(AiMessage.session_id == session_id).order_by(AiMessage.id)
    ).all()
    return [AssistantMessageOut.model_validate(m, from_attributes=True) for m in rows]
