from typing import Literal

from pydantic import Field, field_validator

from app.schemas.auth import OptionalCredentials
from app.schemas.common import DTO


class UserCreate(OptionalCredentials):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    display_name: str = Field(min_length=1, max_length=200)
    role: Literal["teacher", "admin", "service"]

    @field_validator("display_name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError("display_name is required")
        return value.strip()


class UserActive(DTO):
    is_active: bool


class CourseCreate(DTO):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)


class ClassCreate(CourseCreate):
    course_id: str


class BotUpdate(DTO):
    bot_enabled: bool


class AssignmentUpdate(DTO):
    is_active: bool = True


class GroupCreate(DTO):
    platform: Literal["zalo_bot"] = "zalo_bot"
    class_id: str
    external_group_id: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)


class IdentityCreate(DTO):
    platform: Literal["zalo_bot"] = "zalo_bot"
    user_id: str
    external_sender_id: str = Field(min_length=1, max_length=200)
    is_bot: bool = False


class ZaloBotBinding(DTO):
    class_id: str
    chat_id: str = Field(min_length=1, max_length=150)
