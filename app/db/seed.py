def retire_automation_demo(s, now):
    """Retire the legacy AUTO demo without deleting its documents or history."""
    old = s.one("SELECT status FROM classes WHERE id='AUTO-N8N-01'")
    if not old:
        return
    s.execute(
        "UPDATE classes SET status='archived',bot_enabled=0,updated_at=:n WHERE id='AUTO-N8N-01'",
        n=now,
    )
    s.execute("UPDATE group_bindings SET is_active=0 WHERE class_id='AUTO-N8N-01'")
    s.execute("UPDATE teacher_assignments SET is_active=0 WHERE class_id='AUTO-N8N-01'")
    s.execute(
        "UPDATE conversation_sessions SET status='closed' WHERE class_id='AUTO-N8N-01' AND status='open'"
    )
    s.execute(
        "UPDATE courses SET status='archived',updated_at=:n WHERE id='AI_AUTO' AND NOT EXISTS(SELECT 1 FROM classes WHERE course_id='AI_AUTO' AND status='active')",
        n=now,
    )
    if old["status"] != "archived":
        s.audit("admin", "demo.auto.retire", "class", "AUTO-N8N-01", now, "retire-auto-demo")


def seed_demo(db, clock):
    """Seed Sheets/ML only. Preserve existing rosters and retire the former AUTO demo."""
    now = clock.stamp()
    users = [
        ("admin", "Quản trị demo", "admin"),
        ("teacher-gs", "Giảng viên Sheets", "teacher"),
        ("teacher-ai", "Giảng viên Machine Learning", "teacher"),
    ]
    with db.write() as s:
        # Preserve old audit records, but retire channels no longer supported by this release.
        from app.services.quota_service import release

        for event in s.all(
            "SELECT event_key FROM webhook_events WHERE platform!='zalo_bot' AND status IN ('queued','processing')"
        ):
            release(s, event["event_key"], now, "transport_removed")
        s.execute(
            "UPDATE webhook_events SET status='ignored',outcome_code='transport_removed',completed_at=:n WHERE platform!='zalo_bot' AND status IN ('queued','processing')",
            n=now,
        )
        s.execute(
            "UPDATE outbound_messages SET status='cancelled',error_code='transport_removed' WHERE status IN ('pending','sending') AND event_key IN (SELECT event_key FROM webhook_events WHERE platform!='zalo_bot')"
        )
        s.execute("UPDATE group_bindings SET is_active=0 WHERE platform!='zalo_bot'")
        for user_id, name, role in users:
            if not s.one("SELECT id FROM users WHERE id=:id", id=user_id):
                s.insert(
                    "users",
                    id=user_id,
                    display_name=name,
                    role=role,
                    created_at=now,
                    updated_at=now,
                )
        retire_automation_demo(s, now)
        for course, cid, teacher, name in [
            ("GS_KPI", "GS-KPI-01", "teacher-gs", "Google Sheets"),
            ("ML-DEMO", "ML-DEMO-01", "teacher-ai", "Machine Learning"),
        ]:
            if not s.one("SELECT id FROM courses WHERE id=:id", id=course):
                s.insert("courses", id=course, name=name, created_at=now, updated_at=now)
                s.insert(
                    "access_scopes", id="course:" + course, scope_type="course", course_id=course
                )
            new_class = not s.one("SELECT id FROM classes WHERE id=:id", id=cid)
            if new_class:
                s.insert(
                    "classes", id=cid, course_id=course, name=name, created_at=now, updated_at=now
                )
                s.insert("access_scopes", id="class:" + cid, scope_type="class", class_id=cid)
            # Existing teacher assignments belong to their admin.
            if not new_class:
                continue
            s.insert("teacher_assignments", teacher_id=teacher, class_id=cid, assigned_at=now)
