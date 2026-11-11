from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import AppError, require
from app.core.security import matches
from app.services.auth_service import COOKIE

bearer = HTTPBearer(auto_error=False)


def current_user(
    request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)
):
    token = credentials.credentials if credentials else ""
    session = (
        None if credentials else request.app.state.auth.resolve_session(request.cookies.get(COOKIE))
    )
    user_id = (
        next(
            (
                user
                for secret, user in request.app.state.settings.auth_tokens_json.items()
                if matches(token, secret)
            ),
            None,
        )
        if credentials
        else (session["user_id"] if session else None)
    )
    if not user_id:
        raise AppError(401, "unauthorized", "Thông tin đăng nhập không hợp lệ.")
    with request.app.state.db.read() as s:
        user = s.one("SELECT * FROM users WHERE id=:id AND is_active=1", id=user_id)
    require(user is not None, 401, "unauthorized", "Tài khoản không còn hiệu lực.")
    if session and session["class_id"]:
        user["session_class_id"] = session["class_id"]
    return user


def staff(user=Depends(current_user)):
    require(user["role"] in {"teacher", "admin"})
    return user


def admin(user=Depends(current_user)):
    require(user["role"] == "admin")
    return user


def local_adapter(request: Request, user=Depends(current_user)):
    require(request.app.state.settings.mock_ui_enabled, 404, "not_found", "Mock API đang tắt.")
    require(user["role"] in {"admin", "service"})
    return user


def ok(request, data):
    return {"data": data, "error": None, "request_id": request.state.request_id}
