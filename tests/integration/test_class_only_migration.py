import sqlite3
from pathlib import Path

from app.core.config import Settings
from app.db.session import Database


def test_v4_student_history_migrates_to_class_only_and_keeps_backup(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as c:
        for name in [
            "0001_initial.sql",
            "0002_authentication.sql",
            "0003_class_rosters.sql",
            "0004_query_rewriting.sql",
        ]:
            c.executescript((Path("app/db/migrations/versions") / name).read_text())
        c.execute(
            "INSERT INTO users(id,display_name,role,created_at,updated_at) VALUES ('old','Old student','student','n','n')"
        )
        c.execute(
            "INSERT INTO users(id,display_name,role,created_at,updated_at) VALUES ('teacher','Teacher','teacher','n','n')"
        )
        c.execute("INSERT INTO courses(id,name,created_at,updated_at) VALUES ('C','C','n','n')")
        c.execute(
            "INSERT INTO classes(id,course_id,name,created_at,updated_at) VALUES ('C1','C','Class','n','n')"
        )
        c.execute(
            "INSERT INTO enrollments(user_id,class_id,joined_at,updated_at) VALUES ('old','C1','n','n')"
        )
        c.execute(
            "INSERT INTO group_bindings(id,class_id,platform,external_group_id,display_name,created_at) VALUES ('G','C1','zalo_bot','123:chat','Group','n')"
        )
        c.execute(
            "INSERT INTO webhook_events(event_key,request_id,platform,external_event_id,raw_group_id,raw_sender_id,group_binding_id,class_id,user_id,payload_sha256,status,sent_at,received_at,next_attempt_at,accepted_at) VALUES ('E','R','zalo_bot','M','123:chat','123:sender','G','C1','old',?,'completed','n','n','n','n')",
            ("a" * 64,),
        )
        c.execute(
            "INSERT INTO support_tickets(id,event_key,class_id,group_binding_id,student_id,question_redacted,reason_code,created_at,updated_at) VALUES ('T','E','C1','G','old','Question','no_evidence','n','n')"
        )
        c.execute(
            "INSERT INTO daily_usage(user_id,local_date,accepted_count,updated_at) VALUES ('old','2026-11-15',1,'n')"
        )
        c.execute(
            "INSERT INTO quota_reservations(event_key,user_id,local_date,status,reserved_at) VALUES ('E','old','2026-11-15','charged','n')"
        )
        c.execute("PRAGMA user_version=4")
    db = Database(
        Settings(_env_file=None, database_url="sqlite:///" + str(path), zalo_bot_enabled=False)
    )
    try:
        db.migrate()
        db.migrate()
        with db.read() as s:
            assert s.one("PRAGMA user_version")["user_version"] == 5
            assert s.all("PRAGMA foreign_key_check") == []
            assert s.one("PRAGMA integrity_check")["integrity_check"] == "ok"
            assert not s.one("SELECT id FROM users WHERE id='old'")
            assert s.one("SELECT id FROM users WHERE id='teacher'")
            assert not s.one("SELECT name FROM sqlite_master WHERE name='enrollments'")
            assert (
                s.one("SELECT user_id FROM webhook_events WHERE event_key='E'")["user_id"] is None
            )
            assert (
                s.one("SELECT requester_user_id FROM support_tickets WHERE id='T'")[
                    "requester_user_id"
                ]
                is None
            )
            assert s.one("SELECT accepted_count FROM daily_usage")["accepted_count"] == 1
            assert len(s.one("SELECT usage_key FROM daily_usage")["usage_key"]) == 64
        with sqlite3.connect(path.with_suffix(".pre-v5.db")) as backup:
            assert backup.execute("PRAGMA user_version").fetchone()[0] == 4
            assert (
                backup.execute("SELECT count(*) FROM users WHERE role='student'").fetchone()[0] == 1
            )
    finally:
        db.engine.dispose()
