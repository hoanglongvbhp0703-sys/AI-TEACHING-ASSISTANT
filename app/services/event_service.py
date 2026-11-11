import hashlib
import re
import time
from datetime import timedelta

from app.core.clock import stamp
from app.core.errors import AppError
from app.core.security import clean, dangerous
from app.rag.schemas import RAGContext, RAGResult
from app.repositories.store import encode, uid
from app.services import memory_service as memory
from app.services.access_service import allowed_sources
from app.services.outbound_service import citation_valid, event_access, queue
from app.services.quota_service import release, reserve


class EventService:
    def __init__(self, db, clock, settings, backend):
        self.db, self.clock, self.settings, self.backend = db, clock, settings, backend

    def receive(self, body, request_id):
        now = self.clock.stamp()
        digest = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
        text = body.message.text.strip()
        with self.db.write() as s:
            old = s.one(
                "SELECT * FROM webhook_events WHERE platform=:p AND external_event_id=:e",
                p=body.platform,
                e=body.event_id,
            )
            if old:
                if old["payload_sha256"] != digest:
                    s.security("event_payload_mismatch", request_id, now, old["event_key"])
                return {
                    "event_key": old["event_key"],
                    "status": "duplicate_ignored",
                    "event_status": old["status"],
                    "outcome_code": old["outcome_code"],
                }
            key = uid()
            s.insert(
                "webhook_events",
                event_key=key,
                request_id=request_id,
                platform=body.platform,
                external_event_id=body.event_id,
                raw_group_id=body.group_id,
                raw_sender_id=body.sender_id,
                payload_sha256=digest,
                reply_to_external_event_id=body.message.reply_to_event_id,
                sent_at=stamp(body.sent_at),
                received_at=now,
                next_attempt_at=now,
                max_attempts=self.settings.job_max_attempts,
            )
            identity = s.one(
                "SELECT * FROM external_identities WHERE platform=:p AND external_sender_id=:u AND is_active=1",
                p=body.platform,
                u=body.sender_id,
            )
            group = s.one(
                "SELECT * FROM group_bindings WHERE platform=:p AND external_group_id=:g AND is_active=1",
                p=body.platform,
                g=body.group_id,
            )
            if group:
                s.update(
                    "webhook_events",
                    "event_key",
                    key,
                    group_binding_id=group["id"],
                    class_id=group["class_id"],
                )
            if identity:
                s.update("webhook_events", "event_key", key, user_id=identity["user_id"])
            if body.is_bot_message or (identity and identity["is_bot"]):
                status, outcome = "ignored", "bot_message"
            elif not re.match(r"^/hoi(?:\s+|$)", text):
                status, outcome = "ignored", "not_a_question"
            else:
                event = s.one("SELECT * FROM webhook_events WHERE event_key=:e", e=key)
                if not group or not identity or not event_access(s, event):
                    status, outcome = "rejected", "access_denied"
                elif not text[4:].strip():
                    status, outcome = "completed", "empty_question"
                    queue(
                        s, event, "validation_notice", "Hãy nhập /hoi và câu hỏi cần hỗ trợ.", now
                    )
                else:
                    s.update(
                        "webhook_events",
                        "event_key",
                        key,
                        question_redacted=clean(self.settings, text[4:].strip()),
                    )
                    denied = reserve(s, event, self.clock, self.settings)
                    status, outcome = ("rejected", denied) if denied else ("queued", None)
                    if denied:
                        queue(
                            s,
                            event,
                            "policy_notice",
                            "Bạn đã hết lượt hỏi hôm nay."
                            if denied == "quota_exceeded"
                            else "Bạn gửi câu hỏi quá nhanh, vui lòng thử lại sau.",
                            now,
                        )
            s.update(
                "webhook_events",
                "event_key",
                key,
                status=status,
                outcome_code=outcome,
                completed_at=now if status != "queued" else None,
            )
            return {"event_key": key, "status": status, "outcome_code": outcome}

    def claim(self):
        now = self.clock.stamp()
        with self.db.write() as s:
            event = s.one(
                "SELECT * FROM webhook_events WHERE (status='queued' AND next_attempt_at<=:n) OR (status='processing' AND lease_expires_at<=:n) ORDER BY received_at,event_key LIMIT 1",
                n=now,
            )
            if not event:
                return None
            if event["attempts"] >= event["max_attempts"]:
                release(s, event["event_key"], now, "retry_exhausted")
                s.update(
                    "webhook_events",
                    "event_key",
                    event["event_key"],
                    status="failed",
                    error_code="retry_exhausted",
                    outcome_code="error",
                    completed_at=now,
                )
                s.execute(
                    "UPDATE rag_runs SET status='error',error_code='retry_exhausted',finished_at=:n WHERE event_key=:e",
                    n=now,
                    e=event["event_key"],
                )
                if event["class_id"]:
                    queue(
                        s,
                        event,
                        "bot_result",
                        "Hệ thống gặp lỗi kỹ thuật. Vui lòng thử lại sau.",
                        now,
                    )
                return event["event_key"]
            token = uid()
            s.update(
                "webhook_events",
                "event_key",
                event["event_key"],
                status="processing",
                lease_token=token,
                lease_expires_at=stamp(
                    self.clock.now() + timedelta(seconds=self.settings.job_lease_seconds)
                ),
                attempts=event["attempts"] + 1,
                processing_started_at=event["processing_started_at"] or now,
            )
            event.update(lease_token=token, status="processing")
            return event

    def process_one(self):
        event = self.claim()
        if not event:
            return False
        if isinstance(event, str):
            return True
        start = time.monotonic()
        with self.db.write() as s:
            now = self.clock.stamp()
            if not event_access(s, event):
                release(s, event["event_key"], now, "access_revoked")
                s.update(
                    "webhook_events",
                    "event_key",
                    event["event_key"],
                    status="rejected",
                    outcome_code="access_revoked",
                    completed_at=now,
                )
                return True
            session = memory.session_for(s, event, self.clock, self.settings)
            memory.add_message(s, event, session, "question", event["question_redacted"], now)
            scopes, versions = allowed_sources(s, event["class_id"])
            turns = memory.memory(s, session, event, self.settings.memory_max_turns)
            run = s.one("SELECT * FROM rag_runs WHERE event_key=:e", e=event["event_key"])
            if not run:
                s.insert(
                    "rag_runs",
                    id=uid(),
                    event_key=event["event_key"],
                    allowed_scopes_json=encode(scopes),
                    active_versions_json=encode(versions),
                    memory_event_keys_json=encode([t["event_key"] for t in turns]),
                    started_at=now,
                )
            else:
                s.update(
                    "rag_runs",
                    "id",
                    run["id"],
                    status="running",
                    allowed_scopes_json=encode(scopes),
                    active_versions_json=encode(versions),
                    memory_event_keys_json=encode([t["event_key"] for t in turns]),
                )
            s.execute(
                "UPDATE quota_reservations SET status='charged',charged_at=:n WHERE event_key=:e AND status='reserved'",
                n=now,
                e=event["event_key"],
            )
            context = RAGContext(
                event["event_key"],
                event["class_id"],
                event["group_binding_id"],
                event["question_redacted"],
                scopes,
                versions,
                turns,
            )
        try:
            if dangerous(context.question):
                result = RAGResult(
                    "blocked",
                    "Mình không thể cung cấp mật khẩu, token hoặc API key nội bộ.",
                    reason="secret_request",
                )
            else:
                result = self.backend.answer(context)
            if result.status not in {"answered", "insufficient_evidence", "blocked", "error"}:
                raise AppError(503, "invalid_rag_result", "RAG trả kết quả không hợp lệ.")
        except Exception as exc:
            result = RAGResult(
                "error",
                "Hệ thống hỏi đáp chưa sẵn sàng. Vui lòng thử lại sau.",
                error_code=exc.code if isinstance(exc, AppError) else "rag_failure",
            )
        with self.db.write() as s:
            now = self.clock.stamp()
            fresh = s.one(
                "SELECT * FROM webhook_events WHERE event_key=:e AND lease_token=:t AND status='processing'",
                e=event["event_key"],
                t=event["lease_token"],
            )
            if not fresh:
                return True
            if not event_access(s, event):
                s.update(
                    "webhook_events",
                    "event_key",
                    event["event_key"],
                    status="rejected",
                    outcome_code="access_revoked",
                    completed_at=now,
                )
                s.execute(
                    "UPDATE rag_runs SET status='error',error_code='access_revoked',finished_at=:n WHERE event_key=:e",
                    n=now,
                    e=event["event_key"],
                )
                return True
            if result.status == "answered":
                if not (
                    result.sufficient
                    and result.citations
                    and result.retrieved_point_ids
                    and all(
                        c.get("point_id") in result.retrieved_point_ids
                        and citation_valid(s, event, c)
                        for c in result.citations
                    )
                ):
                    s.security(
                        "invalid_or_stale_citation", event["request_id"], now, event["event_key"]
                    )
                    result = RAGResult(
                        "insufficient_evidence",
                        "Nguồn trả lời chưa được xác minh.",
                        reason="invalid_or_stale_citation",
                    )
            run = s.one("SELECT * FROM rag_runs WHERE event_key=:e", e=event["event_key"])
            s.update(
                "rag_runs",
                "id",
                run["id"],
                status=result.status,
                evidence_sufficient=int(result.sufficient),
                evidence_reason_redacted=clean(self.settings, result.reason),
                latency_ms=int((time.monotonic() - start) * 1000),
                finished_at=now,
                error_code=result.error_code,
            )
            ticket = None
            citations = []
            if result.status == "insufficient_evidence":
                ticket = self.handoff(s, event, result.reason, now)
                answer = (
                    f"Chưa đủ căn cứ để trả lời. Đã chuyển giảng viên hỗ trợ. Mã yêu cầu: {ticket}."
                )
                kind = "handoff"
            else:
                answer = clean(self.settings, result.answer)
                kind = {"answered": "answer", "blocked": "blocked", "error": "technical_error"}[
                    result.status
                ]
            if result.status == "answered":
                s.execute("DELETE FROM rag_citations WHERE rag_run_id=:r", r=run["id"])
                for i, c in enumerate(result.citations, 1):
                    source = s.one(
                        "SELECT d.title FROM document_chunks c JOIN documents d ON d.id=c.document_id WHERE c.point_id=:p",
                        p=c["point_id"],
                    )
                    snapshot = {
                        **c,
                        "title": source["title"],
                        "evidence_excerpt": clean(self.settings, c["evidence_excerpt"]),
                    }
                    citations.append(snapshot)
                    s.insert(
                        "rag_citations",
                        id=uid(),
                        rag_run_id=run["id"],
                        ordinal=i,
                        point_id=c["point_id"],
                        title_snapshot=source["title"],
                        page=c.get("page"),
                        section_path=c.get("section_path"),
                        evidence_excerpt_redacted=snapshot["evidence_excerpt"],
                        created_at=now,
                    )
            if result.status == "blocked":
                s.security(
                    "blocked_question",
                    event["request_id"],
                    now,
                    event["event_key"],
                    event["user_id"],
                )
            memory.add_message(s, event, session, kind, answer, now)
            queue(s, event, "bot_result", answer, now, citations, ticket)
            s.update(
                "webhook_events",
                "event_key",
                event["event_key"],
                status="failed" if result.status == "error" else "completed",
                outcome_code=result.status,
                completed_at=now,
                error_code=result.error_code,
            )
        return True

    @staticmethod
    def handoff(s, event, reason, now):
        old = s.one("SELECT id FROM support_tickets WHERE event_key=:e", e=event["event_key"])
        if old:
            return old["id"]
        key = uid()
        s.insert(
            "support_tickets",
            id=key,
            event_key=event["event_key"],
            class_id=event["class_id"],
            group_binding_id=event["group_binding_id"],
            student_id=event["user_id"],
            question_redacted=event["question_redacted"],
            reason_code="insufficient_evidence",
            evidence_summary_redacted=reason,
            created_at=now,
            updated_at=now,
        )
        return key
