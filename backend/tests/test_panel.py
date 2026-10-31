"""Stage 4: model components panel, teacher's grade, results, mastery.

ФТ-03, ФТ-07, ФТ-09, ФТ-14, ФТ-36, ФТ-41, ФТ-42, ФТ-43.
"""

import re
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models import AiGrade, ComponentEntry, Submission, Topic
from app.services import ai_grading
from app.services.results import bespalko
from tests.conftest import School, login
from tests.llm_helpers import RecordingProvider
from tests.workspace_helpers import FEATURES, SOLUTION, _open, _submit

LEVELS_OK = {
    c: "high"
    for c in (
        "understanding",
        "algorithm",
        "correctness",
        "code_quality",
        "debugging",
        "explanation",
    )
}


def _add_topic(client: TestClient, ws: dict[str, Any], code: str = "1.3") -> dict[str, Any]:
    topic: dict[str, Any] = client.post(
        f"/api/courses/{ws['course']['id']}/topics",
        headers=ws["teacher"],
        json={
            "code": code,
            "title": "Бүтін сандар",
            "lessons": [{"title": "Целые числа", "url": "https://stepik.org/lesson/13021/step/1"}],
            "knowledge_components": [
                {"code": "int.io", "name": "Енгізу-шығару"},
                {"code": "int.arith", "name": "Бүтін арифметика"},
            ],
        },
    ).json()
    return topic


def _entries(client: TestClient, ws: dict[str, Any], component: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = client.get(
        f"/api/courses/{ws['course']['id']}/components/{component}/entries", headers=ws["teacher"]
    ).json()
    return result


def _generate(client: TestClient, ws: dict[str, Any], component: int) -> dict[str, Any]:
    result: dict[str, Any] = client.post(
        f"/api/courses/{ws['course']['id']}/components/{component}/generate", headers=ws["teacher"]
    ).json()
    return result


# ФТ-07, ФТ-09, ФТ-14 ---------------------------------------------------------------


def test_ft09_goals_and_outcomes_are_suggested_per_topic(
    client: TestClient, ws: dict[str, Any]
) -> None:
    _add_topic(client, ws)
    assert _generate(client, ws, 1)["generated"] == 1
    [entry] = _entries(client, ws, 1)
    assert entry["source"] == "auto" and entry["key"] == "goals"
    assert entry["value"]["knowledge_components"] == ["Енгізу-шығару", "Бүтін арифметика"]
    assert len(entry["value"]["learning_outcomes"]) == 2
    assert entry["value"]["lessons"][0]["url"].startswith("https://stepik.org/lesson/13021")


def test_ft14_rubric_is_adapted_per_task(client: TestClient, ws: dict[str, Any]) -> None:
    _generate(client, ws, 2)
    [entry] = _entries(client, ws, 2)
    assert entry["subject_type"] == "task" and entry["subject_id"] == ws["task"]["id"]
    assert set(entry["value"]) == set(LEVELS_OK)
    assert all(set(v) == {"low", "mid", "high"} for v in entry["value"].values())


def test_ft07_teacher_value_survives_regeneration(
    client: TestClient, ws: dict[str, Any], db: Session
) -> None:
    topic = _add_topic(client, ws)
    _generate(client, ws, 1)
    [entry] = _entries(client, ws, 1)
    mine = {**entry["value"], "goal": "Менің мақсатым"}
    edited = client.put(
        f"/api/entries/{entry['id']}", headers=ws["teacher"], json={"value": mine}
    ).json()
    assert edited["source"] == "auto_edited"

    db_topic = db.get(Topic, topic["id"])
    assert db_topic is not None
    db_topic.title = "Бүтін сандар мен арифметика"  # the automatic value will differ now
    db.flush()
    _generate(client, ws, 1)
    [after] = _entries(client, ws, 1)
    assert after["value"]["goal"] == "Менің мақсатым"
    assert after["source"] == "auto_edited"
    assert after["suggestion"]["goal"].startswith("«Бүтін сандар мен арифметика»")
    # The automatic value and the teacher's value are stored apart.
    assert after["auto_value"] == after["suggestion"] and after["auto_value"] != after["value"]

    rejected = client.post(
        f"/api/entries/{entry['id']}/suggestion/reject", headers=ws["teacher"]
    ).json()
    assert rejected["suggestion"] is None and rejected["value"]["goal"] == "Менің мақсатым"
    _generate(client, ws, 1)
    accepted = client.post(
        f"/api/entries/{entry['id']}/suggestion/accept", headers=ws["teacher"]
    ).json()
    assert accepted["source"] == "auto" and accepted["value"]["goal"].startswith(
        "«Бүтін сандар мен"
    )


def test_ft07_any_version_can_be_restored(client: TestClient, ws: dict[str, Any]) -> None:
    _add_topic(client, ws)
    _generate(client, ws, 1)
    [entry] = _entries(client, ws, 1)
    url = f"/api/entries/{entry['id']}"
    original = entry["value"]
    for goal in ("Бірінші", "Екінші"):
        client.put(url, headers=ws["teacher"], json={"value": {**original, "goal": goal}})
    versions = client.get(f"{url}/versions", headers=ws["teacher"]).json()
    assert [v["value"]["goal"] for v in versions][1:] == ["Бірінші", "Екінші"]
    assert versions[1]["author_id"] is not None and versions[0]["source"] == "auto"
    for number, expected in ((1, original["goal"]), (2, "Бірінші"), (3, "Екінші")):
        restored = client.post(
            f"{url}/revert", headers=ws["teacher"], json={"version": number}
        ).json()
        assert restored["value"]["goal"] == expected
    assert restored["versions"] == 6
    assert (
        client.post(f"{url}/revert", headers=ws["teacher"], json={"version": 99}).status_code == 422
    )


def test_ft07_automatic_filling_can_be_switched_off(
    client: TestClient, ws: dict[str, Any], db: Session
) -> None:
    course = ws["course"]["id"]
    for component in (1, 4, 5):
        client.put(
            f"/api/courses/{course}/components/{component}/settings",
            headers=ws["teacher"],
            json={"auto_enabled": False},
        )
    _add_topic(client, ws)
    assert _generate(client, ws, 1) == {"generated": 0, "auto_enabled": False}
    _submit(client, ws, _open(client, ws))
    assert db.scalars(select(ComponentEntry)).all() == []
    overview = client.get(f"/api/courses/{course}/components", headers=ws["teacher"]).json()
    assert [c["auto_enabled"] for c in overview] == [False, True, True, False, False]


def test_ft07_panel_is_for_the_course_teachers_only(
    client: TestClient, ws: dict[str, Any], school: School
) -> None:
    course = ws["course"]["id"]
    other = login(client, school["teacher_b"].email)
    for headers in (ws["student"], other):
        assert client.get(f"/api/courses/{course}/components", headers=headers).status_code == 403
    _add_topic(client, ws)
    _generate(client, ws, 1)
    [entry] = _entries(client, ws, 1)
    assert (
        client.put(f"/api/entries/{entry['id']}", headers=other, json={"value": {}}).status_code
        == 403
    )


def test_ft07_submission_fills_signals_and_interpretation(
    client: TestClient, ws: dict[str, Any]
) -> None:
    result = _submit(client, ws, _open(client, ws))
    [signals] = _entries(client, ws, 4)
    assert signals["subject_id"] == result["id"] and signals["value"]["tests"]["verdict"] == "OK"
    [interpretation] = _entries(client, ws, 5)
    criteria = interpretation["value"]["criteria"]
    assert len(criteria) == 6 and all(c["interpretation"] for c in criteria)
    edit = client.put(f"/api/entries/{signals['id']}", headers=ws["teacher"], json={"value": {}})
    assert edit.status_code == 422


# ФТ-36 ------------------------------------------------------------------------------


def test_ft36_teacher_chooses_data_for_the_analysis(
    client: TestClient, ws: dict[str, Any], db: Session
) -> None:
    url = f"/api/assessments/{ws['assessment']['id']}/analysis"
    client.put(url, headers=ws["teacher"], json={"excluded": ["genai_log", "process_metrics"]})
    assert client.get(url, headers=ws["student"]).status_code == 403
    result = _submit(client, ws, _open(client, ws))
    provider = RecordingProvider()
    submission = db.get(Submission, result["id"])
    assert submission is not None
    ai_grading.grade(db, provider, submission)
    blocks = provider.requests[-1].data_blocks
    assert blocks["genai_log"].startswith("(оқытушы бұл деректі")
    assert blocks["process_metrics"].startswith("(оқытушы бұл деректі")
    assert blocks["student_code"].strip()


def test_ft36_teacher_adds_own_observation(
    client: TestClient, ws: dict[str, Any], school: School
) -> None:
    result = _submit(client, ws, _open(client, ws))
    url = f"/api/submissions/{result['id']}/observations"
    added = client.post(
        url,
        headers=ws["teacher"],
        json={
            "kind": "oral_defense",
            "text": "Ауызша қорғауда циклдің шартын түсіндірді.",
            "criterion": "explanation",
            "level": "high",
        },
    )
    assert added.status_code == 201
    comment = client.post(
        url,
        headers=ws["teacher"],
        json={
            "kind": "signal_comment",
            "signal": "process.large_pastes",
            "text": "Кірістіру өз кодынан.",
        },
    )
    assert comment.status_code == 201
    assert [o["kind"] for o in client.get(url, headers=ws["teacher"]).json()] == [
        "oral_defense",
        "signal_comment",
    ]
    assert client.get(url, headers=ws["student"]).status_code == 403
    assert (
        client.post(
            url,
            headers=login(client, school["teacher_b"].email),
            json={"kind": "note", "text": "x"},
        ).status_code
        == 403
    )


# ФТ-03, ФТ-41, ФТ-42 ---------------------------------------------------------------


def _ai_levels(db: Session, submission_id: int) -> dict[str, str]:
    grade = db.scalar(select(AiGrade).where(AiGrade.submission_id == submission_id))
    assert grade is not None
    return {c["code"]: c["level"] for c in grade.criteria}


def _confirm(client: TestClient, ws: dict[str, Any], submission_id: int, **body: Any) -> Any:
    payload = {
        "levels": LEVELS_OK,
        "components": {"F": 100, "E": 60, "A": 50},
        "feedback": "fake feedback",
        **body,
    }
    return client.post(
        f"/api/submissions/{submission_id}/teacher-grade", headers=ws["teacher"], json=payload
    )


def test_ft03_teacher_confirms_or_corrects_and_both_grades_stay(
    client: TestClient, ws: dict[str, Any], db: Session
) -> None:
    result = _submit(client, ws, _open(client, ws))
    ai_before = _ai_levels(db, result["id"])
    assert ai_before == LEVELS_OK  # the fake grader: all tests passed
    agreed = _confirm(client, ws, result["id"]).json()
    assert agreed["agrees_with_ai"] is True and agreed["feedback_source"] == "ai"
    assert agreed["score"] == round(0.3626 * 100 + 0.3641 * 60 + 0.2733 * 50, 2)

    lower = {**LEVELS_OK, "explanation": "mid"}
    no_reason = _confirm(client, ws, result["id"], levels=lower)
    assert no_reason.status_code == 422
    corrected = _confirm(
        client,
        ws,
        result["id"],
        levels=lower,
        feedback="Түсіндірмені толықтырыңыз.",
        reason="Ауызша қорғауда негіздеме әлсіз болды.",
    ).json()
    assert corrected["agrees_with_ai"] is False and corrected["feedback_source"] == "ai_edited"
    assert _ai_levels(db, result["id"]) == ai_before  # the AI grade is not overwritten
    current = client.get(
        f"/api/submissions/{result['id']}/teacher-grade", headers=ws["teacher"]
    ).json()
    assert current["id"] == corrected["id"]
    [interpretation] = _entries(client, ws, 5)
    assert interpretation["source"] == "auto_edited"
    assert interpretation["value"]["feedback"] == "Түсіндірмені толықтырыңыз."


def _fill_path(path: str, ids: dict[str, int]) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: str(ids.get(m.group(1), 1)), path)


def test_sec14_student_sees_no_ai_grade_before_confirmation(
    client: TestClient, ws: dict[str, Any], db: Session
) -> None:
    sid = _open(client, ws)
    result = _submit(client, ws, sid)
    grade = db.scalar(select(AiGrade).where(AiGrade.submission_id == result["id"]))
    assert grade is not None and grade.feedback == "fake feedback"
    ids = {
        "submission_id": result["id"],
        "task_id": ws["task"]["id"],
        "assessment_id": ws["assessment"]["id"],
        "course_id": ws["course"]["id"],
        "session_id": 0,
        "entry_id": 1,
        "chunk_id": 1,
        "material_id": 1,
    }
    markers = ("fake feedback", "fake interpretation", "fake next step", str(grade.score))
    paths = [p for p, ops in app.openapi()["paths"].items() if "get" in ops]
    for path in paths:
        for query in ("", f"?course_id={ws['course']['id']}&task_id={ws['task']['id']}"):
            text = client.get(
                _fill_path(path, ids).replace("/0/", f"/{sid}/") + query, headers=ws["student"]
            ).text
            for marker in markers:
                assert marker not in text, f"{path} shows the AI grade before confirmation"
    assert client.get("/api/my/results", headers=ws["student"]).json() == []


def test_ft41_ft42_student_gets_confirmed_levels_and_book_references(
    client: TestClient, ws: dict[str, Any], db: Session
) -> None:
    result = _submit(client, ws, _open(client, ws))
    grade = db.scalar(select(AiGrade).where(AiGrade.submission_id == result["id"]))
    assert grade is not None
    grade.criteria = [
        {
            **c,
            "evidence": [
                *c["evidence"],
                {"type": "book", "ref": "C++ негіздері, 4.2-бөлім, 67-бет", "quote": "while"},
            ],
        }
        for c in grade.criteria
    ]
    db.flush()
    _confirm(client, ws, result["id"], next_step="II деңгейдегі тапсырма")
    [mine] = client.get("/api/my/results", headers=ws["student"]).json()
    assert [c["level"] for c in mine["criteria"]] == ["high"] * 6
    assert mine["criteria"][0]["name"] and mine["criteria"][0]["interpretation"]
    assert mine["feedback_source"] == "ai"  # shown as «AI · алдын ала» in the interface
    assert mine["book_refs"] == ["C++ негіздері, 4.2-бөлім, 67-бет"]
    assert mine["next_step"] == "II деңгейдегі тапсырма"


# ФТ-43 ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "p", "k", "mastered"),
    [
        (7, 10, 0.7, True),
        (6, 10, 0.6, False),
        (69, 100, 0.69, False),
        (10, 10, 1.0, True),
        (0, 3, 0.0, False),
        (0, 0, None, False),
        (2, 3, 0.6667, False),
        (3, 4, 0.75, True),
    ],
)
def test_ft43_bespalko_boundaries(a: int, p: int, k: float | None, mastered: bool) -> None:
    assert bespalko(a, p, 0.7) == (k, mastered)


def test_ft43_mastery_needs_tests_passed_and_no_low_criterion(
    client: TestClient, ws: dict[str, Any], school: School
) -> None:
    second = client.post(
        "/api/tasks",
        headers=ws["teacher"],
        json={
            "course_id": ws["course"]["id"],
            "title": "Second",
            "statement_md": "x",
            "reference_solution": SOLUTION,
            "tests": [{"input": "4\n", "expected_output": "EVEN\n", "is_hidden": False}],
        },
    ).json()
    client.put(
        f"/api/tasks/{second['id']}/level", headers=ws["teacher"], json={"features": FEATURES}
    )
    client.post(f"/api/tasks/{second['id']}/approve", headers=ws["teacher"])
    a = ws["assessment"]
    client.put(
        f"/api/assessments/{a['id']}",
        headers=ws["teacher"],
        json={
            "title": a["title"],
            "starts_at": a["starts_at"],
            "ends_at": a["ends_at"],
            "task_ids": [ws["task"]["id"], second["id"]],
        },
    )

    first = _submit(client, ws, _open(client, ws))
    _confirm(client, ws, first["id"])
    url = f"/api/my/mastery?course_id={ws['course']['id']}"
    [row] = client.get(url, headers=ws["student"]).json()
    assert (row["level"], row["a"], row["p"], row["k"], row["mastered"]) == ("I", 1, 2, 0.5, False)

    other = client.post(
        "/api/sessions",
        headers=ws["student"],
        json={"task_id": second["id"], "assessment_id": a["id"]},
    ).json()
    with_low = _submit(client, ws, other["session_id"])
    _confirm(
        client,
        ws,
        with_low["id"],
        levels={**LEVELS_OK, "code_quality": "low"},
        reason="Код сапасы төмен",
    )
    assert client.get(url, headers=ws["student"]).json()[0]["a"] == 1
    _confirm(client, ws, with_low["id"], levels=LEVELS_OK)
    row = client.get(url, headers=ws["student"]).json()[0]
    assert (row["a"], row["k"], row["mastered"]) == (2, 1.0, True)

    teacher_view = client.get(
        f"/api/courses/{ws['course']['id']}/mastery", headers=ws["teacher"]
    ).json()
    assert {s["user_id"]: s["rows"][0]["mastered"] for s in teacher_view}[school["student_a"].id]
    assert client.get(url, headers=login(client, school["student_b"].email)).status_code == 403


def test_ft43_threshold_is_a_setting(
    client: TestClient, ws: dict[str, Any], make_user: Any
) -> None:
    from app.core.roles import Role

    make_user("root@example.com", Role.ADMIN)
    admin = login(client, "root@example.com")
    body = {"bespalko_threshold": 0.5, "no_low_criterion": True}
    assert client.put("/api/settings/mastery", headers=ws["teacher"], json=body).status_code == 403
    assert client.put("/api/settings/mastery", headers=admin, json=body).status_code == 200
    first = _submit(client, ws, _open(client, ws))
    _confirm(client, ws, first["id"])
    row = client.get(
        f"/api/my/mastery?course_id={ws['course']['id']}", headers=ws["student"]
    ).json()[0]
    assert row["mastered"] is True
