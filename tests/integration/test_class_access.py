from app.schemas.event import IncomingEvent
from tests.conftest import auth, drain, payload


def test_any_transport_sender_uses_only_bound_class(rig):
    app, c, backend, clock = rig
    for eid, group, sender, expected in [
        ("A", "123456:TEST-GS", "unregistered-person", "GS-KPI-01"),
        ("B", "123456:TEST-ML", "another-person", "ML-DEMO-01"),
    ]:
        result = app.state.events.receive(
            IncomingEvent.model_validate(payload(eid, group=group, sender=sender)), eid
        )
        assert result["status"] == "queued"
        drain(app)
        assert backend.contexts[-1].class_id == expected
    assert backend.contexts[-1].memory == []
    with app.state.db.read() as s:
        assert s.one("SELECT count(*) n FROM users WHERE role='student'")["n"] == 0
        assert not s.one("SELECT name FROM sqlite_master WHERE name='enrollments'")
        assert s.one("SELECT count(*) n FROM external_identities")["n"] == 0


def test_unknown_group_and_disabled_class_do_not_call_rag(rig):
    app, c, backend, clock = rig
    event = IncomingEvent.model_validate(payload(group="UNKNOWN", sender="anyone"))
    assert app.state.events.receive(event, "unknown")["outcome_code"] == "access_denied"
    c.patch("/api/v1/classes/GS-KPI-01/bot", headers=auth(), json={"bot_enabled": False})
    event = IncomingEvent.model_validate(payload(eid="off", sender="anyone"))
    assert app.state.events.receive(event, "off")["outcome_code"] == "access_denied"
    drain(app)
    assert not backend.contexts


def test_staff_class_assignment_still_enforced(rig):
    app, c, backend, clock = rig
    assert (
        c.get("/api/v1/classes", headers=auth("teacher-gs")).json()["data"][0]["id"] == "GS-KPI-01"
    )
    assert (
        c.get("/api/v1/classes/ML-DEMO-01/teachers", headers=auth("teacher-gs")).status_code == 403
    )
    assert c.get("/api/v1/auth/me", headers=auth("HV_GS_01")).status_code == 401
