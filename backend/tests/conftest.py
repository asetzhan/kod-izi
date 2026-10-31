"""Test setup.

Tests run against a real PostgreSQL database whose name must end in `_test`: the
schema is dropped and rebuilt by Alembic. Each test runs inside a transaction that
is rolled back. Redis is replaced with fakeredis.
"""

import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import fakeredis
import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://kodizi:kodizi@localhost:5432/kodizi_test"
)
if not (make_url(TEST_DATABASE_URL).database or "").endswith("_test"):
    raise RuntimeError("TEST_DATABASE_URL must point to a database whose name ends in _test")

os.environ.update(
    {
        "APP_ENV": "test",
        "DATABASE_URL": TEST_DATABASE_URL,
        "REDIS_URL": "redis://unused-in-tests:6379/0",
        "JWT_SECRET": "test-only-secret-that-is-long-enough-0123456789",
        "COOKIE_SECURE": "true",
        "LLM_PROVIDER": "fake",
    }
)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.auth import CSRF_HEADER, CSRF_VALUE  # noqa: E402
from app.api.deps import get_redis  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.roles import Role  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Group, GroupMember, GroupTeacher, User  # noqa: E402
from app.services.seed_content import SeedReport, seed_all  # noqa: E402

# Stage 2 fixtures `judge` and `ws` live in tests/workspace_helpers.py.
pytest_plugins = ["tests.workspace_helpers"]

BACKEND_DIR = Path(__file__).resolve().parents[1]
PASSWORD = "correct-horse-battery-staple"
CSRF = {CSRF_HEADER: CSRF_VALUE}


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    eng = create_engine(TEST_DATABASE_URL)
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(alembic_config(), "head")
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis()


@pytest.fixture
def client(db: Session, redis: fakeredis.FakeRedis) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_redis] = lambda: redis
    with TestClient(app, base_url="https://testserver") as c:
        yield c
    app.dependency_overrides.clear()


MakeUser = Callable[..., User]
School = dict[str, Any]


@pytest.fixture
def make_user(db: Session) -> MakeUser:
    def _make(email: str, *roles: Role, active: bool = True) -> User:
        user = User(
            email=email,
            full_name=email.split("@")[0].title(),
            password_hash=hash_password(PASSWORD),
            is_active=active,
        )
        user.set_roles(set(roles))
        db.add(user)
        db.flush()
        return user

    return _make


@pytest.fixture
def school(db: Session, make_user: MakeUser) -> School:
    """Two groups: teacher A teaches group A (student A), teacher B teaches group B (student B)."""
    people: School = {
        "student_a": make_user("student.a@example.com", Role.STUDENT),
        "student_b": make_user("student.b@example.com", Role.STUDENT),
        "teacher_a": make_user("teacher.a@example.com", Role.TEACHER),
        "teacher_b": make_user("teacher.b@example.com", Role.TEACHER),
        "coach": make_user("coach@example.com", Role.COACH),
        "admin": make_user("admin@example.com", Role.ADMIN),
    }
    for suffix in ("a", "b"):
        group = Group(name=f"Group {suffix.upper()}")
        db.add(group)
        db.flush()
        db.add(GroupMember(group_id=group.id, user_id=people[f"student_{suffix}"].id))
        db.add(GroupTeacher(group_id=group.id, user_id=people[f"teacher_{suffix}"].id))
        people[f"group_{suffix}"] = group
    db.flush()
    return people


def login(client: TestClient, email: str, password: str = PASSWORD) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def seeded(db: Session) -> SeedReport:
    """Course catalogue and experiment task drafts from seed/."""
    report = seed_all(db, get_settings().seed_dir)
    db.flush()
    return report
