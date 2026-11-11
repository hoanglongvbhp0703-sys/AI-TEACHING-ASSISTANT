from typing import Literal

from pydantic import Field

from app.schemas.common import DTO


class SimulatedMessage(DTO):
    text: str = Field(min_length=1, max_length=8000)
    group_id: str = Field(default="ZGROUP_GS01", min_length=1, max_length=200)
    sender_id: str = Field(default="HV_GS_01", min_length=1, max_length=200)


class ConnectionReply(DTO):
    reply_id: str
    reply_to_event_id: str
    group_id: str
    kind: Literal[
        "connection_ack", "bot_result", "teacher_answer", "validation_notice", "policy_notice"
    ] = "connection_ack"
    text: str
    is_bot_message: Literal[True] = True
    ticket_id: str | None = None
    citations: list[dict] = Field(default_factory=list, max_length=40)
    processing: dict | None = None


class ConnectionReceipt(DTO):
    event_key: str
    status: Literal["received", "duplicate_ignored"]
    mode: Literal["connection"] = "connection"
    callback_status: Literal["pending", "delivered"]
    callback_http_status: int | None = None
    reply_id: str
