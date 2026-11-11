import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.security import matches
from app.integrations.mock_zalo_adapter import sign_payload
from app.main import create_app
from tests.conftest import auth, drain, payload

URL = "/api/v1/webhooks/mock-zalo"


@pytest.fixture
def signed_rig(rig):
    app, client, backend, clock = rig
    app.state.settings.mock_webhook_auth_mode = "hmac"
    return app, client, backend, clock


def signed(app, body=None, *, raw=None, timestamp=None):
    raw = raw if raw is not None else json.dumps(body or payload(), ensure_ascii=False).encode()
    timestamp = str(int(app.state.clock.now().timestamp())) if timestamp is None else timestamp
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "X-Webhook-Timestamp": timestamp,
        "X-Webhook-Signature": sign_payload(app.state.settings.mock_webhook_secret, timestamp, raw),
    }
    return raw, headers


def event_count(app):
    with app.state.db.read() as s:
        return s.one("SELECT count(*) AS n FROM webhook_events")["n"]


def test_signature_algorithm_matches_independent_hmac():
    raw = b'{"event_id":"example"}'
    expected = (
        "sha256="
        + hmac.new(b"example-shared-secret", b"1700000000." + raw, hashlib.sha256).hexdigest()
    )
    assert sign_payload("example-shared-secret", "1700000000", raw) == expected
    assert Settings(_env_file=None).mock_webhook_auth_mode == "hmac"
    assert not matches("không-phải-secret", "a" * 32)


def test_hmac_accepts_unicode_and_returns_persisted_receipt(signed_rig):
    app, c, _, _ = signed_rig
    raw, headers = signed(app)
    response = c.post(URL, content=raw, headers=headers)
    assert response.status_code == 202, response.text
    result = response.json()["data"]
    with app.state.db.read() as s:
        row = s.one(
            "SELECT status,question_redacted FROM webhook_events WHERE event_key=:e",
            e=result["event_key"],
        )
        assert row["status"] == "queued"
        assert row["question_redacted"] == "Câu hỏi thử nghiệm"
        assert (
            s.one(
                "SELECT status FROM quota_reservations WHERE event_key=:e", e=result["event_key"]
            )["status"]
            == "reserved"
        )


def test_signed_concurrent_retry_has_one_event_quota_ticket_and_reply(signed_rig):
    app, c, backend, _ = signed_rig
    raw, headers = signed(app)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: c.post(URL, content=raw, headers=headers), range(2)))
    assert sorted(r.status_code for r in results) == [200, 202]
    assert len({r.json()["data"]["event_key"] for r in results}) == 1
    drain(app)
    assert len(backend.contexts) == 1
    with app.state.db.read() as s:
        for table in [
            "webhook_events",
            "quota_reservations",
            "support_tickets",
            "outbound_messages",
        ]:
            assert s.one(f"SELECT count(*) AS n FROM {table}")["n"] == 1


def test_body_tampering_is_rejected_before_any_db_write(signed_rig):
    app, c, _, _ = signed_rig
    raw, headers = signed(app)
    response = c.post(URL, content=raw + b" ", headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_webhook_signature"
    assert event_count(app) == 0


@pytest.mark.parametrize("offset", [-301, 301])
def test_old_or_future_delivery_timestamp_rejected(signed_rig, offset):
    app, c, _, clock = signed_rig
    raw, headers = signed(app, timestamp=str(int(clock.now().timestamp()) + offset))
    response = c.post(URL, content=raw, headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "webhook_timestamp_expired"
    assert event_count(app) == 0


@pytest.mark.parametrize("timestamp", ["", "NaN", "-1", "1e10", "1.5", "9" * 100])
def test_malformed_timestamp_is_rejected(signed_rig, timestamp):
    app, c, _, _ = signed_rig
    raw, headers = signed(app)
    headers["X-Webhook-Timestamp"] = timestamp
    assert c.post(URL, content=raw, headers=headers).status_code == 401
    assert event_count(app) == 0


@pytest.mark.parametrize("signature", ["", "wrong", "sha256=" + "0" * 64, "sha256=" + "a" * 63])
def test_invalid_signature_has_no_secret_echo(signed_rig, signature):
    app, c, _, _ = signed_rig
    raw, headers = signed(app)
    headers["X-Webhook-Signature"] = signature
    response = c.post(URL, content=raw, headers=headers)
    assert response.status_code == 401
    assert app.state.settings.mock_webhook_secret not in response.text
    assert event_count(app) == 0


def test_hmac_cannot_downgrade_to_legacy_secret_header(signed_rig):
    app, c, _, _ = signed_rig
    response = c.post(
        URL, json=payload(), headers={"X-Webhook-Secret": app.state.settings.mock_webhook_secret}
    )
    assert response.status_code == 401
    assert event_count(app) == 0


def test_missing_or_duplicate_signature_headers_rejected(signed_rig):
    app, c, _, _ = signed_rig
    raw, headers = signed(app)
    missing = {k: v for k, v in headers.items() if k != "X-Webhook-Timestamp"}
    assert c.post(URL, content=raw, headers=missing).status_code == 401
    repeated = list(headers.items()) + [("X-Webhook-Timestamp", headers["X-Webhook-Timestamp"])]
    assert c.post(URL, content=raw, headers=repeated).status_code == 401


def test_authentication_happens_before_json_parse(signed_rig):
    app, c, _, _ = signed_rig
    assert (
        c.post(
            URL, content=b"{broken-json", headers={"Content-Type": "application/json"}
        ).status_code
        == 401
    )
    raw, headers = signed(app, raw=b"{broken-json")
    assert c.post(URL, content=raw, headers=headers).status_code == 422
    assert event_count(app) == 0


def test_signed_wrong_media_and_unknown_class_payload_rejected(signed_rig):
    app, c, _, _ = signed_rig
    raw, headers = signed(app)
    headers["Content-Type"] = "text/plain"
    assert c.post(URL, content=raw, headers=headers).status_code == 415
    body = payload()
    body["class_id"] = "ML-DEMO-01"
    raw, headers = signed(app, body)
    assert c.post(URL, content=raw, headers=headers).status_code == 422
    assert event_count(app) == 0


def test_webhook_body_limit_counts_actual_bytes(signed_rig):
    app, c, _, _ = signed_rig
    app.state.settings.webhook_max_body_bytes = 1024
    raw, headers = signed(app, raw=b"x" * 1025)
    response = c.post(URL, content=raw, headers=headers)
    assert response.status_code == 413
    assert event_count(app) == 0


def test_missing_secret_is_reported_as_unconfigured(signed_rig):
    app, c, _, _ = signed_rig
    raw, headers = signed(app)
    app.state.settings.mock_webhook_secret = ""
    response = c.post(URL, content=raw, headers=headers)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "webhook_not_configured"


def test_sender_can_resign_retry_while_event_time_stays_old(signed_rig):
    app, c, _, clock = signed_rig
    body = payload()
    body["sent_at"] = "2020-01-01T00:00:00Z"
    raw, headers = signed(app, body)
    first = c.post(URL, content=raw, headers=headers)
    raw, headers = signed(app, body, timestamp=str(int(clock.now().timestamp()) + 2))
    repeated = c.post(URL, content=raw, headers=headers)
    assert first.status_code == 202 and repeated.status_code == 200
    assert repeated.json()["data"]["status"] == "duplicate_ignored"
    assert event_count(app) == 1


def test_committed_signed_event_is_recovered_after_restart(signed_rig):
    app, c, backend, clock = signed_rig
    raw, headers = signed(app)
    receipt = c.post(URL, content=raw, headers=headers).json()["data"]
    restarted = create_app(app.state.settings, backend=backend, clock=clock)
    with TestClient(restarted) as other:
        drain(restarted)
        status = other.get("/api/v1/events/" + receipt["event_key"], headers=auth()).json()["data"]
        assert status["status"] == "completed"
        assert (
            other.get("/api/v1/students/HV_GS_01/quota", headers=auth()).json()["data"]["used"] == 1
        )


def test_webhook_openapi_has_body_and_header_contract(signed_rig):
    _, c, _, _ = signed_rig
    spec = c.get("/openapi.json").json()
    operation = spec["paths"][URL]["post"]
    assert (
        operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/MockEvent"
    )
    assert "MockEvent" in spec["components"]["schemas"]
    assert {"x-webhook-timestamp", "x-webhook-signature"}.issubset(
        {p["name"] for p in operation["parameters"]}
    )
