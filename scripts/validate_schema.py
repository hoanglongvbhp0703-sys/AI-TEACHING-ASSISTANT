#!/usr/bin/env python3
"""Validate proposed SQLite DDL using disposable databases; no app/API claims."""

import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DDL = (ROOT / "docs/database/schema.sqlite.sql").read_text(encoding="utf-8")
NOW = "2026-11-10T00:00:00.000Z"
DAY = "2026-11-10"


def connect(path=":memory:"):
    db = sqlite3.connect(path, isolation_level=None, timeout=5)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=5000")
    return db


def insert(db, table, **values):
    # Table/column identifiers come only from constants in this validation script.
    columns = ",".join(values)
    marks = ",".join("?" for _ in values)
    db.execute(f"INSERT INTO {table} ({columns}) VALUES ({marks})", tuple(values.values()))


def seed(db):
    for uid, role in [("s", "student"), ("t", "teacher"), ("a", "admin")]:
        insert(db, "users", id=uid, display_name=uid, role=role, created_at=NOW, updated_at=NOW)
    for course, cid in [("GS_KPI", "GS-KPI-01"), ("AI_AUTO", "AUTO-N8N-01")]:
        insert(db, "courses", id=course, name=course, created_at=NOW, updated_at=NOW)
        insert(db, "classes", id=cid, course_id=course, name=cid, created_at=NOW, updated_at=NOW)
        insert(db, "enrollments", user_id="s", class_id=cid, joined_at=NOW, updated_at=NOW)
        insert(db, "teacher_assignments", teacher_id="t", class_id=cid, assigned_at=NOW)
        insert(
            db,
            "group_bindings",
            id="g-" + cid,
            class_id=cid,
            platform="mock_zalo",
            external_group_id="ext-" + cid,
            display_name=cid,
            created_at=NOW,
        )
        insert(db, "access_scopes", id="class:" + cid, scope_type="class", class_id=cid)


def event(db, eid="e1", cid="GS-KPI-01", external=None):
    insert(
        db,
        "webhook_events",
        event_key=eid,
        request_id="req-" + eid,
        platform="mock_zalo",
        external_event_id=external or eid,
        raw_group_id="ext-" + cid,
        raw_sender_id="external-s",
        group_binding_id="g-" + cid,
        class_id=cid,
        user_id="s",
        payload_sha256="0" * 64,
        next_attempt_at=NOW,
        sent_at=NOW,
        received_at=NOW,
    )


def document(db, did="d1"):
    insert(
        db,
        "documents",
        id=did,
        title=did,
        topic="test",
        source_kind="file",
        created_by="t",
        created_at=NOW,
        updated_at=NOW,
    )
    insert(
        db,
        "document_access",
        document_id=did,
        scope_id="class:GS-KPI-01",
        granted_by="t",
        created_at=NOW,
    )


def version(db, vid="v1", did="d1", number=1, status="ready"):
    insert(
        db,
        "document_versions",
        id=vid,
        document_id=did,
        version=number,
        sha256="a" * 64,
        file_path=f"{did}/{vid}/source.docx",
        original_filename="source.docx",
        mime_type="application/octet-stream",
        file_size_bytes=10,
        status=status,
        uploaded_by="t",
        uploaded_at=NOW,
    )


def activate(db, did="d1", vid="v1"):
    db.execute("BEGIN IMMEDIATE")
    try:
        db.execute(
            "UPDATE document_versions SET status='superseded' "
            "WHERE document_id=? AND status='active'",
            (did,),
        )
        db.execute(
            "UPDATE documents SET status='active',active_version_id=?,revision=revision+1 "
            "WHERE id=?",
            (vid, did),
        )
        db.execute("UPDATE document_versions SET status='active' WHERE id=?", (vid,))
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.db = connect()
        self.db.executescript(DDL)
        seed(self.db)

    def tearDown(self):
        self.assertEqual(list(self.db.execute("PRAGMA foreign_key_check")), [])
        self.assertEqual(self.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.db.close()

    def test_schema_has_30_tables_and_fk_enabled(self):
        count = self.db.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[
            0
        ]
        self.assertEqual(count, 30)
        self.assertEqual(self.db.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_missing_identity_reference_is_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            insert(
                self.db,
                "enrollments",
                user_id="missing",
                class_id="GS-KPI-01",
                joined_at=NOW,
                updated_at=NOW,
            )

    def test_event_dedup_is_by_external_id_not_question(self):
        event(self.db)
        with self.assertRaises(sqlite3.IntegrityError):
            event(self.db, "e2", external="e1")
        event(self.db, "e3")
        self.assertEqual(self.db.execute("SELECT count(*) FROM webhook_events").fetchone()[0], 2)

    def test_binding_cannot_change_class_or_resolve_wrong_class(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "UPDATE group_bindings SET class_id='AUTO-N8N-01' WHERE id='g-GS-KPI-01'"
            )
        event(self.db)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("UPDATE webhook_events SET class_id='AUTO-N8N-01' WHERE event_key='e1'")

    def test_scope_must_resolve_real_resource_and_canonical_id(self):
        with self.assertRaises(sqlite3.IntegrityError):
            insert(
                self.db, "access_scopes", id="class:missing", scope_type="class", class_id="missing"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            insert(
                self.db, "access_scopes", id="class:wrong", scope_type="class", class_id="GS-KPI-01"
            )

    def test_active_version_must_belong_to_same_document(self):
        document(self.db, "d1")
        document(self.db, "d2")
        version(self.db, "v2", "d2")
        with self.assertRaises(sqlite3.IntegrityError):
            activate(self.db, "d1", "v2")
        self.assertIsNone(
            self.db.execute("SELECT active_version_id FROM documents WHERE id='d1'").fetchone()[0]
        )

    def test_failed_version_cannot_replace_current_active(self):
        document(self.db)
        version(self.db)
        activate(self.db)
        version(self.db, "v2", number=2, status="failed")
        with self.assertRaises(sqlite3.IntegrityError):
            activate(self.db, vid="v2")
        self.assertEqual(
            self.db.execute("SELECT active_version_id FROM documents WHERE id='d1'").fetchone()[0],
            "v1",
        )
        self.assertEqual(
            self.db.execute("SELECT status FROM document_versions WHERE id='v1'").fetchone()[0],
            "active",
        )

    def test_version_switch_and_revoke_are_atomic(self):
        document(self.db)
        version(self.db)
        activate(self.db)
        version(self.db, "v2", number=2)
        activate(self.db, vid="v2")
        self.assertEqual(
            self.db.execute("SELECT id FROM document_versions WHERE status='active'").fetchall(),
            [("v2",)],
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("UPDATE document_versions SET status='active' WHERE id='v1'")
        self.db.execute("BEGIN IMMEDIATE")
        self.db.execute(
            "UPDATE documents SET status='revoked',active_version_id=NULL WHERE id='d1'"
        )
        self.db.execute("UPDATE document_versions SET status='revoked' WHERE id='v2'")
        self.db.execute("COMMIT")
        self.assertIsNone(
            self.db.execute("SELECT active_version_id FROM documents WHERE id='d1'").fetchone()[0]
        )

    def test_hash_can_repeat_for_restore_version(self):
        document(self.db)
        version(self.db)
        version(self.db, "v2", number=2)
        self.assertEqual(self.db.execute("SELECT count(*) FROM document_versions").fetchone()[0], 2)
        with self.assertRaises(sqlite3.IntegrityError):
            version(self.db, "v3", number=2)

    def test_chunk_scope_must_be_in_document_access(self):
        document(self.db)
        version(self.db)
        fields = dict(
            document_id="d1",
            document_version_id="v1",
            chunk_id="ch1",
            section_id="GS-CLASS-01",
            topic="test",
            content_sha256="b" * 64,
            created_at=NOW,
        )
        insert(self.db, "document_chunks", point_id="p1", scope_id="class:GS-KPI-01", **fields)
        with self.assertRaises(sqlite3.IntegrityError):
            insert(
                self.db, "document_chunks", point_id="p2", scope_id="class:AUTO-N8N-01", **fields
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("DELETE FROM document_access WHERE document_id='d1'")

    def test_only_one_live_ingestion_job_per_version(self):
        document(self.db)
        version(self.db)
        fields = dict(document_version_id="v1", next_attempt_at=NOW, created_at=NOW)
        insert(self.db, "ingestion_jobs", id="j1", **fields)
        with self.assertRaises(sqlite3.IntegrityError):
            insert(self.db, "ingestion_jobs", id="j2", **fields)
        self.db.execute("UPDATE ingestion_jobs SET status='failed' WHERE id='j1'")
        insert(self.db, "ingestion_jobs", id="j2", **fields)

    def test_memory_cannot_join_another_groups_event(self):
        event(self.db)
        for cid in ["GS-KPI-01", "AUTO-N8N-01"]:
            insert(
                self.db,
                "conversation_sessions",
                id="session-" + cid,
                class_id=cid,
                group_binding_id="g-" + cid,
                started_at=NOW,
                last_hoi_at=NOW,
                expires_at=NOW,
            )
        with self.assertRaises(sqlite3.IntegrityError):
            insert(
                self.db,
                "messages",
                id="m1",
                session_id="session-AUTO-N8N-01",
                event_key="e1",
                class_id="GS-KPI-01",
                group_binding_id="g-GS-KPI-01",
                role="user",
                message_kind="question",
                text_redacted="test",
                created_at=NOW,
            )
        with self.assertRaises(sqlite3.IntegrityError):
            insert(
                self.db,
                "conversation_sessions",
                id="session-duplicate",
                class_id="GS-KPI-01",
                group_binding_id="g-GS-KPI-01",
                started_at=NOW,
                last_hoi_at=NOW,
                expires_at=NOW,
            )

    def test_ticket_run_and_outbox_are_idempotent(self):
        event(self.db)
        ticket = dict(
            event_key="e1",
            class_id="GS-KPI-01",
            group_binding_id="g-GS-KPI-01",
            student_id="s",
            question_redacted="q",
            reason_code="no_evidence",
            created_at=NOW,
            updated_at=NOW,
        )
        insert(self.db, "support_tickets", id="t1", **ticket)
        with self.assertRaises(sqlite3.IntegrityError):
            insert(self.db, "support_tickets", id="t2", **ticket)
        run = dict(
            event_key="e1", allowed_scopes_json="[]", active_versions_json="[]", started_at=NOW
        )
        insert(self.db, "rag_runs", id="r1", **run)
        with self.assertRaises(sqlite3.IntegrityError):
            insert(self.db, "rag_runs", id="r2", **run)
        out = dict(
            event_key="e1",
            class_id="GS-KPI-01",
            group_binding_id="g-GS-KPI-01",
            message_kind="bot_result",
            reply_to_external_event_id="e1",
            text_redacted="test",
            next_attempt_at=NOW,
            created_at=NOW,
        )
        insert(self.db, "outbound_messages", id="o1", **out)
        with self.assertRaises(sqlite3.IntegrityError):
            insert(self.db, "outbound_messages", id="o2", **out)
        out["message_kind"] = "teacher_answer"
        insert(self.db, "outbound_messages", id="o3", **out)

    def test_quota_release_only_once_and_event_reserves_only_once(self):
        event(self.db)
        insert(
            self.db, "daily_usage", user_id="s", local_date=DAY, accepted_count=1, updated_at=NOW
        )
        reserve = dict(user_id="s", local_date=DAY, status="reserved", reserved_at=NOW)
        insert(self.db, "quota_reservations", event_key="e1", **reserve)
        with self.assertRaises(sqlite3.IntegrityError):
            insert(self.db, "quota_reservations", event_key="e1", **reserve)
        for _ in range(2):
            self.db.execute("BEGIN IMMEDIATE")
            changed = self.db.execute(
                "UPDATE quota_reservations SET status='released',released_at=? "
                "WHERE event_key='e1' AND status='reserved'",
                (NOW,),
            ).rowcount
            if changed:
                self.db.execute(
                    "UPDATE daily_usage SET accepted_count=accepted_count-1 WHERE user_id=? AND local_date=?",
                    ("s", DAY),
                )
            self.db.execute("COMMIT")
        self.assertEqual(self.db.execute("SELECT accepted_count FROM daily_usage").fetchone()[0], 0)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("UPDATE daily_usage SET accepted_count=31")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("UPDATE daily_usage SET accepted_count=-1")

    def test_quota_concurrent_connections_cannot_both_take_30th_slot(self):
        with tempfile.TemporaryDirectory(prefix="gos-schema-") as folder:
            path = str(Path(folder) / "quota.db")
            db = connect(path)
            db.executescript(DDL)
            seed(db)
            insert(
                db, "daily_usage", user_id="s", local_date=DAY, accepted_count=29, updated_at=NOW
            )
            db.close()
            barrier = threading.Barrier(2)

            def claim(_):
                connection = connect(path)
                try:
                    barrier.wait(timeout=5)
                    connection.execute("BEGIN IMMEDIATE")
                    changed = connection.execute(
                        "UPDATE daily_usage SET accepted_count=accepted_count+1 "
                        "WHERE user_id=? AND local_date=? AND accepted_count<30",
                        ("s", DAY),
                    ).rowcount
                    connection.execute("COMMIT")
                    return changed
                finally:
                    connection.close()

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(claim, range(2)))
            self.assertEqual(sorted(results), [0, 1])
            db = connect(path)
            self.assertEqual(db.execute("SELECT accepted_count FROM daily_usage").fetchone()[0], 30)
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            db.close()

    def test_faq_approval_requires_actor_document_and_timestamp(self):
        event(self.db)
        insert(
            self.db,
            "support_tickets",
            id="t1",
            event_key="e1",
            class_id="GS-KPI-01",
            group_binding_id="g-GS-KPI-01",
            student_id="s",
            question_redacted="q",
            reason_code="no_evidence",
            created_at=NOW,
            updated_at=NOW,
        )
        fields = dict(
            source_ticket_id="t1",
            question_redacted="q",
            approved_answer_redacted="a",
            topic="test",
            scope_id="class:GS-KPI-01",
            created_by="t",
            created_at=NOW,
            updated_at=NOW,
        )
        with self.assertRaises(sqlite3.IntegrityError):
            insert(self.db, "faq_entries", id="f1", status="approved", **fields)
        insert(self.db, "faq_entries", id="f1", **fields)

    def test_provider_calls_keep_unknown_cost_and_have_one_owner(self):
        event(self.db)
        insert(
            self.db,
            "rag_runs",
            id="r1",
            event_key="e1",
            allowed_scopes_json="[]",
            active_versions_json="[]",
            started_at=NOW,
        )
        fields = dict(
            stage="generate",
            attempt_no=1,
            provider="test",
            model="test",
            status="unknown",
            started_at=NOW,
        )
        insert(self.db, "rag_run_attempts", id="call1", call_key="key1", rag_run_id="r1", **fields)
        self.assertIsNone(
            self.db.execute("SELECT estimated_cost_usd_micros FROM rag_run_attempts").fetchone()[0]
        )
        with self.assertRaises(sqlite3.IntegrityError):
            insert(self.db, "rag_run_attempts", id="call2", call_key="key2", **fields)
        with self.assertRaises(sqlite3.IntegrityError):
            insert(
                self.db, "rag_run_attempts", id="call2", call_key="key1", rag_run_id="r1", **fields
            )

    def test_invalid_json_and_status_are_rejected(self):
        event(self.db)
        with self.assertRaises(sqlite3.IntegrityError):
            insert(
                self.db,
                "rag_runs",
                id="r1",
                event_key="e1",
                allowed_scopes_json="{bad",
                active_versions_json="[]",
                started_at=NOW,
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("UPDATE webhook_events SET status='imaginary'")


if __name__ == "__main__":
    print(f"Design DDL validation — SQLite {sqlite3.sqlite_version}", flush=True)
    unittest.main(verbosity=2)
