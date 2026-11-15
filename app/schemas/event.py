from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from app.schemas.common import DTO


class IncomingMessage(DTO):
    type: Literal["text"] = "text"
    text: str = Field(max_length=8000)
    reply_to_event_id: str | None = Field(default=None, max_length=200)


class IncomingEvent(DTO):
    event_id: str = Field(min_length=1, max_length=200)
    platform: Literal["zalo_bot"] = "zalo_bot"
    group_id: str = Field(min_length=1, max_length=200)
    sender_id: str = Field(min_length=1, max_length=200)
    sent_at: datetime
    is_bot_message: bool = False
    message: IncomingMessage

    @field_validator("sent_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError("sent_at must have a timezone")
        return value
