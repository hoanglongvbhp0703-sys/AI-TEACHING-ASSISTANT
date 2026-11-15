import json
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.api.deps import current_user, ok
from app.core.errors import require
from app.schemas.common import Envelope
from app.services.access_service import check_class
from app.services.progress_service import event_progress

router = APIRouter(tags=["Event processing"])


@router.get("/events/{event_key}", response_model=Envelope[Any])
def event_status(event_key: str, request: Request, user=Depends(current_user)):
    with request.app.state.db.read() as s:
        event = s.one(
            "SELECT event_key,user_id,class_id,status,outcome_code,error_code,received_at,accepted_at,completed_at FROM webhook_events WHERE event_key=:e",
            e=event_key,
        )
        require(event is not None, 404, "not_found", "Không tìm thấy sự kiện.")
        if user["role"] not in {"admin", "service"}:
            require(event["class_id"] is not None)
            check_class(s, user, event["class_id"])
        details = {**event, "progress": event_progress(s, event)}
        if user["role"] in {"admin", "teacher"}:
            run = s.one("SELECT query_rewrite_json FROM rag_runs WHERE event_key=:e", e=event_key)
            details["query_rewrite"] = json.loads(run["query_rewrite_json"]) if run else None
        return ok(request, details)
