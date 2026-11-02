"""Spec 14.1 and section 2: the administrator manages users, groups and courses from one page."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Course, CourseGroup, CourseTeacher, RefreshToken
from tests.conftest import PASSWORD, School, login


def _actions(db: Session) -> list[str]:
    return list(db.scalars(select(AuditLog.action)))


def test_sec14_admin_searches_users_by_text_and_role(client: TestClient, school: School) -> None:
    headers = login(client, school["admin"].email)
    found = client.get("/api/admin/users", headers=headers, params={"q": "STUDENT.A"}).json()
    assert [u["id"] for u in found] == [school["student_a"].id]
    teachers = client.get("/api/admin/users", headers=headers, params={"role": "teacher"}).json()
    assert {u["id"] for u in teachers} == {school["teacher_a"].id, school["teacher_b"].id}


def test_sec14_blocked_user_cannot_log_in_and_loses_sessions(
    client: TestClient, school: School, db: Session
) -> None:
    student = school["student_a"]
    old_access = login(client, student.email)
    admin = login(client, school["admin"].email)
    response = client.put(
        f"/api/admin/users/{student.id}/active", headers=admin, json={"active": False}
    )
    assert response.status_code == 200 and response.json()["is_active"] is False
    tokens = list(db.scalars(select(RefreshToken).where(RefreshToken.user_id == student.id)))
    assert tokens and all(t.revoked_at is not None for t in tokens)
    login_try = client.post("/api/auth/login", json={"email": student.email, "password": PASSWORD})
    assert login_try.status_code == 401
    assert "user_deactivated" in _actions(db)
    assert client.get("/api/me", headers=old_access).status_code == 401
    client.put(f"/api/admin/users/{student.id}/active", headers=admin, json={"active": True})
    assert "user_activated" in _actions(db)
    login(client, student.email)


def test_sec14_admin_cannot_block_self(client: TestClient, school: School) -> None:
    admin = school["admin"]
    headers = login(client, admin.email)
    response = client.put(
        f"/api/admin/users/{admin.id}/active", headers=headers, json={"active": False}
    )
    assert response.status_code == 400


def test_sec14_admin_sets_new_password(client: TestClient, school: School, db: Session) -> None:
    student = school["student_a"]
    headers = login(client, school["admin"].email)
    short = client.post(
        f"/api/admin/users/{student.id}/password", headers=headers, json={"password": "short"}
    )
    assert short.status_code == 422
    response = client.post(
        f"/api/admin/users/{student.id}/password",
        headers=headers,
        json={"password": "a-new-long-password"},
    )
    assert response.status_code == 200
    assert (
        client.post(
            "/api/auth/login", json={"email": student.email, "password": PASSWORD}
        ).status_code
        == 401
    )
    tokens = list(db.scalars(select(RefreshToken).where(RefreshToken.user_id == student.id)))
    assert all(t.revoked_at is not None for t in tokens)
    login(client, student.email, "a-new-long-password")
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "password_reset"))
    assert entry is not None and "a-new-long-password" not in str(entry.details)


def test_sec14_admin_lists_groups_and_removes_people(
    client: TestClient, school: School, db: Session
) -> None:
    headers = login(client, school["admin"].email)
    groups = client.get("/api/admin/groups", headers=headers).json()
    assert [g["name"] for g in groups] == ["Group A", "Group B"]
    gid = school["group_a"].id
    after = client.delete(
        f"/api/admin/groups/{gid}/members/{school['student_a'].id}", headers=headers
    ).json()
    assert after["students"] == []
    after = client.delete(
        f"/api/admin/groups/{gid}/teachers/{school['teacher_a'].id}", headers=headers
    ).json()
    assert after["teachers"] == []
    assert {"group_member_removed", "group_teacher_removed"} <= set(_actions(db))
    missing = client.delete("/api/admin/groups/999999/members/1", headers=headers)
    assert missing.status_code == 404


def test_sec14_admin_sees_and_detaches_course_links(
    client: TestClient, school: School, db: Session
) -> None:
    course = Course(title="C++ 1", part="part1")
    db.add(course)
    db.flush()
    db.add(CourseGroup(course_id=course.id, group_id=school["group_a"].id))
    db.add(CourseTeacher(course_id=course.id, user_id=school["teacher_a"].id))
    db.flush()
    headers = login(client, school["admin"].email)
    [row] = [
        c for c in client.get("/api/admin/courses", headers=headers).json() if c["id"] == course.id
    ]
    assert row["groups"] == [{"id": school["group_a"].id, "full_name": "Group A"}]
    assert [t["id"] for t in row["teachers"]] == [school["teacher_a"].id]
    assert (
        client.delete(
            f"/api/admin/courses/{course.id}/groups/{school['group_a'].id}", headers=headers
        ).status_code
        == 204
    )
    assert (
        client.delete(
            f"/api/admin/courses/{course.id}/teachers/{school['teacher_a'].id}", headers=headers
        ).status_code
        == 204
    )
    [row] = [
        c for c in client.get("/api/admin/courses", headers=headers).json() if c["id"] == course.id
    ]
    assert row["groups"] == [] and row["teachers"] == []
    assert {"course_group_removed", "course_teacher_removed"} <= set(_actions(db))


def test_sec14_audit_log_filters_by_action_and_actor(client: TestClient, school: School) -> None:
    admin = school["admin"]
    headers = login(client, admin.email)
    client.post("/api/admin/groups", headers=headers, json={"name": "IT-99"})
    rows = client.get(
        "/api/admin/audit-log", headers=headers, params={"action": "group_created"}
    ).json()
    assert rows and all(r["action"] == "group_created" for r in rows)
    mine = client.get("/api/admin/audit-log", headers=headers, params={"actor_id": admin.id}).json()
    assert mine and all(r["actor_id"] == admin.id for r in mine)


def test_sec14_new_admin_endpoints_are_admin_only(client: TestClient, school: School) -> None:
    headers = login(client, school["teacher_a"].email)
    sid = school["student_a"].id
    assert client.get("/api/admin/groups", headers=headers).status_code == 403
    assert client.get("/api/admin/courses", headers=headers).status_code == 403
    assert (
        client.put(
            f"/api/admin/users/{sid}/active", headers=headers, json={"active": False}
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/admin/users/{sid}/password", headers=headers, json={"password": "x" * 12}
        ).status_code
        == 403
    )


def test_sec14_anonymized_account_cannot_be_revived(client: TestClient, school: School) -> None:
    student = school["student_a"]
    headers = login(client, school["admin"].email)
    assert (
        client.post(f"/api/admin/users/{student.id}/anonymize", headers=headers).status_code == 200
    )
    revive = client.put(
        f"/api/admin/users/{student.id}/active", headers=headers, json={"active": True}
    )
    assert revive.status_code == 409
    password = client.post(
        f"/api/admin/users/{student.id}/password", headers=headers, json={"password": "x" * 12}
    )
    assert password.status_code == 409


def test_sec14_admin_cannot_reset_own_password_here(client: TestClient, school: School) -> None:
    admin = school["admin"]
    headers = login(client, admin.email)
    response = client.post(
        f"/api/admin/users/{admin.id}/password", headers=headers, json={"password": "x" * 12}
    )
    assert response.status_code == 400


def test_sec14_user_search_treats_wildcards_literally(client: TestClient, school: School) -> None:
    headers = login(client, school["admin"].email)
    assert client.get("/api/admin/users", headers=headers, params={"q": "%"}).json() == []
    assert client.get("/api/admin/users", headers=headers, params={"q": "_"}).json() == []
