"""Connection-only echo: webhook -> real HTTP callback. No business tables or model calls."""

import hashlib
import threading
from uuid import NAMESPACE_URL, uuid5

import httpx

from app.core.clock import Clock
from app.core.errors import AppError, require
from app.core.security import clean
from app.integrations.mock_zalo_adapter import sign_payload
from app.repositories.store import uid
from app.schemas.connection import ConnectionReply


class ConnectionBridge:
    def __init__(self, settings, clock=None):
        self.settings = settings
        self.clock = clock or Clock()
        self.client = httpx.Client(timeout=5, trust_env=False, follow_redirects=False)
        self.lock = threading.Lock()
        self.events = {}

    def close(self):
        self.client.close()

    def receive(self, event):
        key = (event.platform, event.event_id)
        digest = hashlib.sha256(event.model_dump_json().encode()).hexdigest()
        with self.lock:
            old = self.events.get(key)
            if old:
                require(
                    old["digest"] == digest, 409, "event_conflict", "Event ID đã có nội dung khác."
                )
                if old["state"] != "failed":
                    return self.receipt(old, duplicate=True)
                item = old
            else:
                require(
                    len(self.events) < 1000,
                    503,
                    "demo_history_full",
                    "Lịch sử demo đã đầy; hãy khởi động lại demo.",
                )
                reply = ConnectionReply(
                    reply_id=str(
                        uuid5(NAMESPACE_URL, f"gos-connection:{event.platform}:{event.event_id}")
                    ),
                    reply_to_event_id=event.event_id,
                    group_id=event.group_id,
                    text="Đã kết nối webhook. Hệ thống đã nhận tin: "
                    + clean(self.settings, event.message.text),
                )
                item = {"event_key": uid(), "digest": digest, "reply": reply, "http_status": None}
                self.events[key] = item
            item["state"] = "sending"

        # Release the lock before network I/O: the simulator needs to receive this callback
        # while its original request to the webhook is still waiting for a response.
        raw = item["reply"].model_dump_json().encode("utf-8")
        timestamp = str(int(self.clock.now().timestamp()))
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Timestamp": timestamp,
            "X-Webhook-Signature": sign_payload(self.settings.mock_webhook_secret, timestamp, raw),
        }
        try:
            response = self.client.post(
                self.settings.mock_callback_url, content=raw, headers=headers
            )
            if response.status_code >= 400:
                raise ValueError("Callback failed")
            ack = response.json().get("data", {})
            if ack.get("reply_id") != item["reply"].reply_id or ack.get("status") not in {
                "received",
                "duplicate_ignored",
            }:
                raise ValueError("Callback did not acknowledge this reply")
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            with self.lock:
                item["state"] = "failed"
            raise AppError(
                502,
                "mock_callback_failed",
                "Giả lập chưa xác nhận được phản hồi. Có thể thử gửi lại cùng event ID.",
            ) from None
        with self.lock:
            item.update(state="delivered", http_status=response.status_code)
            return self.receipt(item)

    @staticmethod
    def receipt(item, duplicate=False):
        return {
            "event_key": item["event_key"],
            "status": "duplicate_ignored" if duplicate else "received",
            "mode": "connection",
            "callback_status": "delivered" if item["state"] == "delivered" else "pending",
            "callback_http_status": item["http_status"],
            "reply_id": item["reply"].reply_id,
        }
