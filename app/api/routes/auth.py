from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response

from app.api.deps import admin, current_user, ok
from app.schemas.auth import ChangePassword, Credentials, LoginInput, SetupInput
from app.schemas.common import Envelope
from app.services.auth_service import COOKIE, TTL_SECONDS

router = APIRouter(tags=["Password authentication"])


def session_cookie(response, token):
    response.set_cookie(
        COOKIE, token, max_age=TTL_SECONDS, httponly=True, samesite="strict", secure=False, path="/"
    )


@router.get("/auth/status", response_model=Envelope[Any])
def auth_status(request: Request):
    return ok(request, request.app.state.auth.status())


@router.post("/auth/setup", status_code=201, response_model=Envelope[Any])
def setup(body: SetupInput, request: Request, response: Response):
    user, token = request.app.state.auth.setup(body, request.state.request_id)
    session_cookie(response, token)
    return ok(request, user)


@router.post("/auth/login", response_model=Envelope[Any])
def login(body: LoginInput, request: Request, response: Response):
    user, token = request.app.state.auth.login(body, request.state.request_id)
    request.app.state.auth.revoke(request.cookies.get(COOKIE))
    session_cookie(response, token)
    return ok(request, user)


@router.post("/auth/logout", response_model=Envelope[Any])
def logout(request: Request, response: Response):
    request.app.state.auth.revoke(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/")
    return ok(request, {"logged_out": True})


@router.post("/auth/password", response_model=Envelope[Any])
def change_password(
    body: ChangePassword, request: Request, response: Response, user=Depends(current_user)
):
    token = request.app.state.auth.change_password(
        user["id"], body, request.state.request_id, user.get("session_class_id")
    )
    session_cookie(response, token)
    return ok(request, {"password_changed": True, "other_sessions_revoked": True})


@router.put("/users/{user_id}/credentials", response_model=Envelope[Any])
def credentials(user_id: str, body: Credentials, request: Request, user=Depends(admin)):
    return ok(
        request,
        request.app.state.auth.set_credentials(user, user_id, body, request.state.request_id),
    )


@router.get("/auth/options", response_model=Envelope[Any])
def login_options(
    request: Request,
    role: Literal["admin", "teacher", "student"],
    class_id: str | None = Query(None, max_length=100),
):
    return ok(request, request.app.state.auth.options(role, class_id))
