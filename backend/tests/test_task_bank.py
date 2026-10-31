"""ФТ-18 task bank, ФТ-02 assessments; hidden tests never reach students (spec 14.1)."""

import re
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import School, login

HIDDEN = "HIDDEN-TEST-MARKER-7f3a"
SECRET_ANSWER = "HIDDEN-ANSWER-MARKER-9c1e"
REFERENCE = "REFERENCE-SOLUTION-MARKER-55d2"

FEATURES = {"knowledge_actions": 0, "algorithm_freedom": 0, "edge_cases": 1, "justification": 0}


def _task_body(course_id: int) -> dict[str, Any]:
    return {
        "course_id": course_id,
        "title": "Even or odd",
        "statement_md": "# Even or odd\n\nPrint EVEN or ODD.",
        "input_format": "One integer.",
        "output_format": "EVEN or ODD.",
        "reference_solution": f"// {REFERENCE}\nint main() {{}}",
        "tests": [
            {"input": "4\n", "expected_output": "EVEN\n", "is_hidden": False},
            {"input": f"{HIDDEN}\n", "expected_output": f"{SECRET_ANSWER}\n", "is_hidden": True},
        ],
    }


def _window(start_offset_minutes: int) -> dict[str, str]:
    start = datetime.now(UTC) + timedelta(minutes=start_offset_minutes)
    return {
        "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(hours=2)).isoformat(),
    }


@pytest.fixture
def setup(client: TestClient, school: School) -> dict[str, Any]:
    """Teacher A: course for group A, one approved task, a started and a future assessment."""
    teacher = login(client, school["teacher_a"].email)
    course = client.post("/api/courses", headers=teacher, json={"title": "C++"}).json()
    client.post(
        f"/api/courses/{course['id']}/groups", headers=teacher, json={"id": school["group_a"].id}
    )
    task = client.post("/api/tasks", headers=teacher, json=_task_body(course["id"])).json()
    client.put(f"/api/tasks/{task['id']}/level", headers=teacher, json={"features": FEATURES})
    approved = client.post(f"/api/tasks/{task['id']}/approve", headers=teacher)
    assert approved.status_code == 200, approved.text
    started = client.post(
        "/api/assessments",
        headers=teacher,
        json={
            "course_id": course["id"],
            "title": "1-БЖ",
            "genai_mode": "hints_only",
            "task_ids": [task["id"]],
            **_window(-10),
        },
    ).json()
    future = client.post(
        "/api/assessments",
        headers=teacher,
        json={"course_id": course["id"], "title": "2-БЖ", "task_ids": [task["id"]], **_window(60)},
    ).json()
    return {
        "teacher": teacher,
        "course": course,
        "task": task,
        "started": started,
        "future": future,
    }


def test_ft18_teacher_sees_full_task(client: TestClient, setup: dict[str, Any]) -> None:
    body = client.get(f"/api/tasks/{setup['task']['id']}", headers=setup["teacher"]).json()
    assert body["status"] == "approved"
    assert body["level"] == "I"
    assert [t["is_hidden"] for t in body["tests"]] == [False, True]
    assert REFERENCE in body["reference_solution"]


def test_ft18_task_bank_filters(client: TestClient, setup: dict[str, Any]) -> None:
    course_id = setup["course"]["id"]
    found = client.get(
        f"/api/tasks?course_id={course_id}&level=I&status=approved", headers=setup["teacher"]
    ).json()
    assert [t["id"] for t in found] == [setup["task"]["id"]]
    none = client.get(f"/api/tasks?course_id={course_id}&level=III", headers=setup["teacher"])
    assert none.json() == []


def test_ft18_student_sees_only_public_examples(
    client: TestClient, school: School, setup: dict[str, Any]
) -> None:
    student = login(client, school["student_a"].email)
    body = client.get(f"/api/tasks/{setup['task']['id']}", headers=student).json()
    assert body["examples"] == [{"position": 1, "input": "4\n", "expected_output": "EVEN\n"}]
    assert "tests" not in body and "reference_solution" not in body


def _fill_path(path: str, ids: dict[str, int]) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: str(ids.get(m.group(1), 1)), path)


def test_sec14_hidden_tests_are_not_reachable_by_students_through_any_api(
    client: TestClient, school: School, setup: dict[str, Any]
) -> None:
    ids = {
        "task_id": setup["task"]["id"],
        "course_id": setup["course"]["id"],
        "assessment_id": setup["started"]["id"],
        "group_id": school["group_a"].id,
        "user_id": school["student_a"].id,
        "topic_id": 1,
    }
    student = login(client, school["student_a"].email)
    checked = 0
    # Every GET endpoint the API publishes, read from the OpenAPI schema.
    paths = [p for p, ops in app.openapi()["paths"].items() if "get" in ops]
    for path in paths:
        for query in ("", f"?course_id={ids['course_id']}"):
            response = client.get(_fill_path(path, ids) + query, headers=student)
            for marker in (HIDDEN, SECRET_ANSWER, REFERENCE):
                assert marker not in response.text, f"{path} leaks {marker}"
            checked += 1
    assert checked > 20


def test_sec14_student_cannot_open_draft_task_or_future_assessment(
    client: TestClient, school: School, setup: dict[str, Any]
) -> None:
    draft = client.post(
        "/api/tasks", headers=setup["teacher"], json=_task_body(setup["course"]["id"])
    ).json()
    student = login(client, school["student_a"].email)
    assert client.get(f"/api/tasks/{draft['id']}", headers=student).status_code == 403
    future = client.get(f"/api/assessments/{setup['future']['id']}", headers=student)
    assert future.status_code == 403
    listed = client.get("/api/assessments", headers=student).json()
    assert {a["title"] for a in listed} == {"1-БЖ", "2-БЖ"}
    assert all(a["task_ids"] == [] for a in listed)


def test_sec14_student_of_other_group_cannot_see_task(
    client: TestClient, school: School, setup: dict[str, Any]
) -> None:
    student_b = login(client, school["student_b"].email)
    assert client.get(f"/api/tasks/{setup['task']['id']}", headers=student_b).status_code == 403
    started = client.get(f"/api/assessments/{setup['started']['id']}", headers=student_b)
    assert started.status_code == 403


def test_ft18_task_cannot_be_approved_until_ready(
    client: TestClient, setup: dict[str, Any]
) -> None:
    body = _task_body(setup["course"]["id"])
    body["reference_solution"] = ""
    task = client.post("/api/tasks", headers=setup["teacher"], json=body).json()
    response = client.post(f"/api/tasks/{task['id']}/approve", headers=setup["teacher"])
    assert response.status_code == 422
    assert "level_not_confirmed" in response.json()["detail"]["message"]
    assert "no_reference_solution" in response.json()["detail"]["message"]


def test_ft02_teacher_creates_assessment_with_genai_mode(
    client: TestClient, school: School, setup: dict[str, Any]
) -> None:
    started = setup["started"]
    assert started["genai_mode"] == "hints_only"
    assert started["task_ids"] == [setup["task"]["id"]]
    student = login(client, school["student_a"].email)
    view = client.get(f"/api/assessments/{started['id']}", headers=student).json()
    assert view["genai_mode"] == "hints_only"
    assert [t["id"] for t in view["tasks"]] == [setup["task"]["id"]]


def test_ft02_assessment_accepts_only_approved_tasks_of_its_course(
    client: TestClient, setup: dict[str, Any]
) -> None:
    draft = client.post(
        "/api/tasks", headers=setup["teacher"], json=_task_body(setup["course"]["id"])
    ).json()
    response = client.post(
        "/api/assessments",
        headers=setup["teacher"],
        json={
            "course_id": setup["course"]["id"],
            "title": "X",
            "task_ids": [draft["id"]],
            **_window(0),
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "task_not_approved"


def test_ft02_assessment_window_is_validated(client: TestClient, setup: dict[str, Any]) -> None:
    start = datetime.now(UTC)
    response = client.post(
        "/api/assessments",
        headers=setup["teacher"],
        json={
            "course_id": setup["course"]["id"],
            "title": "X",
            "starts_at": start.isoformat(),
            "ends_at": (start - timedelta(hours=1)).isoformat(),
        },
    )
    assert response.status_code == 422


def test_ft02_other_teacher_cannot_edit_assessment(
    client: TestClient, school: School, setup: dict[str, Any]
) -> None:
    other = login(client, school["teacher_b"].email)
    response = client.put(
        f"/api/assessments/{setup['started']['id']}",
        headers=other,
        json={"title": "Changed", **_window(0)},
    )
    assert response.status_code == 403


def test_sec14_teacher_of_other_course_cannot_change_tasks(
    client: TestClient, school: School, setup: dict[str, Any]
) -> None:
    other = login(client, school["teacher_b"].email)
    task_id = setup["task"]["id"]
    body = _task_body(setup["course"]["id"])
    del body["course_id"]
    attempts = [
        client.put(f"/api/tasks/{task_id}", headers=other, json=body),
        client.put(f"/api/tasks/{task_id}/level", headers=other, json={"features": FEATURES}),
        client.post(f"/api/tasks/{task_id}/approve", headers=other),
        client.post(f"/api/tasks/{task_id}/level-suggestion", headers=other),
        client.post(
            f"/api/courses/{setup['course']['id']}/tasks/import",
            headers=other,
            files={"file": ("x.zip", b"PK", "application/zip")},
        ),
        client.post("/api/tasks", headers=other, json=_task_body(setup["course"]["id"])),
    ]
    assert [r.status_code for r in attempts] == [403] * len(attempts)


def test_sec14_teacher_cannot_take_student_of_another_group(
    client: TestClient, school: School
) -> None:
    headers = login(client, school["teacher_a"].email)
    response = client.post(
        f"/api/groups/{school['group_a'].id}/students",
        headers=headers,
        json={"email": school["student_b"].email},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "student_not_found"
    assert client.get(f"/api/users/{school['student_b'].id}", headers=headers).status_code == 403
