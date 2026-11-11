import hashlib
import json
import logging
from pathlib import Path

from app.core.errors import require
from app.core.security import clean
from app.rag.parsers.files import validate_file
from app.repositories.store import encode, uid
from app.services.access_service import check_document, check_scope, document_scopes
from app.services.progress_service import index_progress


def validate_config(config, settings=None):
    from pydantic import ValidationError

    from app.schemas.documents import ProcessingConfig

    try:
        result = ProcessingConfig.model_validate(config).model_dump(exclude_none=True)
        if settings and settings.rag_enabled:
            result.setdefault("embedding_model", settings.rag_embedding_model)
            result.setdefault("parser_revision", "structure-v1")
            result.setdefault("chunk_size", 900)
            result.setdefault("chunk_overlap", min(100, result["chunk_size"] - 1))
        return result
    except ValidationError:
        require(
            False,
            422,
            "invalid_metadata",
            "Cấu hình xử lý không hợp lệ; MVP không hỗ trợ phân quyền theo chương.",
        )


class DocumentService:
    def __init__(self, db, clock, settings):
        self.db, self.clock, self.settings = db, clock, settings

    def upload(
        self,
        user,
        request_id,
        data,
        filename,
        title=None,
        topic=None,
        scopes=None,
        config=None,
        did=None,
        change_note=None,
        source_code=None,
        source_version=None,
        force_reindex=False,
    ):
        suffix = Path(filename or "").suffix.lower()
        require(
            len(data) <= self.settings.max_upload_bytes,
            413,
            "file_too_large",
            "File vượt giới hạn upload.",
        )
        mime = validate_file(data, suffix)
        digest = hashlib.sha256(data).hexdigest()
        now = self.clock.stamp()
        path = None
        try:
            with self.db.write() as s:
                if did:
                    doc = check_document(s, user, did)
                    require(
                        doc["status"] != "revoked", 409, "document_revoked", "Tài liệu đã thu hồi."
                    )
                    scopes = document_scopes(s, did)
                    current = (
                        s.one(
                            "SELECT * FROM document_versions WHERE id=:v",
                            v=doc["active_version_id"],
                        )
                        if doc["active_version_id"]
                        else None
                    )
                    if not self.settings.rag_jobs_enabled:
                        current = s.one(
                            "SELECT * FROM document_versions WHERE document_id=:d ORDER BY version DESC LIMIT 1",
                            d=did,
                        )
                    if config is None:
                        current_config = (
                            json.loads(current["extraction_config_json"]) if current else {}
                        )
                        config = {
                            k: v
                            for k, v in current_config.items()
                            if not k.startswith("_") and k != "section_scopes"
                        }
                    config = validate_config(config, self.settings)
                    if (
                        not force_reindex
                        and current
                        and current["sha256"] == digest
                        and {
                            k: v
                            for k, v in json.loads(current["extraction_config_json"]).items()
                            if not k.startswith("_")
                        }
                        == config
                    ):
                        return {
                            "document_id": did,
                            "version_id": current["id"],
                            "status": "unchanged",
                            "job_id": None,
                            "version": current["version"],
                        }
                    require(
                        not s.one(
                            "SELECT j.id FROM ingestion_jobs j JOIN document_versions v ON v.id=j.document_version_id WHERE v.document_id=:d AND j.status IN ('queued','processing')",
                            d=did,
                        ),
                        409,
                        "ingestion_in_progress",
                        "Tài liệu đang được index.",
                    )
                    number = s.one(
                        "SELECT COALESCE(MAX(version),0)+1 AS n FROM document_versions WHERE document_id=:d",
                        d=did,
                    )["n"]
                else:
                    require(
                        bool(scopes)
                        and len(scopes) <= 20
                        and all(isinstance(x, str) for x in scopes),
                        422,
                        "invalid_scope",
                        "Cần 1–20 scope hợp lệ.",
                    )
                    scopes = sorted(set(scopes))
                    for scope in scopes:
                        check_scope(s, user, scope)
                    config = config or {}
                    config = validate_config(config, self.settings)
                    did = uid()
                    s.insert(
                        "documents",
                        id=did,
                        title=clean(self.settings, title),
                        topic=clean(self.settings, topic),
                        source_code=source_code,
                        source_kind="file",
                        created_by=user["id"],
                        created_at=now,
                        updated_at=now,
                    )
                    for scope in scopes:
                        s.insert(
                            "document_access",
                            document_id=did,
                            scope_id=scope,
                            granted_by=user["id"],
                            created_at=now,
                        )
                    doc = s.one("SELECT * FROM documents WHERE id=:d", d=did)
                    number = 1
                vid = uid()
                job = uid()
                relative = Path(did) / vid / ("source" + suffix)
                path = self.settings.upload_dir / relative
                path.parent.mkdir(parents=True, exist_ok=False)
                with path.open("xb") as stream:
                    stream.write(data)
                internal = {
                    **config,
                    "_base_revision": doc["revision"],
                    "_base_active_version_id": doc["active_version_id"],
                }
                s.insert(
                    "document_versions",
                    id=vid,
                    document_id=did,
                    version=number,
                    source_version=source_version,
                    sha256=digest,
                    file_path=relative.as_posix(),
                    original_filename=clean(self.settings, Path(filename).name),
                    mime_type=mime,
                    file_size_bytes=len(data),
                    extraction_config_json=encode(internal),
                    change_note=clean(self.settings, change_note or ""),
                    uploaded_by=user["id"],
                    uploaded_at=now,
                )
                s.insert(
                    "ingestion_jobs",
                    id=job,
                    document_version_id=vid,
                    next_attempt_at=now,
                    created_at=now,
                    max_attempts=self.settings.job_max_attempts,
                    status="queued" if self.settings.rag_jobs_enabled else "cancelled",
                    error_code=None if self.settings.rag_jobs_enabled else "rag_deferred",
                    finished_at=None if self.settings.rag_jobs_enabled else now,
                )
                s.update("documents", "id", did, updated_at=now)
                s.audit(
                    user["id"],
                    "document.upload",
                    "document",
                    did,
                    now,
                    request_id,
                    {"version_id": vid, "version": number},
                )
                logging.getLogger(__name__).info(
                    "document_uploaded request_id=%s document_id=%s version_id=%s version=%s bytes=%s job_id=%s",
                    request_id,
                    did,
                    vid,
                    number,
                    len(data),
                    job,
                )
                return {
                    "document_id": did,
                    "version_id": vid,
                    "job_id": job,
                    "version": number,
                    "status": "queued" if self.settings.rag_jobs_enabled else "stored",
                }
        except BaseException:
            if path and path.exists():
                path.unlink()
            raise

    def reindex(self, user, did, body, request_id):
        require(
            self.settings.rag_jobs_enabled,
            409,
            "rag_disabled",
            "Lập chỉ mục chưa được bật trong giai đoạn này.",
        )
        with self.db.read() as s:
            doc = check_document(s, user, did)
            require(doc["status"] != "revoked", 409, "document_revoked", "Tài liệu đã thu hồi.")
            source = s.one(
                "SELECT * FROM document_versions WHERE document_id=:d ORDER BY version DESC LIMIT 1",
                d=did,
            )
        require(source is not None, 409, "missing_source", "Tài liệu chưa có file nguồn.")
        config = (
            body.extraction_config.model_dump(exclude_none=True)
            if body.extraction_config is not None
            else validate_config(
                {
                    k: v
                    for k, v in json.loads(source["extraction_config_json"]).items()
                    if not k.startswith("_") and k != "section_scopes"
                }
            )
        )
        # Reuse only the explicitly selected document's source, never match by name/content.
        return self.upload(
            user,
            request_id,
            (self.settings.upload_dir / source["file_path"]).read_bytes(),
            source["original_filename"],
            did=did,
            config=config,
            change_note=body.change_note,
            force_reindex=True,
        )

    def revoke(self, user, did, request_id):
        now = self.clock.stamp()
        with self.db.write() as s:
            doc = check_document(s, user, did)
            if doc["status"] == "revoked":
                return {"document_id": did, "status": "revoked"}
            s.update(
                "documents",
                "id",
                did,
                status="revoked",
                active_version_id=None,
                revision=doc["revision"] + 1,
                deleted_at=now,
                deleted_by=user["id"],
                updated_at=now,
            )
            versions = s.all("SELECT id FROM document_versions WHERE document_id=:d", d=did)
            for v in versions:
                s.update("document_versions", "id", v["id"], status="revoked")
                s.execute(
                    "UPDATE ingestion_jobs SET status='cancelled',finished_at=:n WHERE document_version_id=:v AND status IN ('queued','processing')",
                    n=now,
                    v=v["id"],
                )
                # An in-flight index may have written points before committing its manifest.
                s.execute(
                    "INSERT OR IGNORE INTO cleanup_jobs (id,document_version_id,cleanup_kind,next_attempt_at,created_at,status,error_code,finished_at) VALUES (:id,:v,'vectors',:n,:n,:status,:error,:finished)",
                    id=uid(),
                    v=v["id"],
                    n=now,
                    status="queued" if self.settings.rag_jobs_enabled else "cancelled",
                    error=None if self.settings.rag_jobs_enabled else "rag_deferred",
                    finished=None if self.settings.rag_jobs_enabled else now,
                )
            s.execute(
                "UPDATE faq_entries SET status='revoked',updated_at=:n WHERE document_id=:d",
                n=now,
                d=did,
            )
            s.audit(user["id"], "document.revoke", "document", did, now, request_id)
        return {"document_id": did, "status": "revoked"}

    def job(self, s, user, jid):
        job = s.one(
            "SELECT j.*,v.document_id,v.chunk_count AS chunks_total,v.point_count AS points_total,v.status AS version_status,d.active_version_id,d.status AS doc_status FROM ingestion_jobs j JOIN document_versions v ON v.id=j.document_version_id JOIN documents d ON d.id=v.document_id WHERE j.id=:j",
            j=jid,
        )
        require(job is not None, 404, "not_found", "Không tìm thấy job.")
        check_document(s, user, job["document_id"])
        state = (
            "revoked"
            if job["doc_status"] == "revoked"
            else (
                "active"
                if job["active_version_id"] == job["document_version_id"]
                else ("indexing" if job["status"] == "processing" else job["version_status"])
            )
        )
        return {
            **{k: v for k, v in job.items() if k not in {"lease_token", "lease_expires_at"}},
            "document_state": state,
            "progress": index_progress(job),
        }

    def retry(self, user, jid, request_id):
        require(
            self.settings.rag_jobs_enabled,
            409,
            "rag_disabled",
            "Lập chỉ mục chưa được bật trong giai đoạn này.",
        )
        with self.db.write() as s:
            job = self.job(s, user, jid)
            require(job["doc_status"] != "revoked", 409, "document_revoked", "Tài liệu đã thu hồi.")
            require(job["status"] == "failed", 409, "job_not_failed", "Chỉ retry job đã thất bại.")
            require(
                not s.one(
                    "SELECT j.id FROM ingestion_jobs j JOIN document_versions v ON v.id=j.document_version_id WHERE v.document_id=:d AND j.status IN ('queued','processing')",
                    d=job["document_id"],
                ),
                409,
                "ingestion_in_progress",
                "Tài liệu đang có job chạy.",
            )
            version = s.one(
                "SELECT * FROM document_versions WHERE id=:v", v=job["document_version_id"]
            )
            config = json.loads(version["extraction_config_json"])
            doc = s.one("SELECT * FROM documents WHERE id=:d", d=job["document_id"])
            require(
                doc["revision"] == config["_base_revision"]
                and doc["active_version_id"] == config["_base_active_version_id"],
                409,
                "stale_version",
                "Tài liệu đã thay đổi sau job này; hãy upload version mới.",
            )
            now = self.clock.stamp()
            key = uid()
            s.update("document_versions", "id", version["id"], status="queued", error_code=None)
            s.insert(
                "ingestion_jobs",
                id=key,
                document_version_id=version["id"],
                created_at=now,
                next_attempt_at=now,
                max_attempts=self.settings.job_max_attempts,
            )
            s.audit(user["id"], "ingestion.retry", "job", key, now, request_id)
            return {"job_id": key, "version_id": version["id"], "status": "queued"}
