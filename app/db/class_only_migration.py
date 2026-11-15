"""v5: staff accounts and class-scoped chats, with a verified pre-migration backup."""

import hashlib
import re
import sqlite3
from pathlib import Path


def migrate_class_only(connection):
    source = connection.driver_connection
    filename = source.execute("PRAGMA database_list").fetchone()[2]
    backup_path = Path(filename).with_suffix(".pre-v5.db")
    if not backup_path.exists():
        with sqlite3.connect(backup_path) as backup:
            source.backup(backup)
        backup_path.chmod(0o600)
    students = {r[0] for r in source.execute("SELECT id FROM users WHERE role='student'")}
    objects = source.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
    ).fetchall()
    target = sqlite3.connect(":memory:")
    try:
        tables = [r for r in objects if r[0] == "table" and r[1] != "enrollments"]
        for _, name, _, sql in tables:
            if name == "users":
                sql = sql.replace("'student',", "")
            elif name == "webhook_events":
                sql = sql.replace(
                    "(user_id IS NOT NULL AND class_id IS NOT NULL)", "(class_id IS NOT NULL)"
                )
            elif name in {"daily_usage", "quota_reservations"}:
                sql = sql.replace("user_id", "usage_key").replace(" REFERENCES users(id)", "")
            elif name == "support_tickets":
                sql = sql.replace("student_id TEXT NOT NULL", "requester_user_id TEXT")
            target.execute(sql)
        for _, name, _, _ in tables:
            cursor = source.execute(f'SELECT * FROM "{name}"')
            columns = [d[0] for d in cursor.description]
            output_columns = [
                "usage_key"
                if name in {"daily_usage", "quota_reservations"} and c == "user_id"
                else "requester_user_id"
                if name == "support_tickets" and c == "student_id"
                else c
                for c in columns
            ]
            nullable_user_refs = {
                r[3]
                for r in source.execute(f'PRAGMA foreign_key_list("{name}")')
                if r[2] == "users"
            }
            for values in cursor:
                row = dict(zip(columns, values))
                if name == "users" and row["id"] in students:
                    continue
                if (
                    name in {"user_credentials", "auth_sessions", "external_identities"}
                    and row["user_id"] in students
                ):
                    continue
                for col in (
                    nullable_user_refs if name not in {"daily_usage", "quota_reservations"} else ()
                ):
                    if row[col] in students:
                        row[col] = None
                target.execute(
                    f'INSERT INTO "{name}" ({",".join(output_columns)}) VALUES ({",".join("?" for _ in columns)})',
                    [row[c] for c in columns],
                )
        for kind, name, table, sql in objects:
            if kind not in {"index", "trigger"} or table == "enrollments":
                continue
            if table == "quota_reservations":
                sql = re.sub(r"\buser_id\b", "usage_key", sql)
            target.execute(sql)
        # Keep today's limits while changing the counter identity from a student to a sender.
        usage = {}
        for event_key, platform, sender, date, status, ts in target.execute(
            "SELECT q.event_key,e.platform,e.raw_sender_id,q.local_date,q.status,q.reserved_at FROM quota_reservations q JOIN webhook_events e ON e.event_key=q.event_key"
        ).fetchall():
            key = hashlib.sha256((platform + ":" + sender).encode()).hexdigest()
            target.execute(
                "UPDATE quota_reservations SET usage_key=? WHERE event_key=?", (key, event_key)
            )
            count, _ = usage.get((key, date), (0, ts))
            usage[key, date] = (count + int(status != "released"), ts)
        target.execute("DELETE FROM daily_usage")
        target.executemany(
            "INSERT INTO daily_usage(usage_key,local_date,accepted_count,updated_at) VALUES (?,?,?,?)",
            [(key, date, min(count, 30), ts) for (key, date), (count, ts) in usage.items()],
        )
        violations = target.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(
                "v5 migration failed foreign-key verification; original DB unchanged"
            )
        target.execute("PRAGMA user_version=5")
        target.commit()
        # SQLite backup replaces the destination as a transaction, including schema and indexes.
        target.backup(source)
        source.execute("PRAGMA foreign_keys=ON")
    finally:
        target.close()
