from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Envelope(BaseModel, Generic[T]):
    data: T | None = None
    error: dict[str, Any] | None = None
    request_id: str
