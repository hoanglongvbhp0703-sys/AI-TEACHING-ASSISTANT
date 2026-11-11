"""Authentication and parsing for our mock webhook, not the official Zalo signature scheme."""

import hashlib
import hmac
import re

from fastapi import Header, Request
from pydantic import ValidationError

from app.core.errors import AppError, require
from app.core.security import matches
from app.schemas.event import MockEvent


def sign_payload(secret: str, timestamp: str, raw_body: bytes) -> str:
    """Sign the exact HTTP body bytes; timestamp is delivery time, not event.sent_at."""
    signed_data = timestamp.encode("ascii") + b"." + raw_body
    digest = hmac.new(secret.encode("utf-8"), signed_data, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(secret, timestamp, signature, raw_body, now, tolerance_seconds):
    require(
        timestamp is not None and re.fullmatch(r"[0-9]{1,12}", timestamp) is not None,
        401,
        "invalid_webhook_timestamp",
        "Thiếu hoặc sai timestamp webhook.",
    )
    require(
        abs(now - int(timestamp)) <= tolerance_seconds,
        401,
        "webhook_timestamp_expired",
        "Timestamp webhook ngoài khoảng thời gian được chấp nhận.",
    )
    require(
        signature is not None and re.fullmatch(r"sha256=[0-9a-f]{64}", signature) is not None,
        401,
        "invalid_webhook_signature",
        "Thiếu hoặc sai định dạng chữ ký webhook.",
    )
    require(
        matches(signature, sign_payload(secret, timestamp, raw_body)),
        401,
        "invalid_webhook_signature",
        "Chữ ký webhook không hợp lệ.",
    )


async def authenticated_event(
    request: Request,
    x_webhook_timestamp: str | None = Header(None, description="Unix seconds của lần gửi HTTP."),
    x_webhook_signature: str | None = Header(
        None, description="sha256=<HMAC hex> của timestamp.raw_body."
    ),
    x_webhook_secret: str | None = Header(None, description="Chỉ dùng khi bật mode secret cũ."),
) -> MockEvent:
    settings = request.app.state.settings
    raw_body = await request.body()
    require(
        len(raw_body) <= settings.webhook_max_body_bytes,
        413,
        "request_too_large",
        "Payload webhook vượt giới hạn kích thước.",
    )
    require(
        bool(settings.mock_webhook_secret),
        503,
        "webhook_not_configured",
        "Webhook chưa được cấu hình secret phía server.",
    )
    if settings.mock_webhook_auth_mode == "hmac":
        require(
            len(request.headers.getlist("x-webhook-timestamp")) == 1
            and len(request.headers.getlist("x-webhook-signature")) == 1,
            401,
            "invalid_webhook_signature",
            "Cần đúng một header timestamp và chữ ký.",
        )
        verify_signature(
            settings.mock_webhook_secret,
            x_webhook_timestamp,
            x_webhook_signature,
            raw_body,
            request.app.state.clock.now().timestamp(),
            settings.webhook_signature_tolerance_seconds,
        )
    else:
        require(
            len(request.headers.getlist("x-webhook-secret")) == 1
            and matches(x_webhook_secret, settings.mock_webhook_secret),
            401,
            "unauthorized",
            "Webhook secret không hợp lệ.",
        )
    require(
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        == "application/json",
        415,
        "unsupported_media_type",
        "Webhook chỉ nhận application/json.",
    )
    try:
        return MockEvent.model_validate_json(raw_body)
    except ValidationError:
        raise AppError(422, "invalid_payload", "Payload webhook không đúng hợp đồng.") from None
