"""Stage 7a: after a contest (ОТ-07), external platforms (ОТ-08), the knowledge map (ОТ-09)."""

import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from app.api.deps import CurrentUser, DbSession, RedisClient, client_ip
from app.core.enums import ParticipationKind
from app.core.roles import Role
from app.jobs import get_explain_enqueue, get_external_enqueue
from app.llm.ollama import LLMUnavailableError
from app.llm.registry import get_provider
from app.models import (
    Assessment,
    ContestAnalysis,
    CourseGroup,
    CourseTeacher,
    Explanation,
    ExternalAccount,
    ExternalSolve,
    GroupMember,
    RatingPoint,
    Submission,
    Task,
    User,
)
from app.services import audit
from app.services.access import can_edit_course, can_view_user, is_staff, studies_course
from app.services.audit import AuditAction
from app.services.contests import is_contest, participation
from app.services.external import SYNC_COOLDOWN_S, problem_key, valid_handle
from app.services.review import (
    explainable,
    generate_analyses,
    knowledge_map,
    round_over,
    upsolve_list,
)

router = APIRouter(prefix="/api", tags=["review"])

ExplainEnqueue = Annotated[Callable[[int], None], Depends(get_explain_enqueue)]
SyncEnqueue = Annotated[Callable[[int], None], Depends(get_external_enqueue)]
ANALYSIS_LOCK = 4_710_007
Platform = Literal["codeforces", "stepik", "cses", "atcoder", "acmp"]


def _forbidden(code: str = "forbidden") -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, detail=code)


def _contest(db: DbSession, contest_id: int) -> Assessment:
    contest = db.get(Assessment, contest_id)
    if contest is None or not is_contest(contest):
        raise _forbidden()
    return contest


def _can_see_student(db: DbSession, viewer: User, student_id: int) -> bool:
    """The student, their teachers, administrators, and coaches of a course the student
    studies (a coach leads the olympiad courses, not every student of the university)."""
    if can_view_user(db, viewer, student_id):
        return True
    if not viewer.has_role(Role.COACH):
        return False
    led = select(CourseTeacher.course_id).where(CourseTeacher.user_id == viewer.id)
    shared = (
        select(CourseGroup.course_id)
        .join(GroupMember, GroupMember.group_id == CourseGroup.group_id)
        .where(GroupMember.user_id == student_id, CourseGroup.course_id.in_(led))
    )
    return db.scalar(select(shared.exists())) is True


# ОТ-07: analysis, upsolving, explanation -----------------------------------------------------


class AnalysisOut(BaseModel):
    id: int
    task_id: int
    title: str
    editorial_md: str
    model: str
    published: bool


def _analysis_out(db: DbSession, a: ContestAnalysis) -> AnalysisOut:
    task = db.get(Task, a.task_id)
    return AnalysisOut(
        id=a.id,
        task_id=a.task_id,
        title=task.title if task else "",
        editorial_md=a.editorial_md,
        model=a.model,
        published=a.published,
    )


class GenerateAnalysesIn(BaseModel):
    language: str = Field(default="kk", pattern="^(kk|ru)$")


@router.post("/contests/{contest_id}/analyses", status_code=status.HTTP_201_CREATED)
def create_analyses(
    contest_id: int, body: GenerateAnalysesIn, request: Request, user: CurrentUser, db: DbSession
) -> list[AnalysisOut]:
    contest = _contest(db, contest_id)
    if not can_edit_course(db, user, contest.course_id):
        raise _forbidden()
    if not db.scalar(select(func.pg_try_advisory_xact_lock(ANALYSIS_LOCK, contest.course_id))):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="generation_running")
    try:
        analyses = generate_analyses(db, get_provider(), contest, body.language, user.id)
    except LLMUnavailableError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="llm_unavailable") from None
    audit.record(
        db,
        AuditAction.CONTEST_ANALYSED,
        actor_id=user.id,
        object_type="assessment",
        object_id=contest.id,
        ip=client_ip(request),
    )
    db.commit()
    return [_analysis_out(db, a) for a in analyses]


@router.get("/contests/{contest_id}/analyses")
def list_analyses(contest_id: int, user: CurrentUser, db: DbSession) -> list[AnalysisOut]:
    contest = _contest(db, contest_id)
    if not can_edit_course(db, user, contest.course_id):
        raise _forbidden()
    rows = db.scalars(select(ContestAnalysis).where(ContestAnalysis.assessment_id == contest.id))
    return [_analysis_out(db, a) for a in rows]


class AnalysisEdit(BaseModel):
    editorial_md: str = Field(min_length=1, max_length=50_000)
    published: bool


@router.put("/contest-analyses/{analysis_id}")
def edit_analysis(
    analysis_id: int, body: AnalysisEdit, request: Request, user: CurrentUser, db: DbSession
) -> AnalysisOut:
    analysis = db.get(ContestAnalysis, analysis_id)
    contest = db.get(Assessment, analysis.assessment_id) if analysis else None
    if analysis is None or contest is None or not can_edit_course(db, user, contest.course_id):
        raise _forbidden()
    analysis.editorial_md = body.editorial_md
    analysis.published = body.published
    audit.record(
        db,
        AuditAction.CONTEST_ANALYSIS_EDITED,
        actor_id=user.id,
        object_type="contest_analysis",
        object_id=analysis.id,
        ip=client_ip(request),
        details={"published": body.published},
    )
    db.commit()
    return _analysis_out(db, analysis)


@router.get("/contests/{contest_id}/review")
def contest_review(contest_id: int, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """After the student's round: published analyses, the upsolve list and the accepted
    solutions they may explain for the dual assessment."""
    contest = _contest(db, contest_id)
    now = datetime.now(UTC)
    if not studies_course(db, user.id, contest.course_id):
        raise _forbidden()
    if not round_over(db, user, contest, now):
        raise _forbidden("contest_not_finished")
    # Only participants read the analysis: someone who has not written the contest could
    # read it and then start a virtual round knowing the solutions (ОТ-03).
    took_part = any(
        participation(db, user.id, contest, kind) is not None
        for kind in (ParticipationKind.OFFICIAL, ParticipationKind.VIRTUAL)
    )
    analyses = (
        db.scalars(
            select(ContestAnalysis).where(
                ContestAnalysis.assessment_id == contest.id, ContestAnalysis.published.is_(True)
            )
        ).all()
        if took_part
        else []
    )
    accepted = db.scalars(
        select(Submission)
        .where(
            Submission.user_id == user.id,
            Submission.assessment_id == contest.id,
            Submission.verdict == "OK",
        )
        .order_by(Submission.id)
    ).all()
    return {
        "analyses": [_analysis_out(db, a) for a in analyses],
        "took_part": took_part,
        "upsolve": upsolve_list(db, user, contest),
        "explainable": [
            {"submission_id": s.id, "task_id": s.task_id, "explained": s.explanation is not None}
            for s in accepted
        ],
    }


class ExplainIn(BaseModel):
    text: str = Field(min_length=20, max_length=20_000)


@router.post("/submissions/{submission_id}/explain", status_code=status.HTTP_201_CREATED)
def explain(
    submission_id: int, body: ExplainIn, user: CurrentUser, db: DbSession, enqueue: ExplainEnqueue
) -> dict[str, Any]:
    """ОТ-07: the student explains an accepted contest solution; the AI grades it on the six
    criteria and the course teacher confirms (as for control works)."""
    submission = db.get(Submission, submission_id)
    if submission is None or not explainable(db, user, submission, datetime.now(UTC)):
        raise _forbidden()
    db.add(
        Explanation(
            submission_id=submission.id,
            text=body.text,
            questions=[],
            question_source="none",
            prompt_version=None,
        )
    )
    db.commit()
    enqueue(submission.id)
    return {"submission_id": submission.id, "status": "queued"}


# ОТ-08: external platforms -------------------------------------------------------------------


class AccountOut(BaseModel):
    platform: str
    handle: str
    verified: bool
    verify_token: str  # shown only to the student, to put in their Codeforces profile
    rating: int | None
    max_rating: int | None
    sync_status: str
    sync_error: str | None
    last_sync_at: datetime | None


class SolveOut(BaseModel):
    id: int
    platform: str
    problem_key: str
    title: str
    url: str
    rating: int | None
    tags: list[str]
    source: str
    verified: bool


def _account_out(a: ExternalAccount) -> AccountOut:
    return AccountOut(
        platform=a.platform,
        handle=a.handle,
        verified=a.verified_at is not None,
        verify_token=a.verify_token,
        rating=a.rating,
        max_rating=a.max_rating,
        sync_status=a.sync_status,
        sync_error=a.sync_error,
        last_sync_at=a.last_sync_at,
    )


def _solve_out(s: ExternalSolve) -> SolveOut:
    return SolveOut(
        id=s.id,
        platform=s.platform,
        problem_key=s.problem_key,
        title=s.title,
        url=s.url,
        rating=s.rating,
        tags=list(s.tags),
        source=s.source,
        verified=s.source == "api" or s.verified_by is not None,
    )


def _external(db: DbSession, user_id: int) -> dict[str, Any]:
    accounts = db.scalars(select(ExternalAccount).where(ExternalAccount.user_id == user_id))
    solves = db.scalars(
        select(ExternalSolve)
        .where(ExternalSolve.user_id == user_id)
        .order_by(ExternalSolve.solved_at.desc().nulls_last(), ExternalSolve.id.desc())
    )
    return {
        "accounts": [_account_out(a) for a in accounts],
        "solves": [_solve_out(s) for s in solves],
    }


def _cooldown(redis: RedisClient, user_id: int) -> None:
    """At most one Codeforces sync per student every SYNC_COOLDOWN_S, linking included."""
    if not redis.set(f"codeforces:cooldown:{user_id}", "1", nx=True, ex=SYNC_COOLDOWN_S):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="sync_too_soon")


def _forget_gathered(db: DbSession, user_id: int) -> None:
    db.execute(
        delete(ExternalSolve).where(
            ExternalSolve.user_id == user_id,
            ExternalSolve.platform == "codeforces",
            ExternalSolve.source == "api",
        )
    )
    db.execute(
        delete(RatingPoint).where(
            RatingPoint.user_id == user_id, RatingPoint.platform == "codeforces"
        )
    )


@router.get("/my/external")
def my_external(user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return _external(db, user.id)


class LinkIn(BaseModel):
    handle: str = Field(min_length=3, max_length=24)
    # Q-18: the student agrees that only this handle is sent to codeforces.com.
    consent: bool


@router.post("/my/external/codeforces", status_code=status.HTTP_201_CREATED)
def link_codeforces(
    body: LinkIn,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    enqueue: SyncEnqueue,
) -> AccountOut:
    if not body.consent:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="external_consent_required"
        )
    if not valid_handle(body.handle):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="bad_handle")
    account = db.scalar(
        select(ExternalAccount).where(
            ExternalAccount.user_id == user.id, ExternalAccount.platform == "codeforces"
        )
    )
    _cooldown(redis, user.id)
    now = datetime.now(UTC)
    if account is None:
        account = ExternalAccount(
            user_id=user.id,
            platform="codeforces",
            handle=body.handle,
            consent_at=now,
            verify_token=f"kodizi-{secrets.token_hex(6)}",
        )
        db.add(account)
    elif account.handle != body.handle:
        # Another handle: nothing gathered for the old one stays, ownership is proven again.
        _forget_gathered(db, user.id)
        account.verify_token = f"kodizi-{secrets.token_hex(6)}"
        account.verified_at = None
        account.rating = account.max_rating = None
    account.handle = body.handle
    account.consent_at = now
    account.sync_status = "pending"
    account.sync_error = None
    db.flush()
    audit.record(
        db,
        AuditAction.EXTERNAL_LINKED,
        actor_id=user.id,
        object_type="external_account",
        object_id=account.id,
        ip=client_ip(request),
        details={"platform": "codeforces"},
    )
    db.commit()
    enqueue(account.id)
    db.refresh(account)
    return _account_out(account)


@router.post("/my/external/codeforces/sync", status_code=status.HTTP_202_ACCEPTED)
def sync_codeforces_now(
    user: CurrentUser, db: DbSession, redis: RedisClient, enqueue: SyncEnqueue
) -> AccountOut:
    account = db.scalar(
        select(ExternalAccount).where(
            ExternalAccount.user_id == user.id, ExternalAccount.platform == "codeforces"
        )
    )
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_linked")
    if account.last_sync_at and datetime.now(UTC) - account.last_sync_at < timedelta(
        seconds=SYNC_COOLDOWN_S
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="sync_too_soon")
    _cooldown(redis, user.id)
    account.sync_status = "pending"
    db.commit()
    enqueue(account.id)
    return _account_out(account)


@router.delete("/my/external/codeforces", status_code=status.HTTP_204_NO_CONTENT)
def unlink_codeforces(request: Request, user: CurrentUser, db: DbSession) -> None:
    """Withdrawing the consent removes the account and everything gathered through it."""
    account = db.scalar(
        select(ExternalAccount).where(
            ExternalAccount.user_id == user.id, ExternalAccount.platform == "codeforces"
        )
    )
    if account is None:
        return
    _forget_gathered(db, user.id)
    audit.record(
        db,
        AuditAction.EXTERNAL_UNLINKED,
        actor_id=user.id,
        object_type="external_account",
        object_id=account.id,
        ip=client_ip(request),
        details={"platform": "codeforces"},
    )
    db.delete(account)
    db.commit()


class ManualSolveIn(BaseModel):
    platform: Platform
    url: str = Field(max_length=500)
    title: str = Field(default="", max_length=300)


@router.post("/my/external/solves", status_code=status.HTTP_201_CREATED)
def mark_solve(body: ManualSolveIn, user: CurrentUser, db: DbSession) -> SolveOut:
    """A problem solved elsewhere, marked by hand with its link (a coach may verify it)."""
    key = problem_key(body.platform, body.url.strip())
    if key is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="bad_problem_url")
    if db.scalar(
        select(ExternalSolve.id).where(
            ExternalSolve.user_id == user.id,
            ExternalSolve.platform == body.platform,
            ExternalSolve.problem_key == key,
        )
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="already_marked")
    solve = ExternalSolve(
        user_id=user.id,
        platform=body.platform,
        problem_key=key,
        title=body.title.strip(),
        url=body.url.strip(),
        solved_at=datetime.now(UTC),
        source="manual",
    )
    db.add(solve)
    db.commit()
    db.refresh(solve)
    return _solve_out(solve)


@router.delete("/my/external/solves/{solve_id}", status_code=status.HTTP_204_NO_CONTENT)
def unmark_solve(solve_id: int, user: CurrentUser, db: DbSession) -> None:
    solve = db.get(ExternalSolve, solve_id)
    if solve is None or solve.user_id != user.id or solve.source != "manual":
        raise _forbidden()
    db.delete(solve)
    db.commit()


@router.get("/users/{student_id}/external")
def student_external(student_id: int, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    if not is_staff(user) or not _can_see_student(db, user, student_id):
        raise _forbidden()
    return _external(db, student_id)


@router.post("/external-solves/{solve_id}/verify")
def verify_solve(solve_id: int, request: Request, user: CurrentUser, db: DbSession) -> SolveOut:
    solve = db.get(ExternalSolve, solve_id)
    if solve is None or not is_staff(user) or not _can_see_student(db, user, solve.user_id):
        raise _forbidden()
    solve.verified_by = user.id
    audit.record(
        db,
        AuditAction.EXTERNAL_SOLVE_VERIFIED,
        actor_id=user.id,
        object_type="external_solve",
        object_id=solve.id,
        ip=client_ip(request),
    )
    db.commit()
    return _solve_out(solve)


# ОТ-09: knowledge map ------------------------------------------------------------------------


@router.get("/my/knowledge-map")
def my_knowledge_map(user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return knowledge_map(db, user)


@router.get("/users/{student_id}/knowledge-map")
def student_knowledge_map(student_id: int, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    student = db.get(User, student_id)
    if student is None or not is_staff(user) or not _can_see_student(db, user, student_id):
        raise _forbidden()
    return knowledge_map(db, student)
