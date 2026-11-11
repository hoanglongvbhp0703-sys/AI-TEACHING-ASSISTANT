from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import ok, staff
from app.schemas.common import Envelope
from app.schemas.handoff import AnswerTicket, AssignTicket, CloseTicket, FAQDraft
from app.services.access_service import check_class, class_ids

router = APIRouter(tags=["Tickets & FAQ"])


@router.get("/tickets", response_model=Envelope[Any])
def tickets(
    request: Request,
    class_id: str | None = None,
    status: Literal["open", "assigned", "answered", "closed"] | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user=Depends(staff),
):
    with request.app.state.db.read() as s:
        if class_id:
            check_class(s, user, class_id)
        allowed = class_ids(s, user)
        result = [
            r
            for r in s.all("SELECT * FROM support_tickets ORDER BY created_at DESC,id")
            if r["class_id"] in allowed
            and (not class_id or r["class_id"] == class_id)
            and (not status or r["status"] == status)
        ]
        return ok(
            request,
            {
                "items": result[offset : offset + limit],
                "total": len(result),
                "limit": limit,
                "offset": offset,
            },
        )


@router.get("/tickets/{ticket_id}", response_model=Envelope[Any])
def ticket(ticket_id: str, request: Request, user=Depends(staff)):
    with request.app.state.db.read() as s:
        value = request.app.state.tickets.get(s, user, ticket_id)
        return ok(
            request,
            {
                **value,
                "reply": s.one("SELECT * FROM ticket_replies WHERE ticket_id=:t", t=ticket_id),
                "faq": s.one(
                    "SELECT id,status,scope_id,topic,document_id FROM faq_entries WHERE source_ticket_id=:t",
                    t=ticket_id,
                ),
            },
        )


@router.post("/tickets/{ticket_id}/assign", response_model=Envelope[Any])
def assign(ticket_id: str, body: AssignTicket, request: Request, user=Depends(staff)):
    return ok(
        request, request.app.state.tickets.assign(user, ticket_id, body, request.state.request_id)
    )


@router.post("/tickets/{ticket_id}/answer", status_code=202, response_model=Envelope[Any])
def answer(ticket_id: str, body: AnswerTicket, request: Request, user=Depends(staff)):
    return ok(
        request, request.app.state.tickets.answer(user, ticket_id, body, request.state.request_id)
    )


@router.post("/tickets/{ticket_id}/close", response_model=Envelope[Any])
def close(ticket_id: str, body: CloseTicket, request: Request, user=Depends(staff)):
    return ok(
        request, request.app.state.tickets.close(user, ticket_id, body, request.state.request_id)
    )


@router.post("/tickets/{ticket_id}/faq-draft", status_code=201, response_model=Envelope[Any])
def draft(ticket_id: str, body: FAQDraft, request: Request, user=Depends(staff)):
    return ok(
        request, request.app.state.tickets.draft(user, ticket_id, body, request.state.request_id)
    )


@router.get("/faqs/{faq_id}", response_model=Envelope[Any])
def faq(faq_id: str, request: Request, user=Depends(staff)):
    with request.app.state.db.read() as s:
        faq = request.app.state.tickets.faq(s, user, faq_id)
        doc = (
            s.one(
                "SELECT status,active_version_id FROM documents WHERE id=:d", d=faq["document_id"]
            )
            if faq["document_id"]
            else None
        )
        return ok(request, {**faq, "document_state": doc})


@router.post("/faqs/{faq_id}/approve", status_code=202, response_model=Envelope[Any])
def approve(faq_id: str, request: Request, user=Depends(staff)):
    return ok(request, request.app.state.tickets.approve(user, faq_id, request.state.request_id))
