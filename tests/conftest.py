import hashlib
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError
from app.jobs.runner import point_id
from app.main import create_app
from app.rag.schemas import RAGResult

TOKENS = {
    u: ("test-only-token-" + u + "-" * 32)
    for u in ["admin", "teacher-gs", "teacher-ai", "adapter", "HV_GS_01", "student-shared"]
}


class TestClock(Clock):
    __test__ = False

    def __init__(self):
        self.value = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)

    def now(self):
        return self.value


class TestOnlyBackend:
    """An injected test double. Never installed in the runnable app or used for demos."""

    __test__ = False
    ready = True

    def __init__(self):
        self.contexts = []
        self.chunks = {}
        self.fail_index = False
        self.reply_mode = "insufficient"
        self.before_answer = None
        self.cleanups = []

    def index(self, version, path, scopes, config):
        if self.fail_index:
            raise AppError(503, "test_index_failure", "Injected test failure.")
        result = []
        for i, scope in enumerate(scopes):
            section = "TEST-01"
            row = {
                "point_id": point_id(version["id"], "CH1", scope),
                "chunk_id": "CH1",
                "document_id": version["document_id"],
                "document_version_id": version["id"],
                "scope_id": scope,
                "section_id": section,
                "section_path": section,
                "page": None,
                "topic": "test",
                "content_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "embedding_model": config.get("embedding_model", "TEST-ONLY"),
                "vector_size": 3,
            }
            self.chunks[row["point_id"]] = row
            result.append(row)
        return result

    def answer(self, context):
        self.contexts.append(context)
        if self.before_answer:
            self.before_answer(context)
        if self.reply_mode == "error":
            raise AppError(503, "test_model_error", "Injected model failure.")
        if self.reply_mode == "invalid":
            return RAGResult(
                "answered",
                "Invalid source test.",
                [{"point_id": "missing"}],
                True,
                retrieved_point_ids=["missing"],
            )
        if self.reply_mode == "answer":
            points = [
                c
                for c in self.chunks.values()
                if c["scope_id"] in context.allowed_scope_ids
                and c["document_version_id"] in context.active_document_version_ids
            ]
            if points:
                c = points[0]
                citation = {
                    k: c[k]
                    for k in [
                        "point_id",
                        "document_id",
                        "document_version_id",
                        "chunk_id",
                        "page",
                        "section_path",
                    ]
                }
                citation["evidence_excerpt"] = "Test fixture evidence."
                return RAGResult(
                    "answered",
                    "Test fixture answer.",
                    [citation],
                    True,
                    "test evidence",
                    [c["point_id"]],
                )
        return RAGResult(
            "insufficient_evidence", "Test fixture has no evidence.", reason="test_no_evidence"
        )

    def cleanup(self, did, vid):
        self.cleanups.append((did, vid))

    def close(self):
        pass


@pytest.fixture
def rig(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None,
        database_url="sqlite:///" + str(tmp_path / "gos.db"),
        upload_dir=tmp_path / "uploads",
        staging_dir=tmp_path / "staging",
        auth_tokens_json={token: user for user, token in TOKENS.items()},
        seed_demo_on_start=True,
        background_jobs_enabled=False,
        rate_limit_enabled=False,
    )
    from app.integrations.zalo_bot import BotPoller

    monkeypatch.setattr(BotPoller, "start", lambda self: None)
    backend = TestOnlyBackend()
    clock = TestClock()
    app = create_app(settings, backend=backend, clock=clock)
    with TestClient(app) as client:
        # Test events use the production service; only the external HTTP delivery is replaced.
        import httpx
        from pydantic import SecretStr

        settings.zalo_bot_enabled = True
        settings.zalo_bot_token = SecretStr("123456:test-only-not-a-real-token")
        monkeypatch.setattr(
            httpx,
            "post",
            lambda *a, **kw: httpx.Response(
                200, json={"ok": True, "result": {"message_id": "TEST-DELIVERED"}}
            ),
        )
        with app.state.db.write() as s:
            for cid, chat in [("GS-KPI-01", "123456:TEST-GS"), ("ML-DEMO-01", "123456:TEST-ML")]:
                s.insert(
                    "group_bindings",
                    id=chat,
                    class_id=cid,
                    platform="zalo_bot",
                    external_group_id=chat,
                    display_name=cid,
                    created_at=clock.stamp(),
                )
        yield app, client, backend, clock


def auth(user="admin"):
    return {"Authorization": "Bearer " + TOKENS[user]}


def payload(eid="E1", group="123456:TEST-GS", sender="HV_GS_01", text="/hoi Câu hỏi thử nghiệm"):
    return {
        "event_id": eid,
        "platform": "zalo_bot",
        "group_id": group,
        "sender_id": sender,
        "sent_at": "2026-11-10T19:00:00+07:00",
        "is_bot_message": False,
        "message": {"type": "text", "text": text, "reply_to_event_id": None},
    }


def drain(app):
    for _ in range(100):
        if not app.state.worker.tick():
            return
    raise AssertionError("Worker did not drain")


def upload(client, user="teacher-gs", scopes=None, config=None, data=None):
    return client.post(
        "/api/v1/documents",
        headers=auth(user),
        data={
            "title": "Fixture FAQ",
            "topic": "testing",
            "scope_ids": json.dumps(scopes or ["class:GS-KPI-01"]),
            "extraction_config": json.dumps(config or {}),
        },
        files={
            "file": (
                "faq.json",
                data or b'{"question":"Question","answer":"Answer"}',
                "application/json",
            )
        },
    )


def usage(app, sender="HV_GS_01", platform="zalo_bot"):
    from app.services.quota_service import quota, usage_key

    with app.state.db.read() as s:
        return quota(s, usage_key({"platform": platform, "raw_sender_id": sender}), app.state.clock)


def outbound(app, group="123456:TEST-GS"):
    with app.state.db.read() as s:
        rows = s.all(
            "SELECT o.* FROM outbound_messages o JOIN group_bindings g ON g.id=o.group_binding_id WHERE g.external_group_id=:g AND o.status='sent' ORDER BY o.rowid",
            g=group,
        )
    for row in rows:
        row["citations"] = json.loads(row["citations_json"])
    return rows
