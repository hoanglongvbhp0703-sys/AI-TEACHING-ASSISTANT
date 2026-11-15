import hashlib
from datetime import timedelta

from app.core.clock import day_key, reset_at, stamp


def usage_key(event):
    return hashlib.sha256((event["platform"] + ":" + event["raw_sender_id"]).encode()).hexdigest()


def reserve(s, event, clock, settings):
    key = usage_key(event)
    now = clock.now()
    if settings.rate_limit_enabled:
        recent = s.one(
            "SELECT count(*) AS n FROM webhook_events WHERE platform=:p AND raw_sender_id=:sender AND accepted_at>:cut AND accepted_at IS NOT NULL AND event_key!=:e",
            p=event["platform"],
            sender=event["raw_sender_id"],
            cut=stamp(now - timedelta(minutes=1)),
            e=event["event_key"],
        )["n"]
        if recent >= settings.rate_limit_per_minute:
            return "rate_limited"
    day = day_key(now)
    ts = stamp(now)
    s.execute(
        "INSERT OR IGNORE INTO daily_usage (usage_key,local_date,accepted_count,updated_at) VALUES (:u,:d,0,:n)",
        u=key,
        d=day,
        n=ts,
    )
    changed = s.execute(
        "UPDATE daily_usage SET accepted_count=accepted_count+1,updated_at=:n WHERE usage_key=:u AND local_date=:d AND accepted_count<30",
        u=key,
        d=day,
        n=ts,
    ).rowcount
    if not changed:
        return "quota_exceeded"
    s.insert(
        "quota_reservations",
        event_key=event["event_key"],
        usage_key=key,
        local_date=day,
        status="reserved",
        reserved_at=ts,
    )
    s.update("webhook_events", "event_key", event["event_key"], accepted_at=ts)
    return None


def release(s, event_key, now, reason):
    reservation = s.one(
        "SELECT * FROM quota_reservations WHERE event_key=:e AND status='reserved'", e=event_key
    )
    if reservation:
        s.update(
            "quota_reservations",
            "event_key",
            event_key,
            status="released",
            released_at=now,
            release_reason=reason,
        )
        s.execute(
            "UPDATE daily_usage SET accepted_count=accepted_count-1,updated_at=:n WHERE usage_key=:u AND local_date=:d",
            n=now,
            u=reservation["usage_key"],
            d=reservation["local_date"],
        )


def quota(s, usage_key, clock):
    day = day_key(clock.now())
    row = s.one(
        "SELECT accepted_count FROM daily_usage WHERE usage_key=:u AND local_date=:d",
        u=usage_key,
        d=day,
    )
    used = row["accepted_count"] if row else 0
    return {
        "usage_key": usage_key,
        "local_date": day,
        "limit": 30,
        "used": used,
        "remaining": 30 - used,
        "reset_at": reset_at(clock.now()),
    }
