"""BKAI -> Qdrant Local Top 10 -> mMARCO Top 5 -> evidence -> Claude.
SQLite remains the authority for document ACLs and active versions.
"""

import hashlib
import logging
import threading
import time
from contextlib import contextmanager
from datetime import timedelta

from qdrant_client import QdrantClient
from qdrant_client import models as qm

from app.core.clock import stamp
from app.core.errors import AppError, require
from app.core.security import clean
from app.jobs.runner import point_id
from app.rag.models import LocalModels
from app.rag.parsers.structure import chunks, normalized
from app.rag.provider import ClaudeGateway
from app.rag.query_rewriter import history_for_rewrite, resolve_rewrite
from app.rag.schemas import RAGResult
from app.repositories.store import encode, uid

log = logging.getLogger(__name__)


class LocalRAG:
    ready = True

    def __init__(self, settings, *, models=None, gateway=None):
        self.settings = settings
        self.models = models or LocalModels(settings)
        self.gateway = gateway or ClaudeGateway(settings)
        self.lock = threading.RLock()
        self.client = None
        self.db = self.clock = None
        self.last_trace = {}

    def bind(self, db, clock):
        self.db, self.clock = db, clock

    def vector_store(self):
        if self.client is None:
            self.settings.rag_vector_dir.mkdir(parents=True, exist_ok=True)
            self.client = QdrantClient(
                path=str(self.settings.rag_vector_dir), force_disable_check_same_thread=True
            )
        return self.client

    @staticmethod
    def collection(model):
        return "gos_" + hashlib.sha256(model.encode()).hexdigest()[:20]

    @contextmanager
    def call(self, owner, stage, model):
        key = uid()
        stats = {}
        started = time.monotonic()
        with self.db.write() as s:
            owner_key, owner_id = next(iter(owner.items()))
            attempt = s.one(
                f"SELECT COALESCE(MAX(attempt_no),0)+1 AS n FROM rag_run_attempts WHERE {owner_key}=:o AND stage=:stage",
                o=owner_id,
                stage=stage,
            )["n"]
            s.insert(
                "rag_run_attempts",
                id=key,
                **owner,
                stage=stage,
                attempt_no=attempt,
                call_key=key,
                provider="hhtech-anthropic" if stage in {"generate", "query_rewrite"} else "local",
                model=model,
                status="started",
                started_at=self.clock.stamp(),
            )
        try:
            yield stats
        except Exception as exc:
            code = exc.code if isinstance(exc, AppError) else "rag_stage_failure"
            with self.db.write() as s:
                s.update(
                    "rag_run_attempts",
                    "id",
                    key,
                    status="unknown" if code == "llm_transport_error" else "failed",
                    finished_at=self.clock.stamp(),
                    error_code=code,
                    **stats,
                )
            log.warning(
                "rag_stage_failed stage=%s code=%s call_id=%s owner=%s",
                stage,
                code,
                key,
                next(iter(owner.values())),
            )
            raise
        else:
            with self.db.write() as s:
                s.update(
                    "rag_run_attempts",
                    "id",
                    key,
                    status="succeeded",
                    finished_at=self.clock.stamp(),
                    **stats,
                )
            log.info(
                "rag_stage_done stage=%s latency_ms=%s call_id=%s owner=%s",
                stage,
                int((time.monotonic() - started) * 1000),
                key,
                next(iter(owner.values())),
            )

    def index_stage(
        self, job, version, stage, *, chunks_done=None, points_done=None, total=None, scopes=None
    ):
        with self.db.write() as s:
            fresh = s.one(
                "SELECT id FROM ingestion_jobs WHERE id=:j AND lease_token=:t AND status='processing'",
                j=job["id"],
                t=job["lease_token"],
            )
            require(
                fresh is not None, 409, "stale_index_claim", "Job index đã đổi chủ hoặc bị hủy."
            )
            changes = {
                "stage": stage,
                "lease_expires_at": stamp(
                    self.clock.now() + timedelta(seconds=self.settings.job_lease_seconds)
                ),
            }
            if chunks_done is not None:
                changes["chunks_indexed"] = chunks_done
            if points_done is not None:
                changes["points_indexed"] = points_done
            s.update("ingestion_jobs", "id", job["id"], **changes)
            if total is not None:
                s.update(
                    "document_versions",
                    "id",
                    version["id"],
                    chunk_count=total,
                    point_count=total * len(scopes),
                )
        log.info(
            "ingestion_progress job_id=%s document_id=%s stage=%s chunks_done=%s points_done=%s chunks_total=%s",
            job["id"],
            version["document_id"],
            stage,
            chunks_done,
            points_done,
            total,
        )

    def index(self, version, path, scopes, config):
        with self.lock:
            model = config.get("embedding_model", self.settings.rag_embedding_model)
            # Never load arbitrary executable/custom models from an uploaded config.
            require(
                model in self.settings.rag_allowed_embedding_models,
                422,
                "unsupported_embedding_model",
                "Model embedding chưa được quản trị cấu hình.",
            )
            revision = config.get("parser_revision", "structure-v1")
            require(
                revision == "structure-v1",
                422,
                "unsupported_parser_revision",
                "Parser revision chưa được hỗ trợ.",
            )
            with self.db.read() as s:
                job = s.one(
                    "SELECT id,lease_token FROM ingestion_jobs WHERE document_version_id=:v AND status='processing'",
                    v=version["id"],
                )
                doc = s.one(
                    "SELECT title,topic FROM documents WHERE id=:d", d=version["document_id"]
                )
            require(job is not None, 409, "missing_index_claim", "Chưa có job được claim.")
            owner = {"ingestion_job_id": job["id"]}
            with self.call(owner, "ingestion_embed", model):
                self.index_stage(job, version, "parse")
                manifest = chunks(
                    path,
                    config.get("chunk_size", 900),
                    config.get("chunk_overlap", 100),
                    fits=lambda text: self.models.fits(text, model),
                    on_progress=lambda count: self.index_stage(
                        job, version, "chunk", total=count, scopes=scopes
                    ),
                )
                vectors = []
                self.index_stage(
                    job, version, "embed", chunks_done=0, total=len(manifest), scopes=scopes
                )
                for offset in range(0, len(manifest), 16):
                    vectors.extend(
                        self.models.embed(
                            [c["text"] for c in manifest[offset : offset + 16]], model
                        )
                    )
                    self.index_stage(job, version, "embed", chunks_done=len(vectors))
                require(
                    len(vectors) == len(manifest) and len(vectors[0]) > 0,
                    422,
                    "invalid_embeddings",
                    "Embedding không hợp lệ.",
                )
                client = self.vector_store()
                collection = self.collection(model)
                if not client.collection_exists(collection):
                    client.create_collection(
                        collection,
                        vectors_config=qm.VectorParams(
                            size=len(vectors[0]), distance=qm.Distance.COSINE
                        ),
                    )
                points, rows = [], []
                for chunk, vector in zip(manifest, vectors, strict=True):
                    for scope in scopes:
                        pid = point_id(version["id"], chunk["chunk_id"], scope)
                        payload = {
                            **chunk,
                            "document_id": version["document_id"],
                            "document_version_id": version["id"],
                            "scope_id": scope,
                            "title": doc["title"],
                            "topic": doc["topic"],
                            "embedding_model": model,
                            "vector_size": len(vector),
                            "content_sha256": hashlib.sha256(chunk["text"].encode()).hexdigest(),
                        }
                        points.append(qm.PointStruct(id=pid, vector=vector, payload=payload))
                        rows.append({**payload, "point_id": pid})
                self.index_stage(job, version, "upsert", points_done=0)
                for offset in range(0, len(points), 64):
                    client.upsert(collection, points=points[offset : offset + 64], wait=True)
                    self.index_stage(
                        job, version, "upsert", points_done=min(offset + 64, len(points))
                    )
                self.index_stage(job, version, "verify")
                stored = client.retrieve(
                    collection, ids=[p.id for p in points], with_payload=True, with_vectors=False
                )
                require(
                    len(stored) == len(points),
                    503,
                    "index_verification_failed",
                    "Qdrant thiếu points sau index.",
                )
                by_id = {str(p.id): p.payload for p in stored}
                require(
                    all(by_id[p.id] == p.payload for p in points),
                    503,
                    "index_verification_failed",
                    "Metadata index không khớp nguồn.",
                )
                sample = client.query_points(
                    collection,
                    query=vectors[0],
                    query_filter=qm.Filter(
                        must=[
                            qm.FieldCondition(
                                key="document_version_id", match=qm.MatchValue(value=version["id"])
                            )
                        ]
                    ),
                    limit=1,
                ).points
                require(
                    bool(sample),
                    503,
                    "index_verification_failed",
                    "Không truy xuất được index mới.",
                )
            log.info(
                "rag_index_ready document_id=%s version=%s chunks=%s points=%s",
                version["document_id"],
                version["version"],
                len(manifest),
                len(rows),
            )
            return rows

    def rewrite_question(self, context, owner):
        original = context.question.strip()
        metadata = {
            "status": "no_history" if not context.memory else "disabled",
            "relation": "standalone",
            "original_question": original,
            "resolved_question": original,
            "used_turn_ids": [],
            "provider_called": False,
        }
        if self.settings.rag_rewrite_enabled and context.memory:
            model = self.settings.rag_rewrite_model or self.settings.claude_model
            try:
                metadata["provider_called"] = True
                with self.call(owner, "query_rewrite", model) as stats:
                    try:
                        output, usage = self.gateway.rewrite(original, context.memory)
                        stats.update(usage)
                        metadata.update(
                            resolve_rewrite(original, history_for_rewrite(context.memory), output)
                        )
                    except Exception:
                        stats.update(getattr(self.gateway, "last_usage", {}))
                        raise
            except Exception as exc:
                metadata.update(
                    status="error_fallback",
                    relation="unknown",
                    resolved_question=original,
                    used_turn_ids=[],
                    error_code=exc.code if isinstance(exc, AppError) else "rewrite_failure",
                )
                log.warning(
                    "query_rewrite_fallback event_key=%s code=%s",
                    context.event_key,
                    metadata["error_code"],
                )
        metadata["original_question"] = clean(self.settings, metadata["original_question"])
        metadata["resolved_question"] = clean(self.settings, metadata["resolved_question"])
        with self.db.write() as s:
            s.update("rag_runs", "id", owner["rag_run_id"], query_rewrite_json=encode(metadata))
        self.last_trace["rewrite"] = metadata
        log.info(
            "query_rewrite_result event_key=%s status=%s relation=%s provider_called=%s",
            context.event_key,
            metadata["status"],
            metadata["relation"],
            metadata["provider_called"],
        )
        return metadata["resolved_question"]

    def retrieve(self, context, owner):
        versions = context.active_document_version_ids
        scopes = context.allowed_scope_ids
        if not versions or not scopes:
            return []
        with self.db.read() as s:
            allowed = {
                r["id"]: r
                for r in s.all(
                    "SELECT v.id,v.embedding_model FROM document_versions v JOIN documents d ON d.active_version_id=v.id WHERE d.status='active'"
                )
                if r["id"] in versions
            }
        if not allowed:
            return []
        candidates = {}
        # Rewriting resolves context; only currently retrieved text is evidence.
        question = self.rewrite_question(context, owner)
        for model in sorted(
            {r["embedding_model"] for r in allowed.values() if r["embedding_model"]}
        ):
            require(
                model in self.settings.rag_allowed_embedding_models,
                503,
                "unsupported_embedding_model",
                "Model của index không được hỗ trợ.",
            )
            model_versions = [v for v, row in allowed.items() if row["embedding_model"] == model]
            with self.call(owner, "query_embed", model):
                vector = self.models.embed([question], model)[0]
            collection = self.collection(model)
            client = self.vector_store()
            if not client.collection_exists(collection):
                raise AppError(
                    503, "active_index_missing", "Thiếu collection của phiên bản hiện hành."
                )
            matches = client.query_points(
                collection,
                query=vector,
                query_filter=qm.Filter(
                    must=[
                        qm.FieldCondition(key="scope_id", match=qm.MatchAny(any=scopes)),
                        qm.FieldCondition(
                            key="document_version_id", match=qm.MatchAny(any=model_versions)
                        ),
                    ]
                ),
                limit=10,
                with_payload=True,
            ).points
            for match in matches:
                payload = match.payload
                with self.db.read() as s:
                    trusted = s.one(
                        "SELECT c.*,d.title FROM document_chunks c JOIN documents d ON d.id=c.document_id WHERE c.point_id=:p AND d.status='active' AND d.active_version_id=c.document_version_id AND EXISTS(SELECT 1 FROM document_access a WHERE a.document_id=d.id AND a.scope_id=c.scope_id)",
                        p=str(match.id),
                    )
                if (
                    not trusted
                    or trusted["document_version_id"] not in versions
                    or trusted["scope_id"] not in scopes
                ):
                    continue
                if (
                    hashlib.sha256(payload.get("text", "").encode()).hexdigest()
                    != trusted["content_sha256"]
                ):
                    continue
                key = (trusted["document_version_id"], trusted["chunk_id"])
                candidate = {**trusted, "text": payload["text"], "vector_score": float(match.score)}
                if (
                    key not in candidates
                    or candidates[key]["vector_score"] < candidate["vector_score"]
                ):
                    candidates[key] = candidate
        retrieved = sorted(candidates.values(), key=lambda p: p["vector_score"], reverse=True)[:10]
        if not retrieved:
            return []
        with self.call(owner, "rerank", self.settings.rag_reranker_model):
            scores = self.models.rerank(question, [p["text"] for p in retrieved])
        require(
            len(scores) == len(retrieved),
            503,
            "invalid_rerank_result",
            "Reranker trả sai số lượng.",
        )
        for point, score in zip(retrieved, scores, strict=True):
            point["rerank_score"] = float(score)
        ranked = sorted(retrieved, key=lambda p: p["rerank_score"], reverse=True)[:5]
        self.last_trace.update(query=question, retrieved=retrieved, ranked=ranked)
        return ranked

    def answer(self, context):
        with self.lock:
            self.last_trace = {}
            with self.db.read() as s:
                run = s.one("SELECT id FROM rag_runs WHERE event_key=:e", e=context.event_key)
            require(run is not None, 409, "missing_rag_run", "Chưa có lượt RAG được đăng ký.")
            owner = {"rag_run_id": run["id"]}
            ranked = self.retrieve(context, owner)
            # Scores only order sources. Claude assesses ALL returned Top 5 chunks.
            sources = ranked
            self.last_trace["evidence_decision"] = (
                "claude_content_assessment" if sources else "no_candidates"
            )
            log.info(
                "rag_evidence_review event_key=%s run_id=%s active_versions=%s chunks_sent=%s decision=%s",
                context.event_key,
                run["id"],
                len(context.active_document_version_ids),
                len(sources),
                self.last_trace["evidence_decision"],
            )
            if not sources:
                return RAGResult(
                    "insufficient_evidence",
                    "Không tìm được nguồn hợp lệ để đánh giá.",
                    reason="no_active_documents"
                    if not context.active_document_version_ids
                    else "no_authorized_candidates",
                )
            with self.call(owner, "generate", self.settings.claude_model) as stats:
                try:
                    generated, usage = self.gateway.generate(
                        context.question,
                        context.memory,
                        sources,
                        resolved_question=self.last_trace.get("query", context.question),
                    )
                    stats.update(usage)
                except Exception:
                    stats.update(getattr(self.gateway, "last_usage", {}))
                    raise
            log.info(
                "rag_content_assessment event_key=%s run_id=%s sufficient=%s claims=%s chunks=%s",
                context.event_key,
                run["id"],
                generated.sufficient,
                len(generated.claims),
                len(sources),
            )
            if not generated.sufficient or not generated.claims:
                return RAGResult(
                    "insufficient_evidence",
                    "Nguồn chưa đủ để trả lời câu hỏi.",
                    reason="model_evidence_insufficient",
                )
            citations, lines = {}, []
            for claim in generated.claims:
                refs = []
                for evidence in claim.evidence:
                    if evidence.source > len(sources):
                        return RAGResult(
                            "insufficient_evidence",
                            "Không xác minh được nguồn.",
                            reason="invalid_source_number",
                        )
                    source = sources[evidence.source - 1]
                    quote = normalized(evidence.quote)
                    if quote not in normalized(source["text"]):
                        self.last_trace["rejected_quote"] = {
                            "quote": quote,
                            "source": source["text"],
                        }
                        return RAGResult(
                            "insufficient_evidence",
                            "Không xác minh được trích dẫn.",
                            reason="quote_not_in_source",
                        )
                    pid = source["point_id"]
                    if pid not in citations:
                        citations[pid] = {
                            k: source.get(k)
                            for k in [
                                "point_id",
                                "document_id",
                                "document_version_id",
                                "chunk_id",
                                "page",
                                "section_path",
                            ]
                        }
                        citations[pid].update(evidence_excerpt=quote, title=source["title"])
                    refs.append(list(citations).index(pid) + 1)
                lines.append(claim.text + " " + "".join(f"[{r}]" for r in sorted(set(refs))))
            for number, cite in enumerate(citations.values(), 1):
                location = (
                    f"trang {cite['page']}" if cite.get("page") else cite.get("section_path", "")
                )
                lines.append(f"[{number}] {cite['title']} — {location}")
            return RAGResult(
                "answered",
                "\n".join(lines),
                list(citations.values()),
                True,
                reason="claude_content_and_verified_citations",
                retrieved_point_ids=[p["point_id"] for p in ranked],
            )

    def cleanup(self, document_id, version_id):
        with self.lock:
            client = self.vector_store()
            for collection in client.get_collections().collections:
                client.delete(
                    collection.name,
                    points_selector=qm.FilterSelector(
                        filter=qm.Filter(
                            must=[
                                qm.FieldCondition(
                                    key="document_id", match=qm.MatchValue(value=document_id)
                                ),
                                qm.FieldCondition(
                                    key="document_version_id", match=qm.MatchValue(value=version_id)
                                ),
                            ]
                        )
                    ),
                    wait=True,
                )

    def close(self):
        self.gateway.close()
        if self.client:
            self.client.close()
