import json
import logging
import threading
from datetime import timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.engine import make_url

from app.core.clock import stamp
from app.core.errors import AppError, require
from app.core.security import clean
from app.repositories.store import uid
from app.services import memory_service as memory
from app.services.access_service import document_scopes
from app.services.outbound_service import citation_valid, event_access

log = logging.getLogger(__name__)


def point_id(version_id, chunk_id, scope_id):
    return str(uuid5(NAMESPACE_URL, f"gos-academy:{version_id}|{chunk_id}|{scope_id}"))


class Worker:
    """One sequential in-process runner; persisted claims survive a process restart."""

    def __init__(self, db, clock, settings, backend, events):
        self.db, self.clock, self.settings, self.backend, self.events = (
            db,
            clock,
            settings,
            backend,
            events,
        )
        self.stop_signal = threading.Event()
        self.thread = None
        self.worker_lock = None

    def start(self):
        if self.settings.rag_jobs_enabled and not self.backend.ready:
            log.warning(
                "worker_paused reason=backend_unconfigured; no RAG/outbox jobs will be claimed"
            )
            return
        import fcntl

        path = (
            Path(make_url(self.settings.database_url).database)
            .resolve()
            .with_suffix(".worker.lock")
        )
        stream = path.open("a")
        path.chmod(0o600)
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            stream.close()
            raise RuntimeError(
                "Database đã có worker khác đang chạy. Dừng backend cũ trước khi khởi động server này."
            ) from None
        self.worker_lock = stream
        self.thread = threading.Thread(target=self.loop, name="gos-jobs", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_signal.set()
        if self.thread:
            self.thread.join(timeout=5)
        if self.worker_lock and (not self.thread or not self.thread.is_alive()):
            self.worker_lock.close()
            self.worker_lock = None

    def loop(self):
        while not self.stop_signal.is_set():
            try:
                self.tick()
            except Exception:
                log.error("job_tick_failed")  # no exception payload/SQL parameters
            self.stop_signal.wait(self.settings.job_poll_seconds)

    def tick(self):
        if self.settings.rag_jobs_enabled and not self.backend.ready:
            return 0
        if not self.settings.rag_jobs_enabled:
            return int(self.send_one())
        # Keep dependent stages sequential; never hold a SQL transaction during indexing/model work.
        return sum(
            [self.ingestion_one(), self.events.process_one(), self.send_one(), self.cleanup_one()]
        )

    def ingestion_one(self):
        now = self.clock.stamp()
        with self.db.write() as s:
            job = s.one(
                "SELECT * FROM ingestion_jobs WHERE (status='queued' AND next_attempt_at<=:n) OR (status='processing' AND lease_expires_at<=:n) ORDER BY created_at,id LIMIT 1",
                n=now,
            )
            if not job:
                return False
            version = s.one(
                "SELECT * FROM document_versions WHERE id=:v", v=job["document_version_id"]
            )
            doc = s.one("SELECT * FROM documents WHERE id=:d", d=version["document_id"])
            if doc["status"] == "revoked":
                s.update("ingestion_jobs", "id", job["id"], status="cancelled", finished_at=now)
                return True
            if job["attempts"] >= job["max_attempts"]:
                s.update(
                    "ingestion_jobs",
                    "id",
                    job["id"],
                    status="failed",
                    error_code="retry_exhausted",
                    finished_at=now,
                )
                s.update(
                    "document_versions",
                    "id",
                    version["id"],
                    status="failed",
                    error_code="retry_exhausted",
                )
                return True
            token = uid()
            s.update(
                "ingestion_jobs",
                "id",
                job["id"],
                status="processing",
                stage="parse",
                lease_token=token,
                lease_expires_at=stamp(
                    self.clock.now() + timedelta(seconds=self.settings.job_lease_seconds)
                ),
                attempts=job["attempts"] + 1,
                started_at=job["started_at"] or now,
            )
            s.update("document_versions", "id", version["id"], status="indexing")
            scopes = document_scopes(s, doc["id"])
            config = json.loads(version["extraction_config_json"])
        try:
            chunks = self.backend.index(
                version,
                self.settings.upload_dir / version["file_path"],
                scopes,
                {
                    k: v
                    for k, v in config.items()
                    if not k.startswith("_") and k != "section_scopes"
                },
            )
            require(bool(chunks), 422, "empty_index", "Không có chunk được index.")
            seen = set()
            for c in chunks:
                require(
                    c["scope_id"] in scopes
                    and c["point_id"] == point_id(version["id"], c["chunk_id"], c["scope_id"]),
                    422,
                    "invalid_chunk_manifest",
                    "Point/scope không hợp lệ.",
                )
                require(c["point_id"] not in seen, 422, "duplicate_chunk", "Chunk-scope trùng.")
                seen.add(c["point_id"])
                require(
                    c.get("embedding_model")
                    and isinstance(c.get("vector_size"), int)
                    and c["vector_size"] > 0,
                    422,
                    "missing_embedding_metadata",
                    "Thiếu metadata embedding.",
                )
            require(
                len({(c["embedding_model"], c["vector_size"]) for c in chunks}) == 1,
                422,
                "mixed_embedding_spaces",
                "Không được trộn embedding spaces.",
            )
            chunk_scopes = {}
            for chunk in chunks:
                chunk_scopes.setdefault(chunk["chunk_id"], set()).add(chunk["scope_id"])
            require(
                all(targets == set(scopes) for targets in chunk_scopes.values()),
                422,
                "incomplete_document_acl",
                "Mọi chunk phải kế thừa toàn bộ quyền của tài liệu.",
            )
            if config.get("embedding_model"):
                require(
                    all(c["embedding_model"] == config["embedding_model"] for c in chunks),
                    422,
                    "embedding_model_mismatch",
                    "Backend index dùng sai model được yêu cầu.",
                )
            with self.db.write() as s:
                s.execute(
                    "UPDATE ingestion_jobs SET stage='activate' WHERE id=:j AND lease_token=:t AND status='processing'",
                    j=job["id"],
                    t=token,
                )
            with self.db.write() as s:
                fresh = s.one(
                    "SELECT * FROM ingestion_jobs WHERE id=:j AND lease_token=:t AND status='processing'",
                    j=job["id"],
                    t=token,
                )
                if not fresh:
                    return True
                latest = s.one("SELECT * FROM documents WHERE id=:d", d=doc["id"])
                require(
                    latest["status"] != "revoked"
                    and latest["revision"] == config["_base_revision"]
                    and latest["active_version_id"] == config["_base_active_version_id"],
                    409,
                    "stale_version",
                    "Tài liệu thay đổi trong lúc index.",
                )
                now = self.clock.stamp()
                for c in chunks:
                    s.execute(
                        "INSERT OR IGNORE INTO document_chunks (point_id,document_id,document_version_id,chunk_id,scope_id,section_id,section_path,topic,page,sheet_name,row_start,row_end,content_sha256,created_at,indexed_at) VALUES (:p,:d,:v,:ch,:scope,:sec,:path,:topic,:page,:sheet,:rs,:re,:sha,:n,:n)",
                        p=c["point_id"],
                        d=doc["id"],
                        v=version["id"],
                        ch=c["chunk_id"],
                        scope=c["scope_id"],
                        sec=c.get("section_id"),
                        path=c.get("section_path"),
                        topic=clean(self.settings, c.get("topic", doc["topic"])),
                        page=c.get("page"),
                        sheet=c.get("sheet_name"),
                        rs=c.get("row_start"),
                        re=c.get("row_end"),
                        sha=c["content_sha256"],
                        n=now,
                    )
                logical = len({c["chunk_id"] for c in chunks})
                s.update(
                    "document_versions",
                    "id",
                    version["id"],
                    status="ready",
                    chunk_count=logical,
                    point_count=len(chunks),
                    embedding_model=chunks[0]["embedding_model"],
                    vector_size=chunks[0]["vector_size"],
                    indexed_at=now,
                    error_code=None,
                )
                old = latest["active_version_id"]
                if old:
                    s.update("document_versions", "id", old, status="superseded")
                s.update(
                    "documents",
                    "id",
                    doc["id"],
                    status="active",
                    active_version_id=version["id"],
                    revision=latest["revision"] + 1,
                    updated_at=now,
                )
                s.update(
                    "document_versions", "id", version["id"], status="active", activated_at=now
                )
                s.update(
                    "ingestion_jobs",
                    "id",
                    job["id"],
                    status="succeeded",
                    stage="done",
                    chunks_indexed=logical,
                    points_indexed=len(chunks),
                    finished_at=now,
                    error_code=None,
                )
                if old:
                    s.execute(
                        "INSERT OR IGNORE INTO cleanup_jobs (id,document_version_id,cleanup_kind,next_attempt_at,created_at) VALUES (:id,:v,'vectors',:n,:n)",
                        id=uid(),
                        v=old,
                        n=now,
                    )
                s.audit(
                    None,
                    "document.activate",
                    "document",
                    doc["id"],
                    now,
                    job["id"],
                    {"version_id": version["id"]},
                )
        except Exception as exc:
            code = exc.code if isinstance(exc, AppError) else "ingestion_failure"
            from app.services.progress_service import error_message

            log.error(
                "ingestion_failed job_id=%s document_id=%s version_id=%s code=%s error_type=%s",
                job["id"],
                doc["id"],
                version["id"],
                code,
                type(exc).__name__,
            )
            with self.db.write() as s:
                fresh = s.one(
                    "SELECT id FROM ingestion_jobs WHERE id=:j AND lease_token=:t AND status='processing'",
                    j=job["id"],
                    t=token,
                )
                if fresh:
                    now = self.clock.stamp()
                    s.update(
                        "ingestion_jobs",
                        "id",
                        job["id"],
                        status="failed",
                        error_code=code,
                        error_message_redacted=clean(
                            self.settings,
                            exc.message if isinstance(exc, AppError) else error_message(code),
                        ),
                        finished_at=now,
                    )
                    s.execute(
                        "UPDATE document_versions SET status='failed',error_code=:code WHERE id=:v AND status!='revoked'",
                        code=code,
                        v=version["id"],
                    )
        return True

    def send_one(self):
        with self.db.write() as s:
            row = s.one(
                "SELECT o.* FROM outbound_messages o JOIN webhook_events e ON e.event_key=o.event_key WHERE (:zalo_enabled=1 OR e.platform!='zalo_bot') AND ((o.status='pending' AND o.next_attempt_at<=:n) OR (o.status='sending' AND o.lease_expires_at<=:n)) ORDER BY o.rowid LIMIT 1",
                n=self.clock.stamp(),
                zalo_enabled=int(self.settings.zalo_bot_enabled),
            )
            if not row:
                return False
            event = s.one("SELECT * FROM webhook_events WHERE event_key=:e", e=row["event_key"])
            if event["platform"] != "zalo_bot":
                s.update(
                    "outbound_messages",
                    "id",
                    row["id"],
                    status="cancelled",
                    error_code="transport_removed",
                )
                return True
            now = self.clock.stamp()
            # Policy notice intentionally reports denial. All business replies recheck current access.
            if row["message_kind"] not in {"policy_notice", "validation_notice"}:
                access = event_access(s, event)
                if row["message_kind"] == "teacher_answer":
                    reply = s.one(
                        "SELECT r.*,u.role,u.is_active FROM ticket_replies r JOIN users u ON u.id=r.teacher_id WHERE r.id=:r",
                        r=row["ticket_reply_id"],
                    )
                    teacher_ok = (
                        reply
                        and reply["is_active"]
                        and (
                            reply["role"] == "admin"
                            or s.one(
                                "SELECT teacher_id FROM teacher_assignments WHERE teacher_id=:u AND class_id=:c AND is_active=1",
                                u=reply["teacher_id"],
                                c=event["class_id"],
                            )
                        )
                    )
                    access = access and teacher_ok
                if not access:
                    s.update(
                        "outbound_messages",
                        "id",
                        row["id"],
                        status="cancelled",
                        error_code="access_revoked",
                    )
                    return True
            citations = json.loads(row["citations_json"])
            if citations and not all(citation_valid(s, event, c) for c in citations):
                tid = self.events.handoff(s, event, "citation_revoked_before_send", now)
                text = f"Nguồn đã thay đổi. Đã chuyển giảng viên hỗ trợ. Mã yêu cầu: {tid}."
                s.update(
                    "outbound_messages",
                    "id",
                    row["id"],
                    text_redacted=text,
                    citations_json="[]",
                    ticket_id=tid,
                )
                s.execute(
                    "UPDATE messages SET status='withdrawn',memory_eligible=0 WHERE event_key=:e AND message_kind='answer'",
                    e=event["event_key"],
                )
                question = s.one(
                    "SELECT session_id FROM messages WHERE event_key=:e AND message_kind='question'",
                    e=event["event_key"],
                )
                if question:
                    memory.add_message(s, event, question["session_id"], "handoff", text, now)
                s.execute(
                    "UPDATE rag_runs SET status='insufficient_evidence',evidence_sufficient=0,evidence_reason_redacted='citation_revoked_before_send' WHERE event_key=:e",
                    e=event["event_key"],
                )
                s.update(
                    "webhook_events",
                    "event_key",
                    event["event_key"],
                    outcome_code="insufficient_evidence",
                )
                s.security(
                    "citation_revoked_before_send", event["request_id"], now, event["event_key"]
                )
                row = s.one("SELECT * FROM outbound_messages WHERE id=:i", i=row["id"])
            if event["platform"] == "zalo_bot" and not self.settings.zalo_bot_enabled:
                # Never mark a real reply sent while its transport is disabled.
                return False
            if row["attempts"] >= row["max_attempts"]:
                s.update(
                    "outbound_messages",
                    "id",
                    row["id"],
                    status="failed",
                    error_code="outbound_retry_exhausted",
                )
                return True
            token = uid()
            s.update(
                "outbound_messages",
                "id",
                row["id"],
                status="sending",
                lease_token=token,
                lease_expires_at=stamp(self.clock.now() + timedelta(seconds=30)),
                attempts=row["attempts"] + 1,
            )
            row = s.one("SELECT * FROM outbound_messages WHERE id=:i", i=row["id"])
            group = s.one(
                "SELECT external_group_id FROM group_bindings WHERE id=:g",
                g=row["group_binding_id"],
            )
            delivery = (row, group["external_group_id"], token)
        if delivery:
            self.deliver_zalo(*delivery[:3])
        return True

    def deliver_zalo(self, row, group_id, token):
        from app.integrations.zalo_bot import BotAPIError, BotClient

        external_id = None
        try:
            external_id = BotClient(self.settings.zalo_bot_token.get_secret_value()).send(
                group_id, row["text_redacted"]
            )
        except BotAPIError:
            pass
        with self.db.write() as s:
            fresh = s.one(
                "SELECT id FROM outbound_messages WHERE id=:i AND status='sending' AND lease_token=:t",
                i=row["id"],
                t=token,
            )
            if not fresh:
                return
            now = self.clock.stamp()
            s.update(
                "outbound_messages",
                "id",
                row["id"],
                status="sent" if external_id else "pending",
                sent_at=now if external_id else None,
                external_message_id=external_id,
                next_attempt_at=stamp(self.clock.now() + timedelta(seconds=5)),
                error_code=None if external_id else "zalo_send_failed",
            )
            if external_id and row["message_kind"] == "teacher_answer":
                s.execute(
                    "UPDATE support_tickets SET status='answered',answered_at=:n,updated_at=:n,revision=revision+1 WHERE id=:t AND status IN ('open','assigned')",
                    n=now,
                    t=row["ticket_id"],
                )
        log.info(
            "zalo_send status=%s reply_id=%s", "delivered" if external_id else "retry", row["id"]
        )

    def cleanup_one(self):
        now = self.clock.stamp()
        with self.db.write() as s:
            job = s.one(
                "SELECT j.*,v.document_id FROM cleanup_jobs j JOIN document_versions v ON v.id=j.document_version_id WHERE (j.status='queued' AND j.next_attempt_at<=:n) OR (j.status='processing' AND j.lease_expires_at<=:n) ORDER BY j.created_at,j.id LIMIT 1",
                n=now,
            )
            if not job:
                return False
            doc = s.one("SELECT * FROM documents WHERE id=:d", d=job["document_id"])
            if (
                doc["active_version_id"] == job["document_version_id"]
                or job["cleanup_kind"] == "file"
            ):
                s.update(
                    "cleanup_jobs",
                    "id",
                    job["id"],
                    status="cancelled",
                    finished_at=now,
                    error_code="active_or_retention_protected",
                )
                return True
            if job["attempts"] >= job["max_attempts"]:
                s.update(
                    "cleanup_jobs",
                    "id",
                    job["id"],
                    status="failed",
                    finished_at=now,
                    error_code="retry_exhausted",
                )
                return True
            token = uid()
            s.update(
                "cleanup_jobs",
                "id",
                job["id"],
                status="processing",
                lease_token=token,
                lease_expires_at=stamp(
                    self.clock.now() + timedelta(seconds=self.settings.job_lease_seconds)
                ),
                attempts=job["attempts"] + 1,
            )
        try:
            self.backend.cleanup(job["document_id"], job["document_version_id"])
            status, code = "succeeded", None
        except Exception as exc:
            status, code = "queued", exc.code if isinstance(exc, AppError) else "cleanup_failure"
        with self.db.write() as s:
            s.execute(
                "UPDATE cleanup_jobs SET status=:st,error_code=:code,next_attempt_at=:retry,finished_at=:finished WHERE id=:j AND lease_token=:token AND status='processing'",
                st=status,
                code=code,
                retry=stamp(self.clock.now() + timedelta(seconds=min(60, 2 ** job["attempts"]))),
                finished=self.clock.stamp() if status == "succeeded" else None,
                j=job["id"],
                token=token,
            )
        return True
