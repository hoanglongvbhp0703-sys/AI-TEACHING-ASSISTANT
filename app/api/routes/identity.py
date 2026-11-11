from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import admin, current_user, ok, staff
from app.core.errors import require
from app.core.passwords import hash_password
from app.repositories.store import uid
from app.schemas.common import Envelope
from app.schemas.identity import (
    AssignmentUpdate,
    BotUpdate,
    ClassCreate,
    CourseCreate,
    EnrollmentUpdate,
    GroupCreate,
    IdentityCreate,
    RosterMetadata,
    UserActive,
    UserCreate,
)
from app.services.access_service import check_class, class_ids
from app.services.roster_service import ensure_roster, roster

router = APIRouter(tags=["Identity & classes"])


@router.get("/auth/me", response_model=Envelope[Any])
def me(request: Request, user=Depends(current_user)):
    with request.app.state.db.read() as s:
        return ok(request, {**user, "class_ids": sorted(class_ids(s, user))})


@router.get("/users", response_model=Envelope[Any])
def users(
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    query: str = Query("", max_length=200),
    role: Literal["student", "teacher", "admin", "service"] | None = None,
    user=Depends(admin),
):
    with request.app.state.db.read() as s:
        return ok(
            request,
            s.all(
                "SELECT u.*,c.username,c.last_login_at FROM users u LEFT JOIN user_credentials c ON c.user_id=u.id WHERE (:role IS NULL OR u.role=:role) AND (:q='' OR account_search(u.display_name,:q) OR account_search(u.id,:q) OR account_search(COALESCE(c.username,''),:q)) ORDER BY u.id LIMIT :l OFFSET :o",
                l=limit,
                o=offset,
                role=role,
                q=query.strip(),
            ),
        )


@router.post("/users", status_code=201, response_model=Envelope[Any])
def create_user(body: UserCreate, request: Request, user=Depends(admin)):
    require(
        body.role != "service" or body.username is None,
        422,
        "invalid_user",
        "Tài khoản dịch vụ không dùng mật khẩu đăng nhập.",
    )
    encoded = hash_password(body.password.get_secret_value()) if body.password else None
    now = request.app.state.clock.stamp()
    with request.app.state.db.write() as s:
        s.insert(
            "users",
            **body.model_dump(exclude={"username", "password"}),
            created_at=now,
            updated_at=now,
        )
        if encoded:
            request.app.state.auth.save_credentials(s, body.id, body.username, encoded, now)
        s.audit(user["id"], "user.create", "user", body.id, now, request.state.request_id)
        return ok(
            request,
            {**s.one("SELECT * FROM users WHERE id=:id", id=body.id), "username": body.username},
        )


@router.patch("/users/{user_id}", response_model=Envelope[Any])
def user_active(user_id: str, body: UserActive, request: Request, user=Depends(admin)):
    require(
        user_id != user["id"],
        409,
        "self_update_denied",
        "Không tự khóa tài khoản quản trị đang sử dụng.",
    )
    with request.app.state.db.write() as s:
        require(
            s.one("SELECT id FROM users WHERE id=:u", u=user_id),
            404,
            "not_found",
            "Không tìm thấy người dùng.",
        )
        now = request.app.state.clock.stamp()
        s.update("users", "id", user_id, is_active=int(body.is_active), updated_at=now)
        s.audit(
            user["id"],
            "user.active",
            "user",
            user_id,
            now,
            request.state.request_id,
            body.model_dump(),
        )
        return ok(request, s.one("SELECT * FROM users WHERE id=:u", u=user_id))


@router.get("/courses", response_model=Envelope[Any])
def courses(request: Request, user=Depends(staff)):
    with request.app.state.db.read() as s:
        allowed = class_ids(s, user)
        visible = {
            r["course_id"] for r in s.all("SELECT id,course_id FROM classes") if r["id"] in allowed
        }
        return ok(
            request,
            [
                r
                for r in s.all("SELECT * FROM courses WHERE status='active' ORDER BY id")
                if user["role"] == "admin" or r["id"] in visible
            ],
        )


@router.post("/courses", status_code=201, response_model=Envelope[Any])
def create_course(body: CourseCreate, request: Request, user=Depends(admin)):
    now = request.app.state.clock.stamp()
    with request.app.state.db.write() as s:
        s.insert("courses", **body.model_dump(), created_at=now, updated_at=now)
        s.insert("access_scopes", id="course:" + body.id, scope_type="course", course_id=body.id)
        s.audit(user["id"], "course.create", "course", body.id, now, request.state.request_id)
        return ok(request, s.one("SELECT * FROM courses WHERE id=:id", id=body.id))


@router.get("/classes", response_model=Envelope[Any])
def classes(request: Request, user=Depends(current_user)):
    with request.app.state.db.read() as s:
        allowed = class_ids(s, user)
        return ok(
            request,
            [
                r
                for r in s.all("SELECT * FROM classes WHERE status='active' ORDER BY id")
                if r["id"] in allowed
            ],
        )


@router.post("/classes", status_code=201, response_model=Envelope[Any])
def create_class(body: ClassCreate, request: Request, user=Depends(admin)):
    now = request.app.state.clock.stamp()
    with request.app.state.db.write() as s:
        require(
            s.one("SELECT id FROM courses WHERE id=:c AND status='active'", c=body.course_id),
            422,
            "invalid_course",
            "Khóa học không tồn tại hoặc đã ngừng hoạt động.",
        )
        s.insert(
            "classes", **body.model_dump(exclude={"student_count"}), created_at=now, updated_at=now
        )
        ensure_roster(s, body.id, body.student_count, now)
        s.insert("access_scopes", id="class:" + body.id, scope_type="class", class_id=body.id)
        s.audit(user["id"], "class.create", "class", body.id, now, request.state.request_id)
        return ok(request, s.one("SELECT * FROM classes WHERE id=:id", id=body.id))


@router.patch("/classes/{class_id}/bot", response_model=Envelope[Any])
def bot(class_id: str, body: BotUpdate, request: Request, user=Depends(admin)):
    with request.app.state.db.write() as s:
        check_class(s, user, class_id)
        now = request.app.state.clock.stamp()
        s.update("classes", "id", class_id, bot_enabled=int(body.bot_enabled), updated_at=now)
        s.audit(
            user["id"],
            "class.bot.update",
            "class",
            class_id,
            now,
            request.state.request_id,
            body.model_dump(),
        )
        return ok(request, s.one("SELECT * FROM classes WHERE id=:id", id=class_id))


@router.get("/classes/{class_id}/members", response_model=Envelope[Any])
def members(
    class_id: str,
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user=Depends(staff),
):
    with request.app.state.db.read() as s:
        check_class(s, user, class_id)
        return ok(request, roster(s, class_id)[offset : offset + limit])


@router.get("/classes/{class_id}/teachers", response_model=Envelope[Any])
def teachers(class_id: str, request: Request, user=Depends(current_user)):
    with request.app.state.db.read() as s:
        check_class(s, user, class_id)
        rows = s.all(
            "SELECT u.id,u.display_name,u.is_active AS user_active,a.is_active AS assignment_active FROM teacher_assignments a JOIN users u ON u.id=a.teacher_id WHERE a.class_id=:c ORDER BY u.display_name",
            c=class_id,
        )
        return ok(
            request,
            rows
            if user["role"] == "admin"
            else [row for row in rows if row["user_active"] and row["assignment_active"]],
        )


@router.put("/classes/{class_id}/members/{student_id}", response_model=Envelope[Any])
def enroll(
    class_id: str, student_id: str, body: EnrollmentUpdate, request: Request, user=Depends(admin)
):
    with request.app.state.db.write() as s:
        check_class(s, user, class_id)
        require(
            s.one(
                "SELECT id FROM users WHERE id=:u AND role='student' AND is_active=1", u=student_id
            ),
            422,
            "invalid_student",
            "Cần tài khoản học viên đang hoạt động.",
        )
        now = request.app.state.clock.stamp()
        s.execute(
            "INSERT INTO enrollments (user_id,class_id,status,joined_at,updated_at) VALUES (:u,:c,:st,:n,:n) ON CONFLICT(user_id,class_id) DO UPDATE SET status=:st,updated_at=:n",
            u=student_id,
            c=class_id,
            st=body.status,
            n=now,
        )
        if body.status == "active":
            from app.services.roster_service import ensure_mock_identity

            ensure_mock_identity(s, student_id, now)
        s.audit(
            user["id"],
            "enrollment.update",
            "class",
            class_id,
            now,
            request.state.request_id,
            {"student_id": student_id, "status": body.status},
        )
        return ok(
            request,
            s.one(
                "SELECT * FROM enrollments WHERE user_id=:u AND class_id=:c",
                u=student_id,
                c=class_id,
            ),
        )


@router.put("/classes/{class_id}/teachers/{teacher_id}", response_model=Envelope[Any])
def assign_teacher(
    class_id: str, teacher_id: str, body: AssignmentUpdate, request: Request, user=Depends(admin)
):
    with request.app.state.db.write() as s:
        check_class(s, user, class_id)
        require(
            s.one(
                "SELECT id FROM users WHERE id=:u AND role='teacher' AND is_active=1", u=teacher_id
            ),
            422,
            "invalid_teacher",
            "Cần tài khoản giảng viên đang hoạt động.",
        )
        now = request.app.state.clock.stamp()
        s.execute(
            "INSERT INTO teacher_assignments (teacher_id,class_id,is_active,assigned_at) VALUES (:u,:c,:a,:n) ON CONFLICT(teacher_id,class_id) DO UPDATE SET is_active=:a",
            u=teacher_id,
            c=class_id,
            a=int(body.is_active),
            n=now,
        )
        s.audit(
            user["id"],
            "teacher_assignment.update",
            "class",
            class_id,
            now,
            request.state.request_id,
            {"teacher_id": teacher_id, "active": body.is_active},
        )
        return ok(
            request,
            s.one(
                "SELECT * FROM teacher_assignments WHERE teacher_id=:u AND class_id=:c",
                u=teacher_id,
                c=class_id,
            ),
        )


@router.post("/group-bindings", status_code=201, response_model=Envelope[Any])
def bind_group(body: GroupCreate, request: Request, user=Depends(admin)):
    with request.app.state.db.write() as s:
        check_class(s, user, body.class_id)
        now = request.app.state.clock.stamp()
        key = uid()
        s.insert(
            "group_bindings", id=key, platform="mock_zalo", **body.model_dump(), created_at=now
        )
        s.audit(user["id"], "group.bind", "group", key, now, request.state.request_id)
        return ok(request, s.one("SELECT * FROM group_bindings WHERE id=:id", id=key))


@router.post("/external-identities", status_code=201, response_model=Envelope[Any])
def bind_identity(body: IdentityCreate, request: Request, user=Depends(admin)):
    with request.app.state.db.write() as s:
        require(
            s.one("SELECT id FROM users WHERE id=:u AND is_active=1", u=body.user_id),
            422,
            "invalid_user",
            "Không tìm thấy user đang hoạt động.",
        )
        now = request.app.state.clock.stamp()
        key = uid()
        s.insert(
            "external_identities", id=key, platform="mock_zalo", **body.model_dump(), created_at=now
        )
        s.audit(user["id"], "identity.bind", "identity", key, now, request.state.request_id)
        return ok(request, s.one("SELECT * FROM external_identities WHERE id=:id", id=key))


@router.put("/classes/{class_id}/roster", response_model=Envelope[Any])
def update_roster(class_id: str, body: RosterMetadata, request: Request, user=Depends(admin)):
    with request.app.state.db.write() as s:
        check_class(s, user, class_id)
        now = request.app.state.clock.stamp()
        created = ensure_roster(s, class_id, body.student_count, now)
        s.audit(
            user["id"],
            "class.roster.update",
            "class",
            class_id,
            now,
            request.state.request_id,
            {"student_count": body.student_count, "created": len(created)},
        )
        return ok(
            request,
            {"class_id": class_id, "created": len(created), "students": roster(s, class_id)},
        )
