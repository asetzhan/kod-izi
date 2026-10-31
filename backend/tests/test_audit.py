"""Spec 14.1, "Аудит": login, logout and role changes are logged; the log cannot be altered."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.api.auth import REFRESH_COOKIE
from app.models import AuditLog
from app.services import audit
from app.services.audit import AuditAction
from tests.conftest import CSRF, School, login


def _actions(db: Session) -> list[str]:
    return list(db.scalars(select(AuditLog.action).order_by(AuditLog.id)))


def test_sec14_audit_records_login_logout_and_role_change(
    client: TestClient, db: Session, school: School
) -> None:
    client.post("/api/auth/login", json={"email": school["student_a"].email, "password": "bad"})
    headers = login(client, school["admin"].email)
    raw = client.cookies[REFRESH_COOKIE]
    client.put(
        f"/api/admin/users/{school['student_a'].id}/roles",
        headers=headers,
        json={"roles": ["student", "coach"]},
    )
    client.cookies.clear()
    client.post("/api/auth/logout", headers={**CSRF, "Cookie": f"{REFRESH_COOKIE}={raw}"})

    assert _actions(db) == ["login_failed", "login_success", "role_changed", "logout"]
    role_change = db.scalar(select(AuditLog).where(AuditLog.action == "role_changed"))
    assert role_change is not None
    assert role_change.actor_id == school["admin"].id
    assert role_change.details == {"before": ["student"], "after": ["coach", "student"]}


def test_sec14_admin_reads_audit_log(client: TestClient, school: School) -> None:
    headers = login(client, school["admin"].email)
    entries = client.get("/api/admin/audit-log", headers=headers).json()
    assert entries[0]["action"] == "login_success"


@pytest.mark.parametrize(
    "statement",
    ["UPDATE audit_log SET action = 'edited'", "DELETE FROM audit_log", "TRUNCATE audit_log"],
)
def test_sec14_audit_log_is_append_only(db: Session, statement: str) -> None:
    audit.record(db, AuditAction.LOGIN_FAILED, details={"email": "x@example.com"})
    db.flush()
    with pytest.raises(DBAPIError, match="append-only"), db.begin_nested():
        db.execute(text(statement))
    assert _actions(db) == ["login_failed"]
