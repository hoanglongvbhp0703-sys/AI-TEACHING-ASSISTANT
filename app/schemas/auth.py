from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


class AuthInput(BaseModel):
    # Passwords must not inherit DTO.str_strip_whitespace: every character is significant.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class Credentials(AuthInput):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    password: SecretStr = Field(min_length=15, max_length=128)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class LoginInput(AuthInput):
    role: Literal["admin", "teacher", "student"] | None = None
    class_id: str | None = Field(default=None, min_length=1, max_length=100)
    username: str = Field(min_length=1, max_length=64)
    password: SecretStr = Field(min_length=1, max_length=1024)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class SetupInput(Credentials):
    display_name: str = Field(default="Quản trị viên", min_length=1, max_length=200)


class ChangePassword(AuthInput):
    current_password: SecretStr = Field(min_length=1, max_length=1024)
    new_password: SecretStr = Field(min_length=15, max_length=128)


class OptionalCredentials(AuthInput):
    username: str | None = Field(
        default=None, min_length=3, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$"
    )
    password: SecretStr | None = Field(default=None, min_length=15, max_length=128)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

    @model_validator(mode="after")
    def pair_required(self):
        if (self.username is None) != (self.password is None):
            raise ValueError("username and password must be provided together")
        return self
