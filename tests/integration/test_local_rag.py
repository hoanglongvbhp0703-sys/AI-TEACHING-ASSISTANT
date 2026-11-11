import httpx
import pytest

from app.core.errors import AppError
from app.rag.local_backend import LocalRAG
from app.rag.provider import Claim, ClaudeGateway, GroundedAnswer, Quote
from app.schemas.event import MockEvent
from tests.conftest import drain, payload, upload


class TinyModels:
    """Deterministic injected test doubles; live evaluation uses actual BKAI/mMARCO."""

    def fits(self, text, model):
        return len(text) < 500

    def embed(self, texts, model):
        return [[1.0, 0.0, 0.0] for _ in texts]

    def rerank(self, question, texts):
        return [0.9 for _ in texts]


class GroundedGateway:
    def generate(self, question, memory, sources, resolved_question=None):
        return GroundedAnswer(
            sufficient=True,
            claims=[
                Claim(
                    text="Có câu trả lời trong tài liệu.",
                    evidence=[Quote(source=1, quote=sources[0]["text"][:40])],
                )
            ],
        ), {"input_tokens": 100, "output_tokens": 30}

    def close(self):
        pass


@pytest.fixture
def local(rig, tmp_path):
    app, c, _, clock = rig
    settings = app.state.settings
    settings.rag_vector_dir = tmp_path / "qdrant"
    backend = LocalRAG(settings, models=TinyModels(), gateway=GroundedGateway())
    backend.bind(app.state.db, clock)
    app.state.backend = backend
    app.state.worker.backend = backend
    app.state.events.backend = backend
    yield app, c, backend, clock
    backend.close()


def process(app, text="/hoi Question", eid="local-rag"):
    receipt = app.state.events.receive(
        MockEvent.model_validate(payload(eid=eid, text=text)), "request-test"
    )
    app.state.events.process_one()
    app.state.worker.send_one()
    with app.state.db.read() as s:
        run = s.one("SELECT * FROM rag_runs WHERE event_key=:e", e=receipt["event_key"])
        out = s.one("SELECT * FROM outbound_messages WHERE event_key=:e", e=receipt["event_key"])
    return run, out


def test_real_qdrant_index_retrieve_citations_and_provider_audit(local):
    app, c, backend, _ = local
    upload(c)
    drain(app)
    run, out = process(app)
    assert run["status"] == "answered" and "[1]" in out["text_redacted"]
    assert backend.last_trace["ranked"][0]["scope_id"] == "class:GS-KPI-01"
    with app.state.db.read() as s:
        calls = s.all("SELECT * FROM rag_run_attempts WHERE rag_run_id=:r", r=run["id"])
        assert {r["stage"] for r in calls} == {"query_embed", "rerank", "generate"}
        generated = next(r for r in calls if r["stage"] == "generate")
        assert generated["input_tokens"] == 100 and generated["output_tokens"] == 30
        assert generated["estimated_cost_usd_micros"] is None


def test_presearch_acl_and_no_active_documents_never_generate(local):
    app, c, backend, _ = local
    upload(c, user="admin", scopes=["class:ML-DEMO-01"])
    drain(app)
    run, _ = process(app)
    assert run["status"] == "insufficient_evidence"
    assert not backend.last_trace.get("retrieved")
    with app.state.db.read() as s:
        assert not s.all("SELECT * FROM rag_run_attempts WHERE stage='generate'")


def test_fabricated_quote_fails_closed(local):
    app, c, backend, _ = local
    upload(c)
    drain(app)
    backend.gateway.generate = lambda *args, **kwargs: (
        GroundedAnswer(
            sufficient=True,
            claims=[
                Claim(
                    text="Bịa thông tin",
                    evidence=[Quote(source=1, quote="This does not exist in the source document")],
                )
            ],
        ),
        {},
    )
    run, _ = process(app)
    assert run["status"] == "insufficient_evidence"
    assert run["evidence_reason_redacted"] == "quote_not_in_source"


def test_llm_error_is_sanitized(local):
    app, c, backend, _ = local
    upload(c)
    drain(app)
    gateway = ClaudeGateway(app.state.settings)
    app.state.settings.claude_api_key = "unused" if False else app.state.settings.claude_api_key
    from pydantic import SecretStr

    app.state.settings.claude_api_key = SecretStr("test-private-api-key")
    gateway.client.close()
    gateway.client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(401, json={"error": "test-private-api-key"})
        )
    )
    with pytest.raises(AppError) as exc:
        gateway.generate("Question", [], [{"text": "source"}])
    assert exc.value.code == "llm_http_401" and "test-private-api-key" not in exc.value.message
    gateway.close()


def test_business_http_callback_waits_for_ack_and_retries(local, monkeypatch):
    app, c, _, clock = local
    app.state.settings.mock_outbound_http_enabled = True
    app.state.settings.simulator_business_mode = True
    upload(c)
    drain(app)
    attempted = []

    def failed(*args, **kwargs):
        attempted.append(kwargs)
        return httpx.Response(503, json={})

    monkeypatch.setattr(httpx, "post", failed)
    _, out = process(app)
    assert out["status"] == "pending" and out["sent_at"] is None
    from datetime import timedelta

    clock.value += timedelta(seconds=6)

    def success(*args, **kwargs):
        import json

        reply = json.loads(kwargs["content"])
        return httpx.Response(
            200, json={"data": {"reply_id": reply["reply_id"], "status": "received"}}
        )

    monkeypatch.setattr(httpx, "post", success)
    assert app.state.worker.send_one()
    with app.state.db.read() as s:
        row = s.one("SELECT * FROM outbound_messages WHERE id=:i", i=out["id"])
        assert row["status"] == "sent" and row["attempts"] == 2
    assert attempted[0]["headers"]["X-Webhook-Signature"].startswith("sha256=")


def test_qdrant_presearch_filters_other_class_even_with_identical_vectors(local):
    app, c, backend, _ = local
    gs = upload(c).json()["data"]
    other = upload(
        c,
        user="admin",
        scopes=["class:ML-DEMO-01"],
        data=b'{"question":"Private ML source","answer":"Never visible in GS"}',
    ).json()["data"]
    drain(app)
    run, _ = process(app, eid="cross-class-vector-filter")
    assert run["status"] == "answered"
    assert backend.last_trace["retrieved"]
    assert {point["document_version_id"] for point in backend.last_trace["retrieved"]} == {
        gs["version_id"]
    }
    assert other["version_id"] not in {
        point["document_version_id"] for point in backend.last_trace["ranked"]
    }


def test_live_rag_generation_progress_and_class_acl(local):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from tests.conftest import auth

    app, c, backend, _ = local
    upload(c)
    drain(app)
    entered, release = Event(), Event()
    generate = backend.gateway.generate

    def slow_generate(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=10)
        return generate(*args, **kwargs)

    backend.gateway.generate = slow_generate
    receipt = app.state.events.receive(
        MockEvent.model_validate(payload(eid="progress-test")), "request-progress"
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(app.state.events.process_one)
        try:
            assert entered.wait(timeout=5)
            response = c.get("/api/v1/events/" + receipt["event_key"], headers=auth("HV_GS_01"))
            progress = response.json()["data"]["progress"]
            assert progress["stage"] == "generate" and progress["percent"] == 75
            assert (
                c.get(
                    "/api/v1/events/" + receipt["event_key"], headers=auth("teacher-ai")
                ).status_code
                == 403
            )
        finally:
            release.set()
        future.result(timeout=5)
    app.state.worker.send_one()
    completed = c.get("/api/v1/events/" + receipt["event_key"], headers=auth()).json()["data"][
        "progress"
    ]
    assert completed["stage"] == "done" and completed["percent"] == 100


def test_low_rank_scores_do_not_block_claude_or_citation_validation(local):
    app, c, backend, _ = local
    upload(c)
    drain(app)
    backend.models.rerank = lambda question, texts: [0.03 for _ in texts]
    run, _ = process(app, eid="marginal-evidence-case")
    assert run["status"] == "answered"
    assert run["evidence_reason_redacted"] == "claude_content_and_verified_citations"
    with app.state.db.read() as s:
        assert (
            s.one(
                "SELECT count(*) AS n FROM rag_run_attempts WHERE rag_run_id=:r AND stage='generate'",
                r=run["id"],
            )["n"]
            == 1
        )


def test_low_scores_still_call_claude_and_its_insufficient_result_hands_off(local):
    app, c, backend, _ = local
    upload(c)
    drain(app)
    backend.models.rerank = lambda question, texts: [0.000001 for _ in texts]
    calls = []

    def reject(question, memory, sources, resolved_question=None):
        calls.append(sources)
        return GroundedAnswer(sufficient=False, claims=[]), {}

    backend.gateway.generate = reject
    run, out = process(app, eid="low-scores-claude-review")
    assert (
        run["status"] == "insufficient_evidence"
        and run["evidence_reason_redacted"] == "model_evidence_insufficient"
    )
    assert calls and out["ticket_id"]
    with app.state.db.read() as s:
        assert (
            s.one(
                "SELECT status FROM rag_run_attempts WHERE rag_run_id=:r AND stage='generate'",
                r=run["id"],
            )["status"]
            == "succeeded"
        )


def test_quota_callback_reports_no_rag_or_provider_call(local, monkeypatch):
    import json

    from app.core.clock import day_key

    app, _, _, clock = local
    app.state.settings.mock_outbound_http_enabled = True
    with app.state.db.write() as s:
        s.insert(
            "daily_usage",
            user_id="HV_GS_01",
            local_date=day_key(clock.now()),
            accepted_count=30,
            updated_at=clock.stamp(),
        )
    receipt = app.state.events.receive(
        MockEvent.model_validate(payload(eid="quota-outcome-progress")), "request-quota"
    )
    assert receipt["status"] == "rejected"
    callbacks = []

    def ack(*args, **kwargs):
        body = json.loads(kwargs["content"])
        callbacks.append(body)
        return httpx.Response(
            200, json={"data": {"reply_id": body["reply_id"], "status": "received"}}
        )

    monkeypatch.setattr(httpx, "post", ack)
    assert app.state.worker.send_one()
    progress = callbacks[0]["processing"]
    assert progress["percent"] == 0 and progress["outcome_code"] == "quota_exceeded"
    assert progress["llm_called"] is False and progress["retrieval_called"] is False
    with app.state.db.read() as s:
        assert not s.all("SELECT * FROM rag_runs")


def test_contextual_rewrite_precedes_embedding_and_preserves_generation_question(local):
    import json

    from app.rag.query_rewriter import RewriteOutput

    app, c, backend, _ = local
    upload(c)
    drain(app)
    process(app, text="/hoi KNN là gì?", eid="rewrite-history")
    sequence = []

    def rewrite(question, memory):
        sequence.append("rewrite")
        assert question == "Nó có nhược điểm gì?"
        return RewriteOutput(
            relation="follow_up",
            standalone_question="Thuật toán KNN có nhược điểm gì?",
            used_turn_ids=[memory[-1]["event_key"]],
        ), {"input_tokens": 40, "output_tokens": 15}

    embed = backend.models.embed

    def record_embed(texts, model):
        sequence.append(("embed", texts[0]))
        return embed(texts, model)

    generate = backend.gateway.generate

    def record_generate(question, memory, sources, resolved_question=None):
        assert question == "Nó có nhược điểm gì?"
        assert resolved_question == "Thuật toán KNN có nhược điểm gì?"
        return generate(question, memory, sources, resolved_question)

    backend.gateway.rewrite = rewrite
    backend.models.embed = record_embed
    backend.gateway.generate = record_generate
    run, _ = process(app, text="/hoi Nó có nhược điểm gì?", eid="rewrite-followup")
    assert run["status"] == "answered"
    assert sequence[:2] == ["rewrite", ("embed", "Thuật toán KNN có nhược điểm gì?")]
    trace = json.loads(run["query_rewrite_json"])
    assert trace["original_question"] == "Nó có nhược điểm gì?" and trace["relation"] == "follow_up"
    with app.state.db.read() as s:
        calls = s.all(
            "SELECT stage,provider,input_tokens FROM rag_run_attempts WHERE rag_run_id=:r ORDER BY rowid",
            r=run["id"],
        )
    assert [r["stage"] for r in calls] == ["query_rewrite", "query_embed", "rerank", "generate"]
    assert calls[0]["provider"] == "hhtech-anthropic" and calls[0]["input_tokens"] == 40


def test_rewrite_failure_falls_back_to_current_question(local):
    import json

    app, c, backend, _ = local
    upload(c)
    drain(app)
    process(app, text="/hoi Hồi quy là gì?", eid="fallback-history")

    def failed_rewrite(*args):
        raise AppError(503, "llm_transport_error", "Timeout")

    backend.gateway.rewrite = failed_rewrite
    run, _ = process(app, text="/hoi Machine Learning là gì?", eid="rewrite-timeout")
    assert run["status"] == "answered"
    rewrite = json.loads(run["query_rewrite_json"])
    assert rewrite["status"] == "error_fallback"
    assert backend.last_trace["query"] == "Machine Learning là gì?"
    with app.state.db.read() as s:
        assert (
            s.one(
                "SELECT status FROM rag_run_attempts WHERE rag_run_id=:r AND stage='query_rewrite'",
                r=run["id"],
            )["status"]
            == "unknown"
        )


def test_rewrite_provider_call_is_separate_from_answer_generation(local):
    from app.rag.query_rewriter import RewriteOutput
    from tests.conftest import auth

    app, c, backend, _ = local
    upload(c)
    drain(app)
    process(app, text="/hoi KNN là gì?", eid="count-history")
    backend.gateway.rewrite = lambda question, memory: (
        RewriteOutput(relation="standalone", standalone_question=question, used_turn_ids=[]),
        {},
    )
    backend.models.rerank = lambda question, texts: [0.001] * len(texts)
    backend.gateway.generate = lambda *args, **kwargs: (
        GroundedAnswer(sufficient=False, claims=[]),
        {},
    )
    run, _ = process(app, text="/hoi Câu hỏi mới không có nguồn", eid="count-rewrite-only")
    assert run["status"] == "insufficient_evidence"
    with app.state.db.read() as s:
        event = s.one("SELECT event_key FROM rag_runs WHERE id=:r", r=run["id"])
    details = c.get("/api/v1/events/" + event["event_key"], headers=auth()).json()["data"]
    assert details["progress"]["rewrite_called"] is True
    assert details["progress"]["llm_called"] is True
    assert details["progress"]["provider_called"] is True
    assert details["query_rewrite"]["relation"] == "standalone"
    from datetime import timedelta

    app.state.clock.value += timedelta(seconds=1)
    report = c.get("/api/v1/reports/summary", headers=auth()).json()["data"]
    assert report["rewrite_usage"]["calls"] == 1


def test_rewrite_can_never_grant_access_to_another_class(local):
    from app.rag.query_rewriter import RewriteOutput

    app, c, backend, _ = local
    own = upload(c).json()["data"]
    other = upload(
        c,
        user="admin",
        scopes=["class:ML-DEMO-01"],
        data=b'{"question":"Private other class","answer":"Private answer"}',
    ).json()["data"]
    drain(app)
    process(app, text="/hoi Lịch sử của lớp tôi", eid="acl-rewrite-history")
    backend.gateway.rewrite = lambda question, memory: (
        RewriteOutput(
            relation="follow_up",
            standalone_question="Private other class",
            used_turn_ids=[memory[-1]["event_key"]],
        ),
        {},
    )
    process(app, text="/hoi Nội dung đó là gì?", eid="acl-rewrite-followup")
    assert {p["document_version_id"] for p in backend.last_trace["retrieved"]} == {
        own["version_id"]
    }
    assert other["version_id"] not in {
        p["document_version_id"] for p in backend.last_trace["retrieved"]
    }


@pytest.mark.parametrize("evidence_sources", [[5], [2, 5]])
def test_claude_receives_all_five_with_zero_vector_scores_and_may_use_nonfirst_sources(
    local, evidence_sources
):
    import json

    app, c, backend, _ = local
    faq = [
        {
            "question": "UNRELATED information" if i == 0 else f"Relevant content {i}",
            "answer": f"Detailed source evidence for item {i}, available to the model for answering.",
        }
        for i in range(5)
    ]
    upload(c, data=json.dumps(faq).encode())
    drain(app)
    backend.models.embed = lambda texts, model: [[0.0, 1.0, 0.0] for _ in texts]
    backend.models.rerank = lambda question, texts: [
        0.99 if "UNRELATED" in t else 0.000001 for t in texts
    ]
    captured = []

    def review(question, memory, sources, resolved_question=None):
        captured.extend(sources)
        assert len(sources) == 5 and "UNRELATED" in sources[0]["text"]
        assert all(p["vector_score"] == 0 for p in sources)
        return GroundedAnswer(
            sufficient=True,
            claims=[
                Claim(
                    text="Nội dung được tổng hợp từ nguồn phù hợp.",
                    evidence=[
                        Quote(source=n, quote=sources[n - 1]["text"][:45]) for n in evidence_sources
                    ],
                )
            ],
        ), {}

    backend.gateway.generate = review
    run, _ = process(app, eid="full-five-review")
    assert run["status"] == "answered" and len(captured) == 5
    with app.state.db.read() as s:
        cites = s.all("SELECT point_id FROM rag_citations WHERE rag_run_id=:r", r=run["id"])
    assert {row["point_id"] for row in cites} == {
        captured[n - 1]["point_id"] for n in evidence_sources
    }
