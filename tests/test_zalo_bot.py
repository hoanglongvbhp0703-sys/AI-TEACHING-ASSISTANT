from datetime import timedelta

import httpx
import pytest

from app.core.security import clean
from app.integrations.zalo_bot import BotAPIError, BotClient, BotPoller, normalize
from tests.conftest import auth, drain, upload

TOKEN = "123456:test-only-not-a-real-token"


def update(mid="M1", chat="CHAT1", sender="USER1", text="/hoi câu hỏi"):
    return {
        "message": {
            "message_id": mid,
            "date": 1794312000000,
            "chat": {"id": chat, "chat_type": "PRIVATE"},
            "from": {"id": sender, "is_bot": False},
            "text": text,
        }
    }


def enable(app):
    app.state.settings.zalo_bot_enabled = True
    app.state.settings.zalo_bot_token = type(app.state.settings.zalo_bot_token)(TOKEN)


def bind(client, **overrides):
    return client.post(
        "/api/v1/integrations/zalo-bot/bindings",
        headers=auth(),
        json={
            "class_id": "GS-KPI-01",
            "chat_id": "123456:CHAT1",
            **overrides,
        },
    )


def test_normalization_and_bot_echo():
    event = normalize(update(), "123456")
    assert event.platform == "zalo_bot"
    assert event.group_id == "123456:CHAT1"
    assert event.sender_id == "123456:USER1"
    assert event.sent_at.tzinfo is not None
    assert event.event_id != normalize(update(chat="CHAT2"), "123456").event_id
    assert normalize(update(sender="123456"), "123456").is_bot_message
    assert normalize({"message": {"photo_url": "ignored"}}, "123456") is None


def test_admin_binding_acl_and_real_outbox(rig, monkeypatch):
    app, client, backend, clock = rig
    enable(app)
    poller = BotPoller(app.state.settings, app.state.events)
    assert poller.ingest(update())["outcome_code"] == "access_denied"
    assert backend.contexts == []
    assert (
        client.get("/api/v1/integrations/zalo-bot/inbox", headers=auth("teacher-gs")).status_code
        == 403
    )
    assert bind(client).status_code == 200
    assert bind(client).status_code == 200  # Idempotent configuration.
    assert bind(client, class_id="ML-DEMO-01").status_code == 409
    assert bind(client, chat_id="999:CHAT1").status_code == 422
    result = poller.ingest(update(mid="M2"))
    assert result["status"] == "queued"
    assert poller.ingest(update(mid="M2"))["status"] == "duplicate_ignored"
    sent = []
    monkeypatch.setattr(
        BotClient, "send", lambda self, chat, text: sent.append((chat, text)) or "REAL-MESSAGE-ID"
    )
    drain(app)
    assert len(backend.contexts) == 1
    assert backend.contexts[0].class_id == "GS-KPI-01"
    assert sent and sent[0][0] == "123456:CHAT1"
    with app.state.db.read() as s:
        row = s.one("SELECT * FROM outbound_messages WHERE event_key=:e", e=result["event_key"])
        assert row["status"] == "sent" and row["external_message_id"] == "REAL-MESSAGE-ID"
    assert poller.ingest(update(mid="M3", chat="OTHER"))["outcome_code"] == "access_denied"
    assert poller.ingest(update(mid="M4", text="trò chuyện thường"))["outcome_code"] is None
    assert len(backend.contexts) == 1


@pytest.mark.parametrize(
    "text",
    [
        "Machine Learning là gì?",
        "/hoi Machine Learning là gì?",
        "@Bot của long Machine Learning là gì?",
        "@Bot của long /hoi Machine Learning là gì?",
    ],
)
def test_zalo_questions_do_not_require_command(rig, text):
    app, client, backend, clock = rig
    enable(app)
    bind(client)
    poller = BotPoller(app.state.settings, app.state.events)
    poller.bot_names = ("Bot của long",)
    result = poller.ingest(update(text=text))
    assert result["status"] == "queued"
    app.state.events.process_one()
    assert backend.contexts[0].question == "Machine Learning là gì?"


def test_zalo_tag_only_does_not_call_rag(rig):
    app, client, backend, clock = rig
    enable(app)
    bind(client)
    poller = BotPoller(app.state.settings, app.state.events)
    poller.bot_names = ("Bot của long",)
    assert poller.ingest(update(text="@Bot của long"))["outcome_code"] == "empty_question"
    assert not backend.contexts


def test_revoked_membership_and_failed_send(rig, monkeypatch):
    app, client, backend, clock = rig
    enable(app)
    bind(client)
    poller = BotPoller(app.state.settings, app.state.events)
    result = poller.ingest(update())
    app.state.events.process_one()

    def fail(*args):
        raise BotAPIError("failed")

    monkeypatch.setattr(BotClient, "send", fail)
    app.state.worker.send_one()
    with app.state.db.read() as s:
        assert (
            s.one("SELECT status FROM outbound_messages WHERE event_key=:e", e=result["event_key"])[
                "status"
            ]
            == "pending"
        )
    with app.state.db.write() as s:
        s.execute("UPDATE group_bindings SET is_active=0 WHERE platform='zalo_bot'")
    clock.value += timedelta(seconds=10)
    app.state.worker.send_one()
    with app.state.db.read() as s:
        assert (
            s.one("SELECT status FROM outbound_messages WHERE event_key=:e", e=result["event_key"])[
                "status"
            ]
            == "cancelled"
        )


def test_client_rejects_http_200_error_and_redacts(rig, monkeypatch):
    app, *_ = rig
    enable(app)
    monkeypatch.setattr(
        httpx, "post", lambda *a, **kw: httpx.Response(200, json={"ok": False, "error_code": 401})
    )
    with pytest.raises(BotAPIError):
        BotClient(TOKEN).call("getMe")
    assert TOKEN not in clean(app.state.settings, "token=" + TOKEN)
    with pytest.raises(BotAPIError):
        BotClient(TOKEN).send("wrong-bot:CHAT1", "text")


def test_removed_event_ingress_is_not_public(rig):
    _, client, *_ = rig
    from tests.conftest import payload

    body = payload()
    body["platform"] = "zalo_bot"
    response = client.post("/api/v1/mock/events", headers=auth(), json=body)
    assert response.status_code == 404


def test_answer_uses_existing_rag_sources_and_disabled_transport_stays_pending(rig, monkeypatch):
    app, client, backend, clock = rig
    assert upload(client).status_code == 202
    drain(app)
    backend.reply_mode = "answer"
    enable(app)
    bind(client)
    result = BotPoller(app.state.settings, app.state.events).ingest(update())
    app.state.events.process_one()
    app.state.settings.zalo_bot_enabled = False
    assert app.state.worker.send_one() is False
    with app.state.db.read() as s:
        row = s.one("SELECT * FROM outbound_messages WHERE event_key=:e", e=result["event_key"])
        assert row["status"] == "pending" and row["citations_json"] != "[]"
    app.state.settings.zalo_bot_enabled = True
    sent = []
    monkeypatch.setattr(
        BotClient, "send", lambda self, chat, text: sent.append(text) or "ANSWER-ID"
    )
    drain(app)
    assert sent == ["Test fixture answer."]


def test_webhook_absence_and_poll_timeout_are_not_auth_success(monkeypatch):
    def response(code):
        return lambda *a, **kw: httpx.Response(200, json={"ok": False, "error_code": code})

    monkeypatch.setattr(httpx, "post", response(404))
    assert BotClient(TOKEN).call("getWebhookInfo") is None
    with pytest.raises(BotAPIError):
        BotClient(TOKEN).call("getMe")

    monkeypatch.setattr(httpx, "post", response(408))
    assert BotClient(TOKEN).call("getUpdates") is None
    with pytest.raises(BotAPIError):
        BotClient(TOKEN).call("getMe")


def test_new_participants_need_only_chat_class_binding(rig, monkeypatch):
    app, client, backend, clock = rig
    enable(app)
    assert bind(client).status_code == 200
    poller = BotPoller(app.state.settings, app.state.events)
    monkeypatch.setattr(BotClient, "send", lambda *args: "MESSAGE-ID")
    for number in range(3):
        assert poller.ingest(update(mid=str(number), sender=f"NEW-{number}"))["status"] == "queued"
        drain(app)
    assert len(backend.contexts) == 3
    assert len(backend.contexts[-1].memory) == 2
    with app.state.db.read() as s:
        assert s.one("SELECT count(*) n FROM users")["n"] == 3
        assert not s.all("SELECT * FROM external_identities")
        assert len(s.all("SELECT * FROM daily_usage")) == 3
    assert (
        poller.ingest(update(mid="unknown", chat="OTHER", sender="NEW-0"))["outcome_code"]
        == "access_denied"
    )
