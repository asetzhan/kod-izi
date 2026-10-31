"""Spec 14.1, "Рұқсаттар": a student sees only own data, a teacher only own groups."""

import pytest
from fastapi.testclient import TestClient

from app.core.roles import Role
from tests.conftest import PASSWORD, School, login


def test_sec14_unauthenticated_request_returns_401(client: TestClient) -> None:
    assert client.get("/api/me").status_code == 401


def test_sec14_invalid_token_returns_401(client: TestClient) -> None:
    response = client.get("/api/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


def test_sec14_student_reads_own_profile(client: TestClient, school: School) -> None:
    student = school["student_a"]
    headers = login(client, student.email)
    assert client.get("/api/me", headers=headers).json()["id"] == student.id
    assert client.get(f"/api/users/{student.id}", headers=headers).status_code == 200


def test_sec14_student_cannot_read_other_student(client: TestClient, school: School) -> None:
    headers = login(client, school["student_a"].email)
    response = client.get(f"/api/users/{school['student_b'].id}", headers=headers)
    assert response.status_code == 403


def test_sec14_student_gets_403_for_missing_user(client: TestClient, school: School) -> None:
    headers = login(client, school["student_a"].email)
    assert client.get("/api/users/999999", headers=headers).status_code == 403


def test_sec14_student_cannot_read_group(client: TestClient, school: School) -> None:
    headers = login(client, school["student_a"].email)
    assert client.get(f"/api/groups/{school['group_a'].id}", headers=headers).status_code == 403


def test_sec14_teacher_reads_student_of_own_group(client: TestClient, school: School) -> None:
    headers = login(client, school["teacher_a"].email)
    response = client.get(f"/api/users/{school['student_a'].id}", headers=headers)
    assert response.status_code == 200


def test_sec14_teacher_cannot_read_student_of_other_group(
    client: TestClient, school: School
) -> None:
    headers = login(client, school["teacher_a"].email)
    response = client.get(f"/api/users/{school['student_b'].id}", headers=headers)
    assert response.status_code == 403


def test_sec14_teacher_reads_own_group(client: TestClient, school: School) -> None:
    headers = login(client, school["teacher_a"].email)
    body = client.get(f"/api/groups/{school['group_a'].id}", headers=headers).json()
    assert [s["id"] for s in body["students"]] == [school["student_a"].id]


def test_sec14_teacher_cannot_read_other_group(client: TestClient, school: School) -> None:
    headers = login(client, school["teacher_a"].email)
    assert client.get(f"/api/groups/{school['group_b'].id}", headers=headers).status_code == 403


def test_sec14_coach_cannot_read_students(client: TestClient, school: School) -> None:
    headers = login(client, school["coach"].email)
    response = client.get(f"/api/users/{school['student_a'].id}", headers=headers)
    assert response.status_code == 403


@pytest.mark.parametrize("who", ["student_a", "teacher_a", "coach"])
@pytest.mark.parametrize(
    ("method", "path"),
    [("get", "/api/admin/users"), ("get", "/api/admin/audit-log"), ("post", "/api/admin/groups")],
)
def test_sec14_non_admin_roles_are_forbidden_on_admin_api(
    client: TestClient, school: School, who: str, method: str, path: str
) -> None:
    headers = login(client, school[who].email)
    response = client.request(method, path, headers=headers, json={"name": "X"})
    assert response.status_code == 403


def test_sec14_admin_reads_any_user_and_group(client: TestClient, school: School) -> None:
    headers = login(client, school["admin"].email)
    assert client.get(f"/api/users/{school['student_b'].id}", headers=headers).status_code == 200
    assert client.get(f"/api/groups/{school['group_b'].id}", headers=headers).status_code == 200
    assert client.get("/api/users/999999", headers=headers).status_code == 404


def test_sec14_admin_creates_user_who_can_log_in(client: TestClient, school: School) -> None:
    headers = login(client, school["admin"].email)
    response = client.post(
        "/api/admin/users",
        headers=headers,
        json={
            "email": "New.Teacher@Example.com",
            "full_name": "New Teacher",
            "password": PASSWORD,
            "roles": ["teacher", "coach"],
        },
    )
    assert response.status_code == 201
    assert response.json()["roles"] == ["coach", "teacher"]
    login(client, "new.teacher@example.com")
    duplicate = client.post(
        "/api/admin/users",
        headers=headers,
        json={
            "email": "new.teacher@example.com",
            "full_name": "Again",
            "password": PASSWORD,
            "roles": ["student"],
        },
    )
    assert duplicate.status_code == 409


def test_sec14_admin_builds_group(client: TestClient, school: School) -> None:
    headers = login(client, school["admin"].email)
    group = client.post("/api/admin/groups", headers=headers, json={"name": "IT-21"}).json()
    student_id = school["student_b"].id
    added = client.post(
        f"/api/admin/groups/{group['id']}/members", headers=headers, json={"user_id": student_id}
    )
    assert [s["id"] for s in added.json()["students"]] == [student_id]
    wrong_role = client.post(
        f"/api/admin/groups/{group['id']}/teachers", headers=headers, json={"user_id": student_id}
    )
    assert wrong_role.status_code == 400


def test_sec14_role_change_applies_to_existing_token(client: TestClient, school: School) -> None:
    teacher_headers = login(client, school["teacher_a"].email)
    group_path = f"/api/groups/{school['group_a'].id}"
    assert client.get(group_path, headers=teacher_headers).status_code == 200
    admin_headers = login(client, school["admin"].email)
    client.put(
        f"/api/admin/users/{school['teacher_a'].id}/roles",
        headers=admin_headers,
        json={"roles": [Role.COACH]},
    )
    assert client.get(group_path, headers=teacher_headers).status_code == 403


def test_sec14_admin_cannot_remove_own_admin_role(client: TestClient, school: School) -> None:
    admin = school["admin"]
    headers = login(client, admin.email)
    response = client.put(
        f"/api/admin/users/{admin.id}/roles", headers=headers, json={"roles": ["teacher"]}
    )
    assert response.status_code == 400
