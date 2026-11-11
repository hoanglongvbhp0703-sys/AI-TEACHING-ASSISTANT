"""Local mock chat platform. Outgoing webhook and incoming callback use real HTTP."""

import json
import logging
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError, require
from app.core.runtime_logging import attach_runtime_log, detach_runtime_log
from app.integrations.mock_zalo_adapter import sign_payload, verify_signature
from app.repositories.store import uid
from app.schemas.connection import ConnectionReply, SimulatedMessage
from app.schemas.event import MockEvent


def create_simulator(settings=None, *, clock=None):
    settings = settings or Settings()
    clock = clock or Clock()
    lock = threading.Lock()
    records = {}

    @asynccontextmanager
    async def lifespan(app):
        log_handler = attach_runtime_log(settings, "simulator")
        app.state.client = httpx.Client(timeout=10, trust_env=False, follow_redirects=False)
        try:
            yield
        finally:
            app.state.client.close()
            detach_runtime_log(log_handler)

    app = FastAPI(title="Mock Zalo — kiểm tra kết nối", lifespan=lifespan)
    app.state.settings = settings
    app.state.records = records

    @app.middleware("http")
    async def request_context(request, call_next):
        request.state.request_id = uid()
        raw = bytearray()
        async for part in request.stream():
            raw.extend(part)
            if len(raw) > settings.webhook_max_body_bytes:
                return JSONResponse(status_code=413, content={"error": "Payload quá lớn."})
        request._body = bytes(raw)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(AppError)
    async def domain_error(request, exc):
        return JSONResponse(
            status_code=exc.status,
            content={"data": None, "error": {"code": exc.code, "message": exc.message}},
        )

    def envelope(data):
        return {"data": data, "error": None}

    def deliver(app, event_id):
        with lock:
            item = records[event_id]
            if item["sending"]:
                raise AppError(409, "already_sending", "Tin nhắn đang được gửi.")
            item.update(sending=True, error=None)
            raw = item["raw"]
        timestamp = str(int(clock.now().timestamp()))
        headers = {"Content-Type": "application/json"}
        if not settings.simulator_business_mode:
            headers["X-Mock-Connection-Only"] = "true"
        if settings.mock_webhook_auth_mode == "hmac":
            headers.update(
                {
                    "X-Webhook-Timestamp": timestamp,
                    "X-Webhook-Signature": sign_payload(
                        settings.mock_webhook_secret, timestamp, raw
                    ),
                }
            )
        else:
            headers["X-Webhook-Secret"] = settings.mock_webhook_secret
        try:
            response = app.state.client.post(
                settings.mock_backend_url + "/api/v1/webhooks/mock-zalo",
                content=raw,
                headers=headers,
            )
            logging.getLogger(__name__).info(
                "mock_webhook_result event_id=%s http_status=%s", event_id, response.status_code
            )
            receipt = response.json()
            with lock:
                item.update(http_status=response.status_code, receipt=receipt)
            if response.status_code >= 400:
                raise ValueError("Webhook failed")
            require(
                settings.simulator_business_mode
                or receipt.get("data", {}).get("mode") == "connection",
                409,
                "backend_not_in_connection_mode",
                "Backend chưa bật chế độ kiểm tra kết nối.",
            )
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            with lock:
                item["error"] = "Gửi webhook thất bại. Kiểm tra backend và thử gửi lại."
        except AppError as exc:
            with lock:
                item["error"] = exc.message
        finally:
            with lock:
                item["sending"] = False
        return public(item)

    def public(item):
        return {k: v for k, v in item.items() if k != "raw" and not k.startswith("_")}

    @app.get("/")
    def page():
        return FileResponse(Path(__file__).parent / "static/mock_zalo.html")

    @app.get("/health")
    def health():
        return envelope(
            {
                "application": "ok",
                "mode": "simulator",
                "backend_url": settings.mock_backend_url,
                "business_mode": settings.simulator_business_mode,
            }
        )

    def refresh_progress(request, group_id):
        if not settings.simulator_business_mode:
            return
        adapter = next(
            (token for token, user in settings.auth_tokens_json.items() if user == "adapter"), None
        )
        if not adapter:
            return
        with lock:
            pending = [
                (key, ((item.get("receipt") or {}).get("data") or {}).get("event_key"))
                for key, item in records.items()
                if item["payload"]["group_id"] == group_id
                and not item["callback"]
                and item.get("receipt")
                and time.monotonic() - item.get("_progress_checked_at", 0) >= 1
            ]
            for key, _ in pending:
                records[key]["_progress_checked_at"] = time.monotonic()
        for key, event_key in pending:
            if not event_key:
                continue
            try:
                response = request.app.state.client.get(
                    settings.mock_backend_url + "/api/v1/events/" + event_key,
                    headers={"Authorization": "Bearer " + adapter},
                )
                if response.status_code == 200:
                    progress = response.json().get("data", {}).get("progress")
                    if progress:
                        with lock:
                            if not records[key]["callback"]:
                                records[key]["progress"] = progress
            except (httpx.HTTPError, ValueError, AttributeError, TypeError):
                pass

    @app.get("/api/mock/messages")
    def messages(
        request: Request, group_id: str = Query("ZGROUP_GS01", min_length=1, max_length=200)
    ):
        refresh_progress(request, group_id)
        with lock:
            return envelope(
                [
                    public(item)
                    for item in records.values()
                    if item["payload"]["group_id"] == group_id
                ]
            )

    @app.get("/api/mock/catalog")
    def catalog(request: Request):
        adapter = next(
            (token for token, user_id in settings.auth_tokens_json.items() if user_id == "adapter"),
            None,
        )
        require(
            adapter is not None,
            503,
            "adapter_not_configured",
            "Chưa cấu hình tài khoản tích hợp giả lập.",
        )
        try:
            response = request.app.state.client.get(
                settings.mock_backend_url + "/api/v1/mock/catalog",
                headers={"Authorization": "Bearer " + adapter},
            )
            require(
                response.status_code == 200,
                503,
                "catalog_unavailable",
                "Không đọc được metadata lớp từ backend.",
            )
            return envelope(response.json()["data"])
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise AppError(
                503, "catalog_unavailable", "Không đọc được metadata lớp từ backend."
            ) from None

    @app.post("/api/mock/messages")
    def send(body: SimulatedMessage, request: Request):
        require(
            bool(settings.mock_webhook_secret),
            503,
            "webhook_not_configured",
            "Chưa cấu hình secret webhook.",
        )
        event = MockEvent(
            event_id=uid(),
            group_id=body.group_id,
            sender_id=body.sender_id,
            sent_at=clock.now(),
            message={"text": body.text},
        )
        raw = event.model_dump_json().encode("utf-8")
        with lock:
            require(
                len(records) < 1000,
                503,
                "demo_history_full",
                "Lịch sử demo đã đầy; hãy khởi động lại demo.",
            )
            records[event.event_id] = {
                "event_id": event.event_id,
                "payload": json.loads(raw),
                "raw": raw,
                "sending": False,
                "http_status": None,
                "receipt": None,
                "callback": None,
                "progress": {
                    "stage": "queued",
                    "status": "queued",
                    "percent": 0,
                    "label": "Đang chờ xử lý",
                },
                "error": None,
            }
        return envelope(deliver(request.app, event.event_id))

    @app.post("/api/mock/messages/{event_id}/retry")
    def retry(
        event_id: str,
        request: Request,
        group_id: str = Query("ZGROUP_GS01", min_length=1, max_length=200),
    ):
        with lock:
            require(
                event_id in records and records[event_id]["payload"]["group_id"] == group_id,
                404,
                "not_found",
                "Không tìm thấy tin nhắn trong nhóm đã chọn.",
            )
        return envelope(deliver(request.app, event_id))

    @app.post("/api/mock/replies")
    async def callback(request: Request):
        require(
            bool(settings.mock_webhook_secret),
            503,
            "webhook_not_configured",
            "Chưa cấu hình secret callback.",
        )
        require(
            len(request.headers.getlist("x-webhook-timestamp")) == 1
            and len(request.headers.getlist("x-webhook-signature")) == 1,
            401,
            "invalid_webhook_signature",
            "Thiếu hoặc lặp header chữ ký.",
        )
        raw = await request.body()
        verify_signature(
            settings.mock_webhook_secret,
            request.headers.get("x-webhook-timestamp"),
            request.headers.get("x-webhook-signature"),
            raw,
            clock.now().timestamp(),
            settings.webhook_signature_tolerance_seconds,
        )
        try:
            reply = ConnectionReply.model_validate_json(raw)
        except ValidationError:
            raise AppError(422, "invalid_callback", "Payload callback không hợp lệ.") from None
        with lock:
            item = records.get(reply.reply_to_event_id)
            require(item is not None, 404, "unknown_event", "Callback không khớp tin nhắn đã gửi.")
            require(
                item["payload"]["group_id"] == reply.group_id,
                409,
                "group_mismatch",
                "Callback gửi sai nhóm.",
            )
            callbacks = item.setdefault("callbacks", {})
            old = callbacks.get(reply.reply_id)
            require(
                old is None or old == reply.model_dump(),
                409,
                "reply_conflict",
                "Tin nhắn đã nhận phản hồi khác.",
            )
            callbacks[reply.reply_id] = reply.model_dump()
            logging.getLogger(__name__).info(
                "mock_callback_received event_id=%s reply_id=%s",
                reply.reply_to_event_id,
                reply.reply_id,
            )
            item["callback"] = reply.model_dump()
            item["progress"] = reply.processing or {
                "stage": "done",
                "status": "completed",
                "percent": 100,
                "label": "Đã nhận phản hồi",
            }
        return envelope(
            {"reply_id": reply.reply_id, "status": "duplicate_ignored" if old else "received"}
        )

    return app
