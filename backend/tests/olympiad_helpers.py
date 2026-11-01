"""Shared olympiad setup (stage 6a, 7a): a part 2 course with tagged, rated problems."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import AppSetting
from app.services.olympiad import OLYMPIAD_KEY
from tests.conftest import School, login
from tests.fake_judge import FakeJudge
from tests.workspace_helpers import SOLUTION

III = {"knowledge_actions": 2, "algorithm_freedom": 2, "edge_cases": 1, "justification": 1}


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
