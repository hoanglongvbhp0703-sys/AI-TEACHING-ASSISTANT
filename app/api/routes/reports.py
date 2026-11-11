import math
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import ok, staff
from app.core.clock import stamp
from app.core.errors import AppError, require
from app.schemas.common import Envelope
from app.services.access_service import check_class, check_document, class_ids

router = APIRouter(tags=["Reports"])


@router.get("/reports/summary", response_model=Envelope[Any])
def summary(
    request: Request,
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = None,
    class_id: str | None = None,
    user=Depends(staff),
):
    now = request.app.state.clock.now()
    start, end = from_ or now - timedelta(days=30), to or now
    require(
        start.tzinfo is not None and end.tzinfo is not None,
        422,
        "timezone_required",
        "from/to phải có múi giờ.",
    )
    require(
        start < end and (end - start) <= timedelta(days=366),
        422,
        "invalid_date_range",
        "Khoảng thời gian phải tăng dần, tối đa 366 ngày.",
    )
    begin, finish = stamp(start), stamp(end)
    with request.app.state.db.read() as s:
        if class_id:
            check_class(s, user, class_id)
        allowed = class_ids(s, user)
        events = [
            e
            for e in s.all(
                "SELECT * FROM webhook_events WHERE received_at>=:a AND received_at<:b",
                a=begin,
                b=finish,
            )
            if (user["role"] == "admin" or e["class_id"] in allowed)
            and (not class_id or e["class_id"] == class_id)
        ]
        ids = {e["event_key"] for e in events}
        runs = [r for r in s.all("SELECT * FROM rag_runs") if r["event_key"] in ids]
        run_ids = {r["id"] for r in runs}
        visible_docs = set()
        for doc in s.all("SELECT id FROM documents"):
            try:
                check_document(s, user, doc["id"])
            except AppError as exc:
                if exc.status == 403:
                    continue
                raise
            if class_id:
                course = s.one("SELECT course_id FROM classes WHERE id=:c", c=class_id)["course_id"]
                scopes = {
                    r["scope_id"]
                    for r in s.all(
                        "SELECT scope_id FROM document_access WHERE document_id=:d", d=doc["id"]
                    )
                }
                if not scopes.intersection({"class:" + class_id, "course:" + course}):
                    continue
            visible_docs.add(doc["id"])
        jobs = [
            j
            for j in s.all(
                "SELECT j.*,v.document_id FROM ingestion_jobs j JOIN document_versions v ON v.id=j.document_version_id WHERE j.created_at>=:a AND j.created_at<:b",
                a=begin,
                b=finish,
            )
            if j["document_id"] in visible_docs
        ]
        job_ids = {j["id"] for j in jobs}
        calls = [
            c
            for c in s.all("SELECT * FROM rag_run_attempts")
            if c["rag_run_id"] in run_ids or c["ingestion_job_id"] in job_ids
        ]
        latency = sorted(r["latency_ms"] for r in runs if r["latency_ms"] is not None)
        reservations = {
            r["event_key"]: r for r in s.all("SELECT event_key,status FROM quota_reservations")
        }

        def costs(rows):
            return {
                "known_cost_usd_micros": sum(c["estimated_cost_usd_micros"] or 0 for c in rows),
                "unknown_cost_calls": sum(c["estimated_cost_usd_micros"] is None for c in rows),
                "input_tokens_known": sum(c["input_tokens"] or 0 for c in rows),
                "output_tokens_known": sum(c["output_tokens"] or 0 for c in rows),
                "calls": len(rows),
            }

        return ok(
            request,
            {
                "from": begin,
                "to": finish,
                "class_id": class_id,
                "unique_events": len(events),
                "accepted_questions": sum(
                    e["event_key"] in reservations
                    and reservations[e["event_key"]]["status"] != "released"
                    for e in events
                ),
                "event_outcomes": dict(Counter(e["outcome_code"] or e["status"] for e in events)),
                "rag_results": dict(Counter(r["status"] for r in runs)),
                "tickets": sum(
                    t["event_key"] in ids for t in s.all("SELECT event_key FROM support_tickets")
                ),
                "latency": {
                    "samples": len(latency),
                    "p50_ms": latency[math.ceil(len(latency) * 0.5) - 1] if latency else None,
                    "p95_ms": latency[math.ceil(len(latency) * 0.95) - 1] if latency else None,
                },
                "question_usage": costs([c for c in calls if c["rag_run_id"] is not None]),
                "rewrite_usage": costs([c for c in calls if c["stage"] == "query_rewrite"]),
                "answer_generation_usage": costs([c for c in calls if c["stage"] == "generate"]),
                "ingestion_usage": costs([c for c in calls if c["ingestion_job_id"] is not None]),
                "ingestion_jobs": dict(Counter(j["status"] for j in jobs)),
            },
        )
