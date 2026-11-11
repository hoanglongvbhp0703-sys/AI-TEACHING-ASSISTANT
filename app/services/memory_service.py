from datetime import timedelta

from app.core.clock import stamp
from app.repositories.store import uid
from app.services.access_service import allowed_sources


def session_for(s, event, clock, settings):
    existing = s.one(
        "SELECT session_id FROM messages WHERE event_key=:e AND message_kind='question'",
        e=event["event_key"],
    )
    if existing:
        return existing["session_id"]
    now = clock.stamp()
    row = s.one(
        "SELECT * FROM conversation_sessions WHERE class_id=:c AND group_binding_id=:g AND status='open'",
        c=event["class_id"],
        g=event["group_binding_id"],
    )
    if row and now > row["expires_at"]:
        s.update("conversation_sessions", "id", row["id"], status="expired")
        row = None
    expires = stamp(clock.now() + timedelta(minutes=settings.memory_ttl_minutes))
    if row:
        s.update("conversation_sessions", "id", row["id"], last_hoi_at=now, expires_at=expires)
        return row["id"]
    key = uid()
    s.insert(
        "conversation_sessions",
        id=key,
        class_id=event["class_id"],
        group_binding_id=event["group_binding_id"],
        started_at=now,
        last_hoi_at=now,
        expires_at=expires,
    )
    return key


def add_message(s, event, session_id, kind, text, now):
    eligible = kind in {"question", "answer", "handoff"}
    s.execute(
        "INSERT OR IGNORE INTO messages (id,session_id,event_key,class_id,group_binding_id,sender_user_id,role,message_kind,text_redacted,memory_eligible,created_at) VALUES (:id,:session,:event,:class,:group,:sender,:role,:kind,:text,:eligible,:now)",
        id=uid(),
        session=session_id,
        event=event["event_key"],
        **{"class": event["class_id"], "group": event["group_binding_id"]},
        sender=event["user_id"] if kind == "question" else None,
        role="user" if kind == "question" else "assistant",
        kind=kind,
        text=text,
        eligible=int(eligible),
        now=now,
    )


def memory(s, session_id, event, limit):
    scopes, versions = allowed_sources(s, event["class_id"])
    rows = s.all(
        "SELECT q.event_key,q.text_redacted AS question,a.text_redacted AS answer,q.created_at FROM messages q JOIN messages a ON a.event_key=q.event_key AND a.role='assistant' AND a.memory_eligible=1 AND a.status='committed' WHERE q.session_id=:sid AND q.message_kind='question' AND q.memory_eligible=1 AND q.status='committed' AND q.event_key!=:e ORDER BY q.created_at DESC,q.id DESC",
        sid=session_id,
        e=event["event_key"],
    )
    result = []
    for row in rows:
        citations = s.all(
            "SELECT c.document_version_id,c.scope_id FROM rag_citations r JOIN rag_runs run ON run.id=r.rag_run_id JOIN document_chunks c ON c.point_id=r.point_id WHERE run.event_key=:e",
            e=row["event_key"],
        )
        if any(
            c["document_version_id"] not in versions or c["scope_id"] not in scopes
            for c in citations
        ):
            continue
        result.append(row)
        if len(result) >= limit:
            break
    return list(reversed(result))
