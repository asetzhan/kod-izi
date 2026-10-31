"""ФТ-19: task level from four features (spec 5.2), confirmed by the teacher."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import LevelStatus, TaskLevel
from app.core.roles import Role
from app.models import CourseTeacher, Task
from app.models.task import FEATURE_CODES
from app.services.levels import RuleError, default_rule_data, get_rule, parse_rule
from tests.conftest import MakeUser, login


def _scores(total: int) -> dict[str, int]:
    """Spread a total over the four features, at most 2 each."""
    scores = {}
    for code in FEATURE_CODES:
        scores[code] = min(2, total)
        total -= scores[code]
    return scores


@pytest.mark.parametrize(
    ("total", "level"),
    [(0, "I"), (2, "I"), (3, "II"), (4, "II"), (5, "III"), (6, "III"), (7, "IV"), (8, "IV")],
)
def test_ft19_default_rule_boundaries(total: int, level: str) -> None:
    rule = parse_rule(default_rule_data())
    assert rule.level_for(_scores(total)) == TaskLevel(level)


def test_ft19_default_rule_comes_from_seed() -> None:
    seed = json.loads((get_settings().seed_dir / "task_levels.json").read_text(encoding="utf-8"))
    assert parse_rule(default_rule_data()).to_json()["sum_to_level"] == seed["sum_to_level"]


@pytest.mark.parametrize(
    "ranges",
    [
        [(0, 2, "I"), (4, 8, "II")],  # gap
        [(0, 3, "I"), (3, 8, "II")],  # overlap
        [(0, 4, "II"), (5, 8, "I")],  # levels go down
        [(0, 2, "I"), (3, 7, "II")],  # does not reach 8
        [(1, 8, "I")],  # does not start at 0
    ],
)
def test_ft19_invalid_rules_are_rejected(ranges: list[tuple[int, int, str]]) -> None:
    with pytest.raises(RuleError):
        parse_rule({"sum_to_level": [{"min": a, "max": b, "level": lv} for a, b, lv in ranges]})


def test_ft19_scores_out_of_range_are_rejected() -> None:
    rule = parse_rule(default_rule_data())
    with pytest.raises(RuleError):
        rule.level_for({**_scores(0), "edge_cases": 3})


def test_ft19_admin_changes_rule(client: TestClient, db: Session, make_user: MakeUser) -> None:
    make_user("admin@example.com", Role.ADMIN)
    make_user("teacher@example.com", Role.TEACHER)
    new_rule = {
        "sum_to_level": [
            {"min": 0, "max": 3, "level": "I"},
            {"min": 4, "max": 5, "level": "II"},
            {"min": 6, "max": 8, "level": "III"},
        ]
    }
    teacher = login(client, "teacher@example.com")
    assert (
        client.put("/api/settings/task-level-rule", json=new_rule, headers=teacher).status_code
        == 403
    )
    admin = login(client, "admin@example.com")
    response = client.put("/api/settings/task-level-rule", json=new_rule, headers=admin)
    assert response.status_code == 200
    assert get_rule(db).level_for(_scores(3)) == TaskLevel.I
    shown = client.get("/api/settings/task-level-rule", headers=teacher).json()
    assert shown["sum_to_level"] == new_rule["sum_to_level"]
    assert len(shown["features"]) == 4
    bad = {"sum_to_level": [{"min": 0, "max": 5, "level": "I"}]}
    assert client.put("/api/settings/task-level-rule", json=bad, headers=admin).status_code == 422


def _teacher_with_seed(db: Session, make_user: MakeUser) -> Task:
    teacher = make_user("teacher@example.com", Role.TEACHER)
    task = db.scalar(select(Task).where(Task.external_key == "EXP-II-5"))
    assert task is not None
    db.add(CourseTeacher(course_id=task.course_id, user_id=teacher.id))
    db.flush()
    return task


@pytest.mark.usefixtures("seeded")
def test_ft19_teacher_confirms_or_changes_level(
    client: TestClient, db: Session, make_user: MakeUser
) -> None:
    task = _teacher_with_seed(db, make_user)
    assert task.level_status == LevelStatus.SUGGESTED.value
    headers = login(client, "teacher@example.com")
    body = {"features": _scores(6), "rationale": "two-pointer proof required"}
    response = client.put(f"/api/tasks/{task.id}/level", json=body, headers=headers)
    assert response.status_code == 200
    assert response.json()["level"] == "III"
    assert response.json()["level_status"] == "confirmed"
    override = {"features": _scores(6), "level": "II"}
    response = client.put(f"/api/tasks/{task.id}/level", json=override, headers=headers)
    assert response.json()["level"] == "II"


@pytest.mark.usefixtures("seeded")
def test_ft19_llm_suggestion_never_overwrites_confirmed_level(
    client: TestClient, db: Session, make_user: MakeUser
) -> None:
    task = _teacher_with_seed(db, make_user)
    headers = login(client, "teacher@example.com")
    suggestion = client.post(f"/api/tasks/{task.id}/level-suggestion", headers=headers).json()
    # The fake provider answers with the smallest valid scores.
    assert suggestion == {
        "features": dict.fromkeys(FEATURE_CODES, 0),
        "level": "I",
        "rationale": "fake",
        "saved": True,
    }
    client.put(f"/api/tasks/{task.id}/level", json={"features": _scores(4)}, headers=headers)
    again = client.post(f"/api/tasks/{task.id}/level-suggestion", headers=headers).json()
    assert again["saved"] is False
    db.refresh(task)
    assert task.level == "II"
    assert task.level_status == LevelStatus.CONFIRMED.value


@pytest.mark.usefixtures("seeded")
def test_ft19_student_cannot_change_level(
    client: TestClient, db: Session, make_user: MakeUser
) -> None:
    task = _teacher_with_seed(db, make_user)
    make_user("s@example.com", Role.STUDENT)
    headers = login(client, "s@example.com")
    response = client.put(
        f"/api/tasks/{task.id}/level", json={"features": _scores(0)}, headers=headers
    )
    assert response.status_code == 403
