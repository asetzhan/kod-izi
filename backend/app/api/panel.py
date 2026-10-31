"""Stage 4 API: model components panel, teacher's grade, results for students.

ФТ-03, ФТ-07, ФТ-09, ФТ-14, ФТ-36, ФТ-41, ФТ-42, ФТ-43.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import AdminUser, CurrentUser, DbSession, client_ip
from app.core.enums import EntrySource
from app.llm.ollama import LLMUnavailableError
from app.llm.registry import get_provider
from app.models import (
    AppSetting,
    Assessment,
    ComponentEntry,
    Course,
    CourseGroup,
    GroupMember,
    Observation,
    Submission,
    Task,
    User,
)
from app.services import audit
from app.services.access import can_edit_course, studies_course
from app.services.audit import AuditAction
from app.services.component_fill import descriptors_for, fill_descriptors, fill_goals
from app.services.components import (
    COMPONENT_NAMES,
    EntryError,
    accept_suggestion,
    auto_enabled,
    edit,
    reject_suggestion,
    revert,
    set_auto_enabled,
)
from app.services.results import (
    MASTERY_KEY,
    GradeError,
    MasterySettings,
    confirm,
    confirmed_grade,
    mastery,
    mastery_settings,
)
from app.services.rubrics import get_or_create_rubric

router = APIRouter(prefix="/api", tags=["panel"])

Component = Annotated[int, Field(ge=1, le=5)]


def _forbidden() -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")


def _unprocessable(code: str, message: str = "") -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": code, "message": message}
    )


def _course_for_edit(db: DbSession, user: User, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None or not can_edit_course(db, user, course_id):
        raise _forbidden()
    return course


# Components (ФТ-07) ------------------------------------------------------------------------


class VersionOut(BaseModel):
    version: int
    value: Any
    source: EntrySource
    author_id: int | None
    note: str
    created_at: datetime


class EntryOut(BaseModel):
    id: int
    component: int
    subject_type: str
    subject_id: int
    key: str
    value: Any
    auto_value: Any | None
    source: EntrySource
    suggestion: Any | None
    updated_by: int | None
    updated_at: datetime
    versions: int

    @classmethod
    def build(cls, e: ComponentEntry) -> "EntryOut":
        return cls(
            id=e.id,
            component=e.component,
            subject_type=e.subject_type,
            subject_id=e.subject_id,
            key=e.key,
            value=e.value,
            auto_value=e.auto_value,
            source=EntrySource(e.source),
            suggestion=e.suggestion,
            updated_by=e.updated_by,
            updated_at=e.updated_at,
            versions=len(e.versions),
        )


class ComponentSummary(BaseModel):
    component: int
    name: str
    auto_enabled: bool
    entries: int
    by_source: dict[str, int]
    suggestions: int


@router.get("/courses/{course_id}/components")
def components_overview(course_id: int, user: CurrentUser, db: DbSession) -> list[ComponentSummary]:
    """The model diagram: five components around the core (ФТ-07)."""
    _course_for_edit(db, user, course_id)
    rows = db.execute(
        select(
            ComponentEntry.component,
            ComponentEntry.source,
            func.count(),
            func.count(ComponentEntry.suggestion),
        )
        .where(ComponentEntry.course_id == course_id)
        .group_by(ComponentEntry.component, ComponentEntry.source)
    ).all()
    out = []
    for number, name in COMPONENT_NAMES.items():
        mine = [r for r in rows if r[0] == number]
        out.append(
            ComponentSummary(
                component=number,
                name=name,
                auto_enabled=auto_enabled(db, course_id, number),
                entries=sum(r[2] for r in mine),
                by_source={r[1]: r[2] for r in mine},
                suggestions=sum(r[3] for r in mine),
            )
        )
    return out


@router.get("/courses/{course_id}/components/{component}/entries")
def list_entries(
    course_id: int,
    component: Component,
    user: CurrentUser,
    db: DbSession,
    subject_type: str | None = None,
    subject_id: int | None = None,
) -> list[EntryOut]:
    _course_for_edit(db, user, course_id)
    query = select(ComponentEntry).where(
        ComponentEntry.course_id == course_id, ComponentEntry.component == component
    )
    if subject_type is not None:
        query = query.where(ComponentEntry.subject_type == subject_type)
    if subject_id is not None:
        query = query.where(ComponentEntry.subject_id == subject_id)
    return [EntryOut.build(e) for e in db.scalars(query.order_by(ComponentEntry.id))]


class AutoSetting(BaseModel):
    auto_enabled: bool


@router.put("/courses/{course_id}/components/{component}/settings")
def component_settings(
    course_id: int,
    component: Component,
    body: AutoSetting,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> AutoSetting:
    _course_for_edit(db, user, course_id)
    set_auto_enabled(db, course_id, component, body.auto_enabled)
    audit.record(
        db,
        AuditAction.COMPONENT_EDITED,
        actor_id=user.id,
        object_type="course",
        object_id=course_id,
        ip=client_ip(request),
        details={"component": component, "auto_enabled": body.auto_enabled},
    )
    db.commit()
    return body


class GenerateOut(BaseModel):
    generated: int
    auto_enabled: bool


@router.post("/courses/{course_id}/components/{component}/generate")
def generate(
    course_id: int, component: Component, request: Request, user: CurrentUser, db: DbSession
) -> GenerateOut:
    """Regenerate component 1 (ФТ-09) or 2 (ФТ-14). Teacher values are kept (spec 6)."""
    course = _course_for_edit(db, user, course_id)
    if component not in (1, 2):
        raise _unprocessable(
            "not_generated_here", "components 3–5 are filled from tasks and submissions"
        )
    enabled = auto_enabled(db, course_id, component)
    count = 0
    if enabled:
        try:
            fill = fill_goals if component == 1 else fill_descriptors
            count = fill(db, get_provider(), course)
        except LLMUnavailableError:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, detail="llm_unavailable"
            ) from None
    audit.record(
        db,
        AuditAction.COMPONENT_GENERATED,
        actor_id=user.id,
        object_type="course",
        object_id=course_id,
        ip=client_ip(request),
        details={"component": component},
    )
    db.commit()
    return GenerateOut(generated=count, auto_enabled=enabled)


def _entry_for_edit(db: DbSession, user: User, entry_id: int) -> ComponentEntry:
    entry = db.get(ComponentEntry, entry_id)
    if entry is None or not can_edit_course(db, user, entry.course_id):
        raise _forbidden()
    return entry


class EntryEdit(BaseModel):
    value: Any
    note: str = Field(default="", max_length=200)


@router.put("/entries/{entry_id}")
def edit_entry(
    entry_id: int, body: EntryEdit, request: Request, user: CurrentUser, db: DbSession
) -> EntryOut:
    entry = _entry_for_edit(db, user, entry_id)
    if entry.component == 4 and entry.key == "signals":
        raise _unprocessable("signals_are_computed", "comment on a signal instead (ФТ-36)")
    edit(db, entry, body.value, user.id, body.note)
    audit.record(
        db,
        AuditAction.COMPONENT_EDITED,
        actor_id=user.id,
        object_type="component_entry",
        object_id=entry.id,
        ip=client_ip(request),
    )
    db.commit()
    return EntryOut.build(entry)


@router.get("/entries/{entry_id}/versions")
def entry_versions(entry_id: int, user: CurrentUser, db: DbSession) -> list[VersionOut]:
    entry = _entry_for_edit(db, user, entry_id)
    return [VersionOut.model_validate(v, from_attributes=True) for v in entry.versions]


class RevertIn(BaseModel):
    version: int = Field(ge=1)


@router.post("/entries/{entry_id}/revert")
def revert_entry(
    entry_id: int, body: RevertIn, request: Request, user: CurrentUser, db: DbSession
) -> EntryOut:
    entry = _entry_for_edit(db, user, entry_id)
    try:
        revert(db, entry, body.version, user.id)
    except EntryError as exc:
        raise _unprocessable(str(exc)) from None
    audit.record(
        db,
        AuditAction.COMPONENT_EDITED,
        actor_id=user.id,
        object_type="component_entry",
        object_id=entry.id,
        ip=client_ip(request),
        details={"restored": body.version},
    )
    db.commit()
    return EntryOut.build(entry)


@router.post("/entries/{entry_id}/suggestion/{decision}")
def decide_suggestion(
    entry_id: int,
    decision: Literal["accept", "reject"],
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> EntryOut:
    entry = _entry_for_edit(db, user, entry_id)
    try:
        (accept_suggestion if decision == "accept" else reject_suggestion)(db, entry, user.id)
    except EntryError as exc:
        raise _unprocessable(str(exc)) from None
    audit.record(
        db,
        AuditAction.COMPONENT_EDITED,
        actor_id=user.id,
        object_type="component_entry",
        object_id=entry.id,
        ip=client_ip(request),
        details={"suggestion": decision},
    )
    db.commit()
    return EntryOut.build(entry)


# ФТ-36: data and methods of an assessment, observations -----------------------------


class AnalysisConfig(BaseModel):
    excluded: list[
        Literal[
            "static_analysis",
            "process_metrics",
            "student_explanation",
            "genai_log",
            "book_fragments",
        ]
    ] = Field(default_factory=list)
    note: str = Field(default="", max_length=2000)


@router.get("/assessments/{assessment_id}/analysis")
def read_analysis(assessment_id: int, user: CurrentUser, db: DbSession) -> AnalysisConfig:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None or not can_edit_course(db, user, assessment.course_id):
        raise _forbidden()
    return AnalysisConfig.model_validate(assessment.analysis_config or {})


@router.put("/assessments/{assessment_id}/analysis")
def set_analysis(
    assessment_id: int, body: AnalysisConfig, request: Request, user: CurrentUser, db: DbSession
) -> AnalysisConfig:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None or not can_edit_course(db, user, assessment.course_id):
        raise _forbidden()
    assessment.analysis_config = body.model_dump()
    audit.record(
        db,
        AuditAction.COMPONENT_EDITED,
        actor_id=user.id,
        object_type="assessment",
        object_id=assessment_id,
        ip=client_ip(request),
        details=body.model_dump(),
    )
    db.commit()
    return body


def _teacher_submission(db: DbSession, user: User, submission_id: int) -> tuple[Submission, Task]:
    submission = db.get(Submission, submission_id)
    task = db.get(Task, submission.task_id) if submission else None
    if submission is None or task is None or not can_edit_course(db, user, task.course_id):
        raise _forbidden()
    return submission, task


class ObservationIn(BaseModel):
    kind: Literal["oral_defense", "signal_comment", "note"]
    text: str = Field(min_length=1, max_length=10_000)
    signal: str | None = Field(default=None, max_length=64)
    criterion: (
        Literal[
            "understanding", "algorithm", "correctness", "code_quality", "debugging", "explanation"
        ]
        | None
    ) = None
    level: Literal["low", "mid", "high"] | None = None


class ObservationOut(ObservationIn):
    id: int
    author_id: int | None
    created_at: datetime


@router.post("/submissions/{submission_id}/observations", status_code=status.HTTP_201_CREATED)
def add_observation(
    submission_id: int, body: ObservationIn, request: Request, user: CurrentUser, db: DbSession
) -> ObservationOut:
    _teacher_submission(db, user, submission_id)
    observation = Observation(submission_id=submission_id, author_id=user.id, **body.model_dump())
    db.add(observation)
    db.flush()
    audit.record(
        db,
        AuditAction.OBSERVATION_ADDED,
        actor_id=user.id,
        object_type="submission",
        object_id=submission_id,
        ip=client_ip(request),
        details={"kind": body.kind},
    )
    db.commit()
    return ObservationOut.model_validate(observation, from_attributes=True)


@router.get("/submissions/{submission_id}/observations")
def list_observations(submission_id: int, user: CurrentUser, db: DbSession) -> list[ObservationOut]:
    _teacher_submission(db, user, submission_id)
    rows = db.scalars(
        select(Observation)
        .where(Observation.submission_id == submission_id)
        .order_by(Observation.id)
    )
    return [ObservationOut.model_validate(o, from_attributes=True) for o in rows]


# ФТ-03: the teacher's grade ---------------------------------------------------------------


Level = Literal["low", "mid", "high"]


class GradeIn(BaseModel):
    levels: dict[str, Level]
    components: dict[Literal["F", "E", "A"], Annotated[float, Field(ge=0, le=100)]]
    feedback: str = Field(min_length=1, max_length=10_000)
    next_step: str = Field(default="", max_length=2000)
    reason: str = Field(default="", max_length=5000)


class TeacherGradeOut(BaseModel):
    id: int
    submission_id: int
    ai_grade_id: int | None
    criteria: list[dict[str, Any]]
    components: dict[str, float]
    score: float
    feedback: str
    feedback_source: str
    book_refs: list[str]
    next_step: str
    reason: str
    agrees_with_ai: bool
    confirmed_by: int | None
    confirmed_at: datetime


def _grade_out(g: Any) -> TeacherGradeOut:
    return TeacherGradeOut(
        id=g.id,
        submission_id=g.submission_id,
        ai_grade_id=g.ai_grade_id,
        criteria=g.criteria,
        components={"F": g.component_f, "E": g.component_e, "A": g.component_a},
        score=g.score,
        feedback=g.feedback,
        feedback_source=g.feedback_source,
        book_refs=g.book_refs,
        next_step=g.next_step,
        reason=g.reason,
        agrees_with_ai=g.agrees_with_ai,
        confirmed_by=g.confirmed_by,
        confirmed_at=g.confirmed_at,
    )


@router.post("/submissions/{submission_id}/teacher-grade", status_code=status.HTTP_201_CREATED)
def confirm_grade(
    submission_id: int, body: GradeIn, request: Request, user: CurrentUser, db: DbSession
) -> TeacherGradeOut:
    submission, _ = _teacher_submission(db, user, submission_id)
    if set(body.components) != {"F", "E", "A"}:
        raise _unprocessable("components", "give F, E and A")
    try:
        grade = confirm(
            db,
            submission,
            user.id,
            dict(body.levels),
            {str(k): v for k, v in body.components.items()},
            body.feedback,
            body.next_step,
            body.reason,
        )
    except GradeError as exc:
        raise _unprocessable("bad_grade", str(exc)) from None
    audit.record(
        db,
        AuditAction.GRADE_CONFIRMED,
        actor_id=user.id,
        object_type="submission",
        object_id=submission_id,
        ip=client_ip(request),
        details={
            "score": grade.score,
            "agrees_with_ai": grade.agrees_with_ai,
            "levels": body.levels,
        },
    )
    db.commit()
    return _grade_out(grade)


@router.get("/submissions/{submission_id}/teacher-grade")
def read_teacher_grade(
    submission_id: int, user: CurrentUser, db: DbSession
) -> TeacherGradeOut | None:
    _teacher_submission(db, user, submission_id)
    grade = confirmed_grade(db, submission_id)
    return _grade_out(grade) if grade else None


# ФТ-41, ФТ-42: what the student sees after confirmation ---------------------------------


class CriterionResult(BaseModel):
    code: str
    name: str
    level: Level
    interpretation: str


class StudentResult(BaseModel):
    submission_id: int
    task_id: int
    criteria: list[CriterionResult]
    score: float
    feedback: str
    # ФТ-41: text written by AI is marked "AI" and "preliminary"; edited — "AI, edited".
    feedback_source: str
    book_refs: list[str]
    next_step: str
    confirmed_at: datetime


@router.get("/my/results")
def my_results(user: CurrentUser, db: DbSession, task_id: int | None = None) -> list[StudentResult]:
    """Only teacher-confirmed results. No AI grade reaches the student before that."""
    query = select(Submission).where(Submission.user_id == user.id).order_by(Submission.id.desc())
    if task_id is not None:
        query = query.where(Submission.task_id == task_id)
    out = []
    for submission in db.scalars(query):
        grade = confirmed_grade(db, submission.id)
        task = db.get(Task, submission.task_id)
        if grade is None or task is None:
            continue
        descriptors = descriptors_for(db, task)
        names = {c.code: c.name for c in get_or_create_rubric(db, task.course_id).criteria}
        out.append(
            StudentResult(
                submission_id=submission.id,
                task_id=task.id,
                criteria=[
                    CriterionResult(
                        code=c["code"],
                        name=names.get(c["code"], c["code"]),
                        level=c["level"],
                        interpretation=descriptors.get(c["code"], {}).get(c["level"], ""),
                    )
                    for c in grade.criteria
                ],
                score=grade.score,
                feedback=grade.feedback,
                feedback_source=grade.feedback_source,
                book_refs=grade.book_refs,
                next_step=grade.next_step,
                confirmed_at=grade.confirmed_at,
            )
        )
    return out


# ФТ-43: mastery ------------------------------------------------------------------------------


class MasteryRow(BaseModel):
    topic_id: int | None
    level: str | None
    a: int
    p: int
    k: float | None
    mastered: bool


class StudentMastery(BaseModel):
    user_id: int
    full_name: str
    rows: list[MasteryRow]


@router.get("/my/mastery")
def my_mastery(course_id: int, user: CurrentUser, db: DbSession) -> list[MasteryRow]:
    if not studies_course(db, user.id, course_id):
        raise _forbidden()
    return [MasteryRow(**row) for row in mastery(db, course_id, user.id)]


@router.get("/courses/{course_id}/mastery")
def course_mastery(course_id: int, user: CurrentUser, db: DbSession) -> list[StudentMastery]:
    _course_for_edit(db, user, course_id)
    students = db.scalars(
        select(User)
        .join(GroupMember, GroupMember.user_id == User.id)
        .join(CourseGroup, CourseGroup.group_id == GroupMember.group_id)
        .where(CourseGroup.course_id == course_id)
        .distinct()
        .order_by(User.full_name)
    ).all()
    return [
        StudentMastery(
            user_id=s.id,
            full_name=s.full_name,
            rows=[MasteryRow(**r) for r in mastery(db, course_id, s.id)],
        )
        for s in students
    ]


class MasteryIn(BaseModel):
    bespalko_threshold: float = Field(gt=0, le=1)
    no_low_criterion: bool = True


@router.get("/settings/mastery")
def read_mastery_settings(user: CurrentUser, db: DbSession) -> MasteryIn:
    s = mastery_settings(db)
    return MasteryIn(bespalko_threshold=s.bespalko_threshold, no_low_criterion=s.no_low_criterion)


@router.put("/settings/mastery")
def update_mastery_settings(
    body: MasteryIn, request: Request, admin: AdminUser, db: DbSession
) -> MasteryIn:
    """Spec 5.3: the thresholds are settings (0,7 by default)."""
    stored = db.get(AppSetting, MASTERY_KEY)
    value = MasterySettings(body.bespalko_threshold, body.no_low_criterion).__dict__
    if stored is None:
        db.add(AppSetting(key=MASTERY_KEY, value=value, updated_by=admin.id))
    else:
        stored.value, stored.updated_by = value, admin.id
    audit.record(
        db,
        AuditAction.SETTING_CHANGED,
        actor_id=admin.id,
        object_type="setting",
        object_id=MASTERY_KEY,
        ip=client_ip(request),
        details=value,
    )
    db.commit()
    return body
