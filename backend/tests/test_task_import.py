"""ФТ-22: ZIP and Polygon import; ФТ-18: the 9 experiment task drafts."""

import io
import json
import zipfile
from collections.abc import Mapping
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import LevelStatus, TaskStatus
from app.core.roles import Role
from app.models import Course, CourseTeacher, Task
from app.services.seed_content import read_package_dir
from app.services.task_import import TaskImportError, parse_package, read_zip
from tests.conftest import MakeUser, login

EXPERIMENT_DIR = get_settings().seed_dir / "tasks" / "experiment"


def make_zip(files: Mapping[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


NATIVE = {
    "statement.md": "# Sum\n\nPrint a + b.",
    "input.md": "Two integers.",
    "output.md": "Their sum.",
    "solution.cpp": "int main() {}",
    "config.json": json.dumps(
        {
            "level": "I",
            "features": {
                "knowledge_actions": 0,
                "algorithm_freedom": 0,
                "edge_cases": 1,
                "justification": 0,
            },
            "topic": "1.3",
            "knowledge_components": ["int.io", "int.arith"],
            "time_limit_ms": 2000,
        }
    ),
    "tests/01.in": "1 2\n",
    "tests/01.out": "3\n",
    "tests/02.in": "5 5\n",
    "tests/02.out": "10\n",
}


def test_ft22_native_package_is_parsed() -> None:
    draft = parse_package(read_zip(make_zip(NATIVE)))
    assert draft.title == "Sum"
    assert draft.time_limit_ms == 2000
    assert [(t.input, t.is_hidden) for t in draft.tests] == [("1 2\n", False), ("5 5\n", True)]
    assert draft.knowledge_components == ["int.io", "int.arith"]


def test_ft22_package_in_a_top_level_folder_is_accepted() -> None:
    wrapped = {f"sum/{name}": content for name, content in NATIVE.items()}
    assert parse_package(read_zip(make_zip(wrapped))).title == "Sum"


@pytest.mark.parametrize(
    ("files", "code"),
    [
        ({k: v for k, v in NATIVE.items() if k != "statement.md"}, "missing_statement"),
        ({k: v for k, v in NATIVE.items() if k != "tests/02.out"}, "unpaired_test"),
        ({k: v for k, v in NATIVE.items() if not k.startswith("tests/")}, "no_tests"),
        ({**NATIVE, "config.json": "{not json"}, "bad_config"),
        ({**NATIVE, "config.json": json.dumps({"time_limit_ms": 5})}, "bad_config"),
        ({**NATIVE, "config.json": json.dumps({"features": {"edge_cases": 1}})}, "bad_config"),
        ({**NATIVE, "../evil.txt": "x"}, "unsafe_path"),
        ({**NATIVE, "statement.md": b"\xff\xfe\x00bad"}, "bad_encoding"),
    ],
)
def test_ft22_broken_package_gives_clear_error(files: dict[str, str | bytes], code: str) -> None:
    with pytest.raises(TaskImportError) as error:
        parse_package(read_zip(make_zip(files)))
    assert error.value.code == code
    assert error.value.message


def test_ft22_non_zip_is_rejected() -> None:
    with pytest.raises(TaskImportError) as error:
        read_zip(b"definitely not a zip")
    assert error.value.code == "not_zip"


PROBLEM_XML = """<?xml version="1.0" encoding="utf-8"?>
<problem revision="3" short-name="a-plus-b">
  <names><name language="russian" value="A+B"/></names>
  <statements>
    <statement language="russian" path="statements/russian/problem.tex" type="application/x-tex"/>
  </statements>
  <judging>
    <testset name="tests">
      <time-limit>2000</time-limit>
      <memory-limit>268435456</memory-limit>
      <test-count>2</test-count>
      <input-path-pattern>tests/%02d</input-path-pattern>
      <answer-path-pattern>tests/%02d.a</answer-path-pattern>
      <tests><test method="manual" sample="true"/><test method="manual"/></tests>
    </testset>
  </judging>
  <assets><solutions>
    <solution tag="main"><source path="solutions/main.cpp" type="cpp.g++17"/></solution>
  </solutions></assets>
</problem>
"""

POLYGON = {
    "problem.xml": PROBLEM_XML,
    "statement-sections/russian/legend.tex": "Даны два числа.",
    "statement-sections/russian/input.tex": "Два целых числа.",
    "statement-sections/russian/output.tex": "Их сумма.",
    "tests/01": "1 2\n",
    "tests/01.a": "3\n",
    "tests/02": "2 2\n",
    "tests/02.a": "4\n",
    "solutions/main.cpp": "int main() { return 0; }",
}


def test_ft22_polygon_package_is_parsed() -> None:
    draft = parse_package(read_zip(make_zip(POLYGON)))
    assert draft.title == "A+B"
    assert draft.time_limit_ms == 2000
    assert draft.memory_limit_kb == 262144
    assert draft.input_format == "Два целых числа."
    assert draft.reference_solution.startswith("int main")
    assert [t.is_hidden for t in draft.tests] == [False, True]


def test_ft22_polygon_without_generated_tests_is_rejected() -> None:
    files = {k: v for k, v in POLYGON.items() if k != "tests/02.a"}
    with pytest.raises(TaskImportError) as error:
        parse_package(read_zip(make_zip(files)))
    assert error.value.code == "polygon_tests_missing"


def test_ft22_polygon_xml_entities_are_refused() -> None:
    bomb = '<?xml version="1.0"?><!DOCTYPE p [<!ENTITY a "aaaa">]><problem>&a;</problem>'
    with pytest.raises(TaskImportError) as error:
        parse_package(read_zip(make_zip({**POLYGON, "problem.xml": bomb})))
    assert error.value.code == "bad_problem_xml"


def _teacher_on_part1(db: Session, make_user: MakeUser) -> Course:
    course = db.scalar(select(Course).where(Course.stepik_course_id == 363))
    assert course is not None
    teacher = make_user("teacher@example.com", Role.TEACHER)
    db.add(CourseTeacher(course_id=course.id, user_id=teacher.id))
    db.flush()
    return course


@pytest.mark.usefixtures("seeded")
def test_ft22_import_endpoint_creates_draft(
    client: TestClient, db: Session, make_user: MakeUser
) -> None:
    course = _teacher_on_part1(db, make_user)
    headers = login(client, "teacher@example.com")
    response = client.post(
        f"/api/courses/{course.id}/tasks/import",
        headers=headers,
        files={"file": ("sum.zip", make_zip(NATIVE), "application/zip")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "draft"
    assert body["level"] == "I"
    assert body["level_status"] == "suggested"
    assert len(body["knowledge_component_ids"]) == 2


@pytest.mark.usefixtures("seeded")
def test_ft22_import_endpoint_reports_errors(
    client: TestClient, db: Session, make_user: MakeUser
) -> None:
    course = _teacher_on_part1(db, make_user)
    headers = login(client, "teacher@example.com")
    bad = {**NATIVE, "config.json": json.dumps({"topic": "9.9"})}
    response = client.post(
        f"/api/courses/{course.id}/tasks/import",
        headers=headers,
        files={"file": ("bad.zip", make_zip(bad), "application/zip")},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unknown_topic"
    mismatch = {
        **NATIVE,
        "config.json": json.dumps(
            {"level": "III", "features": json.loads(NATIVE["config.json"])["features"]}
        ),
    }
    response = client.post(
        f"/api/courses/{course.id}/tasks/import",
        headers=headers,
        files={"file": ("bad.zip", make_zip(mismatch), "application/zip")},
    )
    assert response.json()["detail"]["code"] == "level_mismatch"


@pytest.mark.usefixtures("seeded")
def test_ft22_student_cannot_import(client: TestClient, db: Session, make_user: MakeUser) -> None:
    course = db.scalar(select(Course).where(Course.stepik_course_id == 363))
    assert course is not None
    make_user("s@example.com", Role.STUDENT)
    response = client.post(
        f"/api/courses/{course.id}/tasks/import",
        headers=login(client, "s@example.com"),
        files={"file": ("sum.zip", make_zip(NATIVE), "application/zip")},
    )
    assert response.status_code == 403


EXPERIMENT_KEYS = [p.name for p in sorted(EXPERIMENT_DIR.iterdir()) if p.is_dir()]


def test_ft18_nine_experiment_task_packages_exist() -> None:
    assert EXPERIMENT_KEYS == [
        "EXP-I-1",
        "EXP-I-2",
        "EXP-I-3",
        "EXP-II-4",
        "EXP-II-5",
        "EXP-II-6",
        "EXP-III-7",
        "EXP-III-8",
        "EXP-III-9",
    ]


@pytest.mark.parametrize("key", EXPERIMENT_KEYS)
def test_ft18_experiment_task_is_complete(key: str) -> None:
    package = EXPERIMENT_DIR / key
    draft = parse_package(read_package_dir(package))
    seed = json.loads((get_settings().seed_dir / "experiment_tasks.json").read_text("utf-8"))
    original = next(t for t in seed["tasks"] if t["id"] == key)
    assert draft.external_key == key
    assert draft.level is not None and draft.level.value == original["level"]
    assert original["statement_kk"].split(" Мысал")[0] in draft.statement_md
    assert draft.input_format and draft.output_format
    assert draft.reference_solution
    assert len(draft.tests) >= 5
    assert not draft.tests[0].is_hidden


def test_ft18_seed_loads_experiment_tasks_as_drafts(db: Session, seeded: object) -> None:
    tasks = db.scalars(select(Task).where(Task.external_key.like("EXP-%"))).all()
    assert len(tasks) == 9
    for task in tasks:
        assert task.status == TaskStatus.DRAFT.value
        assert task.level_status == LevelStatus.SUGGESTED.value
        assert task.topic_id is not None
        assert task.kc_links
    assert Path(EXPERIMENT_DIR).is_dir()
