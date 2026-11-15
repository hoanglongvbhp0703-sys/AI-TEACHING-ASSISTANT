"""Official Bot API transport. Polling feeds the same durable EventService as the portal."""

import hashlib
import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.repositories.store import uid
from app.schemas.event import IncomingEvent

log = logging.getLogger(__name__)
API_ORIGIN = "https://bot-api.zapps.me"  # Host used by python-zalo-bot 0.1.9.


class BotAPIError(Exception):
    """Do not propagate HTTP request URLs: Bot API credentials are part of the path."""


class BotClient:
    def __init__(self, token):
        # httpx INFO logs include token-bearing request paths.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        self.token = token
        self.bot_id = token.split(":", 1)[0]

    def call(self, method, data=None, timeout=15):
        try:
            response = httpx.post(
                f"{API_ORIGIN}/bot{self.token}/{method}",
                json=data or {},
                timeout=timeout,
                trust_env=False,
                follow_redirects=False,
            )
            payload = response.json()
            # The live API returns ok=false/error_code=404 when no webhook is registered.
            # Do not delete a webhook or treat any authentication/network error as absence.
            if (
                method == "getWebhookInfo"
                and response.status_code == 200
                and payload.get("error_code") == 404
            ):
                return None
            if response.status_code != 200 or payload.get("ok") is not True:
                code = payload.get("error_code")
                if method == "getUpdates" and code == 408:
                    return None
                raise BotAPIError(
                    f"zalo_api_rejected_{code if isinstance(code, int) else 'unknown'}"
                )
            return payload.get("result")
        except (httpx.HTTPError, ValueError, AttributeError, TypeError):
            raise BotAPIError("zalo_api_unavailable") from None

    def send(self, namespaced_chat_id, text):
        prefix = self.bot_id + ":"
        if not namespaced_chat_id.startswith(prefix):
            raise BotAPIError("zalo_bot_destination_mismatch")
        result = self.call(
            "sendMessage", {"chat_id": namespaced_chat_id[len(prefix) :], "text": text}
        )
        if not isinstance(result, dict) or not result.get("message_id"):
            raise BotAPIError("zalo_send_unconfirmed")
        return str(result["message_id"])


def normalize(update, bot_id, bot_names=()):
    """Preserve actual chat/sender IDs; never infer class or enrollment from text."""
    if not isinstance(update, dict):
        return None
    message = update.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("text"), str):
        return None
    chat, sender = message.get("chat"), message.get("from")
    if not isinstance(chat, dict) or not isinstance(sender, dict):
        return None
    if not all(message.get(k) is not None for k in ("message_id", "date")):
        return None
    if not chat.get("id") or not sender.get("id"):
        return None
    text = message["text"].strip()
    for name in sorted((n for n in bot_names if n), key=len, reverse=True):
        tagged = re.match(r"^@" + re.escape(name) + r"(?:\s+|$)", text)
        if tagged:
            text = text[tagged.end() :].strip()
            break
    return IncomingEvent(
        platform="zalo_bot",
        event_id=hashlib.sha256(
            f"{bot_id}:{chat['id']}:{message['message_id']}".encode()
        ).hexdigest(),
        group_id=f"{bot_id}:{chat['id']}",
        sender_id=f"{bot_id}:{sender['id']}",
        sent_at=datetime.fromtimestamp(float(message["date"]) / 1000, timezone.utc),
        is_bot_message=bool(sender.get("is_bot")) or str(sender["id"]) == bot_id,
        message={"text": text},
    )


class BotPoller:
    def __init__(self, settings, events):
        self.settings, self.events = settings, events
        self.client = BotClient(settings.zalo_bot_token.get_secret_value())
        self.stop_signal = threading.Event()
        self.thread = None
        self.lock = None
        self.bot_names = ()

    def start(self):
        import fcntl

        # One poller per bot on this machine, even when using different demo databases.
        from tempfile import gettempdir

        path = Path(gettempdir()) / f"gos-zalo-bot-{self.client.bot_id}.lock"
        self.lock = path.open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            me = self.client.call("getMe")
            if not me or str(me.get("id")) != self.client.bot_id:
                raise BotAPIError("zalo_bot_identity_mismatch")
            self.bot_names = (me.get("display_name"), me.get("account_name"))
            info = self.client.call("getWebhookInfo")
            if info and info.get("url"):
                raise BotAPIError("zalo_webhook_already_configured")
        except Exception:
            self.lock.close()
            self.lock = None
            raise
        self.thread = threading.Thread(target=self.loop, name="zalo-bot-poll", daemon=True)
        self.thread.start()
        log.info("zalo_bot_started bot_id=%s transport=polling", self.client.bot_id)

    def stop(self):
        self.stop_signal.set()
        if self.thread:
            self.thread.join(timeout=40)
        if self.lock and (not self.thread or not self.thread.is_alive()):
            self.lock.close()
            self.lock = None

    def ingest(self, update):
        event = normalize(update, self.client.bot_id, self.bot_names)
        if event is None:
            return None
        result = self.events.receive(event, uid())
        log.info(
            "zalo_bot_received chat=%s sender=%s event_key=%s status=%s outcome=%s",
            event.group_id,
            event.sender_id,
            result["event_key"],
            result["status"],
            result.get("outcome_code"),
        )
        return result

    def loop(self):
        while not self.stop_signal.is_set():
            try:
                update = self.client.call("getUpdates", {"timeout": 20}, timeout=30)
                if update:
                    self.ingest(update)
                else:
                    self.stop_signal.wait(1)
            except Exception as exc:
                # Never log response bodies, questions, HTTP URLs or token-bearing exceptions.
                log.warning(
                    "zalo_poll_failed error_type=%s code=%s",
                    type(exc).__name__,
                    str(exc) if isinstance(exc, BotAPIError) else "invalid_update",
                )
                self.stop_signal.wait(5)
