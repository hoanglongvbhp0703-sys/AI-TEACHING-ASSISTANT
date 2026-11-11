import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.deps import ok
from app.api.routes import auth, documents, events, identity, portal, reports, tickets, webhooks
from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError
from app.core.runtime_logging import attach_runtime_log, detach_runtime_log
from app.db.seed import seed_demo
from app.db.session import Database
from app.integrations.connection_bridge import ConnectionBridge
from app.jobs.runner import Worker
from app.rag.backend import UnconfiguredRAG
from app.repositories.store import uid
from app.schemas.common import Envelope
from app.services.auth_service import AuthService
from app.services.document_service import DocumentService
from app.services.event_service import EventService
from app.services.ticket_service import TicketService


def create_app(settings=None, *, backend=None, clock=None):
    settings = settings or Settings()
    if backend is None and settings.rag_enabled:
        from app.rag.local_backend import LocalRAG

        backend = LocalRAG(settings)
    backend = backend or UnconfiguredRAG()
    clock = clock or Clock()

    @asynccontextmanager
    async def lifespan(app):
        db = Database(settings)
        db.migrate()
        for path in [settings.upload_dir, settings.staging_dir]:
            path.mkdir(parents=True, exist_ok=True)
        if settings.seed_demo_on_start:
            seed_demo(db, clock)
        log_handler = attach_runtime_log(settings, "backend")
        app.state.db = db
        app.state.auth = AuthService(db, clock, settings)
        if hasattr(backend, "bind"):
            backend.bind(db, clock)
        app.state.events = EventService(db, clock, settings, backend)
        app.state.documents = DocumentService(db, clock, settings)
        app.state.tickets = TicketService(db, clock, settings)
        app.state.connection_bridge = ConnectionBridge(settings, clock)
        app.state.worker = Worker(db, clock, settings, backend, app.state.events)
        jobs_enabled = settings.background_jobs_enabled and settings.mock_webhook_mode == "business"
        try:
            if jobs_enabled:
                app.state.worker.start()
            yield
        finally:
            app.state.worker.stop()
            app.state.connection_bridge.close()
            backend.close()
            db.engine.dispose()
            detach_runtime_log(log_handler)

    app = FastAPI(
        title="GOS Academy Backend API",
        version="0.1.0",
        lifespan=lifespan,
        description="Local MVP API. Bearer tokens map to server-side users. RAG model adapters are configured separately.",
    )
    app.state.settings, app.state.clock, app.state.backend = settings, clock, backend

    static = Path(__file__).parent / "static"
    app.mount("/portal-assets", StaticFiles(directory=static), name="portal-assets")

    @app.get("/", include_in_schema=False)
    def home():
        return RedirectResponse("/portal")

    @app.get("/portal", include_in_schema=False)
    def portal_page():
        return FileResponse(static / "portal.html")

    def failure(request, status, code, message):
        logging.getLogger(__name__).warning(
            "request_rejected request_id=%s method=%s path=%s http_status=%s code=%s",
            getattr(request.state, "request_id", "unknown"),
            request.method,
            request.url.path,
            status,
            code,
        )
        return JSONResponse(
            status_code=status,
            content={
                "data": None,
                "error": {"code": code, "message": message},
                "request_id": getattr(request.state, "request_id", "unknown"),
            },
        )

    @app.middleware("http")
    async def request_context(request, call_next):
        request.state.request_id = uid()
        limit = settings.max_request_bytes
        if request.url.path.rstrip("/") == "/api/v1/webhooks/mock-zalo":
            limit = min(limit, settings.webhook_max_body_bytes)
        parts = []
        size = 0
        async for part in request.stream():
            size += len(part)
            if size > limit:
                response = failure(
                    request, 413, "request_too_large", "Request vượt giới hạn kích thước."
                )
                response.headers["X-Request-ID"] = request.state.request_id
                return response
            parts.append(part)
        request._body = b"".join(parts)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(AppError)
    async def domain_error(request, exc):
        return failure(request, exc.status, exc.code, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        return failure(
            request,
            exc.status_code,
            {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error"),
            "Không tìm thấy tài nguyên hoặc phương thức không được hỗ trợ.",
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Do not reflect raw inputs, secret headers, uploaded bytes or exception context.
        return failure(
            request, 422, "invalid_payload", "Dữ liệu không hợp lệ; kiểm tra hợp đồng tại /docs."
        )

    @app.exception_handler(IntegrityError)
    async def constraint_error(request, exc):
        return failure(
            request, 409, "data_conflict", "Dữ liệu trùng hoặc vi phạm quan hệ/ràng buộc."
        )

    @app.exception_handler(OperationalError)
    async def db_error(request, exc):
        return failure(request, 503, "database_unavailable", "Database tạm thời chưa sẵn sàng.")

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        logging.getLogger(__name__).error("request_failed request_id=%s", request.state.request_id)
        return failure(
            request, 500, "internal_error", "Hệ thống gặp lỗi; dùng request_id để truy vết."
        )

    for router in [
        identity.router,
        auth.router,
        portal.router,
        webhooks.router,
        events.router,
        documents.router,
        tickets.router,
        reports.router,
    ]:
        app.include_router(router, prefix="/api/v1")

    @app.get("/api/v1/health", tags=["Health"], response_model=Envelope[Any])
    def health(request: Request):
        with app.state.db.read() as s:
            s.one("SELECT 1 AS ok")
        return ok(
            request,
            {
                "application": "ok",
                "sqlite": "ok",
                "schema_version": 4,
                "rag": "ready" if backend.ready else "unconfigured",
                "background_jobs": settings.background_jobs_enabled
                and settings.mock_webhook_mode == "business",
                "webhook_mode": settings.mock_webhook_mode,
                "rag_jobs_enabled": settings.rag_jobs_enabled,
                "worker_running": bool(
                    app.state.worker.thread and app.state.worker.thread.is_alive()
                ),
                "max_upload_bytes": settings.max_upload_bytes,
                "integration": "mock_zalo_only",
            },
        )

    return app


app = create_app()


def create_connection_app():
    """Explicit transport-only entrypoint for the two-way local simulator."""
    return create_app(
        Settings(
            mock_webhook_mode="connection",
            background_jobs_enabled=False,
            rag_enabled=False,
            rag_jobs_enabled=False,
        )
    )


def create_portal_app():
    """Portal uses the configured local RAG backend when explicitly enabled."""
    return create_app(
        Settings(
            seed_demo_on_start=True,
            mock_webhook_mode="business",
            rag_jobs_enabled=Settings().rag_enabled,
            background_jobs_enabled=True,
        )
    )
