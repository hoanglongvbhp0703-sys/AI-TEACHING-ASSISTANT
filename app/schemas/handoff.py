from pydantic import Field

from app.schemas.common import DTO


class AssignTicket(DTO):
    teacher_id: str
    revision: int = Field(ge=0)


class AnswerTicket(DTO):
    answer: str = Field(min_length=1, max_length=12000)
    revision: int = Field(ge=0)


class CloseTicket(DTO):
    revision: int = Field(ge=0)


class FAQDraft(DTO):
    scope_id: str
    topic: str = Field(min_length=1, max_length=200)
