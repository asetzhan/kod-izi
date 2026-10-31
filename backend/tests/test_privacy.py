"""Stage 5: second factor, consent, anonymization, row-level security, pilot export.

Spec 13, 14.1, 14.3, 16; ФТ-49 (core).
"""

import csv
import io
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pyotp
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.api.auth import REFRESH_COOKIE
from app.core.config import Settings, get_settings
from app.core.roles import Role
from app.db.context import set_actor, set_system
from app.models import AuditLog, User
from app.services.privacy import apply_retention
from app.services.research import agreement, mean_difference, pearson, spearman
from tests.conftest import CSRF, PASSWORD, MakeUser, School, login
from tests.workspace_helpers import _open, _submit

# Second factor (spec 14.1) ----------------------------------------------------------------


@pytest.fixture
def strict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "require_2fa_for_staff", True)
    monkeypatch.setattr(get_settings(), "require_consent", True)


def _login(client: TestClient, email: str, otp: str | None = None) -> Any:
    return client.post("/api/auth/login", json={"email": email, "password": PASSWORD, "otp": otp})


@pytest.mark.usefixtures("strict")
def test_sec14_teacher_must_set_up_second_factor(
    client: TestClient, make_user: MakeUser, db: Session
) -> None:
    make_user("t@example.com", Role.TEACHER)
    token = _login(client, "t@example.com").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    blocked = client.get("/api/courses", headers=headers)
    assert blocked.status_code == 403 and blocked.json()["detail"] == "2fa_required"
    assert client.get("/api/me", headers=headers).json()["two_factor_enabled"] is False

    setup = client.post("/api/auth/2fa/setup", headers=headers).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/")
    totp = pyotp.TOTP(setup["secret"])
    enable = "/api/auth/2fa/enable"
    wrong = client.post(enable, headers=headers, json={"code": "000000", "password": PASSWORD})
    assert wrong.json()["detail"] == "otp_invalid"
    no_password = client.post(enable, headers=headers, json={"code": totp.now(), "password": "x"})
    assert no_password.json()["detail"] == "invalid_password"
    ok = client.post(enable, headers=headers, json={"code": totp.now(), "password": PASSWORD})
    assert ok.status_code == 200
    assert client.get("/api/courses", headers=headers).status_code == 200

    assert _login(client, "t@example.com").json()["detail"] == "otp_required"
    assert _login(client, "t@example.com", "123456").json()["detail"] == "otp_invalid"
    # The code used to enable is spent; the next 30-second step is still accepted.
    assert _login(client, "t@example.com", totp.now()).json()["detail"] == "otp_invalid"
    next_code = totp.at(datetime.now(UTC) + timedelta(seconds=30))
    assert _login(client, "t@example.com", next_code).status_code == 200


@pytest.mark.usefixtures("strict")
def test_sec14_totp_code_cannot_be_replayed(client: TestClient, make_user: MakeUser) -> None:
    teacher = make_user("t@example.com", Role.TEACHER)
    secret = pyotp.random_base32()
    teacher.totp_secret, teacher.totp_enabled_at = secret, datetime.now(UTC)
    code = pyotp.TOTP(secret).now()
    assert _login(client, "t@example.com", code).status_code == 200
    assert _login(client, "t@example.com", code).json()["detail"] == "otp_invalid"


@pytest.mark.usefixtures("strict")
def test_sec14_enabling_second_factor_signs_out_password_only_sessions(
    client: TestClient, make_user: MakeUser
) -> None:
    make_user("t@example.com", Role.TEACHER)
    headers = login(client, "t@example.com")
    old_refresh = client.cookies[REFRESH_COOKIE]
    secret = client.post("/api/auth/2fa/setup", headers=headers).json()["secret"]
    client.post(
        "/api/auth/2fa/enable",
        headers=headers,
        json={"code": pyotp.TOTP(secret).now(), "password": PASSWORD},
    )
    client.cookies.clear()
    refreshed = client.post(
        "/api/auth/refresh", headers={**CSRF, "Cookie": f"{REFRESH_COOKIE}={old_refresh}"}
    )
    assert refreshed.status_code == 401


def test_sec14_students_cannot_set_up_a_second_factor(
    client: TestClient, make_user: MakeUser
) -> None:
    make_user("s@example.com", Role.STUDENT)
    headers = login(client, "s@example.com")
    response = client.post("/api/auth/2fa/setup", headers=headers)
    assert response.status_code == 403 and response.json()["detail"] == "2fa_not_applicable"


def test_sec14_production_refuses_unsafe_switches(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "REQUIRE_2FA_FOR_STAFF",
        "REQUIRE_CONSENT",
        "DB_APP_ROLE",
        "JUDGE_BACKEND",
        "GRADING_INLINE",
        "COOKIE_SECURE",
    ):
        monkeypatch.delenv(name, raising=False)
    base: dict[str, Any] = {
        "app_env": "prod",
        "database_url": "postgresql+psycopg://x@/y",
        "redis_url": "redis://r",
        "jwt_secret": "s" * 40,
    }
    Settings.model_validate(base)
    for switch in (
        {"require_2fa_for_staff": False},
        {"require_consent": False},
        {"db_app_role": ""},
        {"judge_backend": "simulated"},
        {"grading_inline": True},
        {"cookie_secure": False},
    ):
        with pytest.raises(ValidationError, match="APP_ENV=prod"):
            Settings.model_validate({**base, **switch})
    Settings.model_validate({**base, "app_env": "dev", "grading_inline": True})


def test_sec14_failed_login_is_audited_without_the_address(client: TestClient, db: Session) -> None:
    client.post("/api/auth/login", json={"email": "who@example.com", "password": "bad-password"})
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "login_failed"))
    assert entry is not None and "who@example.com" not in str(entry.details)
    assert entry.details["email_hash"]


@pytest.mark.usefixtures("strict")
def test_sec14_admin_resets_lost_second_factor(client: TestClient, make_user: MakeUser) -> None:
    admin = make_user("a@example.com", Role.ADMIN)
    teacher = make_user("t@example.com", Role.TEACHER)
    secret = pyotp.random_base32()
    for user in (admin, teacher):
        user.totp_secret, user.totp_enabled_at = secret, datetime.now(UTC)
    token = _login(client, "a@example.com", pyotp.TOTP(secret).now()).json()["access_token"]
    response = client.post(
        f"/api/admin/users/{teacher.id}/2fa/reset", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.json()["two_factor_enabled"] is False
    assert _login(client, "t@example.com").status_code == 200  # no code until set up again


def test_sec14_students_and_coaches_need_no_second_factor(
    client: TestClient, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "require_2fa_for_staff", True)
    make_user("c@example.com", Role.COACH)
    headers = login(client, "c@example.com")
    assert client.get("/api/courses", headers=headers).status_code == 200


# Consent and retention (spec 13, 14.3) ---------------------------------------------------


@pytest.mark.usefixtures("strict")
def test_sec14_student_gives_and_withdraws_consent(client: TestClient, make_user: MakeUser) -> None:
    make_user("s@example.com", Role.STUDENT)
    headers = login(client, "s@example.com")
    assert client.get("/api/courses", headers=headers).json()["detail"] == "consent_required"
    consent = client.get("/api/consent", headers=headers).json()
    outdated = client.post("/api/consent", headers=headers, json={"version": "2000-0"})
    assert outdated.status_code == 422
    client.post("/api/consent", headers=headers, json={"version": consent["version"]})
    assert client.get("/api/courses", headers=headers).status_code == 200
    client.post("/api/consent/withdraw", headers=headers)
    assert client.get("/api/courses", headers=headers).status_code == 403


def test_sec14_retention_anonymizes_withdrawn_and_inactive_students(
    db: Session, make_user: MakeUser
) -> None:
    active = make_user("active@example.com", Role.STUDENT)
    withdrawn = make_user("gone@example.com", Role.STUDENT)
    old = make_user("old@example.com", Role.STUDENT)
    teacher = make_user("t@example.com", Role.TEACHER)
    withdrawn.consent_withdrawn_at = datetime.now(UTC)
    old.created_at = datetime.now(UTC) - timedelta(days=400)
    teacher.created_at = datetime.now(UTC) - timedelta(days=400)
    db.flush()
    done = apply_retention(db, retention_days=365)
    assert sorted(done) == sorted([withdrawn.id, old.id])
    assert old.email == f"deleted-{old.id}@invalid.local" and not old.is_active
    assert active.anonymized_at is None and teacher.anonymized_at is None


def test_sec14_admin_anonymizes_a_user(client: TestClient, school: School) -> None:
    admin = login(client, school["admin"].email)
    student = school["student_a"]
    name = student.full_name
    out = client.post(f"/api/admin/users/{student.id}/anonymize", headers=admin).json()
    assert out["email"].startswith("deleted-") and name not in out["full_name"]
    assert (
        client.post(
            "/api/auth/login", json={"email": "student.a@example.com", "password": PASSWORD}
        ).status_code
        == 401
    )
    assert (
        client.post(
            f"/api/admin/users/{student.id}/anonymize",
            headers=login(client, school["teacher_a"].email),
        ).status_code
        == 403
    )


# Row-level security (spec 14.1, "Рұқсаттар") --------------------------------------------


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """In this module everything works as the application role, the way production does,
    so every API test here also runs under row-level security."""
    connection = engine.connect()
    transaction = connection.begin()
    connection.execute(text("SET ROLE kodizi_app"))
    session = Session(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    yield session
    session.close()
    transaction.rollback()
    connection.close()


def test_sec14_rls_students_see_only_their_own_rows(db: Session) -> None:
    set_system(db)
    ids = {}
    for name in ("a", "b"):
        user = User(email=f"rls.{name}@example.com", full_name=name, password_hash="x")
        user.set_roles({Role.STUDENT})
        db.add(user)
        db.flush()
        ids[name] = user.id
    course = db.execute(
        text("INSERT INTO courses (title, part) VALUES ('C', 'part1') RETURNING id")
    ).scalar()
    task = db.execute(
        text(
            "INSERT INTO tasks (course_id, title, statement_md, time_limit_ms, memory_limit_kb, "
            "reference_language, level_status, status) VALUES (:c, 't', 's', 1000, 65536, 'cpp17', "
            "'unrated', 'approved') RETURNING id"
        ),
        {"c": course},
    ).scalar()
    for name in ("a", "b"):
        session_id = db.execute(
            text(
                "INSERT INTO work_sessions (id, user_id, task_id) "
                "VALUES (gen_random_uuid(), :u, :t) RETURNING id"
            ),
            {"u": ids[name], "t": task},
        ).scalar()
        db.execute(
            text(
                "INSERT INTO submissions (session_id, user_id, task_id, code, language, status, "
                "tests_passed, tests_total) VALUES (:s, :u, :t, 'x', 'cpp17', 'done', 0, 0)"
            ),
            {"s": session_id, "u": ids[name], "t": task},
        )

    student_a = db.get(User, ids["a"])
    set_actor(db, student_a)
    owners = db.execute(text("SELECT user_id FROM submissions")).scalars().all()
    assert owners == [ids["a"]]
    with pytest.raises(DBAPIError), db.begin_nested():
        db.execute(
            text(
                "INSERT INTO trace_events (session_id, user_id, task_id, kind, payload) "
                "SELECT id, :b, task_id, 'snapshot', '{}' FROM work_sessions LIMIT 1"
            ),
            {"b": ids["b"]},
        )
    assert db.execute(text("SELECT count(*) FROM ai_grades")).scalar() == 0

    db.info.pop("db_actor")
    db.execute(
        text(
            "SELECT set_config('app.user_id', '', true), set_config('app.privileged', 'off', true)"
        )
    )
    assert db.execute(text("SELECT count(*) FROM submissions")).scalar() == 0  # nobody: nothing
    set_system(db)
    assert db.execute(text("SELECT count(*) FROM submissions")).scalar() == 2


def test_sec14_app_role_cannot_change_append_only_tables(db: Session) -> None:
    set_system(db)
    for statement in (
        "UPDATE trace_events SET kind = 'run'",
        "DELETE FROM audit_log",
        "TRUNCATE trace_events",
    ):
        with pytest.raises(DBAPIError, match="permission denied"), db.begin_nested():
            db.execute(text(statement))


def test_sec14_whole_flow_works_under_row_level_security(
    client: TestClient, ws: dict[str, Any], db: Session, school: School
) -> None:
    """Student work, grading in the background and the teacher's view, all as kodizi_app."""
    assert db.execute(text("SELECT current_user")).scalar() == "kodizi_app"
    result = _submit(client, ws, _open(client, ws))
    assert result["verdict"] == "OK"
    grades = client.get(f"/api/submissions/{result['id']}/ai-grades", headers=ws["teacher"])
    assert grades.status_code == 200 and grades.json()[0]["status"] == "ready"
    other = login(client, school["student_b"].email)
    assert client.get(f"/api/submissions/{result['id']}", headers=other).status_code == 403
    # Even a direct query in the other student's name finds nothing.
    set_actor(db, school["student_b"])
    assert db.execute(text("SELECT count(*) FROM submissions")).scalar() == 0
    assert db.execute(text("SELECT count(*) FROM trace_events")).scalar() == 0


# Pilot data (ФТ-49 core, spec 16) -------------------------------------------------------


def test_ft49_agreement_statistics() -> None:
    ai, teacher = [80.0, 60.0, 90.0, 40.0], [75.0, 65.0, 85.0, 50.0]
    stats = agreement(ai, teacher)
    assert stats["n"] == 4 and stats["mae"] == 6.25 and stats["md"] == -1.25
    assert pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [10, 20, 40, 30]) == pytest.approx(0.8)
    assert spearman([1, 1, 2], [1, 1, 2]) == pytest.approx(1.0)  # ties
    assert pearson([1, 1], [2, 3]) is None and mean_difference([], []) is None


def test_ft49_export_uses_pseudonyms_and_both_grades(
    client: TestClient, ws: dict[str, Any], school: School, db: Session
) -> None:
    result = _submit(client, ws, _open(client, ws))
    client.post(
        f"/api/submissions/{result['id']}/teacher-grade",
        headers=ws["teacher"],
        json={
            "levels": {
                c: "high"
                for c in (
                    "understanding",
                    "algorithm",
                    "correctness",
                    "code_quality",
                    "debugging",
                    "explanation",
                )
            },
            "components": {"F": 100, "E": 50, "A": 50},
            "feedback": "fake feedback",
        },
    )
    response = client.get(
        f"/api/assessments/{ws['assessment']['id']}/export.csv", headers=ws["teacher"]
    )
    assert response.status_code == 200 and "attachment" in response.headers["content-disposition"]
    [row] = list(csv.DictReader(io.StringIO(response.text)))
    assert row["student"].startswith("S-") and row["ai_S"] and row["teacher_S"]
    student = school["student_a"]
    for secret in (student.full_name, student.email):
        assert secret not in response.text
    stats = client.get(
        f"/api/assessments/{ws['assessment']['id']}/agreement", headers=ws["teacher"]
    ).json()
    assert stats["S"]["n"] == 1 and stats["S"]["mae"] == 0.0
    assert stats["baseline"] == {"mae": 7.34, "pearson": 0.647, "model": "Claude"}
    assert "submission_id" not in row
    assert (
        client.get(
            f"/api/assessments/{ws['assessment']['id']}/export.csv", headers=ws["student"]
        ).status_code
        == 403
    )

    # 14.3: a student who withdrew consent is left out of the research data.
    student.consent_withdrawn_at = datetime.now(UTC)
    db.flush()
    after = client.get(
        f"/api/assessments/{ws['assessment']['id']}/export.csv", headers=ws["teacher"]
    )
    assert list(csv.DictReader(io.StringIO(after.text))) == []
