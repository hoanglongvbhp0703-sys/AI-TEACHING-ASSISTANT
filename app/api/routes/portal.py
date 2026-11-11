import hashlib
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import Field

from app.api.deps import current_user, ok
from app.core.errors import require
from app.core.security import clean
from app.repositories.store import encode, uid
from app.schemas.common import DTO, Envelope
from app.services.access_service import check_class

router = APIRouter(tags=["Local portal & student support"])


class SupportRequest(DTO):
    class_id: str
    question: str = Field(min_length=1, max_length=8000)
    client_request_id: UUID


@router.get("/support-requests", response_model=Envelope[Any])
def own_requests(
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user=Depends(current_user),
):
    require(user["role"] == "student")
    with request.app.state.db.read() as s:
        rows = s.all(
            "SELECT t.*,c.name AS class_name,r.answer_redacted FROM support_tickets t JOIN classes c ON c.id=t.class_id LEFT JOIN ticket_replies r ON r.ticket_id=t.id AND t.status IN ('answered','closed') WHERE t.student_id=:u AND (:sc IS NULL OR t.class_id=:sc) ORDER BY t.created_at DESC,t.id LIMIT :l OFFSET :o",
            u=user["id"],
            sc=user.get("session_class_id"),
            l=limit,
            o=offset,
        )
        total = s.one(
            "SELECT count(*) AS n FROM support_tickets WHERE student_id=:u AND (:sc IS NULL OR class_id=:sc)",
            u=user["id"],
            sc=user.get("session_class_id"),
        )["n"]
        return ok(request, {"items": rows, "total": total, "limit": limit, "offset": offset})


@router.get("/support-requests/{ticket_id}", response_model=Envelope[Any])
def own_request(ticket_id: str, request: Request, user=Depends(current_user)):
    require(user["role"] == "student")
    with request.app.state.db.read() as s:
        ticket = s.one(
            "SELECT t.*,c.name AS class_name,r.answer_redacted FROM support_tickets t JOIN classes c ON c.id=t.class_id LEFT JOIN ticket_replies r ON r.ticket_id=t.id AND t.status IN ('answered','closed') WHERE t.id=:t AND t.student_id=:u AND (:sc IS NULL OR t.class_id=:sc)",
            t=ticket_id,
            u=user["id"],
            sc=user.get("session_class_id"),
        )
        require(ticket is not None, 404, "not_found", "Không tìm thấy yêu cầu của bạn.")
        return ok(request, ticket)


@router.post("/support-requests", status_code=201, response_model=Envelope[Any])
def create_request(
    body: SupportRequest, request: Request, response: Response, user=Depends(current_user)
):
    require(user["role"] == "student")
    settings = request.app.state.settings
    question = clean(settings, body.question)
    external_id = user["id"] + ":" + str(body.client_request_id)
    digest = hashlib.sha256(
        encode({"class_id": body.class_id, "question": question}).encode()
    ).hexdigest()
    now = request.app.state.clock.stamp()
    with request.app.state.db.write() as s:
        check_class(s, user, body.class_id)
        allowed = s.one(
            "SELECT c.id FROM classes c JOIN enrollments e ON e.class_id=c.id WHERE c.id=:c AND c.status='active' AND e.user_id=:u AND e.status='active'",
            c=body.class_id,
            u=user["id"],
        )
        require(allowed is not None)
        old = s.one(
            "SELECT event_key,payload_sha256 FROM webhook_events WHERE platform='portal' AND external_event_id=:e",
            e=external_id,
        )
        if old:
            require(
                old["payload_sha256"] == digest,
                409,
                "request_conflict",
                "Lần gửi này đã có nội dung khác.",
            )
            response.status_code = 200
            return ok(
                request,
                s.one("SELECT * FROM support_tickets WHERE event_key=:e", e=old["event_key"]),
            )
        group = s.one(
            "SELECT * FROM group_bindings WHERE class_id=:c AND is_active=1 ORDER BY id LIMIT 1",
            c=body.class_id,
        )
        require(
            group is not None,
            422,
            "class_group_missing",
            "Lớp chưa có nhóm nhận phản hồi. Vui lòng liên hệ quản trị viên.",
        )
        event_key, ticket_id = uid(), uid()
        s.insert(
            "webhook_events",
            event_key=event_key,
            request_id=request.state.request_id,
            platform="portal",
            external_event_id=external_id,
            raw_group_id=group["external_group_id"],
            raw_sender_id=user["id"],
            group_binding_id=group["id"],
            class_id=body.class_id,
            user_id=user["id"],
            question_redacted=question,
            payload_sha256=digest,
            status="completed",
            outcome_code="manual_support",
            sent_at=now,
            received_at=now,
            next_attempt_at=now,
            completed_at=now,
        )
        s.insert(
            "support_tickets",
            id=ticket_id,
            event_key=event_key,
            class_id=body.class_id,
            group_binding_id=group["id"],
            student_id=user["id"],
            question_redacted=question,
            reason_code="manual_support",
            evidence_summary_redacted="Học viên gửi yêu cầu trực tiếp, không qua RAG.",
            created_at=now,
            updated_at=now,
        )
        s.audit(
            user["id"], "support_request.create", "ticket", ticket_id, now, request.state.request_id
        )
        return ok(request, s.one("SELECT * FROM support_tickets WHERE id=:t", t=ticket_id))
