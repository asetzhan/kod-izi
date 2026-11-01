"""Stage 7a: ОТ-07 (after a contest), ОТ-08 (external platforms), ОТ-09 (knowledge map)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.context import set_system
from app.jobs import get_explain_enqueue, get_external_enqueue
from app.llm.fake import FakeLLMProvider
from app.main import app
from app.models import AiGrade, Assessment, ExternalAccount, ExternalSolve, RatingPoint, Submission
from app.services import ai_grading
from app.services.component_fill import fill_submission
from app.services.external import (
    ExternalError,
    HttpCodeforces,
    RedisRateLimiter,
    problem_key,
    sync_codeforces,
)
from tests.conftest import School, login
from tests.llm_helpers import ScriptedProvider
from tests.olympiad_helpers import _contest, _session, _submit

NOW = int(datetime(2026, 10, 1, tzinfo=UTC).timestamp())


class FakeApi:
    def __init__(self, fail: str | None = None) -> None:
        self.fail = fail
        self.calls: list[str] = []

    def call(self, method: str, params: dict[str, str]) -> Any:
        self.calls.append(method)
        if method == self.fail:
            raise ExternalError("handle: User with handle x not found")
        if method == "user.info":
            return [{"handle": params["handles"], "rating": 1450, "maxRating": 1510}]
        if method == "user.status":
            problem = {
                "contestId": 1520,
                "index": "B",
                "name": "Ordinary Numbers",
                "rating": 800,
                "tags": ["math"],
            }
            return [
                {"verdict": "OK", "problem": problem, "creationTimeSeconds": NOW},
                {"verdict": "OK", "problem": problem, "creationTimeSeconds": NOW + 60},  # again
                {
                    "verdict": "WRONG_ANSWER",
                    "problem": {**problem, "index": "C"},
                    "creationTimeSeconds": NOW,
                },
            ]
        return [{"contestName": "Round 1", "newRating": 1450, "ratingUpdateTimeSeconds": NOW}]


# ОТ-08 ---------------------------------------------------------------------------------------


def test_ot08_codeforces_sync_gathers_solves_and_rating(db: Session, school: School) -> None:
    account = ExternalAccount(
        user_id=school["student_a"].id,
        platform="codeforces",
        handle="tourist_fan",
        consent_at=datetime.now(UTC),
    )
    db.add(account)
    db.flush()
    sync_codeforces(db, account, FakeApi())
    db.flush()
    solves = db.scalars(select(ExternalSolve)).all()
    assert [(s.problem_key, s.url, s.tags) for s in solves] == [
        ("1520B", "https://codeforces.com/contest/1520/problem/B", ["math"])
    ]
    assert account.rating == 1450 and account.sync_status == "ok"
    assert db.scalar(select(RatingPoint.rating)) == 1450
    sync_codeforces(db, account, FakeApi())  # again: nothing is doubled
    db.flush()
    assert len(db.scalars(select(ExternalSolve)).all()) == 1


def test_ot08_api_errors_do_not_stop_the_system(db: Session, school: School) -> None:
    account = ExternalAccount(
        user_id=school["student_a"].id,
        platform="codeforces",
        handle="nobody",
        consent_at=datetime.now(UTC),
    )
    db.add(account)
    db.flush()
    sync_codeforces(db, account, FakeApi(fail="user.status"))
    assert account.sync_status == "error" and "not found" in (account.sync_error or "")

    def answer(status_code: int, body: Any = None) -> HttpCodeforces:
        transport = httpx.MockTransport(lambda request: httpx.Response(status_code, json=body))
        return HttpCodeforces(NoWait(), httpx.Client(transport=transport))

    with pytest.raises(ExternalError, match="503"):
        answer(503).call("user.info", {"handles": "x"})
    with pytest.raises(ExternalError, match="not found"):
        answer(400, {"status": "FAILED", "comment": "handles: not found"}).call("user.info", {})

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    offline = HttpCodeforces(NoWait(), httpx.Client(transport=httpx.MockTransport(down)))
    with pytest.raises(ExternalError, match="network"):
        offline.call("user.info", {})


class NoWait:
    def wait(self) -> None:
        return None


def test_ot08_requests_keep_to_the_codeforces_limit(redis: Any) -> None:
    sleeps: list[float] = []
    limiter = RedisRateLimiter(redis, sleep=sleeps.append)
    limiter.wait()
    assert sleeps == []  # the first request goes at once
    redis.pexpire("codeforces:next", 50)  # pretend the 2 s window is almost over
    calls = 0

    def fake_sleep(seconds: float) -> None:
        nonlocal calls
        calls += 1
        redis.delete("codeforces:next")  # the window passes while waiting

    RedisRateLimiter(redis, sleep=fake_sleep).wait()
    assert calls == 1  # the second request waited for the window


def test_ot08_problem_links_of_each_platform() -> None:
    assert problem_key("codeforces", "https://codeforces.com/problemset/problem/1520/b") == "1520B"
    assert problem_key("cses", "https://cses.fi/problemset/task/1068") == "1068"
    assert (
        problem_key("atcoder", "https://atcoder.jp/contests/abc300/tasks/abc300_a")
        == "abc300-abc300_a"
    )
    assert problem_key("acmp", "https://acmp.ru/index.asp?main=task&id_task=17") == "17"
    assert problem_key("stepik", "https://stepik.org/lesson/307318/step/2") == "307318-2"
    assert problem_key("cses", "https://evil.example/problemset/task/1") is None
    assert problem_key("codeforces", "javascript:alert(1)") is None


@pytest.fixture
def synced(db: Session) -> Iterator[list[int]]:
    queued: list[int] = []
    app.dependency_overrides[get_external_enqueue] = lambda: queued.append
    yield queued
    app.dependency_overrides.pop(get_external_enqueue, None)


def test_ot08_linking_needs_consent_and_unlinking_removes_the_data(
    client: TestClient, school: School, db: Session, synced: list[int]
) -> None:
    student = login(client, school["student_a"].email)
    url = "/api/my/external/codeforces"
    refused = client.post(url, headers=student, json={"handle": "tourist_fan", "consent": False})
    assert refused.json()["detail"] == "external_consent_required"
    bad = client.post(url, headers=student, json={"handle": "a b;c", "consent": True})
    assert bad.json()["detail"] == "bad_handle"
    linked = client.post(url, headers=student, json={"handle": "tourist_fan", "consent": True})
    assert linked.status_code == 201 and len(synced) == 1
    account = db.get(ExternalAccount, synced[0])
    assert account is not None
    sync_codeforces(db, account, FakeApi())
    db.flush()
    assert client.post(f"{url}/sync", headers=student).json()["detail"] == "sync_too_soon"

    manual = client.post(
        "/api/my/external/solves",
        headers=student,
        json={"platform": "cses", "url": "https://cses.fi/problemset/task/1068", "title": "Weird"},
    ).json()
    assert manual["verified"] is False
    coach = login(client, school["coach"].email)
    assert client.post(f"/api/external-solves/{manual['id']}/verify", headers=coach).json()[
        "verified"
    ]
    other = login(client, school["student_b"].email)
    assert (
        client.get(f"/api/users/{school['student_a'].id}/external", headers=other).status_code
        == 403
    )

    assert client.delete(url, headers=student).status_code == 204
    left = client.get("/api/my/external", headers=student).json()
    assert left["accounts"] == [] and [s["platform"] for s in left["solves"]] == ["cses"]
    assert db.scalar(select(RatingPoint.id)) is None


# ОТ-09 ---------------------------------------------------------------------------------------


def test_ot09_knowledge_map_by_topic_and_rating_over_time(
    client: TestClient,
    oly: dict[str, Any],
    school: School,
    db: Session,
) -> None:
    sid = _session(client, oly["a"], oly["tasks"][1]).json()["session_id"]
    _submit(client, oly["a"], sid)  # the 1000-rated "dp" problem
    db.add(
        RatingPoint(
            user_id=school["student_a"].id,
            platform="codeforces",
            contest="Round 1",
            rating=1300,
            at=datetime.now(UTC),
        )
    )
    db.flush()
    data = client.get("/api/my/knowledge-map", headers=oly["a"]).json()
    [dp] = data["topics"]
    assert (dp["tag"], dp["bank"], dp["solved"]) == ("dp", 4, 1)
    assert 0 < dp["mastery"] < 1
    assert data["rating"]["internal"][-1]["rating"] == 1000
    assert data["rating"]["codeforces"][0]["rating"] == 1300
    coach = login(client, school["coach"].email)
    seen = client.get(f"/api/users/{school['student_a'].id}/knowledge-map", headers=coach)
    assert seen.status_code == 200
    assert (
        client.get(
            f"/api/users/{school['student_a'].id}/knowledge-map", headers=oly["b"]
        ).status_code
        == 403
    )


# ОТ-07 ---------------------------------------------------------------------------------------


@pytest.fixture
def finished(client: TestClient, oly: dict[str, Any], db: Session) -> dict[str, Any]:
    """A contest the student took part in, already over: problem A solved, B not."""
    contest = _contest(client, oly, -30, 120)
    sid = _session(client, oly["a"], oly["tasks"][0], contest["id"]).json()["session_id"]
    accepted = _submit(client, oly["a"], sid)
    past = datetime.now(UTC) - timedelta(hours=5)
    db.execute(
        update(Assessment)
        .where(Assessment.id == contest["id"])
        .values(starts_at=past, ends_at=past + timedelta(hours=2))
    )
    return {**oly, "contest": contest, "accepted": accepted}


def test_ot07_ai_analysis_is_published_by_the_coach(
    client: TestClient, finished: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = ScriptedProvider(
        [
            "Негізгі бақылау: жұптылық. Күрделілігі O(1).",
            "```cpp\nint main() { return 0; }\n```",
        ]
    )
    monkeypatch.setattr("app.api.review.get_provider", lambda: provider)
    cid = finished["contest"]["id"]
    made = client.post(f"/api/contests/{cid}/analyses", headers=finished["teacher"], json={}).json()
    assert [a["published"] for a in made] == [False, False]
    assert "код болды" in made[1]["editorial_md"]  # code is never kept
    assert "reference_solution" in provider.requests[0].data_blocks

    review = client.get(f"/api/contests/{cid}/review", headers=finished["a"]).json()
    assert review["analyses"] == []  # nothing before the coach publishes
    client.put(
        f"/api/contest-analyses/{made[0]['id']}",
        headers=finished["teacher"],
        json={"editorial_md": made[0]["editorial_md"], "published": True},
    )
    review = client.get(f"/api/contests/{cid}/review", headers=finished["a"]).json()
    assert [a["title"] for a in review["analyses"]] == ["P900"]
    assert [(u["label"], u["solved_in_round"]) for u in review["upsolve"]] == [
        ("A", True),
        ("B", False),
    ]
    assert (
        client.post(f"/api/contests/{cid}/analyses", headers=finished["a"], json={}).status_code
        == 403
    )


def test_ot07_review_waits_for_the_end_of_the_round(
    client: TestClient, oly: dict[str, Any]
) -> None:
    contest = _contest(client, oly, -10, 120)
    response = client.get(f"/api/contests/{contest['id']}/review", headers=oly["a"])
    assert response.status_code == 403 and response.json()["detail"] == "contest_not_finished"


def test_ot07_explained_solution_gets_the_dual_assessment(
    client: TestClient, finished: dict[str, Any], db: Session
) -> None:
    def grade_inline(submission_id: int) -> None:
        set_system(db)
        submission = db.get(Submission, submission_id)
        assert submission is not None
        grade = ai_grading.grade(db, FakeLLMProvider(), submission)
        fill_submission(db, submission, grade)
        db.commit()

    app.dependency_overrides[get_explain_enqueue] = lambda: grade_inline
    sid = finished["accepted"]["id"]
    text = {"text": "n санының 2-ге бөлінуін тексердім, сондықтан бір амал жеткілікті."}
    response = client.post(f"/api/submissions/{sid}/explain", headers=finished["a"], json=text)
    assert response.status_code == 201
    assert db.scalar(select(AiGrade).where(AiGrade.submission_id == sid)) is not None
    again = client.post(f"/api/submissions/{sid}/explain", headers=finished["a"], json=text)
    assert again.status_code == 403  # explained once
    assert (
        client.post(f"/api/submissions/{sid}/explain", headers=finished["b"], json=text).status_code
        == 403
    )
    confirm = client.post(
        f"/api/submissions/{sid}/teacher-grade",
        headers=finished["teacher"],
        json={
            "levels": {
                c: "high"
                for c in (
                    "understanding",
                    "algorithm",
                    "correctness",
                    "code_quality",
                    "debugging",
                    "explanation",
                )
            },
            "components": {"F": 100, "E": 80, "A": 80},
            "feedback": "Жақсы түсіндірме.",
            "reason": "Оқытушы деңгейлерді нақтылады.",
        },
    )
    assert confirm.status_code == 201  # the teacher's half of the dual assessment
    app.dependency_overrides.pop(get_explain_enqueue, None)
