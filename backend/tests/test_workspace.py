"""Stage 2: editor session, testing, digital trace, explanation, integrity marks.

ФТ-24, ФТ-25, ФТ-27, ФТ-29, ФТ-31. Judge0 is replaced by tests/fake_judge.py; the same
scenarios against a real Judge0 are in test_judge0_integration.py.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.api import workspace
from app.jobs import get_enqueue
from app.judge import get_judge
from app.main import app
from app.models import Submission, TraceEvent
from app.services.grading import grade_submission
from tests.conftest import School, login
from tests.fake_judge import FakeJudge

FEATURES = {"knowledge_actions": 0, "algorithm_freedom": 0, "edge_cases": 1, "justification": 0}
SOLUTION = "#include <iostream>\nint main() { long long n; std::cin >> n; }\n"


@pytest.fixture
def judge(db: Session) -> Iterator[FakeJudge]:
    fake = FakeJudge({"4\n": "EVEN\n", "7\n": "ODD\n", "-3\n": "ODD\n"})

    def grade_inline(submission_id: int) -> None:
        submission = db.get(Submission, submission_id)
        assert submission is not None
        grade_submission(db, fake, submission)
        db.commit()

    app.dependency_overrides[get_judge] = lambda: fake
    app.dependency_overrides[get_enqueue] = lambda: grade_inline
    yield fake


def _window(start: int, length: int = 120) -> dict[str, str]:
    begin = datetime.now(UTC) + timedelta(minutes=start)
    return {
        "starts_at": begin.isoformat(),
        "ends_at": (begin + timedelta(minutes=length)).isoformat(),
    }


@pytest.fixture
def ws(client: TestClient, school: School, judge: FakeJudge) -> dict[str, Any]:
    teacher = login(client, school["teacher_a"].email)
    course = client.post("/api/courses", headers=teacher, json={"title": "C++"}).json()
    client.post(
        f"/api/courses/{course['id']}/groups", headers=teacher, json={"id": school["group_a"].id}
    )
    task = client.post(
        "/api/tasks",
        headers=teacher,
        json={
            "course_id": course["id"],
            "title": "Even or odd",
            "statement_md": "Print EVEN or ODD.",
            "reference_solution": SOLUTION,
            "tests": [
                {"input": "4\n", "expected_output": "EVEN\n", "is_hidden": False},
                {"input": "7\n", "expected_output": "ODD\n", "is_hidden": True},
                {"input": "-3\n", "expected_output": "ODD\n", "is_hidden": True},
            ],
        },
    ).json()
    client.put(f"/api/tasks/{task['id']}/level", headers=teacher, json={"features": FEATURES})
    client.post(f"/api/tasks/{task['id']}/approve", headers=teacher)

    def assessment(window: dict[str, str], title: str) -> dict[str, Any]:
        result: dict[str, Any] = client.post(
            "/api/assessments",
            headers=teacher,
            json={"course_id": course["id"], "title": title, "task_ids": [task["id"]], **window},
        ).json()
        return result

    return {
        "teacher": teacher,
        "student": login(client, school["student_a"].email),
        "course": course,
        "task": task,
        "assessment": assessment(_window(-5), "1-БЖ"),
        "future": assessment(_window(60), "2-БЖ"),
        "ended": assessment(_window(-200, 60), "0-БЖ"),
    }


def _open(client: TestClient, ws: dict[str, Any], headers: dict[str, str] | None = None) -> str:
    response = client.post(
        "/api/sessions",
        headers=headers or ws["student"],
        json={"task_id": ws["task"]["id"], "assessment_id": ws["assessment"]["id"]},
    )
    assert response.status_code == 201, response.text
    session_id: str = response.json()["session_id"]
    return session_id


def _submit(client: TestClient, ws: dict[str, Any], sid: str, code: str = SOLUTION) -> Any:
    response = client.post(
        f"/api/sessions/{sid}/submit",
        headers=ws["student"],
        json={"code": code, "explanation": "n % 2 тексеремін", "ui_language": "kk"},
    )
    assert response.status_code == 201, response.text
    return client.get(f"/api/submissions/{response.json()['id']}", headers=ws["student"]).json()


def test_ft24_student_runs_code_with_own_input(client: TestClient, ws: dict[str, Any]) -> None:
    sid = _open(client, ws)
    response = client.post(
        f"/api/sessions/{sid}/run",
        headers=ws["student"],
        json={"code": "// fake:ECHO\nint main(){}", "stdin": "hello\n"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "finished"
    assert response.json()["stdout"] == "hello\n"


def test_ft24_compile_error_is_shown(client: TestClient, ws: dict[str, Any]) -> None:
    sid = _open(client, ws)
    body = client.post(
        f"/api/sessions/{sid}/run", headers=ws["student"], json={"code": "// fake:CE"}
    ).json()
    assert body["status"] == "compile_error"
    assert "expected ';'" in body["compile_output"]


def test_ft24_public_tests_only_before_submission(
    client: TestClient, ws: dict[str, Any], judge: FakeJudge
) -> None:
    sid = _open(client, ws)
    body = client.post(
        f"/api/sessions/{sid}/test", headers=ws["student"], json={"code": SOLUTION}
    ).json()
    assert [(r["position"], r["verdict"]) for r in body["results"]] == [(1, "OK")]
    assert [r.stdin for r in judge.requests] == ["4\n"]


def test_ft24_session_resumes_last_code(client: TestClient, ws: dict[str, Any]) -> None:
    sid = _open(client, ws)
    now = datetime.now(UTC).isoformat()
    client.post(
        f"/api/sessions/{sid}/events",
        headers=ws["student"],
        json={
            "events": [
                {
                    "seq": 1,
                    "kind": "snapshot",
                    "client_ts": now,
                    "payload": {"code": "int main() { /* draft */ }"},
                }
            ]
        },
    )
    again = client.post(
        "/api/sessions",
        headers=ws["student"],
        json={"task_id": ws["task"]["id"], "assessment_id": ws["assessment"]["id"]},
    ).json()
    assert again["code"] == "int main() { /* draft */ }"
    assert "tests" not in again["task"]


def test_ft31_correct_solution_gets_ok(client: TestClient, ws: dict[str, Any]) -> None:
    result = _submit(client, ws, _open(client, ws))
    assert result["status"] == "done"
    assert result["verdict"] == "OK"
    assert (result["tests_passed"], result["tests_total"]) == (3, 3)
    assert result["max_time_ms"] == 20 and result["max_memory_kb"] == 1024


@pytest.mark.parametrize("verdict", ["WA", "TLE", "MLE", "RE", "CE"])
def test_ft31_wrong_solutions_get_expected_verdict(
    client: TestClient, ws: dict[str, Any], verdict: str
) -> None:
    result = _submit(client, ws, _open(client, ws), code=f"// fake:{verdict}\nint main() {{}}")
    assert result["verdict"] == verdict
    assert result["tests_passed"] == 0
    if verdict == "CE":
        assert len(result["results"]) == 1
        assert "error" in result["compile_output"]


def test_sec14_student_gets_only_totals_for_hidden_tests(
    client: TestClient, ws: dict[str, Any]
) -> None:
    result = _submit(client, ws, _open(client, ws), code="// fake:WA\nint main() {}")
    # Per-test verdicts, time and memory of hidden tests could leak the hidden input.
    assert [r["position"] for r in result["results"]] == [1]
    assert (result["verdict"], result["tests_passed"], result["tests_total"]) == ("WA", 0, 3)
    for r in result["results"]:
        assert set(r) == {"position", "is_hidden", "verdict", "time_ms", "memory_kb"}
    staff = client.get(f"/api/submissions/{result['id']}", headers=ws["teacher"]).json()
    assert [r["is_hidden"] for r in staff["results"]] == [False, True, True]


def test_ft31_judge_down_marks_submission_as_error(
    client: TestClient, ws: dict[str, Any], judge: FakeJudge
) -> None:
    judge.down = True
    result = _submit(client, ws, _open(client, ws))
    assert result["status"] == "error"
    assert result["verdict"] is None


@pytest.mark.parametrize(
    "statement",
    ["UPDATE trace_events SET kind = 'run'", "DELETE FROM trace_events", "TRUNCATE trace_events"],
)
def test_ft25_trace_is_append_only(
    client: TestClient, ws: dict[str, Any], db: Session, statement: str
) -> None:
    _open(client, ws)
    before = db.scalar(select(TraceEvent.id).limit(1))
    assert before is not None
    with pytest.raises(DBAPIError, match="append-only"), db.begin_nested():
        db.execute(text(statement))


def test_ft25_resent_events_are_not_duplicated(client: TestClient, ws: dict[str, Any]) -> None:
    sid = _open(client, ws)
    now = datetime.now(UTC).isoformat()
    batch = {
        "events": [
            {"seq": 1, "kind": "snapshot", "client_ts": now, "payload": {"code": "a"}},
            {"seq": 2, "kind": "focus_lost", "client_ts": now},
        ]
    }
    first = client.post(f"/api/sessions/{sid}/events", headers=ws["student"], json=batch)
    again = client.post(f"/api/sessions/{sid}/events", headers=ws["student"], json=batch)
    assert first.json() == {"stored": 2, "session_closed": False}
    assert again.json() == {"stored": 0, "session_closed": False}


def test_ft25_browser_cannot_forge_server_events(client: TestClient, ws: dict[str, Any]) -> None:
    sid = _open(client, ws)
    forged = {
        "events": [
            {
                "seq": 1,
                "kind": "verdict",
                "client_ts": datetime.now(UTC).isoformat(),
                "payload": {"verdict": "OK"},
            }
        ]
    }
    response = client.post(f"/api/sessions/{sid}/events", headers=ws["student"], json=forged)
    assert response.status_code == 422


def test_ft25_trace_rebuilds_the_whole_work_process(client: TestClient, ws: dict[str, Any]) -> None:
    sid = _open(client, ws)
    start = datetime.now(UTC)
    drafts = ["int main() {", "int main() { long long n; }", SOLUTION]
    events = [
        {
            "seq": i,
            "kind": "snapshot",
            "client_ts": (start + timedelta(seconds=i)).isoformat(),
            "payload": {"code": code},
        }
        for i, code in enumerate(drafts, start=1)
    ]
    # Sent late and out of order, as after a network outage.
    client.post(f"/api/sessions/{sid}/events", headers=ws["student"], json={"events": events[::-1]})
    client.post(f"/api/sessions/{sid}/run", headers=ws["student"], json={"code": "// fake:CE"})
    result = _submit(client, ws, sid)
    client.put(
        f"/api/submissions/{result['id']}/answers",
        headers=ws["student"],
        json={"answers": ["a"] * len(result["questions"])},
    )

    trace = client.get(f"/api/sessions/{sid}/trace", headers=ws["teacher"]).json()
    kinds = [e["kind"] for e in trace["events"]]
    assert kinds[0] == "session_start"
    assert [e["payload"]["code"] for e in trace["events"] if e["kind"] == "snapshot"] == drafts
    for kind in ("compile", "submit", "explanation", "verdict", "answers"):
        assert kind in kinds
    assert kinds.index("submit") < kinds.index("verdict") < kinds.index("answers")
    code_events = [e for e in trace["events"] if "code" in e["payload"]]
    assert code_events[-1]["payload"]["code"] == SOLUTION


def test_ft29_large_paste_is_flagged_for_teacher_only(
    client: TestClient, ws: dict[str, Any], school: School
) -> None:
    sid = _open(client, ws)
    now = datetime.now(UTC).isoformat()
    client.post(
        f"/api/sessions/{sid}/events",
        headers=ws["student"],
        json={
            "events": [
                {
                    "seq": 1,
                    "kind": "paste",
                    "client_ts": now,
                    "payload": {"length": 20, "lines": 1},
                },
                {
                    "seq": 2,
                    "kind": "paste",
                    "client_ts": now,
                    "payload": {"length": 900, "lines": 30},
                },
                {"seq": 3, "kind": "focus_lost", "client_ts": now},
                {"seq": 4, "kind": "focus_back", "client_ts": now},
            ]
        },
    )
    url = f"/api/assessments/{ws['assessment']['id']}/activity"
    rows = client.get(url, headers=ws["teacher"]).json()
    row = next(r for r in rows if r["user_id"] == school["student_a"].id)
    assert (row["large_pastes"], row["pasted_chars"], row["focus_lost"]) == (1, 920, 1)
    assert client.get(url, headers=ws["student"]).status_code == 403
    assert client.get(f"/api/sessions/{sid}/trace", headers=ws["student"]).status_code == 403
    other = login(client, school["teacher_b"].email)
    assert client.get(url, headers=other).status_code == 403


def test_ft29_paste_threshold_is_a_setting(
    client: TestClient, ws: dict[str, Any], make_user: Any
) -> None:
    from app.core.roles import Role

    make_user("root@example.com", Role.ADMIN)
    admin = login(client, "root@example.com")
    assert (
        client.put(
            "/api/settings/integrity", headers=ws["teacher"], json={"large_paste_chars": 10}
        ).status_code
        == 403
    )
    client.put("/api/settings/integrity", headers=admin, json={"large_paste_chars": 10})
    sid = _open(client, ws)
    client.post(
        f"/api/sessions/{sid}/events",
        headers=ws["student"],
        json={
            "events": [
                {
                    "seq": 1,
                    "kind": "paste",
                    "client_ts": datetime.now(UTC).isoformat(),
                    "payload": {"length": 20},
                }
            ]
        },
    )
    rows = client.get(
        f"/api/assessments/{ws['assessment']['id']}/activity", headers=ws["teacher"]
    ).json()
    assert sum(r["large_pastes"] for r in rows) == 1


def test_ft27_submission_asks_two_or_three_questions_about_own_code(
    client: TestClient, ws: dict[str, Any]
) -> None:
    result = _submit(client, ws, _open(client, ws), code="int main() { for (;;) {} if (1) {} }")
    questions = [q["question"] for q in result["questions"]]
    assert 2 <= len(questions) <= 3
    assert any("Цикл" in q for q in questions)
    assert result["explanation"] == "n % 2 тексеремін"


def test_ft27_student_answers_questions(
    client: TestClient, ws: dict[str, Any], school: School
) -> None:
    result = _submit(client, ws, _open(client, ws))
    n = len(result["questions"])
    url = f"/api/submissions/{result['id']}/answers"
    assert client.put(url, headers=ws["student"], json={"answers": ["x"]}).status_code == 422
    other = login(client, school["student_b"].email)
    assert client.put(url, headers=other, json={"answers": ["x"] * n}).status_code == 403
    answered = client.put(url, headers=ws["student"], json={"answers": [f"a{i}" for i in range(n)]})
    assert [q["answer"] for q in answered.json()["questions"]] == [f"a{i}" for i in range(n)]


def test_sec14_only_one_active_session_in_an_assessment(
    client: TestClient, ws: dict[str, Any]
) -> None:
    first = _open(client, ws)
    offline_before = datetime.now(UTC).isoformat()
    second = _open(client, ws)
    later = (datetime.now(UTC) + timedelta(seconds=5)).isoformat()

    def send(sid: str, ts: str) -> Any:
        event = {"events": [{"seq": 1, "kind": "focus_lost", "client_ts": ts}]}
        return client.post(f"/api/sessions/{sid}/events", headers=ws["student"], json=event)

    # The old tab cannot work any more...
    run = client.post(f"/api/sessions/{first}/run", headers=ws["student"], json={"code": "x"})
    assert run.status_code == 409
    after = send(first, later)
    assert after.status_code == 409 and after.json()["detail"] == "session_closed"
    # ...but what it recorded before being replaced is still saved.
    assert send(first, offline_before).json() == {"stored": 1, "session_closed": True}
    assert send(second, later).status_code == 200


def test_sec14_student_cannot_work_outside_own_started_assessment(
    client: TestClient, ws: dict[str, Any], school: School
) -> None:
    def open_as(headers: dict[str, str], assessment: dict[str, Any]) -> int:
        response = client.post(
            "/api/sessions",
            headers=headers,
            json={"task_id": ws["task"]["id"], "assessment_id": assessment["id"]},
        )
        return int(response.status_code)

    assert open_as(ws["student"], ws["future"]) == 403
    assert open_as(ws["student"], ws["ended"]) == 409
    assert open_as(login(client, school["student_b"].email), ws["assessment"]) == 403
    practice = client.post(
        "/api/sessions", headers=ws["student"], json={"task_id": ws["task"]["id"]}
    )
    assert practice.status_code == 403


def test_sec14_students_cannot_touch_each_others_work(
    client: TestClient, ws: dict[str, Any], school: School
) -> None:
    sid = _open(client, ws)
    result = _submit(client, ws, sid)
    other = login(client, school["student_b"].email)
    assert client.get(f"/api/submissions/{result['id']}", headers=other).status_code == 403
    run = client.post(f"/api/sessions/{sid}/run", headers=other, json={"code": "x"})
    assert run.status_code == 403
    assert client.get(f"/api/submissions/{result['id']}", headers=ws["teacher"]).status_code == 200


def test_sec14_judge_runs_are_rate_limited(
    client: TestClient, ws: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(workspace, "JUDGE_JOBS_PER_MINUTE", 5)
    sid = _open(client, ws)
    codes = [
        client.post(
            f"/api/sessions/{sid}/run", headers=ws["student"], json={"code": "// fake:ECHO"}
        ).status_code
        for _ in range(6)
    ]
    assert codes == [200] * 5 + [429]


def test_sec14_one_submission_in_flight_and_limited_per_window(
    client: TestClient, ws: dict[str, Any], db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sid = _open(client, ws)
    app.dependency_overrides[get_enqueue] = lambda: lambda submission_id: None  # stays queued
    body = {"code": SOLUTION, "explanation": "x"}
    assert (
        client.post(f"/api/sessions/{sid}/submit", headers=ws["student"], json=body).status_code
        == 201
    )
    second = client.post(f"/api/sessions/{sid}/submit", headers=ws["student"], json=body)
    assert second.status_code == 429 and second.json()["detail"] == "submission_in_progress"


def test_ft27_llm_quota_falls_back_to_template_questions(
    client: TestClient, ws: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(workspace, "QUESTION_REQUESTS_PER_DAY", 0)

    def no_llm(*args: object) -> None:
        raise AssertionError("LLM must not be called over quota")

    monkeypatch.setattr(workspace, "generate_questions", no_llm)
    result = _submit(client, ws, _open(client, ws))
    assert 2 <= len(result["questions"]) <= 3


@pytest.mark.parametrize(
    "event",
    [
        {"kind": "paste", "payload": {"length": -100000}},
        {"kind": "paste", "payload": {"length": "many"}},
        {"kind": "snapshot", "payload": {"code": 5}},
        {"kind": "focus_lost", "payload": {"extra": "x"}},
    ],
)
def test_ft29_malformed_event_payload_is_rejected(
    client: TestClient, ws: dict[str, Any], event: dict[str, Any]
) -> None:
    sid = _open(client, ws)
    batch = {"events": [{"seq": 1, "client_ts": datetime.now(UTC).isoformat(), **event}]}
    response = client.post(f"/api/sessions/{sid}/events", headers=ws["student"], json=batch)
    assert response.status_code == 422


def test_ft25_browser_clock_is_not_trusted(
    client: TestClient, ws: dict[str, Any], db: Session
) -> None:
    sid = _open(client, ws)
    past = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    future = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    naive = datetime.now().replace(tzinfo=None).isoformat()
    bad = client.post(
        f"/api/sessions/{sid}/events",
        headers=ws["student"],
        json={"events": [{"seq": 9, "kind": "focus_lost", "client_ts": naive}]},
    )
    assert bad.status_code == 422
    client.post(
        f"/api/sessions/{sid}/events",
        headers=ws["student"],
        json={
            "events": [
                {"seq": 1, "kind": "snapshot", "client_ts": past, "payload": {"code": "a"}},
                {"seq": 2, "kind": "snapshot", "client_ts": future, "payload": {"code": "b"}},
            ]
        },
    )
    trace = client.get(f"/api/sessions/{sid}/trace", headers=ws["teacher"]).json()
    started = datetime.fromisoformat(trace["started_at"])
    snapshots = [e for e in trace["events"] if e["kind"] == "snapshot"]
    for e in snapshots:
        ts = datetime.fromisoformat(e["client_ts"])
        assert started <= ts <= datetime.now(UTC) + timedelta(seconds=1)
    rows = client.get(
        f"/api/assessments/{ws['assessment']['id']}/activity", headers=ws["teacher"]
    ).json()
    assert sum(r["late_events"] for r in rows) == 0


def test_ft25_closed_session_accepts_late_events_only_for_a_while(
    client: TestClient, ws: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _open(client, ws)
    before = datetime.now(UTC).isoformat()
    _open(client, ws)
    monkeypatch.setattr(workspace, "LATE_EVENTS_GRACE", timedelta(seconds=-1))
    late = client.post(
        f"/api/sessions/{first}/events",
        headers=ws["student"],
        json={"events": [{"seq": 1, "kind": "focus_lost", "client_ts": before}]},
    )
    assert late.status_code == 409
