"""Stage 6a: olympiad part (spec 4, 10): ОТ-01 … ОТ-06, ОТ-10."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import (
    AiGrade,
    AiMessage,
    AppSetting,
    Assessment,
    AssessmentTask,
    AuditLog,
    Course,
    Explanation,
    Task,
    WorkSession,
)
from app.services.contest_scoring import Attempt, icpc, ioi, submission_points
from app.services.olympiad import OLYMPIAD_KEY
from tests.conftest import School, login
from tests.fake_judge import FakeJudge
from tests.llm_helpers import ScriptedProvider
from tests.workspace_helpers import SOLUTION

III = {"knowledge_actions": 2, "algorithm_freedom": 2, "edge_cases": 1, "justification": 1}
WA = "// fake:WA\n" + SOLUTION


# Standings rules (pure) ----------------------------------------------------------------------


def test_ot02_icpc_penalty_ties_and_compile_errors() -> None:
    attempts = [
        Attempt(1, 10, 5 * 60, "WA"),
        Attempt(1, 10, 6 * 60, "CE"),  # a compilation error costs nothing
        Attempt(1, 10, 12 * 60, "OK"),
        Attempt(1, 10, 15 * 60, "WA"),  # after the acceptance: ignored
        Attempt(2, 10, 32 * 60, "OK"),
        Attempt(3, 10, 32 * 60, "OK"),
        Attempt(3, 11, 40 * 60, "TLE"),
    ]
    rows = {r.user_id: r for r in icpc([1, 2, 3, 4], [10, 11], attempts, penalty_minutes=20)}
    assert (rows[1].solved, rows[1].penalty, rows[1].cells[10].wrong) == (1, 32, 1)
    assert rows[1].rank == 1  # 12 + 20 = 32 minutes, as user 2 and 3
    assert rows[2].rank == rows[3].rank == 1  # equal solved and penalty share the place
    assert rows[3].cells[11].tried and not rows[3].cells[11].solved
    assert rows[4].rank == 4 and rows[4].solved == 0


def test_ot02_freeze_hides_others_in_the_last_hour_but_not_my_own() -> None:
    attempts = [Attempt(1, 10, 30 * 60, "OK"), Attempt(2, 10, 70 * 60, "OK")]
    frozen = {r.user_id: r for r in icpc([1, 2], [10], attempts, frozen_after_s=60 * 60)}
    assert frozen[1].solved == 1
    assert frozen[2].solved == 0 and frozen[2].cells[10].pending == 1
    mine = {r.user_id: r for r in icpc([1, 2], [10], attempts, frozen_after_s=3600, reveal={2})}
    assert mine[2].solved == 1


def test_ot02_ioi_points_for_subtasks_and_best_submission() -> None:
    assert submission_points({"1": 30, "2": 70}, [(1, True), (1, True), (2, False)]) == 30
    assert submission_points({"1": 30, "2": 70}, [(1, True), (2, True)]) == 100
    assert submission_points({}, [(1, True), (1, False), (1, True), (1, True)]) == 75
    attempts = [
        Attempt(1, 10, 60, "WA", 30),
        Attempt(1, 10, 120, "WA", 0),  # a worse later submission does not lower the score
        Attempt(2, 10, 60, "OK", 100),
        Attempt(2, 11, 60, "WA", 40),
    ]
    rows = {r.user_id: r for r in ioi([1, 2], [10, 11], attempts)}
    assert rows[1].score == 30 and rows[2].score == 140
    assert rows[2].rank == 1 and rows[2].solved == 1


def test_ot03_virtual_participant_sees_others_at_the_same_minute() -> None:
    attempts = [Attempt(1, 10, 20 * 60, "OK"), Attempt(1, 11, 90 * 60, "OK")]
    rows = icpc([1], [10, 11], attempts, cutoff_s=45 * 60)
    assert rows[0].solved == 1  # the 90th-minute acceptance has not happened yet


# API setup ------------------------------------------------------------------------------------


def _settings(db: Session, **values: Any) -> None:
    row = db.get(AppSetting, OLYMPIAD_KEY)
    value = {"unlock_topics": [], **values}
    if row is None:
        db.add(AppSetting(key=OLYMPIAD_KEY, value=value))
    else:
        row.value = value
    db.flush()


def _problem(client: TestClient, headers: dict[str, str], course_id: int, **fields: Any) -> int:
    body = {
        "course_id": course_id,
        "title": fields.pop("title", "Problem"),
        "statement_md": "Print EVEN or ODD.",
        "reference_solution": SOLUTION,
        "tests": [
            {"input": "4\n", "expected_output": "EVEN\n", "is_hidden": False},
            {"input": "7\n", "expected_output": "ODD\n", "is_hidden": True},
        ],
        "editorial_md": "Жұптылықты тексеріңіз.",
        **fields,
    }
    response = client.post("/api/tasks", headers=headers, json=body)
    assert response.status_code == 201, response.text
    task_id: int = response.json()["id"]
    client.put(f"/api/tasks/{task_id}/level", headers=headers, json={"features": III})
    assert client.post(f"/api/tasks/{task_id}/approve", headers=headers).status_code == 200
    return task_id


@pytest.fixture
def oly(client: TestClient, school: School, judge: FakeJudge, db: Session) -> dict[str, Any]:
    _settings(db)
    teacher = login(client, school["teacher_a"].email)
    course = client.post(
        "/api/courses", headers=teacher, json={"title": "4.1 Алгоритмдер", "part": "part2"}
    ).json()
    admin = login(client, school["admin"].email)  # teacher A does not teach group B
    for group in ("group_a", "group_b"):
        attached = client.post(
            f"/api/courses/{course['id']}/groups", headers=admin, json={"id": school[group].id}
        )
        assert attached.status_code in (200, 201), attached.text
    tasks = [
        _problem(client, teacher, course["id"], title=f"P{r}", cf_rating=r, tags=["dp"])
        for r in (900, 1000, 1200, 1500)
    ]
    return {
        "teacher": teacher,
        "a": login(client, school["student_a"].email),
        "b": login(client, school["student_b"].email),
        "course": course,
        "tasks": tasks,
    }


def _contest(
    client: TestClient, oly: dict[str, Any], start: int, length: int, **fields: Any
) -> dict[str, Any]:
    begin = datetime.now(UTC) + timedelta(minutes=start)
    response = client.post(
        f"/api/courses/{oly['course']['id']}/contests",
        headers=oly["teacher"],
        json={
            "title": "Contest",
            "starts_at": begin.isoformat(),
            "ends_at": (begin + timedelta(minutes=length)).isoformat(),
            "task_ids": oly["tasks"][:2],
            **fields,
        },
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def _session(
    client: TestClient, headers: dict[str, str], task_id: int, assessment_id: int | None = None
) -> Any:
    return client.post(
        "/api/sessions", headers=headers, json={"task_id": task_id, "assessment_id": assessment_id}
    )


def _submit(client: TestClient, headers: dict[str, str], sid: str, code: str = SOLUTION) -> Any:
    response = client.post(f"/api/sessions/{sid}/submit", headers=headers, json={"code": code})
    assert response.status_code == 201, response.text
    return response.json()


# Contests (ОТ-02) ----------------------------------------------------------------------------


def test_ot02_contest_has_no_ai_and_cannot_change_after_start(
    client: TestClient, oly: dict[str, Any], db: Session
) -> None:
    contest = _contest(client, oly, -30, 120)
    row = db.get(Assessment, contest["id"])
    assert row is not None and row.genai_mode == "forbidden" and row.kind == "contest"
    assert contest["state"] == "running" and contest["format"] == "icpc"
    again = client.put(
        f"/api/contests/{contest['id']}",
        headers=oly["teacher"],
        json={
            "title": "Changed",
            "starts_at": contest["starts_at"],
            "ends_at": contest["ends_at"],
            "task_ids": oly["tasks"][:1],
        },
    )
    assert again.status_code == 409 and again.json()["detail"] == "contest_started"
    # Contests are not control works: not in the assessment list, not editable there.
    listed = client.get("/api/assessments", headers=oly["teacher"]).json()
    assert contest["id"] not in [a["id"] for a in listed]
    assert client.get("/api/contests", headers=oly["a"]).json()[0]["id"] == contest["id"]


def test_ot02_assistant_and_hints_are_off_during_the_contest(
    client: TestClient, oly: dict[str, Any]
) -> None:
    contest = _contest(client, oly, -30, 120)  # problems 0 and 1
    task_id, other = oly["tasks"][0], oly["tasks"][2]
    other_sid = _session(client, oly["a"], other).json()["session_id"]  # practice, before
    sid = _session(client, oly["a"], task_id, contest["id"]).json()["session_id"]
    ask = client.post(
        f"/api/sessions/{sid}/assistant", headers=oly["a"], json={"question": "Қалай?"}
    )
    assert ask.status_code == 403 and ask.json()["detail"] == "assistant_forbidden"
    # No penalty-free tries, statement, editorial or hints of a contest problem in practice.
    blocked = _session(client, oly["a"], task_id)
    assert blocked.status_code == 403
    assert client.get(f"/api/olympiad/problems/{task_id}", headers=oly["a"]).status_code == 403
    # No AI and no tutorials through another problem while the round is on.
    hint = client.post(
        f"/api/olympiad/problems/{other}/hints", headers=oly["a"], json={"session_id": other_sid}
    )
    assert hint.status_code == 403 and hint.json()["detail"] == "assistant_forbidden"
    shown = client.get(f"/api/olympiad/problems/{other}", headers=oly["a"]).json()
    assert shown["in_contest"] and shown["editorial_md"] is None


def test_ot02_contest_problems_stay_out_of_practice_until_the_end(
    client: TestClient, oly: dict[str, Any]
) -> None:
    _contest(client, oly, 60, 120)  # upcoming, problems 0 and 1
    ids = [p["id"] for p in client.get("/api/olympiad/problems", headers=oly["a"]).json()]
    assert oly["tasks"][0] not in ids and oly["tasks"][1] not in ids and oly["tasks"][2] in ids
    assert _session(client, oly["a"], oly["tasks"][0]).status_code == 403
    recommended = client.get("/api/olympiad/recommendations", headers=oly["a"]).json()
    assert oly["tasks"][0] not in [p["id"] for p in recommended["problems"]]
    # Staff still see them (to prepare the contest).
    staff = client.get("/api/olympiad/problems", headers=oly["teacher"]).json()
    assert oly["tasks"][0] in [p["id"] for p in staff]


def test_ot02_only_course_staff_see_names_in_standings(
    client: TestClient, oly: dict[str, Any], school: School
) -> None:
    contest = _contest(client, oly, -200, 120)
    other = login(client, school["teacher_b"].email)  # not a teacher of this course
    rows = client.get(f"/api/contests/{contest['id']}/standings", headers=other).json()["rows"]
    assert all(r["name"] is None for r in rows)
    shown = client.get(f"/api/contests/{contest['id']}", headers=other).json()
    assert shown["task_ids"] == []


def test_ot02_contest_submissions_need_no_explanation_and_get_no_ai_grade(
    client: TestClient, oly: dict[str, Any], db: Session
) -> None:
    contest = _contest(client, oly, -30, 120)
    sid = _session(client, oly["a"], oly["tasks"][0], contest["id"]).json()["session_id"]
    submission = _submit(client, oly["a"], sid)
    assert (
        client.get(f"/api/submissions/{submission['id']}", headers=oly["a"]).json()["verdict"]
        == "OK"
    )
    assert db.scalar(select(AiGrade).where(AiGrade.submission_id == submission["id"])) is None


def test_ot02_icpc_standings_with_freeze_and_hidden_names(
    client: TestClient, oly: dict[str, Any], school: School
) -> None:
    # 100 minutes into a 120-minute contest: the last 60 minutes are frozen.
    contest = _contest(client, oly, -100, 120, freeze_minutes=60)
    a = _session(client, oly["a"], oly["tasks"][0], contest["id"]).json()["session_id"]
    _submit(client, oly["a"], a, WA)
    _submit(client, oly["a"], a)
    b = _session(client, oly["b"], oly["tasks"][0], contest["id"]).json()["session_id"]
    _submit(client, oly["b"], b)

    url = f"/api/contests/{contest['id']}/standings"
    staff = client.get(url, headers=oly["teacher"]).json()
    assert not staff["frozen"]
    first, second = staff["rows"]
    assert first["name"] == school["student_b"].full_name and first["penalty"] in (99, 100)
    assert second["penalty"] == first["penalty"] + 20 and second["cells"][0]["wrong"] == 1

    mine = client.get(url, headers=oly["a"]).json()
    assert mine["frozen"]
    me = next(r for r in mine["rows"] if r["me"])
    other = next(r for r in mine["rows"] if not r["me"])
    assert me["solved"] == 1  # my own verdicts are never hidden
    assert other["solved"] == 0 and other["cells"][0]["pending"] == 1
    assert other["name"] is None  # spec 14.3: no names of other students


def test_ot02_ioi_contest_scores_subtasks(
    client: TestClient, oly: dict[str, Any], judge: FakeJudge
) -> None:
    teacher = oly["teacher"]
    task_id = _problem(
        client,
        teacher,
        oly["course"]["id"],
        title="IOI",
        subtask_points={"1": 40, "2": 60},
        tests=[
            {"input": "4\n", "expected_output": "EVEN\n", "is_hidden": False, "subtask": 1},
            {"input": "7\n", "expected_output": "ODD\n", "subtask": 2},
        ],
    )
    judge.answers["7\n"] = "WRONG\n"  # the solution fails subtask 2
    begin = datetime.now(UTC) - timedelta(minutes=10)
    contest = client.post(
        f"/api/courses/{oly['course']['id']}/contests",
        headers=teacher,
        json={
            "title": "IOI",
            "format": "ioi",
            "starts_at": begin.isoformat(),
            "ends_at": (begin + timedelta(minutes=300)).isoformat(),
            "task_ids": [task_id],
        },
    ).json()
    sid = _session(client, oly["a"], task_id, contest["id"]).json()["session_id"]
    _submit(client, oly["a"], sid)
    rows = client.get(f"/api/contests/{contest['id']}/standings", headers=teacher).json()["rows"]
    assert rows[0]["score"] == 40 and rows[0]["cells"][0]["score"] == 40


# Virtual contests (ОТ-03) --------------------------------------------------------------------


def test_ot03_virtual_contest_after_the_end(
    client: TestClient, oly: dict[str, Any], db: Session
) -> None:
    running = _contest(client, oly, -10, 60)
    early = client.post(f"/api/contests/{running['id']}/virtual", headers=oly["a"])
    assert early.status_code == 409 and early.json()["detail"] == "contest_not_finished"
    db.execute(  # end it, so no round of the course is running any more
        update(Assessment)
        .where(Assessment.id == running["id"])
        .values(
            starts_at=datetime.now(UTC) - timedelta(minutes=300),
            ends_at=datetime.now(UTC) - timedelta(minutes=240),
        )
    )

    past = _contest(client, oly, -200, 120)
    b = _session(client, oly["b"], oly["tasks"][0], past["id"])
    assert b.status_code == 409 and b.json()["detail"] == "assessment_closed"

    start = client.post(f"/api/contests/{past['id']}/virtual", headers=oly["a"])
    assert start.status_code == 201
    sid = _session(client, oly["a"], oly["tasks"][0], past["id"]).json()["session_id"]
    _submit(client, oly["a"], sid)
    standings = client.get(f"/api/contests/{past['id']}/standings", headers=oly["a"]).json()
    me = next(r for r in standings["rows"] if r["me"])
    assert me["virtual"] and me["solved"] == 1
    again = client.post(f"/api/contests/{past['id']}/virtual", headers=oly["a"])
    assert again.json()["detail"] == "virtual_already_used"
    # An official participant already knows the problems: no virtual round for them.
    live = _contest(client, oly, -10, 20, freeze_minutes=0)
    _session(client, oly["b"], oly["tasks"][0], live["id"])
    db.execute(
        update(Assessment)
        .where(Assessment.id == live["id"])
        .values(
            starts_at=datetime.now(UTC) - timedelta(minutes=50),
            ends_at=datetime.now(UTC) - timedelta(minutes=30),
        )
    )
    used = client.post(f"/api/contests/{live['id']}/virtual", headers=oly["b"])
    assert used.json()["detail"] == "already_participated"
    # The AI stays off during the student's own virtual round as well.
    ask = client.post(f"/api/sessions/{sid}/assistant", headers=oly["a"], json={"question": "?"})
    assert ask.status_code == 403


# Practice: access, recommendations, the one-hour rule, hints ---------------------------------


def test_ot01_part2_opens_when_topics_are_mastered(
    client: TestClient, oly: dict[str, Any], db: Session
) -> None:
    _settings(db, unlock_topics=["1.11", "1.12"])
    locked = client.get("/api/olympiad/problems", headers=oly["a"])
    assert locked.status_code == 403 and locked.json()["detail"] == "part2_locked"
    assert _session(client, oly["a"], oly["tasks"][0]).status_code == 403
    overview = client.get("/api/olympiad", headers=oly["a"]).json()
    assert overview["unlock"] == {
        "unlocked": False,
        "required": ["1.11", "1.12"],
        "missing": ["1.11", "1.12"],
    }
    _settings(db)
    problems = client.get("/api/olympiad/problems?tag=dp&min_rating=1000", headers=oly["a"])
    assert [p["cf_rating"] for p in problems.json()] == [1000, 1200, 1500]


def test_ot01_bank_fields_and_memory_limits(client: TestClient, oly: dict[str, Any]) -> None:
    course_id = oly["course"]["id"]
    for memory_kb in (16384, 1048576):
        task_id = _problem(client, oly["teacher"], course_id, memory_limit_kb=memory_kb)
        task = client.get(f"/api/tasks/{task_id}", headers=oly["teacher"]).json()
        assert task["memory_limit_kb"] == memory_kb
    base = {"course_id": course_id, "title": "x", "statement_md": "x"}
    for bad in ({"memory_limit_kb": 8192}, {"cf_rating": 700}, {"subtask_points": {"1": 50}}):
        response = client.post("/api/tasks", headers=oly["teacher"], json={**base, **bad})
        assert response.status_code == 422, bad
    shown = client.get(f"/api/olympiad/problems/{oly['tasks'][1]}", headers=oly["a"]).json()
    assert shown["tags"] == ["dp"] and shown["cf_rating"] == 1000


def test_ot04_recommendations_are_slightly_above_the_rating(
    client: TestClient, oly: dict[str, Any]
) -> None:
    first = client.get("/api/olympiad/recommendations", headers=oly["a"]).json()
    assert first["rating"] == 800 and first["range"] == [900, 1100]
    assert [p["cf_rating"] for p in first["problems"]] == [900, 1000]
    sid = _session(client, oly["a"], oly["tasks"][1]).json()["session_id"]
    _submit(client, oly["a"], sid)  # solves the 1000 problem
    after = client.get("/api/olympiad/recommendations", headers=oly["a"]).json()
    assert after["rating"] == 1000 and [p["cf_rating"] for p in after["problems"]] == [1200]


def test_ot05_editorial_opens_after_one_hour(
    client: TestClient, oly: dict[str, Any], db: Session
) -> None:
    task_id = oly["tasks"][2]
    url = f"/api/olympiad/problems/{task_id}"
    assert client.get(url, headers=oly["a"]).json()["editorial_md"] is None
    sid = _session(client, oly["a"], task_id).json()["session_id"]
    shown = client.get(url, headers=oly["a"]).json()
    assert not shown["editorial_available"] and shown["editorial_opens_at"]
    db.execute(
        update(WorkSession)
        .where(WorkSession.id == sid)
        .values(started_at=datetime.now(UTC) - timedelta(minutes=59))
    )
    assert client.get(url, headers=oly["a"]).json()["editorial_md"] is None
    db.execute(
        update(WorkSession)
        .where(WorkSession.id == sid)
        .values(started_at=datetime.now(UTC) - timedelta(minutes=61))
    )
    opened = client.get(url, headers=oly["a"]).json()
    assert opened["editorial_md"] == "Жұптылықты тексеріңіз." and opened["minutes_spent"] >= 60


def test_ot05_hints_open_step_by_step(client: TestClient, oly: dict[str, Any], db: Session) -> None:
    task_id = oly["tasks"][2]
    sid = _session(client, oly["a"], task_id).json()["session_id"]
    url = f"/api/olympiad/problems/{task_id}/hints"
    body = {"session_id": sid, "code": SOLUTION}
    first = client.post(url, headers=oly["a"], json=body)
    assert first.status_code == 201 and first.json()["level"] == 1
    too_soon = client.post(url, headers=oly["a"], json=body)
    assert too_soon.status_code == 409 and too_soon.json()["detail"]["code"] == "hint_not_yet"
    for level in (2, 3):
        db.execute(
            update(AiMessage)
            .where(AiMessage.task_id == task_id)
            .values(created_at=datetime.now(UTC) - timedelta(minutes=16))
        )
        assert client.post(url, headers=oly["a"], json=body).json()["level"] == level
    assert client.post(url, headers=oly["a"], json=body).json()["detail"] == "no_more_hints"
    prompts = db.scalars(select(AiMessage.prompt_version).where(AiMessage.task_id == task_id))
    assert set(prompts) == {"olympiad-hint-v1"}


def test_ot05_hint_with_ready_code_is_withheld(
    client: TestClient, oly: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.api.olympiad.get_provider",
        lambda: ScriptedProvider(["```cpp\nint main() { return 0; }\n```"]),
    )
    task_id = oly["tasks"][2]
    sid = _session(client, oly["a"], task_id).json()["session_id"]
    hint = client.post(
        f"/api/olympiad/problems/{task_id}/hints", headers=oly["a"], json={"session_id": sid}
    ).json()
    assert hint["blocked"] and "int main" not in hint["answer"]


def test_ot05_practice_gets_only_step_by_step_hints(
    client: TestClient, oly: dict[str, Any]
) -> None:
    """Free questions would skip the order direction → idea → pseudocode."""
    sid = _session(client, oly["a"], oly["tasks"][2]).json()["session_id"]
    answer = client.post(
        f"/api/sessions/{sid}/assistant", headers=oly["a"], json={"question": "Псевдокод бер"}
    )
    assert answer.status_code == 403 and answer.json()["detail"] == "assistant_forbidden"


# Own tests and the stress test (ОТ-06) -------------------------------------------------------


def test_ot06_own_tests_run_with_one_button(
    client: TestClient, oly: dict[str, Any], judge: FakeJudge
) -> None:
    task_id = oly["tasks"][2]
    tests_url = f"/api/olympiad/problems/{task_id}/my-tests"
    first = client.post(
        tests_url, headers=oly["a"], json={"input": "4\n", "expected_output": "EVEN\n"}
    ).json()
    client.post(tests_url, headers=oly["a"], json={"input": "9\n"})
    assert len(client.get(tests_url, headers=oly["a"]).json()) == 2
    assert client.get(tests_url, headers=oly["b"]).json() == []  # own tests are private
    assert (
        client.put(f"/api/olympiad/my-tests/{first['id']}", headers=oly["b"], json={"input": "1"})
    ).status_code == 403

    sid = _session(client, oly["a"], task_id).json()["session_id"]
    before = len(judge.requests)
    run = client.post(
        f"/api/sessions/{sid}/my-tests/run", headers=oly["a"], json={"code": SOLUTION}
    ).json()
    assert [r["verdict"] for r in run] == ["OK", None]  # no answer given: output only
    assert len(judge.requests) - before == 2  # everything ran in the judge
    wrong = client.post(f"/api/sessions/{sid}/my-tests/run", headers=oly["a"], json={"code": WA})
    assert wrong.json()[0]["verdict"] == "WA"


def test_ot06_stress_test_shows_the_differing_input(
    client: TestClient, oly: dict[str, Any], judge: FakeJudge
) -> None:
    sid = _session(client, oly["a"], oly["tasks"][2]).json()["session_id"]
    url = f"/api/sessions/{sid}/stress"
    body = {"brute_code": "// fake:ECHO", "generator_code": "// fake:GEN", "iterations": 5}
    found = client.post(url, headers=oly["a"], json={**body, "code": "// fake:DIFF:3"}).json()
    assert found["status"] == "mismatch" and found["iterations"] == 3
    assert found["input"] == "case 3\n" and found["expected"] == "case 3\n"
    assert found["actual"] == "wrong\n"
    same = client.post(url, headers=oly["a"], json={**body, "code": "// fake:ECHO"}).json()
    assert same == {**same, "status": "ok", "iterations": 5}
    broken = client.post(
        url, headers=oly["a"], json={**body, "generator_code": "// fake:CE", "code": "x"}
    ).json()
    assert broken["status"] == "generator_failed"
    # 3 judge runs per iteration must fit the per-minute budget.
    too_many = {**body, "code": "x", "iterations": 21}
    assert client.post(url, headers=oly["a"], json=too_many).status_code == 422


def test_ot06_one_run_at_a_time_and_no_empty_runs(
    client: TestClient, oly: dict[str, Any], school: School, redis: Any
) -> None:
    sid = _session(client, oly["a"], oly["tasks"][2]).json()["session_id"]
    empty = client.post(f"/api/sessions/{sid}/my-tests/run", headers=oly["a"], json={"code": "x"})
    assert empty.status_code == 409 and empty.json()["detail"] == "no_tests"
    redis.set(f"olympiad_run:{school['student_a'].id}", "1")  # a run is in progress
    body = {"code": "x", "brute_code": "// fake:ECHO", "generator_code": "// fake:GEN"}
    busy = client.post(f"/api/sessions/{sid}/stress", headers=oly["a"], json=body)
    assert busy.status_code == 429 and busy.json()["detail"] == "run_in_progress"


# Reference (ОТ-10), the drafted bank (Q-13), settings ----------------------------------------


def test_ot10_reference_lists_lessons_and_materials(
    client: TestClient, school: School, seeded: object, db: Session
) -> None:
    coach = login(client, school["coach"].email)
    data = client.get("/api/olympiad", headers=coach).json()
    course = next(c for c in data["courses"] if "64454" in (c["url"] or ""))
    module = next(t for t in course["topics"] if t["code"] == "4.1.1")
    assert any("stepik.org/lesson/" in lesson["url"] for lesson in module["lessons"])
    assert {r["name"] for r in module["resources"]} == {"Codeforces EDU", "ACMP курсы"}
    assert any("cses.fi" in r["url"] for r in data["practice"]["resources"])
    assert data["practice"]["rules"]


def test_ot01_seeded_olympiad_bank_is_a_draft(db: Session, seeded: object) -> None:
    tasks = db.scalars(select(Task).where(Task.external_key.like("OLY-%"))).all()
    assert len(tasks) == 8
    for task in tasks:
        course = db.get(Course, task.course_id)
        assert course is not None and course.part == "part2"
        assert task.status == "draft" and task.level in ("III", "IV")
        assert task.cf_rating and task.tags and task.editorial_md
    acmp = next(t for t in tasks if t.external_key == "OLY-4.1.3-2")
    assert acmp.memory_limit_kb == 16384
    ioi_task = next(t for t in tasks if t.external_key == "OLY-4.2.2-2")
    assert ioi_task.subtask_points == {"1": 30, "2": 70}
    assert {t.subtask for t in ioi_task.tests} == {1, 2}


def test_ot04_settings_are_changed_by_coach_or_admin(
    client: TestClient, school: School, db: Session
) -> None:
    body = {"unlock_topics": [], "recommend_min": 50, "recommend_max": 200}
    student = login(client, school["student_a"].email)
    assert client.put("/api/settings/olympiad", headers=student, json=body).status_code == 403
    coach = login(client, school["coach"].email)
    saved = client.put("/api/settings/olympiad", headers=coach, json=body)
    assert saved.status_code == 200 and saved.json()["editorial_after_minutes"] == 60
    bad = client.put(
        "/api/settings/olympiad", headers=coach, json={"recommend_min": 300, "recommend_max": 100}
    )
    assert bad.status_code == 422
    assert db.scalar(select(AuditLog).where(AuditLog.action == "olympiad_settings_changed"))


def test_ot02_ai_is_off_for_course_students_before_they_open_a_contest_problem(
    client: TestClient, oly: dict[str, Any]
) -> None:
    other = oly["tasks"][2]
    sid = _session(client, oly["a"], other).json()["session_id"]
    _contest(client, oly, -10, 120)  # running, the student has not opened it
    hint = client.post(
        f"/api/olympiad/problems/{other}/hints", headers=oly["a"], json={"session_id": sid}
    )
    assert hint.status_code == 403 and hint.json()["detail"] == "assistant_forbidden"


def test_ot02_old_practice_session_closes_when_the_problem_joins_a_contest(
    client: TestClient, oly: dict[str, Any]
) -> None:
    task_id = oly["tasks"][0]
    sid = _session(client, oly["a"], task_id).json()["session_id"]  # practice, before
    _contest(client, oly, 30, 120)  # the problem is now kept for a contest
    for path, body in (("test", {"code": SOLUTION}), ("submit", {"code": SOLUTION})):
        response = client.post(f"/api/sessions/{sid}/{path}", headers=oly["a"], json=body)
        assert response.status_code == 403, path


def test_ot01_problems_kept_for_a_contest_stay_out_of_the_bank(
    client: TestClient, oly: dict[str, Any]
) -> None:
    hidden = _problem(client, oly["teacher"], oly["course"]["id"], title="Kept", in_bank=False)
    ids = [p["id"] for p in client.get("/api/olympiad/problems", headers=oly["a"]).json()]
    assert hidden not in ids
    assert _session(client, oly["a"], hidden).status_code == 403
    staff = [p["id"] for p in client.get("/api/olympiad/problems", headers=oly["teacher"]).json()]
    assert hidden in staff
    task = client.get(f"/api/tasks/{hidden}", headers=oly["teacher"]).json()
    assert task["in_bank"] is False


def test_ot06_a_run_lock_is_released_only_by_its_owner(redis: Any, school: School) -> None:
    from app.api.olympiad import _one_run_at_a_time, _release

    user = school["student_a"]
    token = _one_run_at_a_time(redis, user)
    redis.set(f"olympiad_run:{user.id}", "someone-else")  # expired and taken again
    _release(redis, user, token)
    assert redis.get(f"olympiad_run:{user.id}") in (b"someone-else", "someone-else")
    redis.delete(f"olympiad_run:{user.id}")
    mine = _one_run_at_a_time(redis, user)
    _release(redis, user, mine)
    assert redis.get(f"olympiad_run:{user.id}") is None


def test_ot02_no_llm_and_no_early_access_through_control_works(
    client: TestClient, oly: dict[str, Any], db: Session
) -> None:
    contest = _contest(client, oly, 60, 120)  # upcoming, problems 0 and 1
    begin = datetime.now(UTC) - timedelta(minutes=5)
    control = Assessment(
        course_id=oly["course"]["id"],
        title="Open homework",
        starts_at=begin,
        ends_at=begin + timedelta(hours=3),
        genai_mode="open",
    )
    db.add(control)
    db.flush()
    db.add(AssessmentTask(assessment_id=control.id, task_id=oly["tasks"][0]))
    db.add(AssessmentTask(assessment_id=control.id, task_id=oly["tasks"][2]))
    db.flush()
    # The contest problem is not opened early through the homework.
    assert _session(client, oly["a"], oly["tasks"][0], control.id).status_code == 403
    # While a round of the course runs, a submission elsewhere gets template questions.
    db.execute(
        update(Assessment)
        .where(Assessment.id == contest["id"])
        .values(starts_at=datetime.now(UTC) - timedelta(minutes=10))
    )
    sid = _session(client, oly["a"], oly["tasks"][2], control.id).json()["session_id"]
    response = client.post(
        f"/api/sessions/{sid}/submit",
        headers=oly["a"],
        json={"code": SOLUTION, "explanation": "n % 2"},
    )
    assert response.status_code == 201
    explanation = db.scalar(
        select(Explanation).where(Explanation.submission_id == response.json()["id"])
    )
    assert explanation is not None and explanation.question_source == "template"


def test_ot03_virtual_round_accepts_trace_events(client: TestClient, oly: dict[str, Any]) -> None:
    past = _contest(client, oly, -200, 120)
    client.post(f"/api/contests/{past['id']}/virtual", headers=oly["a"])
    sid = _session(client, oly["a"], oly["tasks"][0], past["id"]).json()["session_id"]
    event = {
        "seq": 1,
        "kind": "snapshot",
        "client_ts": datetime.now(UTC).isoformat(),
        "payload": {"code": "int main() {}"},
    }
    response = client.post(
        f"/api/sessions/{sid}/events", headers=oly["a"], json={"events": [event]}
    )
    assert response.status_code == 200, response.text


def test_ot01_problems_of_upcoming_control_works_stay_out_of_practice(
    client: TestClient, oly: dict[str, Any], db: Session
) -> None:
    begin = datetime.now(UTC) + timedelta(hours=1)
    work = Assessment(
        course_id=oly["course"]["id"],
        title="Later",
        starts_at=begin,
        ends_at=begin + timedelta(hours=1),
    )
    db.add(work)
    db.flush()
    db.add(AssessmentTask(assessment_id=work.id, task_id=oly["tasks"][2]))
    db.flush()
    assert _session(client, oly["a"], oly["tasks"][2]).status_code == 403
    ids = [p["id"] for p in client.get("/api/olympiad/problems", headers=oly["a"]).json()]
    assert oly["tasks"][2] not in ids
