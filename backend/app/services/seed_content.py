"""`make seed`: load the course catalogue and draft tasks from seed/ (ФТ-08, ФТ-12).

Safe to run again: existing rows are updated, teacher edits to tasks are never overwritten.
Stepik problem statements are not copied, only lesson links (Q-05).
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import CoursePart
from app.models import Course, ExternalLesson, KnowledgeComponent, Task, Topic, TopicResource
from app.services.levels import get_rule
from app.services.task_import import parse_package
from app.services.tasks import create_from_draft

PART1_STEPIK_ID = 363


@dataclass
class SeedReport:
    courses: int = 0
    topics: int = 0
    lessons: int = 0
    knowledge_components: int = 0
    tasks_created: int = 0
    tasks_skipped: int = 0
    resources: int = 0


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def seed_courses(db: Session, seed_dir: Path, report: SeedReport) -> dict[int, Course]:
    courses: dict[int, Course] = {}
    for c in _load(seed_dir / "stepik_lessons.json")["courses"]:
        course = db.scalar(select(Course).where(Course.stepik_course_id == c["stepik_id"]))
        if course is None:
            course = Course(stepik_course_id=c["stepik_id"])
            db.add(course)
        course.title = c["title"]
        course.description = f"{c['system_part']}. {c['authors']}."
        course.part = (
            CoursePart.PART1 if c["stepik_id"] == PART1_STEPIK_ID else CoursePart.PART2
        ).value
        course.source_url = c["url"]
        db.flush()
        report.courses += 1
        units = c.get("topics") or c.get("modules") or []
        for position, unit in enumerate(units, start=1):
            topic = db.scalar(
                select(Topic).where(Topic.course_id == course.id, Topic.code == unit["code"])
            )
            if topic is None:
                topic = Topic(course_id=course.id, code=unit["code"])
                db.add(topic)
            topic.title = unit["title_kk"]
            topic.position = position
            topic.lessons = [
                ExternalLesson(
                    stepik_lesson_id=lesson["lesson_id"],
                    title=lesson["title_ru"],
                    url=lesson["url"],
                    kind=lesson.get("kind", "lecture_and_practice"),
                    position=i,
                )
                for i, lesson in enumerate(unit["lessons"], start=1)
            ]
            report.topics += 1
            report.lessons += len(unit["lessons"])
        db.flush()
        courses[c["stepik_id"]] = course
    return courses


def seed_knowledge_components(
    db: Session, seed_dir: Path, courses: dict[int, Course], report: SeedReport
) -> None:
    data = _load(seed_dir / "knowledge_components.json")
    course = courses[data["stepik_course_id"]]
    topics = {t.code: t for t in course.topics}
    for entry in data["topics"]:
        topic = topics[entry["topic"]]
        existing = {kc.code: kc for kc in topic.knowledge_components}
        for position, kc in enumerate(entry["components"], start=1):
            row = existing.get(kc["code"])
            if row is None:
                row = KnowledgeComponent(code=kc["code"])
                topic.knowledge_components.append(row)
            row.name = kc["name_kk"]
            row.position = position
            report.knowledge_components += 1
    db.flush()


def read_package_dir(path: Path) -> dict[str, bytes]:
    return {
        str(f.relative_to(path).as_posix()): f.read_bytes()
        for f in sorted(path.rglob("*"))
        if f.is_file()
    }


def _course_for(courses: dict[int, Course], topic_code: str | None) -> Course:
    """A seed task goes to the course that has its topic: 1.x to part 1, 4.1.x and 4.2.x
    to the olympiad courses (ОТ-01)."""
    for course in courses.values():
        if topic_code and any(t.code == topic_code for t in course.topics):
            return course
    return courses[PART1_STEPIK_ID]


def seed_tasks(db: Session, seed_dir: Path, courses: dict[int, Course], report: SeedReport) -> None:
    rule = get_rule(db)
    for package in sorted((seed_dir / "tasks").glob("*/*/")):
        draft = parse_package(read_package_dir(package))
        if draft.external_key and db.scalar(
            select(Task.id).where(Task.external_key == draft.external_key)
        ):
            report.tasks_skipped += 1
            continue
        course = _course_for(courses, draft.topic_code)
        create_from_draft(db, course.id, draft, rule, author_id=None)
        report.tasks_created += 1


def seed_topic_resources(
    db: Session, seed_dir: Path, courses: dict[int, Course], report: SeedReport
) -> None:
    """ОТ-10: extra materials of each olympiad module (links only)."""
    path = seed_dir / "olympiad_module_resources.json"
    if not path.exists():
        return
    topics = {t.code: t for c in courses.values() for t in c.topics}
    for module in _load(path)["modules"]:
        topic = topics.get(module["topic"])
        if topic is None:
            continue
        existing = {
            r.url: r
            for r in db.scalars(select(TopicResource).where(TopicResource.topic_id == topic.id))
        }
        for position, item in enumerate(module["resources"], start=1):
            row = existing.get(item["url"])
            if row is None:
                row = TopicResource(topic_id=topic.id, url=item["url"])
                db.add(row)
            row.name = item["name"]
            row.purpose = item.get("purpose", "")
            row.position = position
            report.resources += 1
    db.flush()


def seed_all(db: Session, seed_dir: Path) -> SeedReport:
    report = SeedReport()
    courses = seed_courses(db, seed_dir, report)
    seed_knowledge_components(db, seed_dir, courses, report)
    seed_tasks(db, seed_dir, courses, report)
    seed_topic_resources(db, seed_dir, courses, report)
    return report
