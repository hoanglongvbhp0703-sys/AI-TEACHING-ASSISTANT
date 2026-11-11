from app.core.passwords import hash_password
from app.schemas.event import MockEvent
from tests.conftest import auth, drain, payload, upload

PASSWORD = "Class isolation password 2026!"


def test_metadata_49_students_numbered_per_class_and_stable(rig):
    app, c, _, _ = rig
    created = c.post(
        "/api/v1/classes",
        headers=auth(),
        json={"id": "CLASS-49", "name": "Lớp 49", "course_id": "GS_KPI", "student_count": 49},
    )
    assert created.status_code == 201
    students = c.get("/api/v1/classes/CLASS-49/members?limit=100", headers=auth()).json()["data"]
    assert len(students) == 49
    assert [s["student_number"] for s in students] == list(range(1, 50))
    assert students[0]["display_name"] == "Học viên 1"
    snapshot = [s["id"] for s in students]
    assert (
        c.put(
            "/api/v1/classes/CLASS-49/roster",
            headers=auth("teacher-gs"),
            json={"student_count": 50},
        ).status_code
        == 403
    )
    assert (
        c.put(
            "/api/v1/classes/CLASS-49/roster", headers=auth(), json={"student_count": 48}
        ).status_code
        == 409
    )
    same = c.put(
        "/api/v1/classes/CLASS-49/roster", headers=auth(), json={"student_count": 49}
    ).json()["data"]
    assert same["created"] == 0 and [s["id"] for s in same["students"]] == snapshot
    new = c.put(
        "/api/v1/classes/CLASS-49/roster", headers=auth(), json={"student_count": 50}
    ).json()["data"]
    assert new["students"][-1]["student_number"] == 50
    c.put(
        "/api/v1/classes/CLASS-49/members/" + students[3]["id"],
        headers=auth(),
        json={"status": "suspended"},
    )
    assert (
        c.get("/api/v1/classes/CLASS-49/members?limit=100", headers=auth()).json()["data"][3][
            "student_number"
        ]
        == 4
    )
    metadata = c.get("/api/v1/auth/options?role=student&class_id=CLASS-49").json()["data"]
    assert len(metadata["profiles"]) == 49 and all(
        "password" not in p for p in metadata["profiles"]
    )


def test_selected_role_does_not_grant_privileges_and_class_session_enforced(rig):
    app, c, _, clock = rig
    with app.state.db.write() as s:
        for user in ["teacher-gs", "student-shared"]:
            app.state.auth.save_credentials(s, user, user, hash_password(PASSWORD), clock.stamp())
    assert (
        c.post(
            "/api/v1/auth/login",
            json={"username": "teacher-gs", "password": PASSWORD, "role": "admin"},
        ).status_code
        == 401
    )
    assert (
        c.post(
            "/api/v1/auth/login",
            json={"username": "student-shared", "password": PASSWORD, "role": "student"},
        ).status_code
        == 401
    )
    assert (
        c.post(
            "/api/v1/auth/login",
            json={
                "username": "student-shared",
                "password": PASSWORD,
                "role": "student",
                "class_id": "GS-KPI-01",
            },
        ).status_code
        == 200
    )
    assert [r["id"] for r in c.get("/api/v1/classes").json()["data"]] == ["GS-KPI-01"]
    assert c.get("/api/v1/classes/ML-DEMO-01/teachers").status_code == 403
    assert c.get("/api/v1/mock/groups/ZGROUP_ML01/messages").status_code == 403
    assert (
        c.post(
            "/api/v1/support-requests",
            json={
                "class_id": "ML-DEMO-01",
                "question": "No cross class",
                "client_request_id": "4dfda193-3fb2-46c5-a2d3-8d729c5b1f11",
            },
        ).status_code
        == 403
    )
    assert (
        c.post(
            "/api/v1/auth/password",
            json={"current_password": PASSWORD, "new_password": PASSWORD + "new"},
        ).status_code
        == 200
    )
    assert c.get("/api/v1/mock/groups/ZGROUP_ML01/messages").status_code == 403


def test_teacher_directory_only_admin_registered_credentials(rig):
    app, c, _, _ = rig
    assert c.get("/api/v1/auth/options?role=teacher").json()["data"]["profiles"] == []
    assert (
        c.post(
            "/api/v1/users",
            headers=auth("teacher-gs"),
            json={"id": "rogue", "role": "teacher", "display_name": "Rogue"},
        ).status_code
        == 403
    )
    assert (
        c.post(
            "/api/v1/users",
            headers=auth(),
            json={
                "id": "registered-teacher",
                "role": "teacher",
                "display_name": "Giảng viên đã đăng ký",
                "username": "registered.teacher",
                "password": PASSWORD,
            },
        ).status_code
        == 201
    )
    profiles = c.get("/api/v1/auth/options?role=teacher").json()["data"]["profiles"]
    assert profiles == [{"display_name": "Giảng viên đã đăng ký", "username": "registered.teacher"}]


def test_cross_class_sender_rejected_before_rag_and_memory_isolated(rig):
    app, c, backend, _ = rig
    forged = payload(eid="wrong-class", group="ZGROUP_ML01", sender="HV_GS_01")
    result = app.state.events.receive(MockEvent.model_validate(forged), "request")
    assert result["status"] == "rejected"
    drain(app)
    assert backend.contexts == []
    with app.state.db.read() as s:
        assert not s.all("SELECT * FROM rag_runs") and not s.all(
            "SELECT * FROM conversation_sessions"
        )
    info = upload(c).json()["data"]
    drain(app)
    app.state.events.receive(MockEvent.model_validate(payload(eid="authorized-gs")), "request")
    drain(app)
    app.state.events.receive(
        MockEvent.model_validate(
            payload(eid="authorized-ai", group="ZGROUP_ML01", sender="HV_ML_01")
        ),
        "request",
    )
    drain(app)
    assert info["version_id"] not in backend.contexts[-1].active_document_version_ids
    assert backend.contexts[-1].memory == []
