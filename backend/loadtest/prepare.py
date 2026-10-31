"""Prepare a database for the load test: 100 students, a teacher, a course, an approved
task and a started assessment. Prints nothing secret; all accounts share LOAD_PASSWORD.

    DATABASE_URL=... REDIS_URL=... JWT_SECRET=... LOAD_PASSWORD=... python -m loadtest.prepare
"""

import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.roles import Role
from app.core.security import hash_password
from app.db.context import set_system
from app.db.session import get_sessionmaker
from app.models import (
    Assessment,
    AssessmentTask,
    Course,
    CourseGroup,
    CourseTeacher,
    Group,
    GroupMember,
    Task,
    TestCase,
    User,
)

STUDENTS = int(os.environ.get("LOAD_STUDENTS", "100"))


def main() -> None:
    password = hash_password(os.environ["LOAD_PASSWORD"])
    with get_sessionmaker()() as db:
        set_system(db)
        if db.scalar(select(User).where(User.email == "load.teacher@example.com")):
            print("already prepared")
            return
        teacher = User(
            email="load.teacher@example.com", full_name="Load Teacher", password_hash=password
        )
        teacher.set_roles({Role.TEACHER})
        db.add(teacher)
        group = Group(name="Load group")
        course = Course(title="Load course", part="part1")
        db.add_all([group, course])
        db.flush()
        db.add_all(
            [
                CourseTeacher(course_id=course.id, user_id=teacher.id),
                CourseGroup(course_id=course.id, group_id=group.id),
            ]
        )
        task = Task(
            course_id=course.id,
            title="Even or odd",
            statement_md="EVEN or ODD",
            reference_solution="int main(){}",
            level="I",
            level_status="confirmed",
            status="approved",
            time_limit_ms=1000,
            memory_limit_kb=262144,
        )
        task.tests = [
            TestCase(position=i, input=f"{i}\n", expected_output="EVEN\n", is_hidden=i > 1)
            for i in range(1, 11)
        ]
        db.add(task)
        db.flush()
        now = datetime.now(UTC)
        assessment = Assessment(
            course_id=course.id,
            title="Load",
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(days=1),
            genai_mode="forbidden",
        )
        assessment.task_links = [AssessmentTask(task_id=task.id, position=1)]
        db.add(assessment)
        for i in range(STUDENTS):
            student = User(
                email=f"load.student{i}@example.com",
                full_name=f"Student {i}",
                password_hash=password,
                consent_version="load",
            )
            student.set_roles({Role.STUDENT})
            db.add(student)
            db.flush()
            db.add(GroupMember(group_id=group.id, user_id=student.id))
        db.commit()
        print(f"prepared: task {task.id}, assessment {assessment.id}, {STUDENTS} students")


if __name__ == "__main__":
    main()
