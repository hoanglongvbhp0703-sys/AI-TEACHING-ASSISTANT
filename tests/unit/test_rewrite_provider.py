import json

import httpx
from pydantic import SecretStr

from app.core.config import Settings
from app.rag.provider import ClaudeGateway


def test_rewrite_uses_current_question_and_structured_history_not_answer_prompt():
    settings = Settings(_env_file=None, claude_api_key=SecretStr("qa-rewrite-secret-only"))
    gateway = ClaudeGateway(settings)
    captured = []

    def reply(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "rewrite-call",
                "stop_reason": "end_turn",
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "relation": "standalone",
                                "standalone_question": "Machine Learning là gì?",
                                "used_turn_ids": [],
                            }
                        ),
                    }
                ],
                "usage": {"input_tokens": 30, "cache_read_input_tokens": 20, "output_tokens": 15},
            },
        )

    gateway.client.close()
    gateway.client = httpx.Client(transport=httpx.MockTransport(reply))
    try:
        result, usage = gateway.rewrite(
            "Machine Learning là gì?",
            [
                {
                    "event_key": "old-turn",
                    "question": "Hồi quy là gì?",
                    "answer": "Hồi quy tuyến tính...",
                }
            ],
        )
        body = captured[0]
        payload = json.loads(body["messages"][0]["content"])
        assert payload["current_question"] == "Machine Learning là gì?"
        assert payload["history"][0]["turn_id"] == "old-turn"
        assert "SOURCES" not in payload
        assert "KHÔNG phải bộ trả lời" in body["system"]
        assert result.relation == "standalone" and usage["input_tokens"] == 50
    finally:
        gateway.close()


def test_answer_prompt_and_request_include_all_five_chunks_for_content_assessment():
    from app.rag.provider import SYSTEM

    settings = Settings(_env_file=None, claude_api_key=SecretStr("qa-content-review-secret"))
    gateway = ClaudeGateway(settings)
    bodies = []

    def reply(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "review-call",
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": '{"sufficient":false,"claims":[]}'}],
                "usage": {"input_tokens": 120, "output_tokens": 12},
            },
        )

    gateway.client.close()
    gateway.client = httpx.Client(transport=httpx.MockTransport(reply))
    sources = [
        {"text": f"Chunk {i}: complete source text", "rerank_score": 0.00001, "vector_score": 0.0}
        for i in range(1, 6)
    ]
    try:
        answer, _ = gateway.generate("Câu hỏi nhiều ý", [], sources)
        payload = json.loads(bodies[0]["messages"][0]["content"])
        assert payload["SOURCES"] == [
            {"source": i, "text": s["text"]} for i, s in enumerate(sources, 1)
        ]
        assert "TOÀN BỘ SOURCES" in SYSTEM and "Không bắt buộc cả 5" in SYSTEM
        assert answer.sufficient is False
    finally:
        gateway.close()
