"""Olympiad part (spec 4, 10): reference (ОТ-10), problem bank (ОТ-01), recommendations
(ОТ-04), the "one hour" rule and step-by-step hints (ОТ-05), own tests and the stress
test (ОТ-06). Contests are in api/contests.py.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.content_schemas import StudentTaskOut
from app.api.deps import CurrentUser, DbSession, RedisClient, client_ip, require_roles
from app.api.workspace import Code, Judge, Language, _limit_judge, _writable
from app.core.enums import AssessmentKind, TaskLevel, TraceKind
from app.core.roles import Role
from app.judge.client import JudgeUnavailableError
from app.llm import gateway
from app.llm.ollama import LLMUnavailableError
from app.llm.registry import get_provider
from app.models import (
    AppSetting,
    Assessment,
    AssessmentTask,
    StudentTest,
    Task,
    TopicResource,
    User,
)
from app.services import audit, olympiad, own_tests
from app.services.access import is_staff, studies_course
from app.services.assistant import olympiad_hint
from app.services.audit import AuditAction
from app.services.contests import in_running_contest
from app.services.trace import record_server_event

router = APIRouter(prefix="/api", tags=["olympiad"])

CoachOrAdmin = Annotated[User, Depends(require_roles(Role.COACH, Role.ADMIN))]
MAX_TEST_CHARS = 64 * 1024


def _forbidden(code: str = "forbidden") -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, detail=code)


def _require_unlocked(db: DbSession, user: User) -> None:
    if not olympiad.unlock_state(db, user)["unlocked"]:
        raise _forbidden("part2_locked")


def _practice_task(db: DbSession, user: User, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None or not olympiad.can_practice(db, user, task):
        raise _forbidden()
    return task


def _usable_task(db: DbSession, user: User, task_id: int) -> Task:
    """Own tests: practice problems, and problems of started contests of the user's courses."""
    task = db.get(Task, task_id)
    if task is None:
        raise _forbidden()
    if olympiad.can_practice(db, user, task):
        return task
    started = db.scalars(
        select(Assessment)
        .join(AssessmentTask, AssessmentTask.assessment_id == Assessment.id)
        .where(
            AssessmentTask.task_id == task.id,
            Assessment.kind == AssessmentKind.CONTEST.value,
            Assessment.starts_at <= datetime.now(UTC),
        )
    )
    if any(studies_course(db, user.id, c.course_id) for c in started):
        return task
    raise _forbidden()


# Reference (ОТ-10) -----------------------------------------------------------------------


@router.get("/olympiad")
def overview(user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Modules of 4.1 and 4.2 with Stepik lessons and extra materials, and 4.3 practice."""
    seed = olympiad.resources_seed()
    courses = []
    for course in olympiad.part2_courses(db, user):
        topics = []
        for topic in course.topics:
            resources = db.scalars(
                select(TopicResource)
                .where(TopicResource.topic_id == topic.id)
                .order_by(TopicResource.position)
            )
            topics.append(
                {
                    "id": topic.id,
                    "code": topic.code,
                    "title": topic.title,
                    "lessons": [
                        {"title": lesson.title, "url": lesson.url, "kind": lesson.kind}
                        for lesson in topic.lessons
                    ],
                    "resources": [
                        {"name": r.name, "url": r.url, "purpose": r.purpose} for r in resources
                    ],
                }
            )
        courses.append(
            {"id": course.id, "title": course.title, "url": course.source_url, "topics": topics}
        )
    return {
        "unlock": olympiad.unlock_state(db, user),
        "courses": courses,
        "practice": {"rules": seed.get("rules", []), "resources": seed.get("resources", [])},
    }


# Problem bank (ОТ-01) and recommendations (ОТ-04) -------------------------------------------


class ProblemSummary(BaseModel):
    id: int
    course_id: int
    topic_id: int | None
    title: str
    level: TaskLevel | None
    cf_rating: int | None
    tags: list[str]
    time_limit_ms: int
    memory_limit_kb: int
    solved: bool

    @classmethod
    def build(cls, task: Task, solved: set[int]) -> "ProblemSummary":
        return cls(
            id=task.id,
            course_id=task.course_id,
            topic_id=task.topic_id,
            title=task.title,
            level=TaskLevel(task.level) if task.level else None,
            cf_rating=task.cf_rating,
            tags=list(task.tags),
            time_limit_ms=task.time_limit_ms,
            memory_limit_kb=task.memory_limit_kb,
            solved=task.id in solved,
        )


@router.get("/olympiad/problems")
def list_problems(
    user: CurrentUser,
    db: DbSession,
    topic_id: int | None = None,
    tag: str | None = None,
    level: TaskLevel | None = None,
    min_rating: int | None = None,
    max_rating: int | None = None,
) -> list[ProblemSummary]:
    _require_unlocked(db, user)
    solved = olympiad.solved_task_ids(db, user.id)
    out = []
    for task in olympiad.bank(db, user):
        if topic_id is not None and task.topic_id != topic_id:
            continue
        if tag is not None and tag not in task.tags:
            continue
        if level is not None and task.level != level.value:
            continue
        rating = task.cf_rating
        if min_rating is not None and (rating is None or rating < min_rating):
            continue
        if max_rating is not None and (rating is None or rating > max_rating):
            continue
        out.append(ProblemSummary.build(task, solved))
    return out


class Recommendations(BaseModel):
    rating: int
    range: list[int]
    problems: list[ProblemSummary]


@router.get("/olympiad/recommendations")
def recommendations(user: CurrentUser, db: DbSession) -> Recommendations:
    _require_unlocked(db, user)
    picked = olympiad.recommend(db, user)
    return Recommendations(
        rating=picked["rating"],
        range=picked["range"],
        problems=[ProblemSummary.build(t, set()) for t in picked["tasks"]],
    )


# One problem: editorial (ОТ-05) and hints ---------------------------------------------------


class HintOut(BaseModel):
    level: int
    answer: str
    blocked: bool
    created_at: datetime


class ProblemOut(BaseModel):
    task: StudentTaskOut
    tags: list[str]
    cf_rating: int | None
    solved: bool
    minutes_spent: int
    editorial_available: bool
    editorial_opens_at: datetime | None
    editorial_md: str | None
    hints: list[HintOut]
    next_hint_level: int | None
    next_hint_at: datetime | None
    in_contest: bool  # the AI is off while the problem is in the user's running contest


@router.get("/olympiad/problems/{task_id}")
def get_problem(task_id: int, user: CurrentUser, db: DbSession) -> ProblemOut:
    task = _practice_task(db, user, task_id)
    now = datetime.now(UTC)
    editorial = olympiad.editorial_state(db, user, task, now)
    level, at = olympiad.next_hint(db, user, task, now)
    return ProblemOut(
        task=StudentTaskOut.build(task),
        tags=list(task.tags),
        cf_rating=task.cf_rating,
        solved=task.id in olympiad.solved_task_ids(db, user.id),
        minutes_spent=editorial.minutes_spent,
        editorial_available=editorial.available,
        editorial_opens_at=editorial.opens_at,
        editorial_md=task.editorial_md if editorial.available else None,
        hints=[
            HintOut(
                level=m.hint_level or 0, answer=m.answer, blocked=m.blocked, created_at=m.created_at
            )
            for m in olympiad.hints_given(db, user.id, task.id)
        ],
        next_hint_level=level,
        next_hint_at=at,
        in_contest=in_running_contest(db, user.id, task.id, now),
    )


class HintIn(BaseModel):
    session_id: uuid.UUID
    code: str = Field(default="", max_length=100_000)
    ui_language: str = Field(default="kk", pattern="^(kk|ru)$")


@router.post("/olympiad/problems/{task_id}/hints", status_code=status.HTTP_201_CREATED)
def ask_hint(task_id: int, body: HintIn, user: CurrentUser, db: DbSession) -> HintOut:
    """ОТ-05: direction, then idea, then pseudocode; never ready code, never in a contest."""
    task = _practice_task(db, user, task_id)
    session = _writable(db, user, body.session_id)
    if session.task_id != task.id or session.assessment_id is not None:
        raise _forbidden()
    now = datetime.now(UTC)
    if in_running_contest(db, user.id, task.id, now):
        raise _forbidden("assistant_forbidden")
    level, opens_at = olympiad.next_hint(db, user, task, now)
    if level is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="no_more_hints")
    if opens_at is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "hint_not_yet", "opens_at": opens_at.isoformat()},
        )
    try:
        message = olympiad_hint(db, get_provider(), session, level, body.code, body.ui_language)
    except gateway.QuotaExceededError:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="llm_quota") from None
    except LLMUnavailableError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="llm_unavailable") from None
    db.commit()
    return HintOut(
        level=level, answer=message.answer, blocked=message.blocked, created_at=message.created_at
    )


# Own tests and the stress test (ОТ-06) ------------------------------------------------------


class OwnTestIn(BaseModel):
    input: str = Field(max_length=MAX_TEST_CHARS)
    expected_output: str | None = Field(default=None, max_length=MAX_TEST_CHARS)


class OwnTestOut(OwnTestIn):
    id: int
    position: int


def _tests(db: DbSession, user_id: int, task_id: int) -> list[StudentTest]:
    return list(
        db.scalars(
            select(StudentTest)
            .where(StudentTest.user_id == user_id, StudentTest.task_id == task_id)
            .order_by(StudentTest.position, StudentTest.id)
        )
    )


def _own_out(test: StudentTest) -> OwnTestOut:
    return OwnTestOut(
        id=test.id, position=test.position, input=test.input, expected_output=test.expected_output
    )


@router.get("/olympiad/problems/{task_id}/my-tests")
def list_own_tests(task_id: int, user: CurrentUser, db: DbSession) -> list[OwnTestOut]:
    _usable_task(db, user, task_id)
    return [_own_out(t) for t in _tests(db, user.id, task_id)]


@router.post("/olympiad/problems/{task_id}/my-tests", status_code=status.HTTP_201_CREATED)
def add_own_test(task_id: int, body: OwnTestIn, user: CurrentUser, db: DbSession) -> OwnTestOut:
    _usable_task(db, user, task_id)
    count = db.scalar(
        select(func.count())
        .select_from(StudentTest)
        .where(StudentTest.user_id == user.id, StudentTest.task_id == task_id)
    )
    if (count or 0) >= own_tests.MAX_OWN_TESTS:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="too_many_tests")
    test = StudentTest(
        user_id=user.id,
        task_id=task_id,
        position=(count or 0) + 1,
        input=body.input,
        expected_output=body.expected_output or None,
    )
    db.add(test)
    db.commit()
    return _own_out(test)


def _own_test(db: DbSession, user: User, test_id: int) -> StudentTest:
    test = db.get(StudentTest, test_id)
    if test is None or test.user_id != user.id:
        raise _forbidden()
    return test


@router.put("/olympiad/my-tests/{test_id}")
def update_own_test(test_id: int, body: OwnTestIn, user: CurrentUser, db: DbSession) -> OwnTestOut:
    test = _own_test(db, user, test_id)
    test.input = body.input
    test.expected_output = body.expected_output or None
    db.commit()
    return _own_out(test)


@router.delete("/olympiad/my-tests/{test_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_own_test(test_id: int, user: CurrentUser, db: DbSession) -> None:
    db.delete(_own_test(db, user, test_id))
    db.commit()


class OwnRunIn(BaseModel):
    code: Code
    language: Language = "cpp17"


class OwnResultOut(BaseModel):
    test_id: int
    status: str
    verdict: str | None
    output: str
    time_ms: int | None


@router.post("/sessions/{session_id}/my-tests/run")
def run_own_tests(
    session_id: uuid.UUID,
    body: OwnRunIn,
    user: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    judge: Judge,
) -> list[OwnResultOut]:
    """ОТ-06: all saved tests with one button, in Judge0."""
    session = _writable(db, user, session_id)
    task = _usable_task(db, user, session.task_id)
    tests = _tests(db, user.id, task.id)
    _limit_judge(redis, user, len(tests))
    try:
        results = own_tests.run_own(judge, task, body.code, body.language, tests)
    except JudgeUnavailableError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="judge_unavailable"
        ) from None
    record_server_event(
        db,
        session,
        TraceKind.TEST,
        {
            "own": True,
            "code": body.code,
            "language": body.language,
            "verdicts": [r.verdict.value if r.verdict else r.status for r in results],
        },
    )
    db.commit()
    return [
        OwnResultOut(
            test_id=r.test_id,
            status=r.status,
            verdict=r.verdict.value if r.verdict else None,
            output=r.output,
            time_ms=r.time_ms,
        )
        for r in results
    ]


class StressIn(BaseModel):
    code: Code
    brute_code: Code
    generator_code: Code
    language: Language = "cpp17"
    iterations: int = Field(default=10, ge=1, le=own_tests.MAX_STRESS_ITERATIONS)


class StressOut(BaseModel):
    status: str
    iterations: int
    input: str
    expected: str
    actual: str
    detail: str


@router.post("/sessions/{session_id}/stress")
def stress_test(
    session_id: uuid.UUID,
    body: StressIn,
    user: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    judge: Judge,
) -> StressOut:
    """ОТ-06: compare with a slow correct solution on generated tests; show the first
    input where the answers differ."""
    session = _writable(db, user, session_id)
    task = _usable_task(db, user, session.task_id)
    _limit_judge(redis, user, 3 * body.iterations)
    try:
        result = own_tests.stress(
            judge,
            task,
            body.language,
            body.code,
            body.brute_code,
            body.generator_code,
            body.iterations,
        )
    except JudgeUnavailableError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="judge_unavailable"
        ) from None
    record_server_event(
        db,
        session,
        TraceKind.TEST,
        {
            "stress": True,
            "code": body.code,
            "brute_code": body.brute_code,
            "generator_code": body.generator_code,
            "status": result.status,
            "iterations": result.iterations,
            "input": result.input[:4096],
        },
    )
    db.commit()
    return StressOut(
        status=result.status,
        iterations=result.iterations,
        input=result.input,
        expected=result.expected,
        actual=result.actual,
        detail=result.detail,
    )


# Settings ----------------------------------------------------------------------------------


@router.get("/settings/olympiad")
def read_settings(user: CurrentUser, db: DbSession) -> olympiad.OlympiadSettings:
    if not is_staff(user):
        raise _forbidden()
    return olympiad.get_olympiad_settings(db)


@router.put("/settings/olympiad")
def save_settings(
    body: olympiad.OlympiadSettings, request: Request, user: CoachOrAdmin, db: DbSession
) -> olympiad.OlympiadSettings:
    if body.recommend_min > body.recommend_max:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="bad_value")
    stored = db.get(AppSetting, olympiad.OLYMPIAD_KEY)
    if stored is None:
        db.add(AppSetting(key=olympiad.OLYMPIAD_KEY, value=body.model_dump(), updated_by=user.id))
    else:
        stored.value = body.model_dump()
        stored.updated_by = user.id
    audit.record(
        db,
        AuditAction.OLYMPIAD_SETTINGS_CHANGED,
        actor_id=user.id,
        object_type="setting",
        object_id=olympiad.OLYMPIAD_KEY,
        ip=client_ip(request),
        details=body.model_dump(),
    )
    db.commit()
    return body
