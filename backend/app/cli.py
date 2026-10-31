"""Management commands: `python -m app.cli create-admin | seed | seed-demo`."""

import argparse
import getpass
import os
import secrets
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.roles import Role
from app.core.security import hash_password
from app.db.context import set_system
from app.db.session import get_sessionmaker
from app.models import Course, CourseGroup, CourseTeacher, Group, GroupMember, GroupTeacher, User
from app.services.privacy import apply_retention
from app.services.research import agreement
from app.services.seed_content import PART1_STEPIK_ID, seed_all

DEMO_USERS = [
    ("student@example.com", "Demo Student", {Role.STUDENT}),
    ("student2@example.com", "Demo Student 2", {Role.STUDENT}),
    ("teacher@example.com", "Demo Teacher", {Role.TEACHER}),
    ("coach@example.com", "Demo Coach", {Role.COACH}),
    ("admin@example.com", "Demo Admin", {Role.ADMIN}),
]


def _get_or_create_user(
    db: Session, email: str, full_name: str, password: str, roles: set[Role]
) -> tuple[User, bool]:
    user = db.scalar(select(User).where(User.email == email))
    if user is not None:
        return user, False
    user = User(email=email, full_name=full_name, password_hash=hash_password(password))
    user.set_roles(roles)
    db.add(user)
    db.flush()
    return user, True


def create_admin(email: str, full_name: str) -> int:
    password = getpass.getpass("Password (min 12 chars): ")
    if len(password) < 12 or password != getpass.getpass("Repeat password: "):
        print("Passwords differ or are shorter than 12 characters.", file=sys.stderr)
        return 1
    with get_sessionmaker()() as db:
        set_system(db)
        _, created = _get_or_create_user(db, email.lower(), full_name, password, {Role.ADMIN})
        if not created:
            print(f"User {email} already exists.", file=sys.stderr)
            return 1
        db.commit()
    print(f"Administrator {email} created.")
    return 0


def seed_demo() -> int:
    """Demo accounts for local development only."""
    if get_settings().app_env != "dev":
        print("seed-demo runs only with APP_ENV=dev.", file=sys.stderr)
        return 1
    password = os.environ.get("DEMO_PASSWORD") or secrets.token_urlsafe(12)
    with get_sessionmaker()() as db:
        set_system(db)
        users = {}
        for email, name, roles in DEMO_USERS:
            users[email], created = _get_or_create_user(db, email, name, password, roles)
            print(f"{'created' if created else 'exists '}  {email}  ({', '.join(sorted(roles))})")
        group = db.scalar(select(Group).where(Group.name == "Demo group"))
        if group is None:
            group = Group(name="Demo group")
            db.add(group)
            db.flush()
            db.add(GroupMember(group_id=group.id, user_id=users["student@example.com"].id))
            db.add(GroupTeacher(group_id=group.id, user_id=users["teacher@example.com"].id))
        db.commit()
    if not os.environ.get("DEMO_PASSWORD"):
        print(f"Password for new demo accounts: {password}")
    return 0


def seed() -> int:
    """`make seed`: course catalogue and draft tasks; demo accounts too when APP_ENV=dev."""
    with get_sessionmaker()() as db:
        set_system(db)
        report = seed_all(db, get_settings().seed_dir)
        db.commit()
    print(
        f"courses {report.courses}, topics {report.topics}, lessons {report.lessons}, "
        f"knowledge components {report.knowledge_components}, "
        f"tasks created {report.tasks_created}, skipped {report.tasks_skipped}"
    )
    if get_settings().app_env != "dev":
        return 0
    result = seed_demo()
    with get_sessionmaker()() as db:
        set_system(db)
        course = db.scalar(select(Course).where(Course.stepik_course_id == PART1_STEPIK_ID))
        teacher = db.scalar(select(User).where(User.email == "teacher@example.com"))
        group = db.scalar(select(Group).where(Group.name == "Demo group"))
        if course and teacher and group:
            db.merge(CourseTeacher(course_id=course.id, user_id=teacher.id))
            db.merge(CourseGroup(course_id=course.id, group_id=group.id))
            db.commit()
            print("Demo teacher and group attached to the C++ basics course.")
    return result


def retention() -> int:
    """Spec 14.3: anonymize students past the retention period or without consent."""
    with get_sessionmaker()() as db:
        set_system(db)
        done = apply_retention(db, get_settings().retention_days)
        db.commit()
    print(f"anonymized {len(done)} user(s)")
    return 0


def agreement_report(path: str) -> int:
    """ФТ-49: agreement statistics from an exported CSV (ai_S/teacher_S, ai_F/teacher_F...)."""
    import csv

    with open(path, encoding="utf-8") as handle:
        rows = [r for r in csv.DictReader(handle) if r.get("ai_S")]
    for key in ("S", "F", "E", "A"):
        stats = agreement(
            [float(r[f"ai_{key}"]) for r in rows], [float(r[f"teacher_{key}"]) for r in rows]
        )
        print(key, stats)
    print("baseline (dissertation, Claude): MAE = 7.34, r = 0.647")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("create-admin")
    admin.add_argument("--email", required=True)
    admin.add_argument("--full-name", default="Administrator")
    sub.add_parser("seed-demo")
    sub.add_parser("seed")
    sub.add_parser("retention")
    report = sub.add_parser("agreement")
    report.add_argument("csv_path")
    args = parser.parse_args(argv)
    if args.command == "retention":
        return retention()
    if args.command == "agreement":
        return agreement_report(args.csv_path)
    if args.command == "create-admin":
        return create_admin(args.email, args.full_name)
    if args.command == "seed":
        return seed()
    return seed_demo()


if __name__ == "__main__":
    sys.exit(main())
