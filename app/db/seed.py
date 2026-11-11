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
        "UPDATE enrollments SET status='left',updated_at=:n WHERE class_id='AUTO-N8N-01' AND status!='left'",
        n=now,
    )
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
        ("adapter", "Mock adapter", "service"),
        ("student-shared", "Học viên hai lớp", "student"),
    ]
    with db.write() as s:
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
        for course, cid, group, teacher, prefix, name in [
            ("GS_KPI", "GS-KPI-01", "ZGROUP_GS01", "teacher-gs", "GS", "Google Sheets"),
            ("ML-DEMO", "ML-DEMO-01", "ZGROUP_ML01", "teacher-ai", "ML", "Machine Learning"),
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
            if not s.one(
                "SELECT id FROM group_bindings WHERE platform='mock_zalo' AND external_group_id=:g",
                g=group,
            ):
                s.insert(
                    "group_bindings",
                    id=group,
                    class_id=cid,
                    platform="mock_zalo",
                    external_group_id=group,
                    display_name=name,
                    created_at=now,
                )
            # Existing rosters and assignments belong to their admin.
            if not new_class:
                continue
            s.insert("teacher_assignments", teacher_id=teacher, class_id=cid, assigned_at=now)
            for user_id in [f"HV_{prefix}_{n:02}" for n in range(1, 5)] + ["student-shared"]:
                if not s.one("SELECT id FROM users WHERE id=:u", u=user_id):
                    s.insert(
                        "users",
                        id=user_id,
                        display_name="Học viên " + user_id,
                        role="student",
                        created_at=now,
                        updated_at=now,
                    )
                s.insert(
                    "enrollments", user_id=user_id, class_id=cid, joined_at=now, updated_at=now
                )
                s.execute(
                    "INSERT OR IGNORE INTO external_identities(id,user_id,platform,external_sender_id,created_at) VALUES (:u,:u,'mock_zalo',:u,:n)",
                    u=user_id,
                    n=now,
                )
