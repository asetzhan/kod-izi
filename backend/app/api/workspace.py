"""Student workspace: editor session, run, tests, submit, explanation, trace.

ФТ-24 editor actions, ФТ-25 digital trace, ФТ-27 explanation, ФТ-29 integrity marks,
ФТ-31 testing. Student code runs only in Judge0.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.content_schemas import StudentTaskOut
from app.api.deps import AdminUser, CurrentUser, DbSession, RedisClient, client_ip
from app.core.enums import (
    ActivityStage,
    GenAiMode,
    ParticipationKind,
    SubmissionStatus,
    TraceKind,
    Verdict,
)
from app.jobs import get_enqueue
from app.judge import get_judge
from app.judge.client import JudgeClient, JudgeUnavailableError, RunStatus
from app.llm import gateway
from app.llm.registry import get_provider
from app.models import (
    AppSetting,
    Assessment,
    Explanation,
    GroupMember,
    Submission,
    Task,
    TraceEvent,
    User,
    WorkSession,
)
from app.models.course import CourseGroup
from app.services import audit
from app.services.access import can_edit_course, can_view_user, is_staff
from app.services.analytics import label_stages
from app.services.assignments import assignment_for
from app.services.assistant import MODE_ORDER, strictest_running_mode
from app.services.audit import AuditAction
from app.services.contests import (
    active_window,
    duration,
    is_contest,
    participation,
    writing_any_contest,
)
from app.services.grading import run_request, run_tests
from app.services.questions import generate_questions, template_questions
from app.services.sessions import SessionError, latest_code, open_session, writable_session
from app.services.trace import (
    INTEGRITY_KEY,
    ClientEvent,
    IntegritySettings,
    get_integrity,
    ingest_client_events,
    record_server_event,
    session_events,
)

router = APIRouter(prefix="/api", tags=["workspace"])

Judge = Annotated[JudgeClient, Depends(get_judge)]
Enqueue = Annotated[Callable[[int], None], Depends(get_enqueue)]

MAX_CODE = 100_000
OUTPUT_SHOWN = 16_000
# Budgets per student (spec 14.1: Judge0 and the LLM are shared resources).
JUDGE_JOBS_PER_MINUTE = 60  # one job = one program run in Judge0
SUBMITS_PER_10_MIN = 10
EVENTS_PER_MINUTE = 300
EVENTS_PER_SESSION = 20_000
LLM_CODE_LIMIT = 20_000
# Offline events of a closed session are accepted for this long after closing.
LATE_EVENTS_GRACE = timedelta(minutes=30)


def _session_error(exc: SessionError) -> HTTPException:
    return HTTPException(exc.status, detail=exc.code)


def _writable(db: Session, user: User, session_id: uuid.UUID) -> WorkSession:
    try:
        return writable_session(db, user, session_id)
    except SessionError as exc:
        raise _session_error(exc) from None


def _task(db: Session, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    return task


def _spend(redis: RedisClient, key: str, amount: int, limit: int, ttl_s: int) -> bool:
    """Add `amount` to a counter; False when it went over `limit`."""
    total = int(redis.incrby(key, amount))
    if total == amount:
        redis.expire(key, ttl_s)
    return total <= limit


def _limit_judge(redis: RedisClient, user: User, jobs: int) -> None:
    """Judge0 is shared by everyone: count every program run, not every request."""
    key = f"judge_jobs:{user.id}:{datetime.now(UTC):%Y%m%d%H%M}"
    if not _spend(redis, key, max(jobs, 1), JUDGE_JOBS_PER_MINUTE, 120):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="too_many_runs")


Language = Annotated[str, Field(pattern="^cpp(17|20)$")]
Code = Annotated[str, Field(max_length=MAX_CODE)]


class SessionCreate(BaseModel):
    task_id: int
    assessment_id: int | None = None


class SessionOut(BaseModel):
    session_id: uuid.UUID
    task: StudentTaskOut
    assessment_id: int | None
    genai_mode: GenAiMode
    ends_at: datetime | None
    code: str


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def create_session(
    body: SessionCreate, request: Request, user: CurrentUser, db: DbSession
) -> SessionOut:
    try:
        session = open_session(
            db, user, body.task_id, body.assessment_id, request.headers.get("user-agent")
        )
    except SessionError as exc:
        raise _session_error(exc) from None
    task = _task(db, body.task_id)
    assessment = db.get(Assessment, body.assessment_id) if body.assessment_id else None
    code = latest_code(db, user.id, task.id, body.assessment_id)
    db.commit()
    return SessionOut(
        session_id=session.id,
        task=StudentTaskOut.build(task),
        assessment_id=body.assessment_id,
        genai_mode=_session_mode(db, user, task, assessment),
        ends_at=assessment.ends_at if assessment else None,
        code=code,
    )


def _session_mode(db: Session, user: User, task: Task, assessment: Assessment | None) -> GenAiMode:
    """What the assistant allows here; the server enforces it again on every request."""
    if assessment is not None:
        mode = GenAiMode(assessment.genai_mode)
    else:
        assignment = assignment_for(db, user.id, task.id)
        mode = GenAiMode(assignment.genai_mode) if assignment else GenAiMode.OPEN
    running = strictest_running_mode(
        db, user.id, datetime.now(UTC), other_than=assessment.id if assessment else None
    )
    if running is not None and MODE_ORDER.index(running) < MODE_ORDER.index(mode):
        return running
    return mode


class EventBatch(BaseModel):
    events: list[ClientEvent] = Field(max_length=200)


@router.post("/sessions/{session_id}/events")
def post_events(
    session_id: uuid.UUID, body: EventBatch, user: CurrentUser, db: DbSession, redis: RedisClient
) -> dict[str, Any]:
    """Browser events (snapshots, pastes, focus). Resending a batch is safe.

    Events kept in the browser while offline may arrive after the session was closed
    (replaced by a new tab, or the assessment ended). Those that happened before the
    closing time are still stored, so no part of the trace is lost; later ones are refused.
    """
    session = db.get(WorkSession, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")
    for event in body.events:
        try:
            event.checked_payload()
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from None
    now = datetime.now(UTC)
    deadline = _closing_time(db, session)
    events = body.events
    if deadline is not None:
        events = [e for e in events if e.client_ts <= deadline]
        if not events or now > deadline + LATE_EVENTS_GRACE:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="session_closed")
    count = len(events)
    if not _spend(
        redis, f"events:{user.id}:{now:%Y%m%d%H%M}", count, EVENTS_PER_MINUTE, 120
    ) or not _spend(redis, f"events_session:{session.id}", count, EVENTS_PER_SESSION, 7 * 86400):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="too_many_events")
    stored = ingest_client_events(db, session, events, latest=deadline or now)
    db.commit()
    return {"stored": stored, "session_closed": deadline is not None}


def _closing_time(db: Session, session: WorkSession) -> datetime | None:
    """When the session stopped accepting new work, if it has."""
    times = [session.closed_at] if session.closed_at else []
    if session.assessment_id is not None:
        assessment = db.get(Assessment, session.assessment_id)
        now = datetime.now(UTC)
        if assessment is not None and is_contest(assessment):
            # A virtual round (ОТ-03) ends at its own start + duration, not at ends_at.
            if active_window(db, session.user_id, assessment, now) is None:
                end = assessment.ends_at
                virtual = participation(db, session.user_id, assessment, ParticipationKind.VIRTUAL)
                if virtual is not None:
                    end = max(end, virtual.started_at + duration(assessment))
                times.append(min(end, now))
        elif assessment is not None and now > assessment.ends_at:
            times.append(assessment.ends_at)
    return min(times) if times else None


class RunIn(BaseModel):
    code: Code
    language: Language = "cpp17"
    stdin: str = Field(default="", max_length=1_000_000)


class RunOut(BaseModel):
    status: RunStatus
    stdout: str
    stderr: str
    compile_output: str
    time_ms: int | None
    memory_kb: int | None


@router.post("/sessions/{session_id}/run")
def run_code(
    session_id: uuid.UUID,
    body: RunIn,
    user: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    judge: Judge,
) -> RunOut:
    """ФТ-24: compile and run with the student's own input."""
    session = _writable(db, user, session_id)
    _limit_judge(redis, user, 1)
    task = _task(db, session.task_id)
    try:
        result = judge.run(run_request(task, body.code, body.language, body.stdin))
    except JudgeUnavailableError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="judge_unavailable"
        ) from None
    out = RunOut(
        status=result.status,
        stdout=result.stdout[:OUTPUT_SHOWN],
        stderr=result.stderr[:OUTPUT_SHOWN],
        compile_output=result.compile_output[:OUTPUT_SHOWN],
        time_ms=round(result.time_s * 1000) if result.time_s is not None else None,
        memory_kb=result.memory_kb,
    )
    kind = TraceKind.COMPILE if result.status == RunStatus.COMPILE_ERROR else TraceKind.RUN
    record_server_event(
        db,
        session,
        kind,
        {
            "code": body.code,
            "language": body.language,
            "stdin": body.stdin[:4096],
            "status": out.status.value,
            "compile_output": out.compile_output[:4096],
            "stdout": out.stdout[:4096],
            "time_ms": out.time_ms,
            "memory_kb": out.memory_kb,
        },
    )
    db.commit()
    return out


class TestRunOut(BaseModel):
    __test__ = False

    position: int
    verdict: Verdict
    input: str
    expected_output: str
    actual_output: str
    time_ms: int | None


class TestsOut(BaseModel):
    compile_output: str
    results: list[TestRunOut]


@router.post("/sessions/{session_id}/test")
def run_public_tests(
    session_id: uuid.UUID,
    body: RunIn,
    user: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    judge: Judge,
) -> TestsOut:
    """ФТ-24: run the public tests only; hidden tests are used at submission."""
    session = _writable(db, user, session_id)
    task = _task(db, session.task_id)
    public = [t for t in task.tests if not t.is_hidden]
    _limit_judge(redis, user, len(public))
    try:
        results, compile_output = run_tests(judge, task, body.code, body.language, public)
    except JudgeUnavailableError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="judge_unavailable"
        ) from None
    out = TestsOut(
        compile_output=compile_output[:OUTPUT_SHOWN],
        results=[
            TestRunOut(
                position=test.position,
                verdict=verdict,
                input=test.input,
                expected_output=test.expected_output,
                actual_output=result.stdout[:OUTPUT_SHOWN],
                time_ms=round(result.time_s * 1000) if result.time_s is not None else None,
            )
            for test, verdict, result in results
        ],
    )
    record_server_event(
        db,
        session,
        TraceKind.COMPILE if compile_output else TraceKind.TEST,
        {
            "code": body.code,
            "language": body.language,
            "compile_output": compile_output[:4096],
            "per_test": [r.verdict.value for r in out.results],
        },
    )
    db.commit()
    return out


class SubmitIn(BaseModel):
    code: Code = Field(min_length=1)
    language: Language = "cpp17"
    # Required in control works (ФТ-27); optional in olympiad practice and contests.
    explanation: str = Field(default="", max_length=20_000)
    ui_language: str = Field(default="kk", pattern="^(kk|ru)$")


class TestResultOut(BaseModel):
    __test__ = False

    position: int
    is_hidden: bool
    verdict: Verdict
    time_ms: int | None
    memory_kb: int | None


class SubmissionOut(BaseModel):
    id: int
    task_id: int
    assessment_id: int | None
    status: SubmissionStatus
    verdict: Verdict | None
    tests_passed: int
    tests_total: int
    max_time_ms: int | None
    max_memory_kb: int | None
    compile_output: str
    results: list[TestResultOut]
    created_at: datetime
    explanation: str | None
    questions: list[dict[str, Any]]

    @classmethod
    def build(cls, s: Submission, *, for_staff: bool = False) -> "SubmissionOut":
        """Students get only totals for hidden tests.

        Per-test verdicts, time and memory of hidden tests would let a program leak the
        hidden input bit by bit (spec 14.1); the teacher sees everything.
        """
        shown = s.results if for_staff else [r for r in s.results if not r.is_hidden]
        times = [r.time_ms for r in shown if r.time_ms is not None]
        memories = [r.memory_kb for r in shown if r.memory_kb is not None]
        return cls(
            id=s.id,
            task_id=s.task_id,
            assessment_id=s.assessment_id,
            status=SubmissionStatus(s.status),
            verdict=Verdict(s.verdict) if s.verdict else None,
            tests_passed=s.tests_passed,
            tests_total=s.tests_total,
            max_time_ms=s.max_time_ms if for_staff else (max(times) if times else None),
            max_memory_kb=s.max_memory_kb if for_staff else (max(memories) if memories else None),
            compile_output=s.compile_output,
            results=[
                TestResultOut(
                    position=r.position,
                    is_hidden=r.is_hidden,
                    verdict=Verdict(r.verdict),
                    time_ms=r.time_ms,
                    memory_kb=r.memory_kb,
                )
                for r in shown
            ],
            created_at=s.created_at,
            explanation=s.explanation.text if s.explanation else None,
            questions=s.explanation.questions if s.explanation else [],
        )


@router.post("/sessions/{session_id}/submit", status_code=status.HTTP_201_CREATED)
def submit(
    session_id: uuid.UUID,
    body: SubmitIn,
    user: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    enqueue: Enqueue,
) -> SubmissionOut:
    """Submission with explanation (ФТ-27); grading runs in the background (ФТ-31)."""
    session = _writable(db, user, session_id)
    task = _task(db, session.task_id)
    assessment = db.get(Assessment, session.assessment_id) if session.assessment_id else None
    assigned = assessment is None and assignment_for(db, user.id, task.id) is not None
    # Control works and individual tasks (ФТ-05) ask for an explanation (ФТ-27).
    olympiad = (assessment is None and not assigned) or is_contest(assessment)
    if not olympiad and not body.explanation.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="explanation_required")
    in_flight = db.scalar(
        select(Submission.id).where(
            Submission.user_id == user.id,
            Submission.status.in_([SubmissionStatus.QUEUED.value, SubmissionStatus.RUNNING.value]),
            Submission.created_at > datetime.now(UTC) - timedelta(minutes=15),
        )
    )
    if in_flight is not None:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="submission_in_progress")
    window = f"submits:{user.id}:{datetime.now(UTC).timestamp() // 600:.0f}"
    if not _spend(redis, window, 1, SUBMITS_PER_10_MIN, 900):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="too_many_submissions")
    _limit_judge(redis, user, len(task.tests))
    submission = Submission(
        session_id=session.id,
        user_id=user.id,
        task_id=task.id,
        assessment_id=session.assessment_id,
        code=body.code,
        language=body.language,
        status=SubmissionStatus.QUEUED.value,
        tests_total=len(task.tests),
    )
    db.add(submission)
    db.flush()
    record_server_event(
        db,
        session,
        TraceKind.SUBMIT,
        {"submission_id": submission.id, "code": body.code, "language": body.language},
    )
    if olympiad:
        # No questions about the code here: no LLM call during a contest (ОТ-02).
        db.commit()
        enqueue(submission.id)
        db.refresh(submission)
        return SubmissionOut.build(submission)
    provider = get_provider()
    now = datetime.now(UTC)
    if writing_any_contest(db, user.id, now) or (
        strictest_running_mode(db, user.id, now, other_than=session.assessment_id)
        == GenAiMode.FORBIDDEN
    ):
        # No LLM call while the student writes a round or another work without AI: the
        # code could carry that work's statement to the model.
        questions, source = template_questions(body.code, body.ui_language), "template"
    else:
        try:
            questions, source = generate_questions(
                lambda request: gateway.call(
                    db, provider, request, purpose="questions", user_id=user.id
                ),
                task.statement_md,
                body.code[:LLM_CODE_LIMIT],
                body.ui_language,
            )
        except gateway.QuotaExceededError:  # LLM quota used up: template questions, no LLM
            questions, source = template_questions(body.code, body.ui_language), "template"
    db.add(
        Explanation(
            submission_id=submission.id,
            text=body.explanation,
            questions=[{"question": q, "answer": None} for q in questions],
            question_source=source,
            prompt_version="own-code-questions-v1",
        )
    )
    record_server_event(
        db,
        session,
        TraceKind.EXPLANATION,
        {"submission_id": submission.id, "text": body.explanation, "questions": questions},
    )
    db.commit()
    enqueue(submission.id)
    db.refresh(submission)
    return SubmissionOut.build(submission)


def _readable_submission(db: Session, user: User, submission_id: int) -> Submission:
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")
    task = db.get(Task, submission.task_id)
    if submission.user_id == user.id or (task and can_edit_course(db, user, task.course_id)):
        return submission
    raise HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")


@router.get("/submissions/{submission_id}")
def get_submission(submission_id: int, user: CurrentUser, db: DbSession) -> SubmissionOut:
    submission = _readable_submission(db, user, submission_id)
    return SubmissionOut.build(submission, for_staff=submission.user_id != user.id)


@router.get("/my/submissions")
def my_submissions(
    user: CurrentUser, db: DbSession, task_id: int, assessment_id: int | None = None
) -> list[SubmissionOut]:
    query = (
        select(Submission)
        .where(Submission.user_id == user.id, Submission.task_id == task_id)
        .order_by(Submission.id.desc())
    )
    if assessment_id is not None:
        query = query.where(Submission.assessment_id == assessment_id)
    return [SubmissionOut.build(s) for s in db.scalars(query)]


class AnswersIn(BaseModel):
    answers: list[Annotated[str, Field(max_length=5000)]] = Field(max_length=5)


@router.put("/submissions/{submission_id}/answers")
def answer_questions(
    submission_id: int, body: AnswersIn, user: CurrentUser, db: DbSession
) -> SubmissionOut:
    """ФТ-27: answers to the questions about the student's own code."""
    submission = db.get(Submission, submission_id)
    if submission is None or submission.user_id != user.id or submission.explanation is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")
    session = _writable(db, user, submission.session_id)
    questions = submission.explanation.questions
    if len(body.answers) != len(questions):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="answer_count")
    submission.explanation.questions = [
        {"question": q["question"], "answer": a}
        for q, a in zip(questions, body.answers, strict=True)
    ]
    submission.explanation.answered_at = datetime.now(UTC)
    record_server_event(
        db,
        session,
        TraceKind.ANSWERS,
        {"submission_id": submission.id, "answers": body.answers},
    )
    db.commit()
    return SubmissionOut.build(submission)


# Teacher side -------------------------------------------------------------------------


class TraceEventOut(BaseModel):
    id: int
    seq: int | None
    kind: TraceKind
    client_ts: datetime | None
    server_ts: datetime
    payload: dict[str, Any]
    flagged: bool
    stage: ActivityStage | None = None  # ФТ-26, computed when the trace is read


class SessionTraceOut(BaseModel):
    session_id: uuid.UUID
    user_id: int
    task_id: int
    assessment_id: int | None
    started_at: datetime
    closed_at: datetime | None
    events: list[TraceEventOut]


@router.get("/sessions/{session_id}/trace")
def get_trace(session_id: uuid.UUID, user: CurrentUser, db: DbSession) -> SessionTraceOut:
    """ФТ-25: the full trace of a session for the course's teachers (replay in stage 6b)."""
    session = db.get(WorkSession, session_id)
    task = db.get(Task, session.task_id) if session else None
    if (
        session is None
        or task is None
        or not can_edit_course(db, user, task.course_id)
        or not can_view_user(db, user, session.user_id)  # only the student's own teachers
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")
    events = session_events(db, session.id)
    stages = label_stages(events)
    return SessionTraceOut(
        session_id=session.id,
        user_id=session.user_id,
        task_id=session.task_id,
        assessment_id=session.assessment_id,
        started_at=session.started_at,
        closed_at=session.closed_at,
        events=[
            TraceEventOut(
                id=e.id,
                seq=e.seq,
                kind=TraceKind(e.kind),
                client_ts=e.client_ts,
                server_ts=e.server_ts,
                payload=e.payload,
                flagged=e.flagged,
                stage=stage,
            )
            for e, stage in zip(events, stages, strict=True)
        ],
    )


class StudentActivityOut(BaseModel):
    user_id: int
    full_name: str
    sessions: list[uuid.UUID]
    large_pastes: int
    pasted_chars: int
    focus_lost: int
    # Events that reached the server long after they happened: worth a look.
    late_events: int
    last_verdicts: dict[int, Verdict | None]
    last_submissions: dict[int, int | None]


@router.get("/assessments/{assessment_id}/activity")
def assessment_activity(
    assessment_id: int, user: CurrentUser, db: DbSession
) -> list[StudentActivityOut]:
    """ФТ-29: integrity marks per student, for the teacher only. Marks are hints, not proof."""
    assessment = db.get(Assessment, assessment_id)
    if assessment is None or not can_edit_course(db, user, assessment.course_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")
    students = db.scalars(
        select(User)
        .join(GroupMember, GroupMember.user_id == User.id)
        .join(CourseGroup, CourseGroup.group_id == GroupMember.group_id)
        .where(CourseGroup.course_id == assessment.course_id)
        .distinct()
        .order_by(User.full_name)
    ).all()
    out = []
    for student in students:
        base = select(TraceEvent).where(
            TraceEvent.assessment_id == assessment_id, TraceEvent.user_id == student.id
        )
        pastes = db.scalars(base.where(TraceEvent.kind == TraceKind.PASTE.value)).all()
        late = db.scalar(
            select(func.count())
            .select_from(TraceEvent)
            .where(
                TraceEvent.assessment_id == assessment_id,
                TraceEvent.user_id == student.id,
                TraceEvent.flagged.is_(True),
                TraceEvent.kind != TraceKind.PASTE.value,
            )
        )
        focus_lost = db.scalar(
            select(func.count())
            .select_from(TraceEvent)
            .where(
                TraceEvent.assessment_id == assessment_id,
                TraceEvent.user_id == student.id,
                TraceEvent.kind == TraceKind.FOCUS_LOST.value,
            )
        )
        sessions = db.scalars(
            select(WorkSession.id)
            .where(WorkSession.assessment_id == assessment_id, WorkSession.user_id == student.id)
            .order_by(WorkSession.started_at)
        ).all()
        verdicts: dict[int, Verdict | None] = {}
        last_ids: dict[int, int | None] = {}
        for link in assessment.task_links:
            last = db.execute(
                select(Submission.verdict, Submission.id)
                .where(
                    Submission.assessment_id == assessment_id,
                    Submission.user_id == student.id,
                    Submission.task_id == link.task_id,
                )
                .order_by(Submission.id.desc())
                .limit(1)
            ).first()
            verdicts[link.task_id] = Verdict(last.verdict) if last and last.verdict else None
            last_ids[link.task_id] = last.id if last else None
        out.append(
            StudentActivityOut(
                user_id=student.id,
                full_name=student.full_name,
                sessions=list(sessions),
                large_pastes=sum(1 for p in pastes if p.flagged),
                pasted_chars=sum(int(p.payload.get("length", 0)) for p in pastes),
                focus_lost=int(focus_lost or 0),
                late_events=int(late or 0),
                last_verdicts=verdicts,
                last_submissions=last_ids,
            )
        )
    return out


@router.get("/settings/integrity")
def read_integrity(user: CurrentUser, db: DbSession) -> IntegritySettings:
    if not is_staff(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")
    return get_integrity(db)


@router.put("/settings/integrity")
def update_integrity(
    body: IntegritySettings, request: Request, admin: AdminUser, db: DbSession
) -> IntegritySettings:
    before = get_integrity(db).model_dump()
    stored = db.get(AppSetting, INTEGRITY_KEY)
    if stored is None:
        db.add(AppSetting(key=INTEGRITY_KEY, value=body.model_dump(), updated_by=admin.id))
    else:
        stored.value = body.model_dump()
        stored.updated_by = admin.id
    audit.record(
        db,
        AuditAction.SETTING_CHANGED,
        actor_id=admin.id,
        object_type="setting",
        object_id=INTEGRITY_KEY,
        ip=client_ip(request),
        details={"before": before, "after": body.model_dump()},
    )
    db.commit()
    return body
