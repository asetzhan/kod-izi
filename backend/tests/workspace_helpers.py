"""Shared stage 2 setup: a course with an approved task and assessments, inline grading."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.jobs import get_enqueue
from app.judge import get_judge
from app.llm.fake import FakeLLMProvider
from app.main import app
from app.models import Submission
from app.services.pipeline import run_pipeline
from app.services.static_analysis import analyse
from tests.conftest import School, login
from tests.fake_judge import FakeJudge

FEATURES = {"knowledge_actions": 0, "algorithm_freedom": 0, "edge_cases": 1, "justification": 0}
SOLUTION = "#include <iostream>\nint main() { long long n; std::cin >> n; }\n"


def fast_analysis(code: str, language: str) -> dict[str, Any]:
    """Metrics only: clang-tidy and cppcheck are tested in test_static_analysis.py."""
    return analyse(code, language, run_tools=False)


@pytest.fixture
def judge(db: Session) -> Iterator[FakeJudge]:
    fake = FakeJudge({"4\n": "EVEN\n", "7\n": "ODD\n", "-3\n": "ODD\n"})

    def grade_inline(submission_id: int) -> None:
        submission = db.get(Submission, submission_id)
        assert submission is not None
        run_pipeline(db, fake, FakeLLMProvider(), submission, analyser=fast_analysis)
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
