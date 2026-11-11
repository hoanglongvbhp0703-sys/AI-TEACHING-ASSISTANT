from app.core.security import redact
from app.repositories.store import encode, uid
from app.services.access_service import allowed_sources


def citation_valid(s, event, citation):
    point = s.one(
        "SELECT c.*,d.active_version_id,d.status AS document_status,d.title FROM document_chunks c JOIN documents d ON d.id=c.document_id WHERE c.point_id=:p",
        p=citation.get("point_id", ""),
    )
    scopes, versions = allowed_sources(s, event["class_id"])
    return bool(
        point
        and point["document_status"] == "active"
        and point["document_version_id"] == point["active_version_id"]
        and point["document_version_id"] in versions
        and point["scope_id"] in scopes
        and all(
            citation.get(k) == point[k]
            for k in ["document_id", "document_version_id", "chunk_id", "page", "section_path"]
        )
        and isinstance(citation.get("evidence_excerpt"), str)
        and citation["evidence_excerpt"].strip()
    )


def queue(s, event, kind, text, now, citations=None, ticket_id=None, reply_id=None):
    old = s.one(
        "SELECT * FROM outbound_messages WHERE event_key=:e AND message_kind=:k",
        e=event["event_key"],
        k=kind,
    )
    if old:
        return old
    key = uid()
    s.insert(
        "outbound_messages",
        id=key,
        event_key=event["event_key"],
        class_id=event["class_id"],
        group_binding_id=event["group_binding_id"],
        message_kind=kind,
        reply_to_external_event_id=event["external_event_id"],
        text_redacted=redact(text),
        citations_json=encode(citations or []),
        ticket_id=ticket_id,
        ticket_reply_id=reply_id,
        next_attempt_at=now,
        created_at=now,
    )
    return s.one("SELECT * FROM outbound_messages WHERE id=:id", id=key)


def event_access(s, event):
    return s.one(
        "SELECT u.id FROM users u JOIN enrollments e ON e.user_id=u.id JOIN classes c ON c.id=e.class_id JOIN group_bindings g ON g.class_id=c.id WHERE u.id=:u AND u.is_active=1 AND u.role='student' AND e.status='active' AND c.id=:c AND c.status='active' AND c.bot_enabled=1 AND g.id=:g AND g.is_active=1 AND (:p='portal' OR (g.platform=:p AND g.external_group_id=:raw_group AND EXISTS(SELECT 1 FROM external_identities i WHERE i.user_id=u.id AND i.platform=:p AND i.external_sender_id=:sender AND i.is_active=1 AND i.is_bot=0)))",
        u=event["user_id"],
        c=event["class_id"],
        g=event["group_binding_id"],
        p=event["platform"],
        raw_group=event["raw_group_id"],
        sender=event["raw_sender_id"],
    )
