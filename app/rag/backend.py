from typing import Protocol

from app.core.errors import AppError
from app.rag.schemas import RAGContext, RAGResult


class RAGBackend(Protocol):
    ready: bool

    def answer(self, context: RAGContext) -> RAGResult: ...
    def index(self, version: dict, path, scopes: list[str], config: dict) -> list[dict]: ...
    def cleanup(self, document_id: str, version_id: str) -> None: ...
    def close(self) -> None: ...


class UnconfiguredRAG:
    """Fail closed until a genuine model/vector backend is attached. No canned AI answers."""

    ready = False

    def answer(self, context):
        if not context.active_document_version_ids:
            return RAGResult(
                "insufficient_evidence",
                "Chưa có học liệu hiện hành đủ căn cứ.",
                reason="no_active_documents",
            )
        raise AppError(503, "model_unavailable", "Chưa cấu hình model RAG.")

    def index(self, version, path, scopes, config):
        raise AppError(
            503,
            "embedding_unconfigured",
            "Chưa cấu hình embedding/index backend. File được giữ để retry.",
        )

    def cleanup(self, document_id, version_id):
        # Do not claim external cleanup succeeded without a configured vector backend.
        raise AppError(503, "vector_backend_unconfigured", "Chưa có vector backend để cleanup.")

    def close(self):
        pass
