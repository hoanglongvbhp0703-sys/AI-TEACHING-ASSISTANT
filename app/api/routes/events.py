import json
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response

from app.api.deps import current_user, local_adapter, ok
from app.core.errors import require
from app.schemas.common import Envelope
from app.schemas.event import MockEvent
from app.services.access_service import check_class, class_ids
from app.services.progress_service import event_progress
from app.services.quota_service import quota

router = APIRouter(tags=["Mock webhook & chat"])


@router.post("/mock/events", status_code=202, response_model=Envelope[Any])
def mock(body: MockEvent, request: Request, response: Response, user=Depends(local_adapter)):
    result = request.app.state.events.receive(body, request.state.request_id)
    if result["status"] != "queued":
        response.status_code = 200
    return ok(request, result)


@router.get("/mock/groups", response_model=Envelope[Any])
def groups(request: Request, user=Depends(current_user)):
    require(request.app.state.settings.mock_ui_enabled, 404, "not_found", "Mock API đang tắt.")
    with request.app.state.db.read() as s:
        allowed = class_ids(s, user)
        return ok(
            request,
            [
                r
                for r in s.all("SELECT * FROM group_bindings WHERE is_active=1 ORDER BY id")
                if user["role"] == "service" or r["class_id"] in allowed
            ],
        )


@router.get("/mock/groups/{group_id}/messages", response_model=Envelope[Any])
def messages(
    group_id: str,
    request: Request,
    after: str | None = Query(None, max_length=300),
    limit: int = Query(50, ge=1, le=100),
    user=Depends(current_user),
):
    require(request.app.state.settings.mock_ui_enabled, 404, "not_found", "Mock API đang tắt.")
    with request.app.state.db.read() as s:
        group = s.one(
            "SELECT * FROM group_bindings WHERE platform='mock_zalo' AND external_group_id=:g AND is_active=1",
            g=group_id,
        )
        require(group is not None, 404, "not_found", "Không tìm thấy nhóm.")
        if user["role"] != "service":
            check_class(s, user, group["class_id"])
        params = {"g": group["id"], "l": limit}
        condition = ""
        if after:
            cursor = s.one(
                "SELECT rowid AS position FROM outbound_messages WHERE id=:id AND group_binding_id=:g AND status='sent'",
                id=after,
                g=group["id"],
            )
            require(cursor is not None, 422, "invalid_cursor", "Cursor không hợp lệ.")
            condition = " AND rowid>:position"
            params.update(position=cursor["position"])
        out = s.all(
            "SELECT id,event_key,message_kind,reply_to_external_event_id,text_redacted,citations_json,ticket_id,status,created_at,sent_at FROM outbound_messages WHERE group_binding_id=:g AND status='sent'"
            + condition
            + " ORDER BY rowid LIMIT :l",
            **params,
        )
        for row in out:
            row["citations"] = json.loads(row.pop("citations_json"))
        return ok(request, {"items": out, "next_cursor": out[-1]["id"] if out else after})


@router.get("/events/{event_key}", response_model=Envelope[Any])
def event_status(event_key: str, request: Request, user=Depends(current_user)):
    with request.app.state.db.read() as s:
        event = s.one(
            "SELECT event_key,user_id,class_id,status,outcome_code,error_code,received_at,accepted_at,completed_at FROM webhook_events WHERE event_key=:e",
            e=event_key,
        )
        require(event is not None, 404, "not_found", "Không tìm thấy sự kiện.")
        if user["role"] not in {"admin", "service"}:
            if user["role"] == "student":
                require(event["user_id"] == user["id"])
                check_class(s, user, event["class_id"])
            else:
                require(event["class_id"] is not None)
                check_class(s, user, event["class_id"])
        details = {**event, "progress": event_progress(s, event)}
        if user["role"] in {"admin", "teacher"}:
            run = s.one("SELECT query_rewrite_json FROM rag_runs WHERE event_key=:e", e=event_key)
            details["query_rewrite"] = json.loads(run["query_rewrite_json"]) if run else None
        return ok(request, details)


@router.get("/students/{student_id}/quota", response_model=Envelope[Any])
def student_quota(student_id: str, request: Request, user=Depends(current_user)):
    require(user["role"] == "admin" or (user["role"] == "student" and user["id"] == student_id))
    with request.app.state.db.read() as s:
        require(
            s.one("SELECT id FROM users WHERE id=:u AND role='student'", u=student_id),
            404,
            "not_found",
            "Không tìm thấy học viên.",
        )
        return ok(request, quota(s, student_id, request.app.state.clock))


@router.get("/mock/catalog", response_model=Envelope[Any])
def catalog(request: Request, user=Depends(local_adapter)):
    from app.services.roster_service import mock_catalog

    with request.app.state.db.read() as s:
        return ok(request, mock_catalog(s))
