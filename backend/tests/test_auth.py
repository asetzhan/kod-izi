"""Spec 14.1, "Кіру": Argon2id, login limit, short-lived JWT, revocable refresh token."""

from datetime import timedelta

from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import REFRESH_COOKIE
from app.core.config import get_settings
from app.core.roles import Role
from app.core.security import create_access_token
from app.models import AuditLog
from tests.conftest import CSRF, PASSWORD, MakeUser, login


def _login(client: TestClient, email: str, password: str = PASSWORD) -> Response:
    response: Response = client.post("/api/auth/login", json={"email": email, "password": password})
    return response


def _refresh(client: TestClient, raw: str) -> Response:
    client.cookies.clear()
    headers = {**CSRF, "Cookie": f"{REFRESH_COOKIE}={raw}"}
    response: Response = client.post("/api/auth/refresh", headers=headers)
    return response


def test_sec14_password_is_hashed_with_argon2id(make_user: MakeUser) -> None:
    user = make_user("s@example.com", Role.STUDENT)
    assert user.password_hash.startswith("$argon2id$")
    assert PASSWORD not in user.password_hash


def test_sec14_login_sets_httponly_strict_refresh_cookie(
    client: TestClient, make_user: MakeUser
) -> None:
    make_user("s@example.com", Role.STUDENT)
    response = _login(client, "S@Example.com")
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["roles"] == ["student"]
    assert body["expires_in"] == 15 * 60
    cookie = response.headers["set-cookie"].lower()
    for attribute in ("httponly", "secure", "samesite=strict", "path=/api/auth"):
        assert attribute in cookie


def test_sec14_login_with_wrong_password_returns_401(
    client: TestClient, make_user: MakeUser
) -> None:
    make_user("s@example.com", Role.STUDENT)
    assert _login(client, "s@example.com", "wrong-password").status_code == 401
    assert _login(client, "nobody@example.com").status_code == 401


def test_sec14_inactive_user_cannot_log_in(client: TestClient, make_user: MakeUser) -> None:
    make_user("s@example.com", Role.STUDENT, active=False)
    assert _login(client, "s@example.com").status_code == 401


def test_sec14_login_rate_limited_after_max_attempts(
    client: TestClient, make_user: MakeUser
) -> None:
    make_user("s@example.com", Role.STUDENT)
    for _ in range(get_settings().login_max_attempts):
        assert _login(client, "s@example.com", "wrong-password").status_code == 401
    assert _login(client, "s@example.com").status_code == 429


def test_sec14_successful_login_resets_failure_counter(
    client: TestClient, make_user: MakeUser
) -> None:
    make_user("s@example.com", Role.STUDENT)
    for _ in range(get_settings().login_max_attempts - 1):
        _login(client, "s@example.com", "wrong-password")
    assert _login(client, "s@example.com").status_code == 200
    assert _login(client, "s@example.com", "wrong-password").status_code == 401
    assert _login(client, "s@example.com").status_code == 200


def test_sec14_expired_access_token_is_rejected(client: TestClient, make_user: MakeUser) -> None:
    user = make_user("s@example.com", Role.STUDENT)
    token = create_access_token(user.id, get_settings().jwt_secret, timedelta(seconds=-1))
    response = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_sec14_token_signed_with_other_key_is_rejected(
    client: TestClient, make_user: MakeUser
) -> None:
    user = make_user("s@example.com", Role.STUDENT)
    token = create_access_token(user.id, "another-secret-" + "x" * 32, timedelta(minutes=5))
    response = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_sec14_refresh_rotates_token(client: TestClient, make_user: MakeUser) -> None:
    make_user("s@example.com", Role.STUDENT)
    first = _login(client, "s@example.com").cookies[REFRESH_COOKIE]
    response = _refresh(client, first)
    assert response.status_code == 200
    second = response.cookies[REFRESH_COOKIE]
    assert second != first
    me = client.get(
        "/api/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"}
    )
    assert me.status_code == 200


def test_sec14_refresh_requires_csrf_header(client: TestClient, make_user: MakeUser) -> None:
    make_user("s@example.com", Role.STUDENT)
    _login(client, "s@example.com")
    assert client.post("/api/auth/refresh").status_code == 403


def test_sec14_refresh_token_reuse_revokes_whole_family(
    client: TestClient, db: Session, make_user: MakeUser
) -> None:
    user = make_user("s@example.com", Role.STUDENT)
    first = _login(client, "s@example.com").cookies[REFRESH_COOKIE]
    second = _refresh(client, first).cookies[REFRESH_COOKIE]

    assert _refresh(client, first).status_code == 401
    assert _refresh(client, second).status_code == 401
    actions = db.scalars(select(AuditLog.action).where(AuditLog.actor_id == user.id)).all()
    assert "token_reuse_detected" in actions


def test_sec14_logout_revokes_refresh_token(client: TestClient, make_user: MakeUser) -> None:
    make_user("s@example.com", Role.STUDENT)
    raw = _login(client, "s@example.com").cookies[REFRESH_COOKIE]
    client.cookies.clear()
    response = client.post(
        "/api/auth/logout", headers={**CSRF, "Cookie": f"{REFRESH_COOKIE}={raw}"}
    )
    assert response.status_code == 204
    assert _refresh(client, raw).status_code == 401


def test_sec14_unknown_refresh_token_returns_401(client: TestClient) -> None:
    assert _refresh(client, "made-up-token").status_code == 401


def test_sec14_login_helper_returns_bearer_header(client: TestClient, make_user: MakeUser) -> None:
    make_user("s@example.com", Role.STUDENT)
    assert login(client, "s@example.com")["Authorization"].startswith("Bearer ")
