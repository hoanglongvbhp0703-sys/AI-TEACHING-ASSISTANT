import hashlib
from datetime import timedelta

from app.services.auth_service import COOKIE
from tests.conftest import auth

PASSWORD = "Auth test password 2026!"
NEW_PASSWORD = "Replacement password 2026!"


def setup(c):
    return c.post("/api/v1/auth/setup", json={"username": "Admin.Login", "password": PASSWORD})


def login(c, username="admin.login", password=PASSWORD):
    return c.post("/api/v1/auth/login", json={"username": username, "password": password})


def test_setup_once_hashes_secrets_and_persists_sessions(rig):
    app, c, _, _ = rig
    assert c.get("/api/v1/auth/status").json()["data"]["setup_required"]
    assert setup(c).status_code == 201
    token = c.cookies.get(COOKIE)
    assert setup(c).status_code == 409
    with app.state.db.read() as s:
        credential = s.one("SELECT * FROM user_credentials")
        assert credential["username"] == "admin.login"
        assert credential["password_hash"].startswith("$argon2id$")
        assert PASSWORD not in credential["password_hash"]
        session = s.one("SELECT * FROM auth_sessions")
        assert session["token_hash"] == hashlib.sha256(token.encode()).hexdigest()
        assert PASSWORD not in str(s.all("SELECT * FROM audit_logs"))
    assert app.state.auth.resolve(token) == "admin"
    rows = c.get("/api/v1/users").text
    assert "password_hash" not in rows and token not in rows
    assert c.post("/api/v1/auth/logout").status_code == 200
    assert app.state.auth.resolve(token) is None
    assert login(c, " ADMIN.LOGIN ").status_code == 200


def test_lockout_and_expiration(rig):
    app, c, _, clock = rig
    setup(c)
    for _ in range(5):
        assert login(c, password="wrong").status_code == 401
    assert login(c).status_code == 401
    clock.value += timedelta(minutes=16)
    assert login(c).status_code == 200
    clock.value += timedelta(hours=9)
    assert c.get("/api/v1/auth/me").status_code == 401


def test_change_password_and_admin_reset_revoke_sessions(rig):
    app, c, _, _ = rig
    setup(c)
    old = c.cookies.get(COOKIE)
    assert (
        c.post(
            "/api/v1/auth/password",
            json={"current_password": "wrong", "new_password": NEW_PASSWORD},
        ).status_code
        == 401
    )
    assert (
        c.post(
            "/api/v1/auth/password",
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        ).status_code
        == 200
    )
    assert app.state.auth.resolve(old) is None
    assert login(c).status_code == 401
    assert login(c, password=NEW_PASSWORD).status_code == 200
    payload = {"username": "teacher.login", "password": PASSWORD}
    assert c.put("/api/v1/users/teacher-gs/credentials", json=payload).status_code == 200
    assert login(c, "teacher.login").status_code == 200
    teacher_token = c.cookies.get(COOKIE)
    assert c.put("/api/v1/users/teacher-ai/credentials", json=payload).status_code == 403
    assert (
        c.put(
            "/api/v1/users/teacher-gs/credentials",
            headers=auth(),
            json={**payload, "password": NEW_PASSWORD},
        ).status_code
        == 200
    )
    assert app.state.auth.resolve(teacher_token) is None
    assert login(c, "teacher.login").status_code == 401
    assert login(c, "teacher.login", NEW_PASSWORD).status_code == 200


def test_validation_duplicate_and_legacy_routes(rig):
    app, c, _, _ = rig
    assert (
        c.post("/api/v1/auth/setup", json={"username": "admin", "password": "short"}).status_code
        == 422
    )
    setup(c)
    assert (
        c.put(
            "/api/v1/users/admin/credentials", json={"username": "another", "password": PASSWORD}
        ).status_code
        == 409
    )
    assert (
        c.post(
            "/api/v1/users",
            json={
                "id": "duplicate-login",
                "display_name": "Duplicate",
                "role": "teacher",
                "username": "admin.login",
                "password": PASSWORD,
            },
        ).status_code
        == 409
    )
    with app.state.db.read() as s:
        assert s.one("SELECT id FROM users WHERE id='duplicate-login'") is None
    assert c.get("/api/v1/demo/accounts").status_code == 404
    assert c.post("/api/v1/demo/session", json={"user_id": "admin"}).status_code == 404
    assert login(c, "unknown").status_code == 401


def test_migration_v1_preserves_existing_profiles(tmp_path):
    import sqlite3
    from pathlib import Path

    from app.core.config import Settings
    from app.db.session import Database

    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    sql = Path("app/db/migrations/versions/0001_initial.sql").read_text()
    connection.executescript(sql.replace("COMMIT;", "PRAGMA user_version=1;\nCOMMIT;"))
    connection.execute(
        "INSERT INTO users(id,display_name,role,created_at,updated_at) VALUES ('legacy','Existing teacher','teacher','2026-01-01','2026-01-01')"
    )
    connection.commit()
    before = connection.execute("SELECT * FROM users").fetchall()
    connection.close()
    db = Database(Settings(_env_file=None, database_url="sqlite:///" + str(path)))
    try:
        db.migrate()
        db.migrate()
        with db.engine.connect() as c:
            assert [tuple(row) for row in c.exec_driver_sql("SELECT * FROM users")] == before
            assert c.exec_driver_sql("PRAGMA user_version").scalar() == 4
            assert not c.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            assert c.exec_driver_sql("SELECT count(*) FROM user_credentials").scalar() == 0
    finally:
        db.engine.dispose()
