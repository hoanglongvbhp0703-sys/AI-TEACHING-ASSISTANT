from datetime import timedelta
from unittest.mock import Mock

import pytest

from app.core.passwords import hash_password

TEST_PASSWORD = "Portal test password 2026!"
TEST_HASH = hash_password(TEST_PASSWORD)


@pytest.fixture
def portal(rig):
    app, client, backend, clock = rig
    app.state.settings.rag_jobs_enabled = False
    with app.state.db.write() as store:
        for user in store.all("SELECT id FROM users WHERE role != 'service'"):
            app.state.auth.save_credentials(
                store, user["id"], user["id"].lower(), TEST_HASH, clock.stamp()
            )
    spies = []
    for name in ["answer", "index", "cleanup"]:
        spy = Mock(side_effect=AssertionError("RAG must not run in the portal phase"))
        setattr(backend, name, spy)
        spies.append(spy)
    yield app, client, clock
    for spy in spies:
        spy.assert_not_called()


def login(client, user):
    response = client.post(
        "/api/v1/auth/login", json={"username": user.lower(), "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response


def test_portal_staff_cookie_login_logout(portal):
    app, c, clock = portal
    for path in ["/portal", "/portal-assets/portal.js", "/portal-assets/portal.css"]:
        assert c.get(path).status_code == 200
    response = login(c, "teacher-gs")
    assert "httponly" in response.headers["set-cookie"].lower()
    assert c.get("/api/v1/auth/me").json()["data"]["role"] == "teacher"
    assert c.get("/api/v1/users").status_code == 403
    assert c.get("/api/v1/documents").status_code == 200
    c.post("/api/v1/auth/logout")
    assert c.get("/api/v1/auth/me").status_code == 401


def test_portal_expiry_and_disabled_teacher(portal):
    app, c, clock = portal
    login(c, "teacher-gs")
    clock.value += timedelta(hours=9)
    assert c.get("/api/v1/auth/me").status_code == 401
    login(c, "teacher-gs")
    with app.state.db.write() as s:
        s.execute("UPDATE users SET is_active=0 WHERE id='teacher-gs'")
    assert c.get("/api/v1/auth/me").status_code == 401


def test_student_portal_and_enrollment_routes_are_removed(portal):
    app, c, clock = portal
    login(c, "admin")
    assert (
        c.post(
            "/api/v1/users", json={"id": "x", "display_name": "Old role", "role": "student"}
        ).status_code
        == 422
    )
    assert c.get("/api/v1/auth/options?role=student").status_code == 422
    for path in [
        "/api/v1/support-requests",
        "/api/v1/classes/GS-KPI-01/members",
        "/api/v1/students/old/quota",
    ]:
        assert c.get(path).status_code == 404
    assert (
        c.post(
            "/api/v1/auth/login",
            json={"username": "old", "password": TEST_PASSWORD, "role": "student"},
        ).status_code
        == 422
    )
    assert "Học viên</option>" not in c.get("/portal").text


def test_admin_can_create_teacher_and_class_without_roster(portal):
    app, c, clock = portal
    login(c, "admin")
    assert (
        c.post(
            "/api/v1/users",
            json={
                "id": "new-teacher",
                "display_name": "Teacher",
                "role": "teacher",
                "username": "new-teacher",
                "password": TEST_PASSWORD,
            },
        ).status_code
        == 201
    )
    assert (
        c.post(
            "/api/v1/classes", json={"id": "NEW", "name": "New", "course_id": "ML-DEMO"}
        ).status_code
        == 201
    )
    c.post("/api/v1/auth/logout")
    login(c, "new-teacher")
    assert c.get("/api/v1/classes").json()["data"] == []
