import json
from uuid import uuid4

from sqlalchemy import text


def uid():
    return str(uuid4())


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class Store:
    """A unit-of-work view. Transaction boundaries belong to Database/services."""

    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, **params):
        return self.connection.execute(text(sql), params)

    def one(self, sql, **params):
        row = self.execute(sql, **params).mappings().first()
        return dict(row) if row else None

    def all(self, sql, **params):
        return [dict(row) for row in self.execute(sql, **params).mappings()]

    def insert(self, table, **values):
        # Identifiers are internal constants; all request values are bound parameters.
        columns = ",".join(values)
        bindings = ",".join(":" + key for key in values)
        self.execute(f"INSERT INTO {table} ({columns}) VALUES ({bindings})", **values)
        return values

    def update(self, table, key, value, **changes):
        setters = ",".join(f"{name}=:{name}" for name in changes)
        self.execute(f"UPDATE {table} SET {setters} WHERE {key}=:_key", _key=value, **changes)

    def audit(self, actor, action, entity, entity_id, now, request_id, changes=None):
        self.insert(
            "audit_logs",
            id=uid(),
            request_id=request_id,
            actor_user_id=actor,
            action=action,
            entity_type=entity,
            entity_id=entity_id,
            change_redacted_json=encode(changes or {}),
            created_at=now,
        )

    def security(self, reason, request_id, now, event_key=None, actor=None):
        self.insert(
            "security_events",
            id=uid(),
            event_key=event_key,
            request_id=request_id,
            actor_user_id=actor,
            reason_code=reason,
            severity="warning",
            created_at=now,
        )
