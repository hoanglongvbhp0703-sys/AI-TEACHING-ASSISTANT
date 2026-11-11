import hashlib
import secrets
from datetime import timedelta

from app.core.clock import stamp
from app.core.errors import AppError, require
from app.core.passwords import DUMMY_HASH, HASHER, hash_password, verify_password
from app.core.security import clean
from app.repositories.store import uid

COOKIE = "gos_portal_session"
TTL_SECONDS = 8 * 60 * 60
LOGIN_FAILURES = 5
LOCK_MINUTES = 15


class AuthService:
    def __init__(self, db, clock, settings):
        self.db, self.clock, self.settings = db, clock, settings

    @staticmethod
    def initialized(s):
        return bool(
            s.one(
                "SELECT c.user_id FROM user_credentials c JOIN users u ON u.id=c.user_id WHERE u.role='admin' LIMIT 1"
            )
        )

    def status(self):
        with self.db.read() as s:
            return {"setup_required": not self.initialized(s)}

    def issue(self, s, user_id, class_id=None):
        token = secrets.token_urlsafe(32)
        s.insert(
            "auth_sessions",
            id=uid(),
            user_id=user_id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            created_at=self.clock.stamp(),
            expires_at=stamp(self.clock.now() + timedelta(seconds=TTL_SECONDS)),
            class_id=class_id,
        )
        return token

    def resolve_session(self, token):
        if not token or len(token) > 128:
            return None
        with self.db.read() as s:
            return s.one(
                "SELECT a.user_id,a.class_id FROM auth_sessions a JOIN users u ON u.id=a.user_id WHERE a.token_hash=:h AND a.revoked_at IS NULL AND a.expires_at>:n AND u.is_active=1 AND (a.class_id IS NULL OR EXISTS(SELECT 1 FROM enrollments e JOIN classes c ON c.id=e.class_id WHERE e.user_id=u.id AND e.class_id=a.class_id AND e.status='active' AND c.status='active'))",
                h=hashlib.sha256(token.encode()).hexdigest(),
                n=self.clock.stamp(),
            )

    def resolve(self, token):
        session = self.resolve_session(token)
        return session["user_id"] if session else None

    def options(self, role, class_id):
        with self.db.read() as s:
            if role == "teacher":
                return {
                    "profiles": s.all(
                        "SELECT u.display_name,c.username FROM users u JOIN user_credentials c ON c.user_id=u.id WHERE u.role='teacher' AND u.is_active=1 ORDER BY u.display_name,u.id"
                    )
                }
            if role == "student":
                classes = s.all(
                    "SELECT id,name FROM classes WHERE status='active' ORDER BY name,id"
                )
                profiles = (
                    s.all(
                        "SELECT e.student_number,c.username FROM enrollments e JOIN users u ON u.id=e.user_id LEFT JOIN user_credentials c ON c.user_id=u.id WHERE e.class_id=:c AND e.status='active' AND u.is_active=1 AND u.role='student' ORDER BY e.student_number",
                        c=class_id,
                    )
                    if class_id in {c["id"] for c in classes}
                    else []
                )
                return {
                    "classes": classes,
                    "profiles": [
                        {**p, "display_name": f"Học viên {p['student_number']}"} for p in profiles
                    ],
                }
            return {"profiles": []}

    def revoke(self, token):
        if token:
            with self.db.write() as s:
                s.execute(
                    "UPDATE auth_sessions SET revoked_at=:n WHERE token_hash=:h AND revoked_at IS NULL",
                    n=self.clock.stamp(),
                    h=hashlib.sha256(token.encode()).hexdigest(),
                )

    def setup(self, body, request_id):
        encoded = hash_password(body.password.get_secret_value())
        now = self.clock.stamp()
        with self.db.write() as s:
            require(
                not self.initialized(s),
                409,
                "setup_complete",
                "Tài khoản quản trị đã được khởi tạo. Hãy đăng nhập.",
            )
            user = s.one(
                "SELECT * FROM users WHERE role='admin' AND is_active=1 ORDER BY created_at,id LIMIT 1"
            )
            if user is None:
                require(
                    not s.one("SELECT id FROM users WHERE role='admin' LIMIT 1"),
                    409,
                    "admin_disabled",
                    "Tài khoản quản trị đang bị khóa; cần quản trị hệ thống khôi phục.",
                )
                user = s.insert(
                    "users",
                    id=uid(),
                    display_name=clean(self.settings, body.display_name),
                    role="admin",
                    is_active=1,
                    created_at=now,
                    updated_at=now,
                )
            else:
                s.update(
                    "users",
                    "id",
                    user["id"],
                    display_name=clean(self.settings, body.display_name),
                    updated_at=now,
                )
            self.save_credentials(s, user["id"], body.username, encoded, now)
            token = self.issue(s, user["id"])
            s.audit(
                user["id"],
                "auth.setup",
                "user",
                user["id"],
                now,
                request_id,
                {"username": body.username},
            )
            return s.one("SELECT id,display_name,role FROM users WHERE id=:u", u=user["id"]), token

    @staticmethod
    def save_credentials(s, user_id, username, encoded, now):
        s.execute(
            "INSERT INTO user_credentials (user_id,username,password_hash,password_changed_at,created_at,updated_at) VALUES (:u,:name,:hash,:n,:n,:n) ON CONFLICT(user_id) DO UPDATE SET username=:name,password_hash=:hash,password_changed_at=:n,updated_at=:n,failed_attempts=0,locked_until=NULL",
            u=user_id,
            name=username,
            hash=encoded,
            n=now,
        )
        s.execute(
            "UPDATE auth_sessions SET revoked_at=:n WHERE user_id=:u AND revoked_at IS NULL",
            n=now,
            u=user_id,
        )

    def login(self, body, request_id):
        with self.db.read() as s:
            initial = s.one(
                "SELECT c.*,u.role,u.is_active FROM user_credentials c JOIN users u ON u.id=c.user_id WHERE c.username=:name",
                name=body.username,
            )
        verified = verify_password(
            initial["password_hash"] if initial else DUMMY_HASH, body.password.get_secret_value()
        )
        valid = initial is not None and verified
        rehash = (
            hash_password(body.password.get_secret_value())
            if valid and HASHER.check_needs_rehash(initial["password_hash"])
            else None
        )
        now = self.clock.stamp()
        failed = True
        with self.db.write() as s:
            current = s.one(
                "SELECT c.*,u.role,u.is_active FROM user_credentials c JOIN users u ON u.id=c.user_id WHERE c.username=:name",
                name=body.username,
            )
            locked = current and current["locked_until"] and current["locked_until"] > now
            allowed = (
                current
                and current["is_active"]
                and current["role"] in {"admin", "teacher", "student"}
            )
            if allowed and body.role is not None:
                allowed = current["role"] == body.role
            if allowed and body.role == "student" and body.class_id is None:
                allowed = False
            if allowed and body.class_id is not None:
                allowed = current["role"] == "student" and bool(
                    s.one(
                        "SELECT e.user_id FROM enrollments e JOIN classes c ON c.id=e.class_id WHERE e.user_id=:u AND e.class_id=:c AND e.status='active' AND c.status='active'",
                        u=current["user_id"],
                        c=body.class_id,
                    )
                )
            unchanged = current and initial and current["password_hash"] == initial["password_hash"]
            if valid and unchanged and allowed and not locked:
                s.update(
                    "user_credentials",
                    "user_id",
                    current["user_id"],
                    failed_attempts=0,
                    locked_until=None,
                    last_login_at=now,
                    **({"password_hash": rehash} if rehash else {}),
                )
                token = self.issue(s, current["user_id"], body.class_id)
                user = s.one(
                    "SELECT id,display_name,role FROM users WHERE id=:u", u=current["user_id"]
                )
                s.audit(user["id"], "auth.login", "user", user["id"], now, request_id)
                failed = False
            else:
                if current and not locked:
                    attempts = (0 if current["locked_until"] else current["failed_attempts"]) + 1
                    s.update(
                        "user_credentials",
                        "user_id",
                        current["user_id"],
                        failed_attempts=attempts,
                        locked_until=stamp(self.clock.now() + timedelta(minutes=LOCK_MINUTES))
                        if attempts >= LOGIN_FAILURES
                        else None,
                    )
                s.security("auth_login_failed", request_id, now)
        if failed:
            raise AppError(
                401,
                "invalid_credentials",
                "Tài khoản hoặc mật khẩu không đúng. Nếu thử nhiều lần, vui lòng chờ 15 phút.",
            )
        return user, token

    def set_credentials(self, actor, user_id, body, request_id):
        require(
            actor["id"] != user_id,
            409,
            "use_password_change",
            "Hãy dùng chức năng Đổi mật khẩu cho tài khoản của bạn.",
        )
        encoded = hash_password(body.password.get_secret_value())
        now = self.clock.stamp()
        with self.db.write() as s:
            user = s.one("SELECT id,role FROM users WHERE id=:u", u=user_id)
            require(user is not None, 404, "not_found", "Không tìm thấy người dùng.")
            require(
                user["role"] in {"student", "teacher", "admin"},
                422,
                "invalid_user",
                "Tài khoản dịch vụ không dùng mật khẩu đăng nhập.",
            )
            self.save_credentials(s, user_id, body.username, encoded, now)
            s.audit(
                actor["id"],
                "auth.credentials.reset",
                "user",
                user_id,
                now,
                request_id,
                {"username": body.username},
            )
        return {"user_id": user_id, "username": body.username, "sessions_revoked": True}

    def change_password(self, user_id, body, request_id, class_id=None):
        with self.db.read() as s:
            initial = s.one("SELECT * FROM user_credentials WHERE user_id=:u", u=user_id)
        require(
            initial is not None
            and verify_password(initial["password_hash"], body.current_password.get_secret_value()),
            401,
            "invalid_credentials",
            "Mật khẩu hiện tại không đúng.",
        )
        encoded = hash_password(body.new_password.get_secret_value())
        now = self.clock.stamp()
        with self.db.write() as s:
            current = s.one(
                "SELECT password_hash FROM user_credentials WHERE user_id=:u", u=user_id
            )
            require(
                current and current["password_hash"] == initial["password_hash"],
                409,
                "credentials_changed",
                "Mật khẩu đã thay đổi. Hãy đăng nhập lại.",
            )
            self.save_credentials(s, user_id, initial["username"], encoded, now)
            token = self.issue(s, user_id, class_id)
            s.audit(user_id, "auth.password.change", "user", user_id, now, request_id)
        return token
