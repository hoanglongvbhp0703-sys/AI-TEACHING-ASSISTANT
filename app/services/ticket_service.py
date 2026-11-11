import hashlib

from app.core.errors import require
from app.core.security import clean
from app.repositories.store import encode, uid
from app.services.access_service import check_class, check_scope
from app.services.outbound_service import queue


class TicketService:
    def __init__(self, db, clock, settings):
        self.db, self.clock, self.settings = db, clock, settings

    @staticmethod
    def get(s, user, tid):
        ticket = s.one("SELECT * FROM support_tickets WHERE id=:t", t=tid)
        require(ticket is not None, 404, "not_found", "Không tìm thấy ticket.")
        check_class(s, user, ticket["class_id"])
        return ticket

    def assign(self, user, tid, body, request_id):
        with self.db.write() as s:
            ticket = self.get(s, user, tid)
            require(
                ticket["status"] in {"open", "assigned"},
                409,
                "invalid_ticket_state",
                "Ticket không còn chờ xử lý.",
            )
            require(
                ticket["revision"] == body.revision,
                409,
                "revision_conflict",
                "Ticket đã được thay đổi, hãy tải lại.",
            )
            require(
                s.one(
                    "SELECT u.id FROM users u JOIN teacher_assignments a ON a.teacher_id=u.id WHERE u.id=:u AND u.role='teacher' AND u.is_active=1 AND a.class_id=:c AND a.is_active=1",
                    u=body.teacher_id,
                    c=ticket["class_id"],
                ),
                422,
                "invalid_assignee",
                "Giảng viên không phụ trách lớp này.",
            )
            now = self.clock.stamp()
            s.update(
                "support_tickets",
                "id",
                tid,
                status="assigned",
                assignee_id=body.teacher_id,
                revision=ticket["revision"] + 1,
                updated_at=now,
            )
            s.audit(
                user["id"],
                "ticket.assign",
                "ticket",
                tid,
                now,
                request_id,
                {"teacher_id": body.teacher_id},
            )
            return s.one("SELECT * FROM support_tickets WHERE id=:t", t=tid)

    def answer(self, user, tid, body, request_id):
        answer = clean(self.settings, body.answer)
        with self.db.write() as s:
            ticket = self.get(s, user, tid)
            old = s.one("SELECT * FROM ticket_replies WHERE ticket_id=:t", t=tid)
            if old:
                require(
                    old["answer_redacted"] == answer,
                    409,
                    "reply_exists",
                    "Ticket đã có câu trả lời chính thức khác.",
                )
                return old
            require(
                ticket["status"] in {"open", "assigned"},
                409,
                "invalid_ticket_state",
                "Ticket không còn chờ xử lý.",
            )
            require(
                ticket["revision"] == body.revision,
                409,
                "revision_conflict",
                "Ticket đã thay đổi, hãy tải lại.",
            )
            require(user["role"] == "admin" or ticket["assignee_id"] in {None, user["id"]})
            now = self.clock.stamp()
            key = uid()
            s.insert(
                "ticket_replies",
                id=key,
                ticket_id=tid,
                teacher_id=user["id"],
                answer_redacted=answer,
                created_at=now,
            )
            s.update(
                "support_tickets",
                "id",
                tid,
                status="assigned",
                assignee_id=ticket["assignee_id"] or user["id"],
                revision=ticket["revision"] + 1,
                updated_at=now,
            )
            event = s.one("SELECT * FROM webhook_events WHERE event_key=:e", e=ticket["event_key"])
            queue(s, event, "teacher_answer", answer, now, ticket_id=tid, reply_id=key)
            s.audit(user["id"], "ticket.answer", "ticket", tid, now, request_id)
            return s.one("SELECT * FROM ticket_replies WHERE id=:id", id=key)

    def close(self, user, tid, body, request_id):
        with self.db.write() as s:
            ticket = self.get(s, user, tid)
            if ticket["status"] == "closed":
                return ticket
            require(
                ticket["status"] == "answered",
                409,
                "invalid_ticket_state",
                "Chỉ đóng ticket đã gửi phản hồi thành công.",
            )
            require(
                ticket["revision"] == body.revision,
                409,
                "revision_conflict",
                "Ticket đã thay đổi, hãy tải lại.",
            )
            now = self.clock.stamp()
            s.update(
                "support_tickets",
                "id",
                tid,
                status="closed",
                closed_at=now,
                updated_at=now,
                revision=ticket["revision"] + 1,
            )
            s.audit(user["id"], "ticket.close", "ticket", tid, now, request_id)
            return s.one("SELECT * FROM support_tickets WHERE id=:t", t=tid)

    def draft(self, user, tid, body, request_id):
        with self.db.write() as s:
            ticket = self.get(s, user, tid)
            check_scope(s, user, body.scope_id)
            require(
                ticket["status"] in {"answered", "closed"},
                409,
                "ticket_not_answered",
                "Ticket phải được trả lời trước khi tạo FAQ.",
            )
            old = s.one("SELECT * FROM faq_entries WHERE source_ticket_id=:t", t=tid)
            if old:
                require(
                    old["scope_id"] == body.scope_id and old["topic"] == body.topic,
                    409,
                    "faq_exists",
                    "Ticket đã có FAQ với cấu hình khác.",
                )
                return old
            reply = s.one("SELECT * FROM ticket_replies WHERE ticket_id=:t", t=tid)
            now = self.clock.stamp()
            key = uid()
            s.insert(
                "faq_entries",
                id=key,
                source_ticket_id=tid,
                question_redacted=ticket["question_redacted"],
                approved_answer_redacted=reply["answer_redacted"],
                topic=clean(self.settings, body.topic),
                scope_id=body.scope_id,
                created_by=user["id"],
                created_at=now,
                updated_at=now,
            )
            s.audit(user["id"], "faq.draft", "faq", key, now, request_id)
            return s.one("SELECT * FROM faq_entries WHERE id=:id", id=key)

    def faq(self, s, user, fid):
        faq = s.one("SELECT * FROM faq_entries WHERE id=:id", id=fid)
        require(faq is not None, 404, "not_found", "Không tìm thấy FAQ.")
        self.get(s, user, faq["source_ticket_id"])
        check_scope(s, user, faq["scope_id"])
        return faq

    def approve(self, user, fid, request_id):
        path = None
        try:
            with self.db.write() as s:
                faq = self.faq(s, user, fid)
                require(faq["status"] != "revoked", 409, "faq_revoked", "FAQ đã thu hồi.")
                if faq["status"] == "approved":
                    return faq
                now = self.clock.stamp()
                did, vid, jid = uid(), uid(), uid()
                data = encode(
                    {
                        "question": faq["question_redacted"],
                        "answer": faq["approved_answer_redacted"],
                        "source_ticket_id": faq["source_ticket_id"],
                    }
                ).encode()
                relative = f"{did}/{vid}/source.json"
                path = self.settings.upload_dir / relative
                path.parent.mkdir(parents=True, exist_ok=False)
                path.write_bytes(data)
                s.insert(
                    "documents",
                    id=did,
                    title="FAQ: " + faq["question_redacted"][:150],
                    topic=faq["topic"],
                    source_kind="faq",
                    created_by=user["id"],
                    created_at=now,
                    updated_at=now,
                )
                s.insert(
                    "document_access",
                    document_id=did,
                    scope_id=faq["scope_id"],
                    granted_by=user["id"],
                    created_at=now,
                )
                s.insert(
                    "document_versions",
                    id=vid,
                    document_id=did,
                    version=1,
                    sha256=hashlib.sha256(data).hexdigest(),
                    file_path=relative,
                    original_filename="faq.json",
                    mime_type="application/json",
                    file_size_bytes=len(data),
                    extraction_config_json=encode(
                        {"_base_revision": 0, "_base_active_version_id": None}
                    ),
                    uploaded_by=user["id"],
                    uploaded_at=now,
                )
                s.insert(
                    "ingestion_jobs",
                    id=jid,
                    document_version_id=vid,
                    next_attempt_at=now,
                    created_at=now,
                    max_attempts=self.settings.job_max_attempts,
                    status="queued" if self.settings.rag_jobs_enabled else "cancelled",
                    error_code=None if self.settings.rag_jobs_enabled else "rag_deferred",
                    finished_at=None if self.settings.rag_jobs_enabled else now,
                )
                s.update(
                    "faq_entries",
                    "id",
                    fid,
                    status="approved",
                    document_id=did,
                    approved_by=user["id"],
                    approved_at=now,
                    updated_at=now,
                )
                s.audit(
                    user["id"], "faq.approve", "faq", fid, now, request_id, {"document_id": did}
                )
                return {**s.one("SELECT * FROM faq_entries WHERE id=:id", id=fid), "job_id": jid}
        except BaseException:
            if path and path.exists():
                path.unlink()
            raise
