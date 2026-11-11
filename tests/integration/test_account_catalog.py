from fastapi.testclient import TestClient

from app.db.seed import seed_demo
from app.simulator import create_simulator
from tests.conftest import auth


def test_simulator_proxy_reads_new_classes_without_restart(rig, monkeypatch):
    app, backend, _, clock = rig
    simulator = create_simulator(app.state.settings, clock=clock)
    with TestClient(simulator) as client:
        monkeypatch.setattr(
            simulator.state.client,
            "get",
            lambda _url, **kwargs: backend.get("/api/v1/mock/catalog", **kwargs),
        )
        assert len(client.get("/api/mock/catalog").json()["data"]) == 2
        assert (
            backend.post(
                "/api/v1/classes",
                headers=auth(),
                json={"id": "QA-PROXY", "name": "QA", "course_id": "ML-DEMO", "student_count": 2},
            ).status_code
            == 201
        )
        assert (
            backend.post(
                "/api/v1/group-bindings",
                headers=auth(),
                json={
                    "class_id": "QA-PROXY",
                    "external_group_id": "QA-PROXY",
                    "display_name": "QA",
                },
            ).status_code
            == 201
        )
        groups = client.get("/api/mock/catalog").json()["data"]
        assert len(groups) == 3
        assert next(g for g in groups if g["class_id"] == "QA-PROXY")["student_count"] == 2


def test_search_accounts_by_unicode_name_username_role_and_before_pagination(rig):
    app, c, _, clock = rig
    with app.state.db.write() as s:
        for n in range(24):
            s.insert(
                "users",
                id=f"SEARCH-{n:02}",
                display_name=f"Nguyễn Kiểm Thử {n}",
                role="teacher" if n % 2 else "student",
                created_at=clock.stamp(),
                updated_at=clock.stamp(),
            )
    query = c.get(
        "/api/v1/users",
        headers=auth(),
        params={"query": "NGUYEN KIEM THU", "role": "teacher", "limit": 5, "offset": 5},
    )
    rows = query.json()["data"]
    assert len(rows) == 5 and all(r["role"] == "teacher" for r in rows)
    assert rows[0]["id"] == "SEARCH-11"
    target = c.get("/api/v1/users", headers=auth(), params={"query": "SEARCH-23"}).json()["data"]
    assert [u["id"] for u in target] == ["SEARCH-23"]
    assert c.get("/api/v1/users", headers=auth(), params={"query": "%"}).json()["data"] == []
    assert (
        c.get("/api/v1/users", headers=auth("teacher-gs"), params={"query": "Nguyễn"}).status_code
        == 403
    )
    assert c.get("/api/v1/users?role=invalid", headers=auth()).status_code == 422


def test_new_class_roster_manual_student_and_teacher_reach_catalog(rig):
    _, c, _, _ = rig
    headers = auth()
    cid = "QA-CLASS"
    assert (
        c.post(
            "/api/v1/classes",
            headers=headers,
            json={"id": cid, "course_id": "ML-DEMO", "name": "Lớp kiểm thử", "student_count": 3},
        ).status_code
        == 201
    )
    assert cid in {r["id"] for r in c.get("/api/v1/classes", headers=headers).json()["data"]}
    assert cid not in {
        r["class_id"] for r in c.get("/api/v1/mock/catalog", headers=auth("adapter")).json()["data"]
    }
    assert (
        c.post(
            "/api/v1/group-bindings",
            headers=headers,
            json={"class_id": cid, "external_group_id": "QA-GROUP", "display_name": "QA"},
        ).status_code
        == 201
    )
    for uid, role in [("QA-STUDENT", "student"), ("QA-TEACHER", "teacher")]:
        assert (
            c.post(
                "/api/v1/users",
                headers=headers,
                json={
                    "id": uid,
                    "display_name": "Nguyễn Kiểm Thử",
                    "role": role,
                    "username": uid.lower(),
                    "password": "Evaluation-password-123!",
                },
            ).status_code
            == 201
        )
    found = c.get(
        "/api/v1/users", headers=headers, params={"query": "QA-TEACHER", "role": "teacher"}
    ).json()["data"]
    assert len(found) == 1 and found[0]["username"] == "qa-teacher"
    assert (
        c.put(
            f"/api/v1/classes/{cid}/members/QA-STUDENT", headers=headers, json={"status": "active"}
        ).status_code
        == 200
    )
    assert (
        c.put(
            f"/api/v1/classes/{cid}/teachers/QA-TEACHER", headers=headers, json={"is_active": True}
        ).status_code
        == 200
    )
    group = next(
        g
        for g in c.get("/api/v1/mock/catalog", headers=auth("adapter")).json()["data"]
        if g["class_id"] == cid
    )
    assert group["student_count"] == 4
    assert [s["student_number"] for s in group["students"]] == [1, 2, 3, 4]
    assert "QA-STUDENT" in {s["sender_id"] for s in group["students"]}
    assert "QA-TEACHER" not in {s["sender_id"] for s in group["students"]}
    assert "QA-TEACHER" in {
        t["id"] for t in c.get(f"/api/v1/classes/{cid}/teachers", headers=headers).json()["data"]
    }
    assert (
        c.put(
            f"/api/v1/classes/{cid}/members/QA-STUDENT",
            headers=headers,
            json={"status": "suspended"},
        ).status_code
        == 200
    )
    group = next(
        g
        for g in c.get("/api/v1/mock/catalog", headers=auth("adapter")).json()["data"]
        if g["class_id"] == cid
    )
    assert group["student_count"] == 3


def test_seed_retires_auto_and_does_not_restore_it_or_grow_existing_rosters(rig):
    app, c, _, clock = rig
    now = clock.stamp()
    with app.state.db.write() as s:
        before = s.one("SELECT count(*) AS n FROM enrollments")["n"]
        s.insert("courses", id="AI_AUTO", name="AUTO", created_at=now, updated_at=now)
        s.insert(
            "classes",
            id="AUTO-N8N-01",
            course_id="AI_AUTO",
            name="AUTO",
            created_at=now,
            updated_at=now,
        )
        s.insert(
            "group_bindings",
            id="ZGROUP_AI01",
            class_id="AUTO-N8N-01",
            platform="mock_zalo",
            external_group_id="ZGROUP_AI01",
            display_name="AUTO",
            created_at=now,
        )
    seed_demo(app.state.db, clock)
    seed_demo(app.state.db, clock)
    assert {r["id"] for r in c.get("/api/v1/classes", headers=auth()).json()["data"]} == {
        "GS-KPI-01",
        "ML-DEMO-01",
    }
    assert "AI_AUTO" not in {
        r["id"] for r in c.get("/api/v1/courses", headers=auth()).json()["data"]
    }
    assert {
        r["class_id"] for r in c.get("/api/v1/mock/catalog", headers=auth("adapter")).json()["data"]
    } == {"GS-KPI-01", "ML-DEMO-01"}
    with app.state.db.read() as s:
        assert s.one("SELECT status FROM classes WHERE id='AUTO-N8N-01'")["status"] == "archived"
        assert s.one("SELECT count(*) AS n FROM enrollments")["n"] == before
        assert s.all("PRAGMA foreign_key_check") == []
