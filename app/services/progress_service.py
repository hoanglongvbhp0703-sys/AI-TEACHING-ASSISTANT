"""Progress reflects persisted stages and real counters; percentages are not time estimates."""

INDEX_STAGES = {
    "parse": (5, "Đọc và kiểm tra nội dung file"),
    "chunk": (15, "Tách nội dung thành các đoạn"),
    "embed": (25, "Tạo vector embedding"),
    "upsert": (75, "Lưu vector vào Qdrant"),
    "verify": (90, "Kiểm tra index và metadata"),
    "activate": (95, "Kích hoạt phiên bản mới"),
    "done": (100, "Tài liệu sẵn sàng sử dụng"),
}
ERRORS = {
    "embedding_unconfigured": "Worker chưa cấu hình embedding. Chạy bộ RAG và thử index lại.",
    "empty_extracted_text": "Không đọc được văn bản. PDF scan/ảnh cần OCR trước khi index.",
    "invalid_document": "Không đọc được định dạng hoặc nội dung file.",
    "file_too_large": "File vượt giới hạn dung lượng upload.",
    "request_too_large": "Request vượt giới hạn dung lượng upload.",
    "ingestion_failure": "Index chưa hoàn tất. Xem mã lỗi và log backend.",
    "model_unavailable": "Model chưa sẵn sàng.",
    "llm_transport_error": "Không kết nối được model sinh câu trả lời.",
    "mock_callback_failed": "Đang thử gửi lại phản hồi về giả lập.",
    "rag_deferred": "File đã lưu; lập chỉ mục đang tắt.",
}


def error_message(code):
    return ERRORS.get(code, "Xử lý chưa hoàn tất. Xem mã lỗi và log backend.")


def index_progress(job):
    stage = job["stage"]
    percent, label = INDEX_STAGES.get(stage, (0, "Đang chờ lập chỉ mục"))
    total = job.get("chunks_total") or 0
    points = job.get("points_total") or 0
    if stage == "embed" and total:
        percent += int(45 * min(job["chunks_indexed"] / total, 1))
    elif stage == "upsert" and points:
        percent += int(10 * min(job["points_indexed"] / points, 1))
    status = job["status"]
    if status == "queued":
        stage, percent, label = "queued", 0, "Đang chờ worker"
    elif status == "succeeded":
        stage, percent, label = "done", 100, "Tài liệu sẵn sàng sử dụng"
    elif status in {"failed", "cancelled"}:
        label = error_message(job.get("error_code"))
        if job.get("error_code") in {"embedding_unconfigured", "rag_deferred"}:
            percent = 0
    return {
        "stage": stage,
        "status": status,
        "percent": percent,
        "label": label,
        "chunks_done": job.get("chunks_indexed", 0),
        "chunks_total": total,
        "points_done": job.get("points_indexed", 0),
        "points_total": points,
        "error_code": job.get("error_code"),
    }


def terminal_progress(
    outcome, reason=None, retrieval_called=None, llm_called=None, rewrite_called=None
):
    status, stage, percent, label = "completed", "done", 100, "Đã gửi phản hồi"
    if outcome in {
        "quota_exceeded",
        "rate_limited",
        "access_denied",
        "bot_message",
        "not_a_question",
    }:
        status, stage, percent = "rejected", "policy", 0
        label = {
            "quota_exceeded": "Chặn trước RAG: hết lượt hỏi hôm nay",
            "rate_limited": "Chặn trước RAG: gửi câu hỏi quá nhanh",
            "access_denied": "Chặn trước RAG: không có quyền trong lớp",
            "bot_message": "Tin bot không chạy RAG",
            "not_a_question": "Tin không có lệnh /hoi, không chạy RAG",
        }[outcome]
    elif outcome == "answered":
        label = "LLM đã trả lời và Backend đã kiểm tra trích dẫn"
    elif outcome == "insufficient_evidence":
        label = (
            "Không có tài liệu active được cấp cho lớp"
            if reason == "no_active_documents"
            else (
                "LLM đánh giá chưa đủ căn cứ; chuyển giảng viên"
                if llm_called
                else "Đã tìm nguồn nhưng chưa gọi LLM; chuyển giảng viên"
            )
        )
        if reason in {
            "quote_not_in_source",
            "invalid_source_number",
            "invalid_or_stale_citation",
            "citation_revoked_before_send",
        }:
            label = "Backend không xác minh được nguồn/trích dẫn; chuyển giảng viên"
    elif outcome == "blocked":
        status, stage, percent, label = "rejected", "policy", 0, "Yêu cầu bị chặn trước khi gọi LLM"
    elif outcome == "error":
        status, label = "failed", error_message(reason)
    return {
        "stage": stage,
        "status": status,
        "percent": percent,
        "label": label,
        "error_code": outcome if status == "rejected" else (reason if status == "failed" else None),
        "outcome_code": outcome,
        "retrieval_called": retrieval_called,
        "llm_called": llm_called,
        "rewrite_called": rewrite_called,
        "provider_called": None
        if rewrite_called is None and llm_called is None
        else bool(rewrite_called or llm_called),
    }


def event_progress(s, event):
    run = s.one("SELECT * FROM rag_runs WHERE event_key=:e", e=event["event_key"])
    out = s.one(
        "SELECT status,error_code FROM outbound_messages WHERE event_key=:e ORDER BY rowid DESC LIMIT 1",
        e=event["event_key"],
    )
    flags = (
        s.one(
            "SELECT MAX(stage='query_rewrite') AS rewrite_called,MAX(stage='query_embed') AS retrieval_called,MAX(stage='generate') AS llm_called FROM rag_run_attempts WHERE rag_run_id=:r",
            r=run["id"],
        )
        if run
        else {}
    )
    if out and out["status"] == "sent":
        return terminal_progress(
            event.get("outcome_code"),
            run.get("evidence_reason_redacted") if run else None,
            bool(flags.get("retrieval_called")),
            bool(flags.get("llm_called")),
            bool(flags.get("rewrite_called")),
        )
    if out and out["status"] == "failed":
        return {
            "stage": "send",
            "percent": 95,
            "status": "failed",
            "label": "Gửi phản hồi thất bại",
            "error_code": out["error_code"],
        }
    if event["status"] in {"rejected", "ignored"}:
        return terminal_progress(event.get("outcome_code"), None, False, False, False)
    if out:
        return {
            "stage": "send",
            "percent": 95,
            "status": "processing",
            "label": "Đang gửi phản hồi về giả lập",
            "error_code": out["error_code"],
        }
    call = (
        s.one(
            "SELECT stage,status,error_code FROM rag_run_attempts WHERE rag_run_id=:r ORDER BY rowid DESC LIMIT 1",
            r=run["id"],
        )
        if run
        else None
    )
    stage, percent, label = "queued", 0, "Đang chờ xử lý"
    if run:
        stage, percent, label = "prepare", 10, "Chuẩn bị quyền truy xuất và memory"
    if call:
        stage = call["stage"]
        percent, label = {
            "query_rewrite": (15, "Viết lại câu hỏi theo ngữ cảnh hội thoại"),
            "query_embed": (25, "Embedding câu hỏi và tìm Top 10 nguồn"),
            "rerank": (55, "Rerank các nguồn, chọn Top 5"),
            "generate": (75, "Claude đánh giá bằng chứng và soạn câu trả lời"),
        }.get(stage, (10, "Đang xử lý"))
        if call["status"] == "succeeded":
            stage, percent, label = {
                "query_rewrite": (
                    "query_embed",
                    20,
                    "Đã xác định câu hỏi độc lập; chuẩn bị embedding",
                ),
                "query_embed": ("retrieve", 40, "Tìm nguồn trong tài liệu được cấp quyền"),
                "rerank": ("evidence", 65, "Chuẩn bị gửi toàn bộ nguồn cho Claude"),
                "generate": ("validate", 90, "Xác minh trích dẫn"),
            }.get(stage, (stage, percent, label))
        if call["status"] in {"failed", "unknown"}:
            if call["stage"] == "query_rewrite":
                return {
                    "stage": "query_embed",
                    "percent": 20,
                    "status": "processing",
                    "label": "Không rewrite được; tiếp tục bằng câu hỏi gốc",
                    "error_code": "query_rewrite_fallback",
                }
            return {
                "stage": stage,
                "percent": percent,
                "status": "failed",
                "label": error_message(call["error_code"]),
                "error_code": call["error_code"],
            }
    return {
        "stage": stage,
        "percent": percent,
        "status": "processing" if run else "queued",
        "label": label,
        "error_code": None,
    }
