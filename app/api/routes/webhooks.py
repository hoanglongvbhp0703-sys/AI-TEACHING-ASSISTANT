from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import ok
from app.core.errors import require
from app.integrations.mock_zalo_adapter import authenticated_event
from app.schemas.common import Envelope
from app.schemas.connection import ConnectionReceipt
from app.schemas.event import MockEvent, WebhookReceipt

router = APIRouter(tags=["Webhooks"])


@router.post(
    "/webhooks/mock-zalo",
    status_code=202,
    response_model=Envelope[WebhookReceipt | ConnectionReceipt],
    summary="Nhận sự kiện nhóm Zalo giả lập có xác thực",
    description=(
        "Mặc định HMAC-SHA256 trên timestamp.raw_body, timestamp lệch tối đa 300 giây. "
        "202 sau khi event/quota đã commit; 200 cho duplicate, ignored hoặc policy rejection. "
        "Đây là hợp đồng mock, không phải chữ ký webhook Zalo chính thức."
    ),
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/MockEvent"}}},
        }
    },
    responses={
        200: {
            "model": Envelope[WebhookReceipt | ConnectionReceipt],
            "description": "Đã nhận, trùng hoặc không cần xử lý.",
        },
        401: {"description": "Chữ ký/timestamp hoặc secret không hợp lệ."},
        413: {"description": "Payload lớn hơn giới hạn webhook."},
        415: {"description": "Content-Type không phải application/json."},
        422: {"description": "JSON hoặc event không hợp lệ."},
        503: {"description": "Secret chưa cấu hình hoặc SQLite tạm không sẵn sàng; có thể retry."},
    },
)
def webhook(
    request: Request,
    response: Response,
    body: Annotated[MockEvent, Depends(authenticated_event)],
):
    require(
        request.headers.get("x-mock-connection-only") != "true"
        or request.app.state.settings.mock_webhook_mode == "connection",
        409,
        "backend_not_in_connection_mode",
        "Backend chưa bật chế độ kiểm tra kết nối.",
    )
    if request.app.state.settings.mock_webhook_mode == "connection":
        result = request.app.state.connection_bridge.receive(body)
    else:
        # Business mode commits the durable event and quota in one SQLite transaction.
        result = request.app.state.events.receive(body, request.state.request_id)
    if result["status"] != "queued":
        response.status_code = 200
    return ok(request, result)
