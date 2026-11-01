"""ФТ-01, ФТ-08, ФТ-10, ФТ-12: courses, topics, Stepik lessons, knowledge components."""

import re
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.roles import Role
from app.models import Course, CourseTeacher, ExternalLesson, KnowledgeComponent, Task, Topic
from app.services.seed_content import SeedReport, seed_all
from tests.conftest import PASSWORD, MakeUser, School, login

SPEC_DIR = get_settings().seed_dir.parent / "docs" / "spec"
STEPIK_LINK = re.compile(r"\[([^\]]+)\]\((https://stepik\.org/lesson/\d+/step/1)\)")


def test_ft12_every_stepik_lesson_of_spec_parts_3_and_4_is_in_the_system(
    db: Session, seeded: SeedReport
) -> None:
    expected = {
        url
        for name in ("03-part1-cpp-basics.md", "04-part2-olympiad.md")
        for _, url in STEPIK_LINK.findall((SPEC_DIR / name).read_text(encoding="utf-8"))
    }
    stored = set(db.scalars(select(ExternalLesson.url)))
    assert len(expected) == 12 + 20 + 11
    assert expected == stored


def test_ft12_lesson_links_match_their_stepik_ids(db: Session, seeded: SeedReport) -> None:
    for lesson in db.scalars(select(ExternalLesson)):
        assert lesson.url == f"https://stepik.org/lesson/{lesson.stepik_lesson_id}/step/1"


def test_ft08_part1_course_has_twelve_topics_with_components(
    db: Session, seeded: SeedReport
) -> None:
    course = db.scalar(select(Course).where(Course.stepik_course_id == 363))
    assert course is not None
    assert [t.code for t in course.topics] == [f"1.{i}" for i in range(1, 13)]
    assessed = [t for t in course.topics if t.code not in ("1.1", "1.2")]
    assert all(t.knowledge_components for t in assessed)


def test_ft08_seed_is_idempotent(db: Session, seeded: SeedReport) -> None:
    lessons_before = db.scalar(select(ExternalLesson.id).order_by(ExternalLesson.id.desc()))
    again = seed_all(db, get_settings().seed_dir)
    db.flush()
    assert again.tasks_created == 0 and again.tasks_skipped == 17  # 9 part 1 + 8 olympiad
    assert db.query(Course).count() == 3
    assert db.query(KnowledgeComponent).count() == seeded.knowledge_components
    assert lessons_before is not None


def test_ft01_teacher_creates_course_and_attaches_own_group(
    client: TestClient, school: School
) -> None:
    headers = login(client, school["teacher_a"].email)
    course = client.post(
        "/api/courses", headers=headers, json={"title": "C++ (IT-21)", "part": "part1"}
    ).json()
    own = client.post(
        f"/api/courses/{course['id']}/groups", headers=headers, json={"id": school["group_a"].id}
    )
    assert own.status_code == 200
    other = client.post(
        f"/api/courses/{course['id']}/groups", headers=headers, json={"id": school["group_b"].id}
    )
    assert other.status_code == 403
    groups = client.get(f"/api/courses/{course['id']}/groups", headers=headers).json()
    assert [g["id"] for g in groups] == [school["group_a"].id]


def test_ft01_teacher_adds_student_to_own_group(
    client: TestClient, school: School, make_user: MakeUser
) -> None:
    make_user("new.student@example.com", Role.STUDENT)
    headers = login(client, school["teacher_a"].email)
    group_id = school["group_a"].id
    added = client.post(
        f"/api/groups/{group_id}/students",
        headers=headers,
        json={"email": "New.Student@example.com"},
    )
    assert added.status_code == 200
    assert "New.Student" in {s["full_name"] for s in added.json()["students"]}
    foreign = client.post(
        f"/api/groups/{school['group_b'].id}/students",
        headers=headers,
        json={"email": "new.student@example.com"},
    )
    assert foreign.status_code == 403
    not_student = client.post(
        f"/api/groups/{group_id}/students", headers=headers, json={"email": school["coach"].email}
    )
    assert not_student.status_code == 400


def test_ft01_student_sees_only_courses_of_own_group(client: TestClient, school: School) -> None:
    teacher = login(client, school["teacher_a"].email)
    course = client.post("/api/courses", headers=teacher, json={"title": "Mine"}).json()
    client.post(
        f"/api/courses/{course['id']}/groups", headers=teacher, json={"id": school["group_a"].id}
    )
    other = client.post("/api/courses", headers=teacher, json={"title": "Other"}).json()

    student_a = login(client, school["student_a"].email)
    assert [c["id"] for c in client.get("/api/courses", headers=student_a).json()] == [course["id"]]
    assert client.get(f"/api/courses/{other['id']}", headers=student_a).status_code == 403
    student_b = login(client, school["student_b"].email)
    assert client.get(f"/api/courses/{course['id']}", headers=student_b).status_code == 403


def test_ft08_teacher_edits_topic_with_lessons_and_components(
    client: TestClient, school: School
) -> None:
    headers = login(client, school["teacher_a"].email)
    course = client.post("/api/courses", headers=headers, json={"title": "C++"}).json()
    topic: dict[str, Any] = {
        "code": "1.3",
        "title": "Бүтін сандар",
        "learning_outcomes": "Бүтін арифметиканы қолданады",
        "lessons": [{"title": "Целые числа", "url": "https://stepik.org/lesson/13021/step/1"}],
        "knowledge_components": [{"code": "int.io", "name": "Енгізу-шығару"}],
    }
    created = client.post(f"/api/courses/{course['id']}/topics", headers=headers, json=topic)
    assert created.status_code == 201
    kc_id = created.json()["knowledge_components"][0]["id"]
    topic["knowledge_components"].append({"code": "int.arith", "name": "Арифметика"})
    updated = client.put(f"/api/topics/{created.json()['id']}", headers=headers, json=topic).json()
    assert updated["knowledge_components"][0]["id"] == kc_id
    assert len(updated["knowledge_components"]) == 2
    duplicate = client.post(f"/api/courses/{course['id']}/topics", headers=headers, json=topic)
    assert duplicate.status_code == 409
    coach = login(client, school["coach"].email)
    assert (
        client.put(f"/api/topics/{created.json()['id']}", headers=coach, json=topic).status_code
        == 403
    )


@pytest.mark.usefixtures("seeded")
def test_ft10_task_links_only_components_of_its_course(
    client: TestClient, db: Session, make_user: MakeUser
) -> None:
    teacher = make_user("teacher@example.com", Role.TEACHER)
    part1 = db.scalar(select(Course).where(Course.stepik_course_id == 363))
    part2 = db.scalar(select(Course).where(Course.stepik_course_id == 64454))
    assert part1 is not None and part2 is not None
    db.add(CourseTeacher(course_id=part2.id, user_id=teacher.id))
    db.flush()
    part1_kc = db.scalar(
        select(KnowledgeComponent.id).join(Topic).where(Topic.course_id == part1.id)
    )
    headers = login(client, "teacher@example.com", PASSWORD)
    response = client.post(
        "/api/tasks",
        headers=headers,
        json={
            "course_id": part2.id,
            "title": "Binary search",
            "statement_md": "Find x.",
            "knowledge_component_ids": [part1_kc],
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "kc_not_in_course"


@pytest.mark.usefixtures("seeded")
def test_ft10_experiment_tasks_are_linked_to_components(db: Session) -> None:
    task = db.scalar(select(Task).where(Task.external_key == "EXP-III-8"))
    assert task is not None
    codes = set(
        db.scalars(
            select(KnowledgeComponent.code).where(
                KnowledgeComponent.id.in_([k.knowledge_component_id for k in task.kc_links])
            )
        )
    )
    assert codes == {"map.map", "map.frequency"}
