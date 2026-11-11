from dataclasses import dataclass, field
from typing import Literal


@dataclass
class RAGContext:
    event_key: str
    class_id: str
    group_id: str
    question: str
    allowed_scope_ids: list[str]
    active_document_version_ids: list[str]
    memory: list[dict]


@dataclass
class RAGResult:
    status: Literal["answered", "insufficient_evidence", "blocked", "error"]
    answer: str
    citations: list[dict] = field(default_factory=list)
    sufficient: bool = False
    reason: str = ""
    retrieved_point_ids: list[str] = field(default_factory=list)
    # Provider adapters must persist started/unknown calls as well as successful calls.
    error_code: str | None = None
