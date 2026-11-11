from datetime import timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.core.passwords import hash_password
from app.services.auth_service import COOKIE
from tests.conftest import upload

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


def support(
    client, question="Em cần giảng viên kiểm tra bài tập", cid="GS-KPI-01", request_id=None
):
    return client.post(
        "/api/v1/support-requests",
        json={
            "class_id": cid,
            "question": question,
            "client_request_id": request_id or str(uuid4()),
        },
    )


def test_portal_html_assets_and_no_secrets_exposed(portal):
    app, c, _ = portal
    for path in ["/", "/portal", "/portal-assets/portal.css", "/portal-assets/portal.js"]:
        response = c.get(path)
        assert response.status_code == 200
        assert app.state.settings.mock_webhook_secret not in response.text
        for token in app.state.settings.auth_tokens_json:
            assert token not in response.text
    assert "Cổng học tập" in c.get("/portal").text
    assert c.get("/api/v1/health").json()["data"]["rag_jobs_enabled"] is False


def test_demo_cookie_auth_logout_and_role_checks(portal):
    app, c, _ = portal
    assert c.get("/api/v1/demo/accounts").status_code == 404
    response = login(c, "HV_GS_01")
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=strict" in response.headers["set-cookie"].lower()
    assert c.cookies.get(COOKIE)
    assert c.get("/api/v1/auth/me").json()["data"]["role"] == "student"
    assert c.get("/api/v1/users").status_code == 403
    assert c.get("/api/v1/documents").status_code == 403
    assert c.post("/api/v1/auth/logout").status_code == 200
    assert c.get("/api/v1/auth/me").status_code == 401
    assert c.post("/api/v1/demo/session", json={"user_id": "adapter"}).status_code == 404


def test_cookie_expiry_disabled_account_and_demo_switch(portal):
    app, c, clock = portal
    login(c, "HV_GS_01")
    clock.value += timedelta(hours=9)
    assert c.get("/api/v1/auth/me").status_code == 401
    login(c, "HV_GS_01")
    with app.state.db.write() as s:
        s.execute("UPDATE users SET is_active=0 WHERE id='HV_GS_01'")
    assert c.get("/api/v1/auth/me").status_code == 401
    assert (
        c.post(
            "/api/v1/auth/login", json={"username": "hv_gs_01", "password": TEST_PASSWORD}
        ).status_code
        == 401
    )
    assert c.get("/api/v1/demo/accounts").status_code == 404
    assert c.post("/api/v1/demo/session", json={"user_id": "admin"}).status_code == 404


def test_student_support_idempotency_and_ownership(portal):
    app, c, _ = portal
    login(c, "HV_GS_01")
    client_id = str(uuid4())
    first = support(c, request_id=client_id)
    assert first.status_code == 201, first.text
    ticket = first.json()["data"]
    repeated = support(c, request_id=client_id)
    assert repeated.status_code == 200 and repeated.json()["data"]["id"] == ticket["id"]
    assert support(c, question="Nội dung khác", request_id=client_id).status_code == 409
    assert support(c, cid="ML-DEMO-01").status_code == 403
    assert c.get("/api/v1/students/HV_GS_01/quota").json()["data"]["used"] == 0
    login(c, "HV_ML_01")
    assert c.get("/api/v1/support-requests/" + ticket["id"]).status_code == 404
    assert c.get("/api/v1/support-requests").json()["data"]["total"] == 0
    with app.state.db.read() as s:
        assert s.one("SELECT count(*) AS n FROM support_tickets")["n"] == 1
        assert not s.all("SELECT * FROM rag_runs")
        assert not s.all("SELECT * FROM quota_reservations")


def test_student_teacher_reply_close_and_faq_without_rag(portal):
    app, c, _ = portal
    login(c, "HV_GS_01")
    tid = support(c).json()["data"]["id"]
    login(c, "teacher-ai")
    assert c.get("/api/v1/tickets/" + tid).status_code == 403
    login(c, "teacher-gs")
    detail = c.get("/api/v1/tickets/" + tid).json()["data"]
    reply = c.post(
        f"/api/v1/tickets/{tid}/answer",
        json={"answer": "Em kiểm tra lại định dạng cột ngày.", "revision": detail["revision"]},
    )
    assert reply.status_code == 202, reply.text
    login(c, "HV_GS_01")
    assert c.get("/api/v1/support-requests/" + tid).json()["data"]["answer_redacted"] is None
    assert app.state.worker.tick() == 1
    own = c.get("/api/v1/support-requests/" + tid).json()["data"]
    assert own["status"] == "answered" and "định dạng" in own["answer_redacted"]
    login(c, "teacher-gs")
    detail = c.get("/api/v1/tickets/" + tid).json()["data"]
    assert (
        c.post(f"/api/v1/tickets/{tid}/close", json={"revision": detail["revision"]}).status_code
        == 200
    )
    faq = c.post(
        f"/api/v1/tickets/{tid}/faq-draft", json={"scope_id": "class:GS-KPI-01", "topic": "Bài tập"}
    ).json()["data"]
    approved = c.post(f"/api/v1/faqs/{faq['id']}/approve")
    assert approved.status_code == 202, approved.text
    assert c.get("/api/v1/tickets/" + tid).json()["data"]["faq"]["status"] == "approved"
    with app.state.db.read() as s:
        job = s.one("SELECT status,error_code FROM ingestion_jobs")
        assert job == {"status": "cancelled", "error_code": "rag_deferred"}
        assert s.one("SELECT active_version_id FROM documents")["active_version_id"] is None
        assert not s.all("SELECT * FROM rag_runs")
    app.state.worker.tick()


def test_stored_documents_replace_unchanged_and_revoke_without_indexing(portal):
    app, c, _ = portal
    login(c, "teacher-gs")
    # No Bearer header: these are the same cookie-authenticated calls the FE makes.
    fields = {
        "title": "Tài liệu cổng học tập",
        "topic": "Bài tập",
        "scope_ids": '["class:GS-KPI-01"]',
    }
    files = {"file": ("faq.json", b'{"question":"Q","answer":"A"}', "application/json")}
    result = c.post("/api/v1/documents", data=fields, files=files)
    assert result.status_code == 201 and result.json()["data"]["status"] == "stored"
    did = result.json()["data"]["document_id"]
    assert (
        c.post(f"/api/v1/documents/{did}/versions", files=files).json()["data"]["status"]
        == "unchanged"
    )
    changed = {"file": ("faq.json", b'{"question":"Q2","answer":"A2"}', "application/json")}
    assert c.post(f"/api/v1/documents/{did}/versions", files=changed).status_code == 201
    assert len(c.get("/api/v1/documents/" + did).json()["data"]["versions"]) == 2
    assert c.get("/api/v1/documents").json()["data"]["items"][0]["latest_version"] == 2
    app.state.worker.tick()
    with app.state.db.read() as s:
        assert not s.all("SELECT * FROM document_chunks")
        assert not s.all("SELECT * FROM ingestion_jobs WHERE status IN ('queued','processing')")
    assert c.delete("/api/v1/documents/" + did).status_code == 200
    app.state.worker.tick()
    with app.state.db.read() as s:
        assert not s.all("SELECT * FROM cleanup_jobs WHERE status IN ('queued','processing')")


def test_admin_user_class_enrollment_and_new_user_login(portal):
    app, c, _ = portal
    login(c, "admin")
    assert (
        c.post(
            "/api/v1/users",
            json={
                "id": "portal-student",
                "display_name": "Học viên mới",
                "role": "student",
                "username": "portal-student",
                "password": TEST_PASSWORD,
            },
        ).status_code
        == 201
    )
    assert (
        c.post("/api/v1/courses", json={"id": "PORTAL", "name": "Khóa thực hành"}).status_code
        == 201
    )
    assert (
        c.post(
            "/api/v1/classes",
            json={"id": "PORTAL-01", "course_id": "PORTAL", "name": "Lớp thực hành"},
        ).status_code
        == 201
    )
    assert (
        c.put(
            "/api/v1/classes/PORTAL-01/members/portal-student", json={"status": "active"}
        ).status_code
        == 200
    )
    assert (
        c.put("/api/v1/classes/PORTAL-01/teachers/teacher-gs", json={"is_active": True}).status_code
        == 200
    )
    assert (
        c.post(
            "/api/v1/group-bindings",
            json={
                "class_id": "PORTAL-01",
                "external_group_id": "PORTAL-GROUP",
                "display_name": "Nhóm thực hành",
            },
        ).status_code
        == 201
    )
    assert c.patch("/api/v1/classes/PORTAL-01/bot", json={"bot_enabled": False}).status_code == 200
    login(c, "portal-student")
    assert [r["id"] for r in c.get("/api/v1/classes").json()["data"]] == ["PORTAL-01"]
    assert c.get("/api/v1/classes/PORTAL-01/teachers").json()["data"][0]["id"] == "teacher-gs"
    assert (
        support(c, cid="PORTAL-01").status_code == 201
    )  # Manual support is independent of bot switch.
    login(c, "admin")
    assert c.get("/api/v1/reports/summary").status_code == 200
    assert (
        c.put(
            "/api/v1/classes/PORTAL-01/members/portal-student", json={"status": "suspended"}
        ).status_code
        == 200
    )
    login(c, "portal-student")
    assert support(c, cid="PORTAL-01").status_code == 403


def test_paused_portal_worker_does_not_consume_queued_rag_work(portal):
    app, c, _ = portal
    app.state.settings.rag_jobs_enabled = True
    queued = upload(c).json()["data"]
    app.state.settings.rag_jobs_enabled = False
    app.state.worker.tick()
    with app.state.db.read() as s:
        assert (
            s.one("SELECT status FROM ingestion_jobs WHERE id=:j", j=queued["job_id"])["status"]
            == "queued"
        )
