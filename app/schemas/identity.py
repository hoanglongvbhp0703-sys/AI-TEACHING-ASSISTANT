from typing import Literal

from pydantic import Field, field_validator

from app.schemas.auth import OptionalCredentials
from app.schemas.common import DTO


class UserCreate(OptionalCredentials):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    display_name: str = Field(min_length=1, max_length=200)
    role: Literal["student", "teacher", "admin", "service"]

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
    student_count: int = Field(default=0, ge=0, le=500)


class RosterMetadata(DTO):
    student_count: int = Field(ge=1, le=500)


class BotUpdate(DTO):
    bot_enabled: bool


class EnrollmentUpdate(DTO):
    status: Literal["active", "suspended", "left"] = "active"


class AssignmentUpdate(DTO):
    is_active: bool = True


class GroupCreate(DTO):
    class_id: str
    external_group_id: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)


class IdentityCreate(DTO):
    user_id: str
    external_sender_id: str = Field(min_length=1, max_length=200)
    is_bot: bool = False
