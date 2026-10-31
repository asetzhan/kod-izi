"""Management commands: `python -m app.cli create-admin`, `python -m app.cli seed-demo`."""

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
from app.db.session import get_sessionmaker
from app.models import Group, GroupMember, GroupTeacher, User

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("create-admin")
    admin.add_argument("--email", required=True)
    admin.add_argument("--full-name", default="Administrator")
    sub.add_parser("seed-demo")
    args = parser.parse_args(argv)
    if args.command == "create-admin":
        return create_admin(args.email, args.full_name)
    return seed_demo()


if __name__ == "__main__":
    sys.exit(main())
