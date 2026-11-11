from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from app.schemas.common import DTO


class MockMessage(DTO):
    type: Literal["text"] = "text"
    text: str = Field(max_length=8000)
    reply_to_event_id: str | None = Field(default=None, max_length=200)


class MockEvent(DTO):
    event_id: str = Field(min_length=1, max_length=200)
    platform: Literal["mock_zalo"] = "mock_zalo"
    group_id: str = Field(min_length=1, max_length=200)
    sender_id: str = Field(min_length=1, max_length=200)
    sent_at: datetime
    is_bot_message: bool = False
    message: MockMessage

    @field_validator("sent_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError("sent_at must have a timezone")
        return value


class WebhookReceipt(DTO):
    event_key: str
    status: Literal[
        "queued", "processing", "completed", "failed", "ignored", "rejected", "duplicate_ignored"
    ]
    event_status: (
        Literal["queued", "processing", "completed", "failed", "ignored", "rejected"] | None
    ) = None
    outcome_code: str | None = None
