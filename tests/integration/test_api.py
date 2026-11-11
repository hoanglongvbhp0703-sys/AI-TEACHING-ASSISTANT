import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from fastapi.testclient import TestClient

from app.db.seed import seed_demo
from app.main import create_app
from app.rag.backend import UnconfiguredRAG
from app.repositories.store import uid
from tests.conftest import auth, drain, payload, upload


def post_event(client, **kwargs):
    response = client.post("/api/v1/mock/events", headers=auth("adapter"), json=payload(**kwargs))
    assert response.status_code in {200, 202}, response.text
    return response.json()["data"]


def test_openapi_health_auth_and_no_secret_echo(rig):
    app, c, backend, clock = rig
    assert c.get("/api/v1/health").json()["data"]["sqlite"] == "ok"
    assert c.get("/api/v1/auth/me").status_code == 401
    assert c.get("/api/v1/auth/me", headers=auth("teacher-gs")).json()["data"]["class_ids"] == [
        "GS-KPI-01"
    ]
    spec = c.get("/openapi.json").json()
    assert sum(len(v) for v in spec["paths"].values()) == 51
    assert c.get("/docs").status_code == 200
    assert c.get("/api/v1/health").headers["x-request-id"]


def test_admin_resources_and_class_permissions(rig):
    app, c, _, _ = rig
    assert (
        c.post(
            "/api/v1/courses", headers=auth("teacher-gs"), json={"id": "NEW", "name": "New"}
        ).status_code
        == 403
    )
    assert (
        c.post(
            "/api/v1/users",
            headers=auth(),
            json={"id": "new-student", "display_name": "New student", "role": "student"},
        ).status_code
        == 201
    )
    assert (
        c.post(
            "/api/v1/courses", headers=auth(), json={"id": "NEW", "name": "New course"}
        ).status_code
        == 201
    )
    assert (
        c.post(
            "/api/v1/classes",
            headers=auth(),
            json={"id": "NEW-01", "name": "New class", "course_id": "NEW"},
        ).status_code
        == 201
    )
    assert (
        c.put(
            "/api/v1/classes/NEW-01/members/new-student", headers=auth(), json={"status": "active"}
        ).status_code
        == 200
    )
    assert (
        c.put(
            "/api/v1/classes/NEW-01/teachers/teacher-gs", headers=auth(), json={"is_active": True}
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/v1/group-bindings",
            headers=auth(),
            json={
                "class_id": "NEW-01",
                "external_group_id": "new-group",
                "display_name": "New group",
            },
        ).status_code
        == 201
    )
    assert (
        c.post(
            "/api/v1/external-identities",
            headers=auth(),
            json={"user_id": "new-student", "external_sender_id": "external-new"},
        ).status_code
        == 201
    )
    assert c.get("/api/v1/classes/NEW-01/members", headers=auth("teacher-ai")).status_code == 403
    assert (
        c.get("/api/v1/classes/NEW-01/members", headers=auth("teacher-gs")).json()["data"][0]["id"]
        == "new-student"
    )
    assert (
        c.post(
            "/api/v1/users",
            headers=auth(),
            json={"id": "new-student", "display_name": "Duplicate", "role": "student"},
        ).status_code
        == 409
    )


def test_trigger_empty_bot_ignored_and_strict_payload(rig):
    app, c, b, _ = rig
    for n, text in enumerate(["Chào cả lớp", "Hello /hoi test", "/hoiabc test"]):
        assert post_event(c, eid=str(n), text=text)["status"] == "ignored"
    assert post_event(c, eid="empty", text="/hoi")["outcome_code"] == "empty_question"
    bot = payload("bot")
    bot["is_bot_message"] = True
    assert (
        c.post("/api/v1/mock/events", headers=auth("adapter"), json=bot).json()["data"]["status"]
        == "ignored"
    )
    bad = payload("spoof")
    bad["class_id"] = "ML-DEMO-01"
    assert c.post("/api/v1/mock/events", headers=auth("adapter"), json=bad).status_code == 422
    assert c.post("/api/v1/webhooks/mock-zalo", json=payload()).status_code == 401
    drain(app)
    assert not b.contexts
    assert c.get("/api/v1/students/HV_GS_01/quota", headers=auth()).json()["data"]["used"] == 0
    with app.state.db.read() as s:
        assert not s.all("SELECT * FROM messages")
        assert not any(e["question_redacted"] for e in s.all("SELECT * FROM webhook_events"))


def test_event_dedup_and_ticket_outbox_once_under_concurrency(rig):
    app, c, b, _ = rig
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: post_event(c), range(2)))
    assert sorted(r["status"] for r in results) == ["duplicate_ignored", "queued"]
    drain(app)
    assert len(b.contexts) == 1
    assert c.get("/api/v1/students/HV_GS_01/quota", headers=auth()).json()["data"]["used"] == 1
    with app.state.db.read() as s:
        for table in ["support_tickets", "rag_runs", "quota_reservations", "outbound_messages"]:
            assert s.one(f"SELECT count(*) AS n FROM {table}")["n"] == 1
    assert post_event(c, text="/hoi Changed payload")["status"] == "duplicate_ignored"
    with app.state.db.read() as s:
        assert (
            s.one(
                "SELECT count(*) AS n FROM security_events WHERE reason_code='event_payload_mismatch'"
            )["n"]
            == 1
        )


def test_quota_across_classes_and_next_vietnam_day(rig):
    app, c, b, clock = rig
    for n in range(30):
        result = post_event(
            c,
            eid=f"e{n}",
            sender="student-shared",
            group="ZGROUP_GS01" if n < 20 else "ZGROUP_ML01",
        )
        assert result["status"] == "queued"
    assert post_event(c, eid="31", sender="student-shared")["outcome_code"] == "quota_exceeded"
    assert (
        c.get("/api/v1/students/student-shared/quota", headers=auth("student-shared")).json()[
            "data"
        ]["remaining"]
        == 0
    )
    clock.value += timedelta(days=1)
    assert (
        c.get("/api/v1/students/student-shared/quota", headers=auth()).json()["data"]["used"] == 0
    )
    drain(app)
    with app.state.db.read() as s:
        assert {r["local_date"] for r in s.all("SELECT * FROM quota_reservations")} == {
            "2026-11-10"
        }
        assert s.one("SELECT count(*) AS n FROM rag_runs")["n"] == 30


def test_quota_simultaneous_30th_slot(rig):
    app, c, _, _ = rig
    for i in range(29):
        post_event(c, eid=f"e{i}")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda n: post_event(c, eid=f"last{n}"), range(2)))
    assert sorted(r["status"] for r in results) == ["queued", "rejected"]
    assert c.get("/api/v1/students/HV_GS_01/quota", headers=auth()).json()["data"]["used"] == 30


def test_bot_off_nonmember_and_revoked_access_release_reservation(rig):
    app, c, b, _ = rig
    assert post_event(c, eid="wrong", group="ZGROUP_ML01")["outcome_code"] == "access_denied"
    accepted = post_event(c)
    assert (
        c.patch(
            "/api/v1/classes/GS-KPI-01/bot", headers=auth(), json={"bot_enabled": False}
        ).status_code
        == 200
    )
    assert post_event(c, eid="off")["status"] == "rejected"
    drain(app)
    assert not b.contexts
    assert c.get("/api/v1/students/HV_GS_01/quota", headers=auth()).json()["data"]["used"] == 0
    assert (
        c.get("/api/v1/events/" + accepted["event_key"], headers=auth()).json()["data"][
            "outcome_code"
        ]
        == "access_revoked"
    )


def test_shared_memory_pair_window_group_isolation_and_ttl(rig):
    app, c, b, clock = rig
    for i in range(7):
        post_event(c, eid=f"e{i}", sender="HV_GS_01" if i % 2 == 0 else "HV_GS_02")
        drain(app)
        clock.value += timedelta(seconds=1)
    assert len(b.contexts[-1].memory) == 5
    post_event(c, eid="ai", group="ZGROUP_ML01", sender="HV_ML_01")
    drain(app)
    assert b.contexts[-1].memory == []
    clock.value += timedelta(minutes=31)
    post_event(c, eid="new-session")
    drain(app)
    assert b.contexts[-1].memory == []


def test_document_lifecycle_hash_failure_retry_and_revoke(rig):
    app, c, b, _ = rig
    first = upload(c)
    assert first.status_code == 202, first.text
    info = first.json()["data"]
    did = info["document_id"]
    drain(app)
    assert (
        c.get("/api/v1/ingestion-jobs/" + info["job_id"], headers=auth("teacher-gs")).json()[
            "data"
        ]["document_state"]
        == "active"
    )
    assert c.get("/api/v1/documents/" + did, headers=auth("teacher-ai")).status_code == 403
    same = c.post(
        f"/api/v1/documents/{did}/versions",
        headers=auth("teacher-gs"),
        files={
            "file": ("faq.json", b'{"question":"Question","answer":"Answer"}', "application/json")
        },
    )
    assert same.status_code == 200 and same.json()["data"]["status"] == "unchanged"
    b.fail_index = True
    new = c.post(
        f"/api/v1/documents/{did}/versions",
        headers=auth("teacher-gs"),
        files={
            "file": ("faq.json", b'{"question":"New","answer":"New answer"}', "application/json")
        },
    ).json()["data"]
    drain(app)
    current = c.get("/api/v1/documents/" + did, headers=auth("teacher-gs")).json()["data"]
    assert current["active_version_id"] == info["version_id"]
    assert (
        c.get("/api/v1/ingestion-jobs/" + new["job_id"], headers=auth("teacher-gs")).json()["data"][
            "status"
        ]
        == "failed"
    )
    b.fail_index = False
    retried = c.post(
        "/api/v1/ingestion-jobs/" + new["job_id"] + "/retry", headers=auth("teacher-gs")
    )
    assert retried.status_code == 202
    drain(app)
    assert (
        c.get("/api/v1/documents/" + did, headers=auth("teacher-gs")).json()["data"][
            "active_version_id"
        ]
        == new["version_id"]
    )
    assert c.delete("/api/v1/documents/" + did, headers=auth("teacher-gs")).status_code == 200
    assert (
        c.get("/api/v1/documents/" + did, headers=auth("teacher-gs")).json()["data"][
            "active_version_id"
        ]
        is None
    )


def test_document_scope_and_file_validation(rig):
    app, c, b, _ = rig
    assert upload(c, scopes=["class:ML-DEMO-01"]).status_code == 403
    assert upload(c, scopes=["course:GS_KPI"]).status_code == 202
    assert (
        upload(c, user="admin", scopes=["class:GS-KPI-01", "class:ML-DEMO-01"]).status_code == 202
    )
    result = upload(
        c,
        user="admin",
        scopes=["class:GS-KPI-01", "class:ML-DEMO-01"],
        config={"chunk_size": 512, "chunk_overlap": 64},
    )
    assert result.status_code == 202
    drain(app)
    assert upload(c, data=b"not JSON").status_code == 422
    bad = c.post(
        "/api/v1/documents",
        headers=auth(),
        data={"title": "bad", "topic": "test", "scope_ids": '["class:GS-KPI-01"]'},
        files={"file": ("../../x.exe", b"data", "application/octet-stream")},
    )
    assert bad.status_code == 422


def test_answer_citation_validation_and_stale_memory(rig):
    app, c, b, clock = rig
    info = upload(c).json()["data"]
    drain(app)
    b.reply_mode = "answer"
    post_event(c)
    drain(app)
    out = c.get("/api/v1/mock/groups/ZGROUP_GS01/messages", headers=auth("HV_GS_01")).json()[
        "data"
    ]["items"]
    assert out[0]["citations"][0]["document_version_id"] == info["version_id"]
    assert (
        c.get("/api/v1/mock/groups/ZGROUP_ML01/messages", headers=auth("HV_GS_01")).status_code
        == 403
    )
    c.delete("/api/v1/documents/" + info["document_id"], headers=auth("teacher-gs"))
    clock.value += timedelta(seconds=1)
    post_event(c, eid="followup")
    drain(app)
    assert b.contexts[-1].memory == []
    b.reply_mode = "invalid"
    post_event(c, eid="invalid")
    drain(app)
    with app.state.db.read() as s:
        assert (
            s.one(
                "SELECT count(*) AS n FROM security_events WHERE reason_code='invalid_or_stale_citation'"
            )["n"]
            == 1
        )
        assert s.one("SELECT count(*) AS n FROM support_tickets")["n"] == 2


def test_revoke_between_generate_and_commit_handoffs(rig):
    app, c, b, _ = rig
    info = upload(c).json()["data"]
    drain(app)
    b.reply_mode = "answer"

    def revoke(_):
        with app.state.db.read() as s:
            user = s.one("SELECT * FROM users WHERE id='teacher-gs'")
        app.state.documents.revoke(user, info["document_id"], "test-race")

    b.before_answer = revoke
    post_event(c)
    drain(app)
    with app.state.db.read() as s:
        assert (
            s.one("SELECT outcome_code FROM webhook_events")["outcome_code"]
            == "insufficient_evidence"
        )
        assert s.one("SELECT citations_json FROM outbound_messages")["citations_json"] == "[]"


def test_revoke_between_generation_and_send_handoffs(rig):
    app, c, b, _ = rig
    info = upload(c).json()["data"]
    drain(app)
    b.reply_mode = "answer"
    post_event(c)
    app.state.events.process_one()
    c.delete("/api/v1/documents/" + info["document_id"], headers=auth("teacher-gs"))
    drain(app)
    out = c.get("/api/v1/mock/groups/ZGROUP_GS01/messages", headers=auth("HV_GS_01")).json()[
        "data"
    ]["items"][0]
    assert out["citations"] == [] and out["ticket_id"]


def test_ticket_reply_faq_and_revision_lifecycle(rig):
    app, c, b, _ = rig
    post_event(c)
    drain(app)
    ticket = c.get("/api/v1/tickets", headers=auth("teacher-gs")).json()["data"]["items"][0]
    tid = ticket["id"]
    assert c.get("/api/v1/tickets/" + tid, headers=auth("teacher-ai")).status_code == 403
    assert (
        c.post(
            f"/api/v1/tickets/{tid}/assign",
            headers=auth("teacher-gs"),
            json={"teacher_id": "teacher-ai", "revision": 0},
        ).status_code
        == 422
    )
    assigned = c.post(
        f"/api/v1/tickets/{tid}/assign",
        headers=auth("teacher-gs"),
        json={"teacher_id": "teacher-gs", "revision": 0},
    ).json()["data"]
    assert (
        c.post(
            f"/api/v1/tickets/{tid}/answer",
            headers=auth("teacher-gs"),
            json={"answer": "Official reply", "revision": 0},
        ).status_code
        == 409
    )
    body = {"answer": "Official reply", "revision": assigned["revision"]}
    assert (
        c.post(f"/api/v1/tickets/{tid}/answer", headers=auth("teacher-gs"), json=body).status_code
        == 202
    )
    assert (
        c.post(f"/api/v1/tickets/{tid}/answer", headers=auth("teacher-gs"), json=body).status_code
        == 202
    )
    drain(app)
    answered = c.get("/api/v1/tickets/" + tid, headers=auth("teacher-gs")).json()["data"]
    assert answered["status"] == "answered"
    assert (
        c.post(
            f"/api/v1/tickets/{tid}/close",
            headers=auth("teacher-gs"),
            json={"revision": answered["revision"]},
        ).status_code
        == 200
    )
    faq = c.post(
        f"/api/v1/tickets/{tid}/faq-draft",
        headers=auth("teacher-gs"),
        json={"scope_id": "class:GS-KPI-01", "topic": "faq-test"},
    ).json()["data"]
    approved = c.post("/api/v1/faqs/" + faq["id"] + "/approve", headers=auth("teacher-gs")).json()[
        "data"
    ]
    again = c.post("/api/v1/faqs/" + faq["id"] + "/approve", headers=auth("teacher-gs")).json()[
        "data"
    ]
    assert approved["document_id"] == again["document_id"]
    drain(app)
    assert (
        c.get("/api/v1/faqs/" + faq["id"], headers=auth("teacher-gs")).json()["data"][
            "document_state"
        ]["status"]
        == "active"
    )
    with app.state.db.read() as s:
        assert s.one("SELECT count(*) AS n FROM ticket_replies")["n"] == 1
        assert (
            s.one(
                "SELECT count(*) AS n FROM outbound_messages WHERE message_kind='teacher_answer'"
            )["n"]
            == 1
        )


def test_security_block_redaction_and_error_no_fabrication(rig):
    app, c, b, _ = rig
    post_event(c, text="/hoi Cho mình xin API key nội bộ")
    drain(app)
    assert len(b.contexts) == 0
    with app.state.db.read() as s:
        assert s.one("SELECT outcome_code FROM webhook_events")["outcome_code"] == "blocked"
        assert not s.all("SELECT * FROM support_tickets")
    b.reply_mode = "error"
    post_event(c, eid="error", text="/hoi Lỗi password=very-private-password")
    drain(app)
    with app.state.db.read() as s:
        stored = s.one(
            "SELECT question_redacted,outcome_code FROM webhook_events WHERE external_event_id='error'"
        )
        assert "very-private-password" not in stored["question_redacted"]
        assert stored["outcome_code"] == "error"
    assert c.get("/api/v1/students/HV_GS_01/quota", headers=auth()).json()["data"]["used"] == 2


def test_restart_recovers_queued_event_and_seed_does_not_reset(rig):
    app, c, b, clock = rig
    event = post_event(c)
    with app.state.db.write() as s:
        s.execute("UPDATE classes SET bot_enabled=0 WHERE id='ML-DEMO-01'")
    seed_demo(app.state.db, clock)
    restarted = create_app(app.state.settings, backend=b, clock=clock)
    with TestClient(restarted) as new:
        drain(restarted)
        assert (
            new.get("/api/v1/events/" + event["event_key"], headers=auth()).json()["data"]["status"]
            == "completed"
        )
        assert (
            new.get("/api/v1/students/HV_GS_01/quota", headers=auth()).json()["data"]["used"] == 1
        )
        assert not next(
            r
            for r in new.get("/api/v1/classes", headers=auth()).json()["data"]
            if r["id"] == "ML-DEMO-01"
        )["bot_enabled"]


def test_unconfigured_worker_never_consumes_index_jobs(rig):
    app, c, b, clock = rig
    app.state.worker.backend = UnconfiguredRAG()
    response = upload(c)
    drain(app)
    job = c.get(
        "/api/v1/ingestion-jobs/" + response.json()["data"]["job_id"], headers=auth()
    ).json()["data"]
    assert job["status"] == "queued" and job["attempts"] == 0
    assert job["progress"]["percent"] == 0
    assert (
        c.get("/api/v1/documents/" + response.json()["data"]["document_id"], headers=auth()).json()[
            "data"
        ]["active_version_id"]
        is None
    )


def test_throttle_report_access_and_cursor(rig):
    app, c, b, clock = rig
    app.state.settings.rate_limit_enabled = True
    for i in range(5):
        assert post_event(c, eid=str(i))["status"] == "queued"
    assert post_event(c, eid="throttle")["outcome_code"] == "rate_limited"
    drain(app)
    first = c.get(
        "/api/v1/mock/groups/ZGROUP_GS01/messages?limit=2", headers=auth("HV_GS_01")
    ).json()["data"]
    next_page = c.get(
        "/api/v1/mock/groups/ZGROUP_GS01/messages",
        params={"after": first["next_cursor"], "limit": 100},
        headers=auth("HV_GS_01"),
    ).json()["data"]
    assert not {r["id"] for r in first["items"]}.intersection(r["id"] for r in next_page["items"])
    assert len(first["items"]) + len(next_page["items"]) == 6
    clock.value += timedelta(seconds=1)
    report = c.get("/api/v1/reports/summary", headers=auth("teacher-gs")).json()["data"]
    assert report["accepted_questions"] == 5 and report["tickets"] == 5
    assert (
        c.get(
            "/api/v1/reports/summary?class_id=ML-DEMO-01", headers=auth("teacher-gs")
        ).status_code
        == 403
    )
    assert (
        c.get("/api/v1/reports/summary?from=2026-11-01T00:00:00", headers=auth()).status_code == 422
    )


def test_size_limits_invalid_metadata_and_raw_inputs_not_echoed(rig):
    app, c, _, _ = rig
    bad = payload()
    bad["private_secret"] = "do-not-echo"
    response = c.post("/api/v1/mock/events", headers=auth("adapter"), json=bad)
    assert response.status_code == 422 and "do-not-echo" not in response.text
    app.state.settings.max_request_bytes = 100
    # Middleware closes over the same Settings instance.
    response = c.post("/api/v1/mock/events", headers=auth("adapter"), content=b"x" * 101)
    assert response.status_code == 413


def test_webhook_secret_disabled_user_and_error_envelopes(rig):
    app, c, _, _ = rig
    accepted = c.post(
        "/api/v1/webhooks/mock-zalo",
        headers={"X-Webhook-Secret": app.state.settings.mock_webhook_secret},
        json=payload(),
    )
    assert accepted.status_code == 202
    assert (
        c.patch("/api/v1/users/HV_GS_01", headers=auth(), json={"is_active": False}).status_code
        == 200
    )
    assert c.get("/api/v1/auth/me", headers=auth("HV_GS_01")).status_code == 401
    drain(app)
    assert c.get("/api/v1/students/HV_GS_01/quota", headers=auth()).json()["data"]["used"] == 0
    for response in [c.get("/missing"), c.delete("/api/v1/health")]:
        assert set(response.json()) == {"data", "error", "request_id"}


def test_revoke_during_index_queues_cleanup_and_cannot_reactivate(rig):
    app, c, b, _ = rig
    info = upload(c).json()["data"]
    original = b.index

    def index_and_revoke(version, path, scopes, config):
        result = original(version, path, scopes, config)
        with app.state.db.read() as s:
            user = s.one("SELECT * FROM users WHERE id='teacher-gs'")
        app.state.documents.revoke(user, info["document_id"], "test-index-race")
        return result

    b.index = index_and_revoke
    drain(app)
    doc = c.get("/api/v1/documents/" + info["document_id"], headers=auth("teacher-gs")).json()[
        "data"
    ]
    assert doc["status"] == "revoked" and doc["active_version_id"] is None
    assert b.cleanups == [(info["document_id"], info["version_id"])]


def test_expired_processing_lease_recovery_without_second_quota(rig):
    app, c, b, clock = rig
    event = post_event(c)
    claimed = app.state.events.claim()
    assert claimed["event_key"] == event["event_key"]
    clock.value += timedelta(seconds=app.state.settings.job_lease_seconds + 1)
    drain(app)
    assert len(b.contexts) == 1
    with app.state.db.read() as s:
        assert s.one("SELECT attempts,status FROM webhook_events") == {
            "attempts": 2,
            "status": "completed",
        }
        assert s.one("SELECT accepted_count FROM daily_usage")["accepted_count"] == 1
        assert s.one("SELECT count(*) AS n FROM outbound_messages")["n"] == 1


def test_report_cost_unknown_and_no_join_multiplication(rig):
    app, c, b, clock = rig
    post_event(c)
    drain(app)
    with app.state.db.write() as s:
        run = s.one("SELECT * FROM rag_runs")
        for index, cost in enumerate([1200, None, 300]):
            s.insert(
                "rag_run_attempts",
                id=uid(),
                rag_run_id=run["id"],
                stage="generate",
                attempt_no=index + 1,
                call_key=f"call-{index}",
                provider="test-only",
                model="test-only",
                status="unknown" if cost is None else "succeeded",
                estimated_cost_usd_micros=cost,
                input_tokens=10 if cost is not None else None,
                output_tokens=2 if cost is not None else None,
                started_at=clock.stamp(),
            )
    clock.value += timedelta(seconds=1)
    usage = c.get("/api/v1/reports/summary", headers=auth("teacher-gs")).json()["data"][
        "question_usage"
    ]
    assert usage == {
        "known_cost_usd_micros": 1500,
        "unknown_cost_calls": 1,
        "input_tokens_known": 20,
        "output_tokens_known": 4,
        "calls": 3,
    }


def test_stale_lease_cannot_publish_result(rig):
    app, c, b, _ = rig
    post_event(c)

    def replace_claim(context):
        with app.state.db.write() as s:
            s.update("webhook_events", "event_key", context.event_key, lease_token="another-owner")

    b.before_answer = replace_claim
    app.state.events.process_one()
    with app.state.db.read() as s:
        assert not s.all("SELECT * FROM support_tickets")
        assert not s.all("SELECT * FROM outbound_messages")


def test_metadata_change_same_file_creates_new_version(rig):
    app, c, b, _ = rig
    info = upload(c).json()["data"]
    drain(app)
    result = c.post(
        "/api/v1/documents/" + info["document_id"] + "/versions",
        headers=auth("teacher-gs"),
        data={"extraction_config": json.dumps({"chunk_size": 512})},
        files={
            "file": ("faq.json", b'{"question":"Question","answer":"Answer"}', "application/json")
        },
    )
    assert result.status_code == 202
    assert result.json()["data"]["version_id"] != info["version_id"]
