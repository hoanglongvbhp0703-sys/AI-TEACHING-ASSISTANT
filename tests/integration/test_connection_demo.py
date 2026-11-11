import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.integrations.mock_zalo_adapter import sign_payload
from app.simulator import create_simulator

BUSINESS_TABLES = [
    "webhook_events",
    "daily_usage",
    "quota_reservations",
    "conversation_sessions",
    "messages",
    "support_tickets",
    "rag_runs",
    "rag_run_attempts",
    "outbound_messages",
]


def counts(app):
    with app.state.db.read() as s:
        return {
            table: s.one(f"SELECT count(*) AS n FROM {table}")["n"] for table in BUSINESS_TABLES
        }


@pytest.fixture
def connection(rig, monkeypatch):
    app, backend_client, rag, clock = rig
    app.state.settings.mock_webhook_mode = "connection"
    simulator = create_simulator(app.state.settings, clock=clock)
    with TestClient(simulator) as client:
        delivered = []

        def to_simulator(url, **kwargs):
            delivered.append(url)
            return client.post("/api/mock/replies", **kwargs)

        monkeypatch.setattr(app.state.connection_bridge.client, "post", to_simulator)
        monkeypatch.setattr(
            simulator.state.client,
            "post",
            lambda url, **kwargs: backend_client.post("/api/v1/webhooks/mock-zalo", **kwargs),
        )
        yield app, client, simulator, rag, delivered, to_simulator


def test_plain_message_round_trip_bypasses_business(connection):
    app, c, _, rag, delivered, _ = connection
    before = counts(app)
    response = c.post("/api/mock/messages", json={"text": "Xin chào, kiểm tra đường truyền"})
    assert response.status_code == 200
    item = response.json()["data"]
    assert item["http_status"] == 200 and item["error"] is None
    assert item["receipt"]["data"]["callback_status"] == "delivered"
    assert item["callback"]["reply_to_event_id"] == item["event_id"]
    assert "Xin chào, kiểm tra đường truyền" in item["callback"]["text"]
    assert len(delivered) == 1 and counts(app) == before and rag.contexts == []
    assert c.get("/api/mock/messages").json()["data"][0]["callback"] == item["callback"]
    assert "raw" not in item


def test_resend_same_event_keeps_one_callback(connection):
    app, c, _, _, delivered, _ = connection
    item = c.post("/api/mock/messages", json={"text": "Gửi lại một lần"}).json()["data"]
    repeated = c.post("/api/mock/messages/" + item["event_id"] + "/retry").json()["data"]
    assert repeated["receipt"]["data"]["status"] == "duplicate_ignored"
    assert repeated["callback"]["reply_id"] == item["callback"]["reply_id"]
    assert len(delivered) == 1 and len(c.get("/api/mock/messages").json()["data"]) == 1


def test_failed_callback_is_not_reported_as_delivered_and_can_retry(connection, monkeypatch):
    app, c, _, _, delivered, original = connection

    def disconnected(*args, **kwargs):
        raise httpx.ConnectError("Test callback disconnected")

    monkeypatch.setattr(app.state.connection_bridge.client, "post", disconnected)
    item = c.post("/api/mock/messages", json={"text": "Callback chưa chạy"}).json()["data"]
    assert item["http_status"] == 502 and item["callback"] is None and item["error"]
    monkeypatch.setattr(app.state.connection_bridge.client, "post", original)
    retried = c.post("/api/mock/messages/" + item["event_id"] + "/retry").json()["data"]
    assert retried["http_status"] == 200 and retried["callback"] and not retried["error"]
    assert len(delivered) == 1


def test_connection_only_header_prevents_accidental_business_processing(connection):
    app, c, _, rag, _, _ = connection
    app.state.settings.mock_webhook_mode = "business"
    before = counts(app)
    item = c.post("/api/mock/messages", json={"text": "/hoi Không chạy nghiệp vụ"}).json()["data"]
    assert item["http_status"] == 409 and item["callback"] is None
    assert counts(app) == before and rag.contexts == []


def test_callback_rejects_unsigned_request(connection):
    _, c, _, _, _, _ = connection
    assert c.post("/api/mock/replies", json={}).status_code == 401


def test_callback_rejects_unknown_event(connection):
    app, c, _, _, _, _ = connection
    raw = json.dumps(
        {
            "reply_id": "unknown",
            "reply_to_event_id": "unknown",
            "group_id": "ZGROUP_GS01",
            "text": "Không có tin gốc",
        }
    ).encode()
    timestamp = str(int(app.state.clock.now().timestamp()))
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Timestamp": timestamp,
        "X-Webhook-Signature": sign_payload(app.state.settings.mock_webhook_secret, timestamp, raw),
    }
    assert c.post("/api/mock/replies", content=raw, headers=headers).status_code == 404


def test_simulator_page_health_and_missing_retry(connection):
    _, c, _, _, _, _ = connection
    response = c.get("/")
    assert response.status_code == 200 and "Giả lập nhóm chat" in response.text
    assert "/api/mock/messages" in response.text
    assert c.get("/health").json()["data"]["mode"] == "simulator"
    assert c.post("/api/mock/messages/missing/retry").status_code == 404


def test_transport_accepts_plain_messages_without_class_enrollment(connection):
    app, c, _, rag, _, _ = connection
    before = counts(app)
    item = c.post(
        "/api/mock/messages",
        json={
            "text": "Chỉ thử mạng",
            "group_id": "TRANSPORT_TEST_GROUP",
            "sender_id": "TEST_SENDER",
        },
    ).json()["data"]
    assert item["callback"]["group_id"] == "TRANSPORT_TEST_GROUP"
    assert counts(app) == before and not rag.contexts


def test_history_and_retry_are_scoped_to_group(connection):
    app, c, _, _, _, _ = connection
    ml = c.post(
        "/api/mock/messages",
        json={"text": "ML private history", "group_id": "ML-GROUP", "sender_id": "ML-STUDENT"},
    ).json()["data"]
    gs = c.post("/api/mock/messages", json={"text": "GS private history"}).json()["data"]
    assert [
        m["event_id"] for m in c.get("/api/mock/messages?group_id=ML-GROUP").json()["data"]
    ] == [ml["event_id"]]
    assert [
        m["event_id"] for m in c.get("/api/mock/messages?group_id=ZGROUP_GS01").json()["data"]
    ] == [gs["event_id"]]
    assert c.get("/api/mock/messages?group_id=EMPTY").json()["data"] == []
    assert (
        c.post("/api/mock/messages/" + ml["event_id"] + "/retry?group_id=ZGROUP_GS01").status_code
        == 404
    )
    assert (
        c.post("/api/mock/messages/" + ml["event_id"] + "/retry?group_id=ML-GROUP").status_code
        == 200
    )


def test_signed_callback_cannot_be_redirected_to_other_class(connection):
    app, c, _, _, _, _ = connection
    item = c.post("/api/mock/messages", json={"text": "Class isolation"}).json()["data"]
    reply = {**item["callback"], "group_id": "ML-GROUP"}
    raw = json.dumps(reply).encode()
    timestamp = str(int(app.state.clock.now().timestamp()))
    response = c.post(
        "/api/mock/replies",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Timestamp": timestamp,
            "X-Webhook-Signature": sign_payload(
                app.state.settings.mock_webhook_secret, timestamp, raw
            ),
        },
    )
    assert response.status_code == 409
